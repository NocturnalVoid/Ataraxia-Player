# -*- coding: utf-8 -*-
import sqlite3
import os
import sys

class DatabaseManager:
    def __init__(self, db_name="ataraxia.db"):
        self.db_path = self._get_secure_db_path(db_name)
        self._initialize_database()

    def _get_secure_db_path(self, db_name: str) -> str:
        app_name = "AtaraxiaPlayer"
        if sys.platform == "win32":
            base_path = os.environ.get("APPDATA", os.path.expanduser("~"))
        else:
            base_path = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
        full_dir = os.path.join(base_path, app_name)
        os.makedirs(full_dir, exist_ok=True)
        return os.path.join(full_dir, db_name)

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _initialize_database(self):
        """
        Inicializa la BD aplicando migraciones pendientes.
        Las migraciones se aplican en orden numérico, solo una vez cada una.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # PRAGMAs persistentes (solo corren la primera vez efectivamente)
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")

            # Tabla de versión de schema (se crea siempre que no exista)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version    INTEGER PRIMARY KEY,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                )
            """)

            self._run_migrations(conn)

    def _run_migrations(self, conn):
        """
        Aplica las migraciones pendientes. Detecta automáticamente BDs que vienen
        de versiones anteriores al sistema de migraciones (legacy adoption).
        """
        from src.models.migrations import MIGRATIONS
        from src.utils.logger import get_logger
        log = get_logger(__name__)

        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
        current_version = cursor.fetchone()[0]

        # ────────────────────────────────────────────────────────────────
        # ADOPCIÓN DE BD PREEXISTENTE
        # Si la tabla schema_version está vacía pero la BD ya tiene tablas
        # de usuario (songs, etc.), no es una BD nueva: es una BD legacy
        # del sistema antiguo. Detectamos su nivel de schema por las
        # columnas presentes y stampeamos la versión apropiada.
        # ────────────────────────────────────────────────────────────────
        if current_version == 0:
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT IN ('schema_version', 'sqlite_sequence')
            """)
            existing_tables = {row[0] for row in cursor.fetchall()}

            if "songs" in existing_tables:
                # BD preexistente — determinamos qué nivel de schema tiene
                detected_version = self._detect_legacy_version(cursor)
                log.info(
                    "BD preexistente detectada — schema actual = v%d. "
                    "Marcando migraciones 1..%d como ya aplicadas.",
                    detected_version, detected_version
                )
                for v, desc, _sql in MIGRATIONS:
                    if v <= detected_version:
                        cursor.execute(
                            "INSERT INTO schema_version (version, description) "
                            "VALUES (?, ?)",
                            (v, desc + "  [adopted from legacy DB]")
                        )
                conn.commit()
                current_version = detected_version

        # ────────────────────────────────────────────────────────────────
        # APLICAR MIGRACIONES PENDIENTES (flujo normal)
        # ────────────────────────────────────────────────────────────────
        pending = [m for m in MIGRATIONS if m[0] > current_version]
        if not pending:
            log.debug("BD está en la última versión (v%d)", current_version)
            return

        self._auto_backup_before_migration(current_version, pending[-1][0])

        for version, description, sql in pending:
            log.info("Aplicando migración v%d: %s", version, description)
            try:
                if callable(sql):
                    sql(cursor)
                else:
                    cursor.executescript(sql)

                cursor.execute(
                    "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                    (version, description)
                )
                conn.commit()
                log.info("Migración v%d aplicada con éxito", version)
            except Exception:
                conn.rollback()
                log.exception("FALLO en migración v%d — se hizo rollback", version)
                raise RuntimeError(
                    f"Migración v{version} falló. La BD está en v{current_version}. "
                    f"Revisa el log y el backup automático."
                )


    def _detect_legacy_version(self, cursor) -> int:
        """
        Infiere la versión de schema de una BD preexistente examinando qué
        columnas e índices contiene. Cada migración suma su 'huella'.

        Retorna el número de versión que mejor describe el estado actual.
        """
        # v1: schema base — si llegamos aquí ya hay tabla songs, mínimo es v1
        detected = 1

        # v2: columna 'favorite' en songs
        cursor.execute("PRAGMA table_info(songs)")
        songs_cols = {row[1] for row in cursor.fetchall()}
        if "favorite" in songs_cols:
            detected = 2

        # v3: índices únicos compuestos
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index'
            AND name IN ('ux_playlist_songs_pair', 'ux_albums_title_artist')
        """)
        if len(cursor.fetchall()) == 2:
            detected = 3

        # v4: índices de rendimiento
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index'
            AND name IN ('ix_songs_album_id', 'ix_songs_favorite', 'ix_songs_play_count')
        """)
        if len(cursor.fetchall()) >= 3:
            detected = 4

        # v5: CHECK constraints en songs (requiere parsear el CREATE TABLE)
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='songs'"
        )
        songs_ddl = (cursor.fetchone() or [""])[0] or ""
        if "CHECK" in songs_ddl.upper() and "favorite IN" in songs_ddl:
            detected = 5

        # v6: UNIQUE(playlist_id, song_id) en playlist_songs
        cursor.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='playlist_songs'"
        )
        ps_ddl = (cursor.fetchone() or [""])[0] or ""
        if "UNIQUE" in ps_ddl.upper() or "ON DELETE CASCADE" in ps_ddl.upper():
            detected = 6

        # v7: tabla play_history
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='play_history'"
        )
        if cursor.fetchone():
            detected = 7

        # v8: tabla virtual FTS songs_fts
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='songs_fts'"
        )
        if cursor.fetchone():
            detected = 8

        return detected

    def _auto_backup_before_migration(self, from_version: int, to_version: int):
        """
        Copia la BD antes de migraciones potencialmente destructivas (v3+).
        Las v1/v2 son aditivas y no requieren backup.
        """
        if to_version < 3:
            return
        import shutil
        from datetime import datetime
        from src.utils.logger import get_logger
        log = get_logger(__name__)

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = (
                f"{self.db_path}.backup-v{from_version}-to-v{to_version}-{timestamp}"
            )
            shutil.copy2(self.db_path, backup_path)
            log.info("Backup automático creado: %s", backup_path)
        except Exception:
            log.exception("No se pudo crear backup automático — CONTINÚA con la migración")

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_tracks(self, query: str) -> dict:
        """
        Busca por título/género usando FTS5. Mucho más rápido que LIKE.
        Soporta operadores (ej: 'queen OR beatles') y coincidencia por palabras.
        """
        from collections import defaultdict
        result = defaultdict(lambda: defaultdict(list))

        if not query or not query.strip():
            return result

        # Sanitizar para FTS: escapar comillas dobles y envolver en comillas
        # para búsqueda por frase exacta con soporte de prefijo.
        safe_query = query.strip().replace('"', '""')
        # "{query}*" → busca por prefijo; p.ej. "bohem" matchea "bohemian"
        fts_query = f'"{safe_query}"*'

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT ar.name, al.title, s.track_number, s.title, s.filepath
                    FROM songs_fts fts
                    JOIN songs s      ON s.id = fts.rowid
                    LEFT JOIN albums al  ON al.id = s.album_id
                    LEFT JOIN artists ar ON ar.id = al.artist_id
                    WHERE songs_fts MATCH ?
                    ORDER BY ar.name, al.title, s.track_number
                """, (fts_query,))
                rows = cursor.fetchall()
            except Exception:
                # Fallback a LIKE si FTS falla por query malformada
                from src.utils.logger import get_logger
                get_logger(__name__).warning(
                    "FTS query falló, fallback a LIKE para '%s'", query
                )
                term = f"%{query}%"
                cursor.execute("""
                    SELECT ar.name, al.title, s.track_number, s.title, s.filepath
                    FROM songs s
                    LEFT JOIN albums al  ON al.id = s.album_id
                    LEFT JOIN artists ar ON ar.id = al.artist_id
                    WHERE s.title LIKE ?
                    OR al.title LIKE ?
                    OR ar.name LIKE ?
                    ORDER BY ar.name, al.title, s.track_number
                """, (term, term, term))
                rows = cursor.fetchall()

        for artist_name, album_title, track_num, title, filepath in rows:
            result[artist_name or "Artista Desconocido"][album_title or "Álbum Desconocido"].append(
                (track_num or 0, title, filepath)
            )
        return result

    # ------------------------------------------------------------------
    # Play count
    # ------------------------------------------------------------------

    def increment_play_count(self, filepath: str):
        """
        Incrementa play_count y registra una fila en play_history.
        Ambas operaciones se hacen en la misma transacción para mantener
        consistencia: o se aplican las dos, o ninguna.
        """
        from src.utils.logger import get_logger
        log = get_logger(__name__)
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Obtener el id de la canción
                cursor.execute("SELECT id FROM songs WHERE filepath = ?", (filepath,))
                row = cursor.fetchone()
                if not row:
                    return
                song_id = row[0]

                # Incrementar contador
                cursor.execute(
                    "UPDATE songs SET play_count = play_count + 1 WHERE id = ?",
                    (song_id,)
                )
                # Registrar en historial (para estadísticas temporales)
                cursor.execute(
                    "INSERT INTO play_history (song_id) VALUES (?)",
                    (song_id,)
                )
                conn.commit()
        except Exception:
            log.exception("No se pudo registrar reproducción de %s", filepath)

    def get_top_played(self, limit: int = 10) -> list:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ar.name, al.title, s.title, s.play_count
                FROM songs s
                JOIN albums  al ON s.album_id  = al.id
                JOIN artists ar ON al.artist_id = ar.id
                WHERE s.play_count > 0
                ORDER BY s.play_count DESC
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()

    # ------------------------------------------------------------------
    # Filepaths
    # ------------------------------------------------------------------

    def get_all_filepaths(self) -> list:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT filepath FROM songs")
            return [row[0] for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Song management
    # ------------------------------------------------------------------

    def remove_song(self, filepath: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM songs WHERE filepath = ?", (filepath,))
            row = cursor.fetchone()
            if not row:
                return
            song_id = row[0]
            cursor.execute("DELETE FROM playlist_songs WHERE song_id = ?", (song_id,))
            cursor.execute("DELETE FROM songs WHERE id = ?", (song_id,))
            conn.commit()
            self.clean_orphaned_records()

    def clean_orphaned_records(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM albums  WHERE id NOT IN (SELECT DISTINCT album_id  FROM songs)")
            cursor.execute("DELETE FROM artists WHERE id NOT IN (SELECT DISTINCT artist_id FROM albums)")
            conn.commit()

    def update_song_metadata(self, filepath: str, title: str, artist: str, album: str, track_number: int):
        """Updates the relational metadata of a song in the database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("INSERT OR IGNORE INTO artists (name) VALUES (?)", (artist,))
            cursor.execute("SELECT id FROM artists WHERE name = ?", (artist,))
            artist_id = cursor.fetchone()[0]

            cursor.execute("INSERT OR IGNORE INTO albums (title, artist_id) VALUES (?, ?)", (album, artist_id))
            cursor.execute("SELECT id FROM albums WHERE title = ? AND artist_id = ?", (album, artist_id))
            album_id = cursor.fetchone()[0]

            cursor.execute("""
                UPDATE songs
                SET title = ?, track_number = ?, album_id = ?
                WHERE filepath = ?
            """, (title, track_number, album_id, filepath))
            conn.commit()

            self.clean_orphaned_records()

    # ------------------------------------------------------------------
    # ReplayGain
    # ------------------------------------------------------------------

    def update_replay_gain(self, filepath: str, gain: float):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE songs SET replay_gain = ? WHERE filepath = ?",
                (gain, filepath)
            )
            conn.commit()

    def get_replay_gain(self, filepath: str) -> float:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT replay_gain FROM songs WHERE filepath = ?", (filepath,))
            row = cursor.fetchone()
            return row[0] if row else 0.0

    # ------------------------------------------------------------------
    # Playlist management
    # ------------------------------------------------------------------

    def delete_playlist(self, playlist_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM playlist_songs WHERE playlist_id = ?", (playlist_id,))
            cursor.execute("DELETE FROM playlists      WHERE id = ?",          (playlist_id,))
            conn.commit()

    def remove_song_from_playlist(self, playlist_id: int, record_id: int):
        """Removes the exact playlist entry by its unique record id."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM playlist_songs WHERE id = ?", (record_id,))
            conn.commit()

    def update_playlist_order(self, playlist_id: int, new_paths: list):
        """Rewrites the full playlist order after a drag-and-drop reorder."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM playlist_songs WHERE playlist_id = ?", (playlist_id,))

            for idx, path in enumerate(new_paths):
                cursor.execute("SELECT id FROM songs WHERE filepath = ?", (path,))
                row = cursor.fetchone()
                if row:
                    cursor.execute("""
                        INSERT INTO playlist_songs (playlist_id, song_id, sort_order)
                        VALUES (?, ?, ?)
                    """, (playlist_id, row[0], idx))
            conn.commit()

    # ------------------------------------------------------------------
    # Smart playlists
    # ------------------------------------------------------------------

    def get_top_played_songs(self, limit: int = 25) -> list:
        """Returns the most-played songs in playlist-panel format."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 0, title, filepath
                FROM songs
                WHERE play_count > 0
                ORDER BY play_count DESC
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()

    def get_recently_added(self, limit: int = 25) -> list:
        """Returns the most recently indexed songs."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 0, title, filepath
                FROM songs
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()

    def get_random_mix(self, limit: int = 50) -> list:
        """Returns a random shuffle of the whole library."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 0, title, filepath
                FROM songs
                ORDER BY RANDOM()
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()

    # ------------------------------------------------------------------
    # Library views
    # ------------------------------------------------------------------

    def get_songs_flat(self) -> list:
        """Returns all songs as a flat list sorted alphabetically by title."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT s.track_number, s.title, s.filepath
                FROM songs s
                ORDER BY s.title COLLATE NOCASE
            """)
            return cursor.fetchall()

    def get_songs_by_album(self) -> dict:
        """Returns songs grouped by album: {album_title: [(track_number, title, filepath)]}"""
        from collections import defaultdict
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT al.title, s.track_number, s.title, s.filepath
                FROM songs s
                JOIN albums al ON s.album_id = al.id
                ORDER BY al.title COLLATE NOCASE, s.track_number, s.title COLLATE NOCASE
            """)
            result = defaultdict(list)
            for album, track_number, title, filepath in cursor.fetchall():
                result[album].append((track_number, title, filepath))
            return dict(result)

    def get_songs_by_genre(self) -> dict:
        """Returns songs grouped by genre: {genre: [(track_number, title, filepath)]}"""
        from collections import defaultdict
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT CASE WHEN genre = '' OR genre IS NULL
                            THEN 'Unknown Genre' ELSE genre END AS g,
                       track_number, title, filepath
                FROM songs
                ORDER BY g COLLATE NOCASE, track_number, title COLLATE NOCASE
            """)
            result = defaultdict(list)
            for genre, track_number, title, filepath in cursor.fetchall():
                result[genre].append((track_number, title, filepath))
            return dict(result)

    def get_songs_by_year(self) -> dict:
        """Returns songs grouped by year (desc): {year_str: [(track_number, title, filepath)]}"""
        from collections import defaultdict
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT CASE WHEN year = 0 OR year IS NULL
                            THEN 'Unknown Year' ELSE CAST(year AS TEXT) END AS y,
                       year, track_number, title, filepath
                FROM songs
                ORDER BY year DESC, track_number, title COLLATE NOCASE
            """)
            result = defaultdict(list)
            for year_str, _year_int, track_number, title, filepath in cursor.fetchall():
                result[year_str].append((track_number, title, filepath))
            return dict(result)

    # ══════════════════════════════════════════════════════════════════
    # FAVORITOS
    # ══════════════════════════════════════════════════════════════════

    def set_favorite(self, filepath: str, is_favorite: bool) -> bool:
        """Marca o desmarca una canción como favorita. Retorna True si la canción existe."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE songs SET favorite = ? WHERE filepath = ?",
                (1 if is_favorite else 0, filepath)
            )
            return cursor.rowcount > 0

    def is_favorite(self, filepath: str) -> bool:
        """Devuelve True si la canción está marcada como favorita."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT favorite FROM songs WHERE filepath = ?", (filepath,))
            row = cursor.fetchone()
            return bool(row[0]) if row else False

    def get_favorite_songs(self) -> list:
        """Retorna todas las favoritas en formato (track_number, title, filepath)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT track_number, title, filepath
                FROM songs
                WHERE favorite = 1
                ORDER BY title COLLATE NOCASE
            """)
            return cursor.fetchall()

    # ══════════════════════════════════════════════════════════════════
    # HISTORIAL DE REPRODUCCIONES (play_history)
    # ══════════════════════════════════════════════════════════════════

    def get_recent_plays(self, limit: int = 50) -> list:
        """
        Retorna las últimas N reproducciones con metadatos completos.
        Útil para una vista "Escuchadas recientemente" o panel de actividad.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT h.played_at, s.title, ar.name AS artist, al.title AS album, s.filepath
                FROM play_history h
                JOIN songs   s  ON s.id  = h.song_id
                LEFT JOIN albums  al ON al.id = s.album_id
                LEFT JOIN artists ar ON ar.id = al.artist_id
                ORDER BY h.played_at DESC
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()

    def get_play_count_in_period(self, days: int = 7) -> int:
        """Número total de reproducciones en los últimos N días."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT COUNT(*) FROM play_history
                WHERE played_at >= datetime('now', '-{int(days)} days')
            """)
            return cursor.fetchone()[0] or 0

    def get_top_played_in_period(self, days: int = 30, limit: int = 25) -> list:
        """
        Top de canciones más reproducidas en los últimos N días.
        Base de un futuro "Wrapped mensual" o smart playlist temporal.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT s.title, ar.name AS artist, COUNT(*) AS plays
                FROM play_history h
                JOIN songs s  ON s.id = h.song_id
                LEFT JOIN albums  al ON al.id = s.album_id
                LEFT JOIN artists ar ON ar.id = al.artist_id
                WHERE h.played_at >= datetime('now', '-{int(days)} days')
                GROUP BY s.id
                ORDER BY plays DESC
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()
