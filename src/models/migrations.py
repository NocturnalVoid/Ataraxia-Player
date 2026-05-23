# -*- coding: utf-8 -*-
"""
Migraciones de schema numeradas.
Cada entrada es (version_number, description, sql_or_callable).
- Si es SQL string, se ejecuta tal cual.
- Si es callable(cursor), se ejecuta como función (útil para migraciones de datos).

NUNCA modifiques una migración ya aplicada en producción. Siempre añade una nueva
con número más alto.
"""

MIGRATIONS = [
    # ──────────────────────────────────────────────────────────────────
    # v1 — Schema base (ya existe en todas las BDs actuales).
    # Se define aquí para BDs nuevas que se crean desde cero.
    # ──────────────────────────────────────────────────────────────────
    (
        1,
        "Schema base (artists, albums, songs, playlists, playlist_songs, config)",
        """
        CREATE TABLE IF NOT EXISTS artists (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS albums (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            cover_path  TEXT,
            artist_id   INTEGER,
            FOREIGN KEY (artist_id) REFERENCES artists (id)
        );

        CREATE TABLE IF NOT EXISTS songs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT    NOT NULL,
            filepath        TEXT    UNIQUE NOT NULL,
            duration        INTEGER DEFAULT 0,
            track_number    INTEGER DEFAULT 0,
            genre           TEXT    DEFAULT '',
            year            INTEGER DEFAULT 0,
            play_count      INTEGER DEFAULT 0,
            replay_gain     REAL    DEFAULT 0.0,
            album_id        INTEGER,
            FOREIGN KEY (album_id) REFERENCES albums (id)
        );

        CREATE TABLE IF NOT EXISTS playlists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS playlist_songs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER,
            song_id     INTEGER,
            sort_order  INTEGER,
            FOREIGN KEY (playlist_id) REFERENCES playlists (id),
            FOREIGN KEY (song_id)     REFERENCES songs (id)
        );

        CREATE TABLE IF NOT EXISTS config (
            key     TEXT PRIMARY KEY,
            value   TEXT NOT NULL
        );
        """,
    ),

    # ──────────────────────────────────────────────────────────────────
    # v2 — Columna 'favorite' para el sistema de favoritos
    # ──────────────────────────────────────────────────────────────────
    (
        2,
        "Añadir columna 'favorite' a 'songs'",
        """
        ALTER TABLE songs ADD COLUMN favorite INTEGER DEFAULT 0;
        """,
    ),

    # ──────────────────────────────────────────────────────────────────
    # v3 — Constraints faltantes (UNIQUE y CHECK)
    # SQLite no soporta ADD CONSTRAINT a una tabla existente, así que
    # para añadir constraints hay que hacer "migración por copia":
    # 1) crear tabla nueva con los constraints
    # 2) copiar los datos limpios
    # 3) borrar la vieja y renombrar
    # En esta v3 solo añadimos UNIQUE por columnas nuevas con CREATE INDEX
    # (equivalente y menos invasivo).
    # Los CHECK los metemos en v5 cuando reconstruimos la tabla songs.
    # ──────────────────────────────────────────────────────────────────
    (
        3,
        "UNIQUE composites: (playlist_id, song_id) y (title, artist_id)",
        """
        -- Primero limpiamos posibles duplicados previos
        DELETE FROM playlist_songs
        WHERE id NOT IN (
            SELECT MIN(id) FROM playlist_songs
            GROUP BY playlist_id, song_id
        );

        DELETE FROM albums
        WHERE id NOT IN (
            SELECT MIN(id) FROM albums
            GROUP BY title, artist_id
        );

        -- UNIQUE a través de índices únicos
        CREATE UNIQUE INDEX IF NOT EXISTS ux_playlist_songs_pair
            ON playlist_songs(playlist_id, song_id);

        CREATE UNIQUE INDEX IF NOT EXISTS ux_albums_title_artist
            ON albums(title, artist_id);
        """,
    ),

    # ──────────────────────────────────────────────────────────────────
    # v4 — Índices no-únicos para consultas frecuentes
    # ──────────────────────────────────────────────────────────────────
    (
        4,
        "Índices de rendimiento",
        """
        CREATE INDEX IF NOT EXISTS ix_songs_album_id
            ON songs(album_id);

        CREATE INDEX IF NOT EXISTS ix_songs_favorite
            ON songs(favorite) WHERE favorite = 1;

        CREATE INDEX IF NOT EXISTS ix_songs_play_count
            ON songs(play_count DESC);

        CREATE INDEX IF NOT EXISTS ix_playlist_songs_playlist
            ON playlist_songs(playlist_id, sort_order);

        CREATE INDEX IF NOT EXISTS ix_playlist_songs_song
            ON playlist_songs(song_id);

        CREATE INDEX IF NOT EXISTS ix_songs_genre
            ON songs(genre);

        CREATE INDEX IF NOT EXISTS ix_songs_year
            ON songs(year);
        """,
    ),

    # ──────────────────────────────────────────────────────────────────
    # v5 — Reconstruir 'songs' con CHECK y ON DELETE apropiados
    # (migración por copia)
    # ──────────────────────────────────────────────────────────────────
    (
        5,
        "Reconstruir 'songs' con CHECK constraints y FK con ON DELETE SET NULL",
        """
        BEGIN;

        CREATE TABLE songs_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT    NOT NULL,
            filepath        TEXT    UNIQUE NOT NULL,
            duration        INTEGER DEFAULT 0 CHECK(duration >= 0),
            track_number    INTEGER DEFAULT 0 CHECK(track_number >= 0),
            genre           TEXT    DEFAULT '',
            year            INTEGER DEFAULT 0 CHECK(year >= 0 AND year <= 9999),
            play_count      INTEGER DEFAULT 0 CHECK(play_count >= 0),
            replay_gain     REAL    DEFAULT 0.0,
            favorite        INTEGER DEFAULT 0 CHECK(favorite IN (0, 1)),
            album_id        INTEGER,
            FOREIGN KEY (album_id) REFERENCES albums (id) ON DELETE SET NULL
        );

        INSERT INTO songs_new
        SELECT
            id, title, filepath,
            COALESCE(MAX(duration, 0), 0),
            COALESCE(MAX(track_number, 0), 0),
            COALESCE(genre, ''),
            CASE WHEN year BETWEEN 0 AND 9999 THEN year ELSE 0 END,
            COALESCE(MAX(play_count, 0), 0),
            COALESCE(replay_gain, 0.0),
            CASE WHEN favorite IN (0, 1) THEN favorite ELSE 0 END,
            album_id
        FROM songs;

        DROP TABLE songs;
        ALTER TABLE songs_new RENAME TO songs;

        -- Recrear índices (se pierden al DROP)
        CREATE INDEX IF NOT EXISTS ix_songs_album_id   ON songs(album_id);
        CREATE INDEX IF NOT EXISTS ix_songs_favorite   ON songs(favorite) WHERE favorite = 1;
        CREATE INDEX IF NOT EXISTS ix_songs_play_count ON songs(play_count DESC);
        CREATE INDEX IF NOT EXISTS ix_songs_genre      ON songs(genre);
        CREATE INDEX IF NOT EXISTS ix_songs_year       ON songs(year);

        COMMIT;
        """,
    ),

    # ──────────────────────────────────────────────────────────────────
    # v6 — Reconstruir 'playlist_songs' con ON DELETE CASCADE
    # ──────────────────────────────────────────────────────────────────
    (
        6,
        "Reconstruir 'playlist_songs' con CASCADE",
        """
        BEGIN;

        CREATE TABLE playlist_songs_new (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            song_id     INTEGER NOT NULL,
            sort_order  INTEGER DEFAULT 0,
            FOREIGN KEY (playlist_id) REFERENCES playlists (id) ON DELETE CASCADE,
            FOREIGN KEY (song_id)     REFERENCES songs (id)     ON DELETE CASCADE,
            UNIQUE(playlist_id, song_id)
        );

        INSERT INTO playlist_songs_new (id, playlist_id, song_id, sort_order)
        SELECT id, playlist_id, song_id, COALESCE(sort_order, 0)
        FROM playlist_songs
        WHERE playlist_id IS NOT NULL AND song_id IS NOT NULL;

        DROP TABLE playlist_songs;
        ALTER TABLE playlist_songs_new RENAME TO playlist_songs;

        CREATE INDEX IF NOT EXISTS ix_playlist_songs_playlist
            ON playlist_songs(playlist_id, sort_order);
        CREATE INDEX IF NOT EXISTS ix_playlist_songs_song
            ON playlist_songs(song_id);

        COMMIT;
        """,
    ),

    # ──────────────────────────────────────────────────────────────────
    # v7 — Historial de reproducciones (habilita features futuras)
    # ──────────────────────────────────────────────────────────────────
    (
        7,
        "Tabla play_history para estadísticas temporales",
        """
        CREATE TABLE IF NOT EXISTS play_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            song_id    INTEGER NOT NULL,
            played_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (song_id) REFERENCES songs (id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS ix_play_history_song
            ON play_history(song_id);
        CREATE INDEX IF NOT EXISTS ix_play_history_date
            ON play_history(played_at DESC);
        """,
    ),

    # ──────────────────────────────────────────────────────────────────
    # v8 — Búsqueda Full-Text Search (FTS5)
    # ──────────────────────────────────────────────────────────────────
    (
        8,
        "FTS5 virtual table para búsqueda rápida",
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS songs_fts USING fts5(
            title,
            genre,
            content='songs',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        );

        -- Poblar FTS con datos existentes
        INSERT INTO songs_fts(rowid, title, genre)
        SELECT id, title, genre FROM songs;

        -- Triggers para mantener FTS sincronizado
        CREATE TRIGGER IF NOT EXISTS tg_songs_ai AFTER INSERT ON songs BEGIN
            INSERT INTO songs_fts(rowid, title, genre)
            VALUES (new.id, new.title, new.genre);
        END;

        CREATE TRIGGER IF NOT EXISTS tg_songs_ad AFTER DELETE ON songs BEGIN
            INSERT INTO songs_fts(songs_fts, rowid, title, genre)
            VALUES ('delete', old.id, old.title, old.genre);
        END;

        CREATE TRIGGER IF NOT EXISTS tg_songs_au AFTER UPDATE ON songs BEGIN
            INSERT INTO songs_fts(songs_fts, rowid, title, genre)
            VALUES ('delete', old.id, old.title, old.genre);
            INSERT INTO songs_fts(rowid, title, genre)
            VALUES (new.id, new.title, new.genre);
        END;
        """,
    ),

    # ──────────────────────────────────────────────────────────────────
    # v9 — Carpetas raíz escaneadas (para botón "Actualizar biblioteca")
    # ──────────────────────────────────────────────────────────────────
    (
        9,
        "Tabla library_folders para soportar reescaneo masivo",
        """
        CREATE TABLE IF NOT EXISTS library_folders (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            path       TEXT NOT NULL UNIQUE,
            added_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """,
    ),
]