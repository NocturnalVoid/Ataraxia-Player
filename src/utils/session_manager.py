# -*- coding: utf-8 -*-
"""
SessionManager
──────────────
Persistencia de sesión entre ejecuciones:

  · Guarda/restaura la cola actual de reproducción (rutas + índice)
  · Guarda/restaura el ID de la playlist activa
  · Guarda/restaura el tema (claro/oscuro)
  · Limpieza ordenada al cerrar (detener audio, borrar temporales)

No maneja lógica de negocio — solo lee y escribe de QSettings de forma segura.
"""
import os

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from src.utils.logger import get_logger

log = get_logger(__name__)


class SessionManager:

    def __init__(self, playback_controller, main_window):
        self.playback_controller = playback_controller
        self.main_window         = main_window
        self.settings            = QSettings("Ataraxia", "Player")

        # Estado de sesión que se lee/escribe desde aquí
        self._active_playlist_id = self.settings.value("active_playlist_id", -1, type=int)

        # Auto-cleanup al cerrar la app
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.save_and_cleanup)

    # ── Getters/setters para el estado volátil ──────────────────────────

    def get_active_playlist_id(self) -> int:
        return self._active_playlist_id

    def set_active_playlist_id(self, playlist_id: int):
        self._active_playlist_id = playlist_id

    # ── Tema ─────────────────────────────────────────────────────────────

    def get_saved_theme(self) -> bool:
        return self.settings.value("dark_mode", False, type=bool)

    def save_theme(self, is_dark: bool):
        self.settings.setValue("dark_mode", is_dark)

    # ── Restauración de la cola al arrancar ──────────────────────────────

    def restore_playback_session(self, playlist_view) -> bool:
        """
        Restaura cola, índice y playlist activa (sin auto-reproducir).
        Retorna True si se restauró algo, False si no había sesión guardada.
        """
        saved_queue = self.settings.value("saved_queue", [])
        # QSettings puede devolver un string cuando la lista tenía un solo elemento
        if isinstance(saved_queue, str):
            saved_queue = [saved_queue]

        saved_index = self.settings.value("saved_index", -1, type=int)

        if saved_queue and 0 <= saved_index < len(saved_queue):
            self.playback_controller.play_queue(saved_queue, saved_index, auto_play=False)
            if self._active_playlist_id != -1:
                playlist_view.set_active_playlist(self._active_playlist_id)
            log.info("Sesión restaurada: %d canciones en cola, índice=%d",
                     len(saved_queue), saved_index)
            return True
        return False

    # ── Limpieza al cerrar ──────────────────────────────────────────────

    def save_and_cleanup(self):
        """
        Guarda el estado de sesión y detiene el motor de audio.
        Llamado automáticamente al cerrar la app.
        """
        log.info("Guardando sesión y liberando recursos…")
        try:
            if hasattr(self.playback_controller, 'media_player'):
                self.playback_controller.media_player.stop()
        except Exception:
            log.exception("Error deteniendo el reproductor durante cleanup")

        try:
            self.settings.setValue("saved_queue",       self.playback_controller.current_queue)
            self.settings.setValue("saved_index",       self.playback_controller.current_index)
            self.settings.setValue("active_playlist_id", self._active_playlist_id)
        except Exception:
            log.exception("Error guardando sesión en QSettings")
