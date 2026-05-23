# -*- coding: utf-8 -*-
"""
PlaylistCoordinator
───────────────────
Gestiona el dominio de **playlists**:

  · CRUD de playlists manuales (crear, eliminar)
  · Smart playlists (IDs virtuales negativos: -1 Top25, -2 Recientes, -3 Mix)
  · Añadir/quitar canciones, reordenamiento por drag & drop
  · Importación y exportación M3U
  · Sincronización en vivo de la cola de reproducción cuando la playlist
    activa cambia mientras suena
"""
import os

from PyQt6.QtCore import QObject, pyqtSignal

from src.models.m3u_manager import M3UManager
from src.utils.logger import get_logger

log = get_logger(__name__)


class PlaylistCoordinator(QObject):

    # Emitida cuando una playlist se reproduce (para que MainController la marque activa)
    play_playlist_queue = pyqtSignal(list, int, int)   # queue, start_index, playlist_id

    def __init__(self, playlist_view, library_view, playback_controller,
                 playlist_model, db_manager, main_window,
                 get_active_playlist_id, set_active_playlist_id):
        super().__init__()
        self.playlist_view        = playlist_view
        self.library_view         = library_view
        self.playback_controller  = playback_controller
        self.playlist_model       = playlist_model
        self.db_manager           = db_manager
        self.main_window          = main_window
        # Callables inyectadas para leer/escribir el estado de playlist activa,
        # que vive en el MainController (Session-scope)
        self._get_active_playlist_id = get_active_playlist_id
        self._set_active_playlist_id = set_active_playlist_id

        self._connect_signals()

    def _connect_signals(self):
        self.playlist_view.create_playlist_requested.connect(self._create_playlist)
        self.playlist_view.playlist_selected.connect(self._load_playlist_songs)
        self.playlist_view.delete_playlist_requested.connect(self._delete_playlist)
        self.playlist_view.import_m3u_requested.connect(self._import_m3u_playlist)
        self.playlist_view.export_m3u_requested.connect(self._export_m3u_playlist)
        self.playlist_view.songs_reordered.connect(self._handle_songs_reordered)
        self.playlist_view.remove_song_requested.connect(self._remove_song_from_playlist_view)
        self.playlist_view.track_selected.connect(self._play_playlist_queue)

        # Desde la biblioteca: añadir canción a una playlist específica
        self.library_view.add_to_playlist_requested.connect(self._add_song_to_playlist)

    # ── Carga inicial y listados ─────────────────────────────────────────

    def load_playlists_from_db(self):
        """Recarga el panel de playlists con la lista actual de la BD."""
        playlists = self.playlist_model.get_all_playlists()
        self.playlist_view.update_playlists(playlists)
        self.library_view.update_available_playlists(playlists)

    # ── CRUD ─────────────────────────────────────────────────────────────

    def _create_playlist(self, name: str):
        self.playlist_model.create_playlist(name)
        self.load_playlists_from_db()
        self.main_window.show_status_message(f"Playlist '{name}' creada con éxito.")

    def _add_song_to_playlist(self, playlist_id: int, filepath: str):
        self.playlist_model.add_song_to_playlist(playlist_id, filepath)
        self._load_playlist_songs(playlist_id)
        self._sync_live_queue(playlist_id)
        self.main_window.show_status_message("Canción agregada a la playlist.")

    def _delete_playlist(self, playlist_id: int):
        self.db_manager.delete_playlist(playlist_id)
        if self._get_active_playlist_id() == playlist_id:
            self._set_active_playlist_id(-1)
            self.playlist_view.set_active_playlist(-1)
            self.playback_controller.clear_playback()

        self.load_playlists_from_db()
        self.playlist_view.update_songs([])
        self.main_window.show_status_message("Playlist eliminada correctamente.")

    # ── Carga de canciones (manual y smart playlists) ────────────────────

    def _load_playlist_songs(self, playlist_id: int):
        """Carga canciones de playlist manual o ejecuta lógica de Smart Playlist."""
        if playlist_id == -1:
            songs = self.db_manager.get_top_played_songs(25)
            self.playlist_view.btn_delete.setEnabled(False)
            self.playlist_view.btn_export.setEnabled(True)
        elif playlist_id == -2:
            songs = self.db_manager.get_recently_added(25)
            self.playlist_view.btn_delete.setEnabled(False)
            self.playlist_view.btn_export.setEnabled(True)
        elif playlist_id == -3:
            songs = self.db_manager.get_random_mix(50)
            self.playlist_view.btn_delete.setEnabled(False)
            self.playlist_view.btn_export.setEnabled(True)
        elif playlist_id == -4:
            songs = self.db_manager.get_favorite_songs()
            self.playlist_view.btn_delete.setEnabled(False)
            self.playlist_view.btn_export.setEnabled(True)
        else:
            songs = self.playlist_model.get_playlist_songs(playlist_id)
            self.playlist_view.btn_delete.setEnabled(True)
            self.playlist_view.btn_export.setEnabled(True)

        self.playlist_view.update_songs(songs)

        if self._get_active_playlist_id() == playlist_id:
            self.playlist_view.highlight_song(self.playback_controller.current_index)

    # ── Reproducción ─────────────────────────────────────────────────────

    def _play_playlist_queue(self, queue: list, start_index: int, playlist_id: int):
        self._set_active_playlist_id(playlist_id)
        self.playlist_view.set_active_playlist(playlist_id)
        self.playback_controller.play_queue(queue, start_index)
        self.play_playlist_queue.emit(queue, start_index, playlist_id)

    # ── Import/Export M3U ────────────────────────────────────────────────

    def _import_m3u_playlist(self, filepath: str):
        tracks = M3UManager.import_from_m3u(filepath)
        if not tracks:
            self.main_window.show_status_message("No se encontraron rutas válidas en el M3U.")
            return

        playlist_name = os.path.splitext(os.path.basename(filepath))[0]
        self.playlist_model.create_playlist(playlist_name)

        playlists = self.playlist_model.get_all_playlists()
        new_id = playlists[0][0]   # get_all_playlists ordena por fecha desc

        for track in tracks:
            self.playlist_model.add_song_to_playlist(new_id, track)

        self.load_playlists_from_db()
        self.main_window.show_status_message(f"Playlist '{playlist_name}' importada.")

    def _export_m3u_playlist(self, playlist_id: int, filepath: str):
        songs = self.playlist_model.get_playlist_songs(playlist_id)
        if not songs:
            self.main_window.show_status_message("No se puede exportar una playlist vacía.")
            return

        playlists = self.playlist_model.get_all_playlists()
        playlist_name = next(
            (name for pid, name in playlists if pid == playlist_id),
            "Playlist_Exportada"
        )
        paths = [path for _, title, path in songs]

        success = M3UManager.export_to_m3u(filepath, playlist_name, paths)
        if success:
            self.main_window.show_status_message(f"Playlist guardada en: {filepath}")
        else:
            self.main_window.show_status_message("Error al exportar la playlist.")

    # ── Reordenamiento y eliminación de canciones en playlist ────────────

    def _handle_songs_reordered(self, playlist_id: int, new_paths: list):
        self.playlist_model.update_order(playlist_id, new_paths)
        self._load_playlist_songs(playlist_id)
        self._sync_live_queue(playlist_id)

    def _remove_song_from_playlist_view(self, playlist_id: int, id_reg: int):
        old_queue = self.playback_controller.current_queue
        old_index = self.playback_controller.current_index
        old_path  = old_queue[old_index] if old_queue and old_index >= 0 else None

        self.playlist_model.remove_song(playlist_id, id_reg)
        self._load_playlist_songs(playlist_id)

        if self._get_active_playlist_id() == playlist_id:
            songs = self.playlist_model.get_playlist_songs(playlist_id)
            new_queue = [path for id_reg, title, path in songs]
            self.playback_controller.current_queue = new_queue

            if old_path not in new_queue:
                if not new_queue:
                    self.playback_controller.clear_playback()
                else:
                    new_idx = min(old_index, len(new_queue) - 1)
                    self.playback_controller.current_index = new_idx - 1
                    self.playback_controller.play_next()
            else:
                self.playback_controller.current_index = new_queue.index(old_path)

    # ── Sincronización en vivo de la cola activa ─────────────────────────

    def _sync_live_queue(self, playlist_id: int):
        """Si la playlist modificada es la que está sonando, actualiza la cola en vivo."""
        if self._get_active_playlist_id() != playlist_id:
            return

        songs = self.playlist_model.get_playlist_songs(playlist_id)
        new_queue = [path for id_reg, title, path in songs]

        old_path = None
        if self.playback_controller.current_queue and self.playback_controller.current_index >= 0:
            old_path = self.playback_controller.current_queue[self.playback_controller.current_index]

        self.playback_controller.current_queue = new_queue
        if old_path in new_queue:
            self.playback_controller.current_index = new_queue.index(old_path)
