# -*- coding: utf-8 -*-
"""
Pruebas de los constraints y comportamientos críticos de la BD.
Se ejecutan con: python -m pytest tests/test_database_constraints.py -v
Requiere: pip install pytest
"""
import os
import sqlite3
import tempfile

import pytest

from src.models.database_manager import DatabaseManager


@pytest.fixture
def db():
    """BD temporal nueva para cada test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    # Hack: forzamos el path para no usar el real del usuario
    dbm = DatabaseManager.__new__(DatabaseManager)
    dbm.db_path = path
    dbm._initialize_database()
    yield dbm
    os.remove(path)
    for ext in (".wal", ".shm"):
        if os.path.exists(path + ext):
            os.remove(path + ext)


def test_foreign_keys_are_enforced(db):
    """Con FK activas, no debe poder insertar song con album_id inválido
    usando valores que violen la referencia (excepto NULL que sí se permite)."""
    with db.get_connection() as conn:
        # album_id NULL es válido
        conn.execute("INSERT INTO songs (title, filepath) VALUES (?, ?)",
                     ("t", "/x.mp3"))
        # album_id = 999 inexistente debe fallar
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO songs (title, filepath, album_id) VALUES (?, ?, ?)",
                ("t", "/y.mp3", 999)
            )


def test_favorite_check_constraint(db):
    """favorite solo acepta 0 o 1."""
    with db.get_connection() as conn:
        conn.execute("INSERT INTO songs (title, filepath, favorite) VALUES (?, ?, ?)",
                     ("t", "/a.mp3", 1))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO songs (title, filepath, favorite) VALUES (?, ?, ?)",
                         ("t", "/b.mp3", 42))


def test_cascade_delete_playlist_songs(db):
    """Al borrar una playlist, sus playlist_songs desaparecen."""
    with db.get_connection() as conn:
        conn.execute("INSERT INTO playlists (name) VALUES ('test')")
        pid = conn.execute("SELECT id FROM playlists WHERE name='test'").fetchone()[0]
        conn.execute("INSERT INTO songs (title, filepath) VALUES ('t', '/x.mp3')")
        sid = conn.execute("SELECT id FROM songs WHERE filepath='/x.mp3'").fetchone()[0]
        conn.execute(
            "INSERT INTO playlist_songs (playlist_id, song_id) VALUES (?, ?)",
            (pid, sid)
        )
        conn.commit()
        # Borrar playlist → fila en playlist_songs debe ir con ella
        conn.execute("DELETE FROM playlists WHERE id = ?", (pid,))
        conn.commit()
        rows = conn.execute(
            "SELECT COUNT(*) FROM playlist_songs WHERE playlist_id = ?", (pid,)
        ).fetchone()
        assert rows[0] == 0


def test_unique_playlist_song_pair(db):
    """No se puede añadir la misma canción dos veces a la misma playlist."""
    with db.get_connection() as conn:
        conn.execute("INSERT INTO playlists (name) VALUES ('p')")
        conn.execute("INSERT INTO songs (title, filepath) VALUES ('t', '/x.mp3')")
        pid = conn.execute("SELECT id FROM playlists LIMIT 1").fetchone()[0]
        sid = conn.execute("SELECT id FROM songs LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT INTO playlist_songs (playlist_id, song_id) VALUES (?, ?)",
            (pid, sid)
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO playlist_songs (playlist_id, song_id) VALUES (?, ?)",
                (pid, sid)
            )


def test_fts_search_works(db):
    """La búsqueda FTS encuentra por título."""
    with db.get_connection() as conn:
        conn.execute("INSERT INTO songs (title, filepath) VALUES ('Bohemian Rhapsody', '/q.mp3')")
        conn.commit()
    result = db.search_tracks("bohemian")
    # Debe encontrar la canción
    assert any("Bohemian" in album for artist in result.values() for album in artist.keys() or []) \
        or any("Bohemian" in title for artist in result.values() for album in artist.values() for _, title, _ in album)


def test_schema_version_is_latest(db):
    """Después de inicializar, la versión de schema debe ser la máxima de MIGRATIONS."""
    from src.models.migrations import MIGRATIONS
    expected = max(v for v, _, _ in MIGRATIONS)
    with db.get_connection() as conn:
        actual = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()[0]
    assert actual == expected