# -*- coding: utf-8 -*-

class Playlist:
    """
    Model for managing playlists.
    Connects directly to SQLite following the MVP architecture.
    """
    def __init__(self, db_manager):
        self.db_manager = db_manager

    def create_playlist(self, name: str):
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO playlists (name) VALUES (?)", (name,))
            conn.commit()

    def get_all_playlists(self) -> list:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM playlists ORDER BY created_at DESC")
            return cursor.fetchall()

    def add_song_to_playlist(self, playlist_id: int, filepath: str):
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM songs WHERE filepath = ?", (filepath,))
            row = cursor.fetchone()
            if not row:
                return  # Song is not indexed in the library
            song_id = row[0]

            cursor.execute(
                "SELECT MAX(sort_order) FROM playlist_songs WHERE playlist_id = ?",
                (playlist_id,)
            )
            max_order = cursor.fetchone()[0]
            next_order = (max_order or 0) + 1

            cursor.execute("""
                INSERT INTO playlist_songs (playlist_id, song_id, sort_order)
                VALUES (?, ?, ?)
            """, (playlist_id, song_id, next_order))
            conn.commit()

    def update_order(self, playlist_id: int, new_paths: list):
        self.db_manager.update_playlist_order(playlist_id, new_paths)

    def get_playlist_songs(self, playlist_id: int) -> list:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ps.id, s.title, s.filepath
                FROM playlist_songs ps
                JOIN songs s ON ps.song_id = s.id
                WHERE ps.playlist_id = ?
                ORDER BY ps.sort_order ASC
            """, (playlist_id,))
            return cursor.fetchall()

    def remove_song(self, playlist_id: int, record_id: int):
        """Removes the exact entry by its unique record id (not visual position)."""
        self.db_manager.remove_song_from_playlist(playlist_id, record_id)
