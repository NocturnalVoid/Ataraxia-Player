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

        Filtra rutas inválidas o que ya no existen en disco para evitar
        'pistas fantasma' cuando la BD fue borrada externamente.
        """
        saved_queue = self.settings.value("saved_queue", [])
        # QSettings puede devolver un string cuando la lista tenía un solo elemento
        if isinstance(saved_queue, str):
            saved_queue = [saved_queue]

        # Filtrar rutas que ya no existen en disco. Si la BD se borró y se
        # recreó vacía (o se restauró una diferente), las rutas de la sesión
        # anterior seguirían en QSettings pero los archivos podrían no
        # corresponder a la nueva BD. Mantener solo las que existen en disco
        # elimina las 'pistas fantasma' más comunes.
        # Nota: no filtramos por la BD porque la sesión se restaura ANTES de
        # que la biblioteca se cargue completamente.
        valid_queue = [p for p in saved_queue if isinstance(p, str) and os.path.exists(p)]

        if len(valid_queue) < len(saved_queue):
            log.info(
                "Sesión: %d ruta(s) descartadas por no existir en disco "
                "(la BD puede haber cambiado)",
                len(saved_queue) - len(valid_queue)
            )
            # Persistir la cola ya limpia para que no vuelvan a aparecer
            self.settings.setValue("saved_queue", valid_queue)

        saved_index = self.settings.value("saved_index", -1, type=int)
        # Ajustar el índice si quedó fuera del rango tras el filtrado
        if saved_index >= len(valid_queue):
            saved_index = 0 if valid_queue else -1
            self.settings.setValue("saved_index", saved_index)

        if valid_queue and 0 <= saved_index < len(valid_queue):
            self.playback_controller.play_queue(valid_queue, saved_index, auto_play=False)
            if self._active_playlist_id != -1:
                playlist_view.set_active_playlist(self._active_playlist_id)
            log.info("Sesión restaurada: %d canciones en cola, índice=%d",
                     len(valid_queue), saved_index)
            return True
        return False

    # ── Limpieza al cerrar ──────────────────────────────────────────────

    def clear_saved_session(self):
        """
        Borra la sesión de reproducción guardada en QSettings y activa un
        flag para que save_and_cleanup (disparado por aboutToQuit) no la
        sobreescriba con la cola actual en memoria.

        Sin este flag, el flujo de restore queda así:
          1. clear_saved_session() borra QSettings ← correcto
          2. QCoreApplication.quit() dispara aboutToQuit
          3. save_and_cleanup() SOBREESCRIBE QSettings con la cola vieja ← bug
          4. La nueva instancia arranca y restaura rutas de la BD anterior (fantasma)
        """
        try:
            self.settings.remove("saved_queue")
            self.settings.remove("saved_index")
            self.settings.remove("active_playlist_id")
            log.info("Sesión de reproducción limpiada (preparando para restart)")
        except Exception:
            log.exception("Error limpiando sesión guardada")
        # Deshabilitar el guardado para este ciclo de vida de la sesión
        self._skip_save = True

    def save_and_cleanup(self):
        """
        Guarda el estado de sesión y detiene el motor de audio.
        Llamado automáticamente al cerrar la app.
        Silenciado si se llamó clear_saved_session() antes (modo restore).
        """
        # Si la sesión fue limpiada explícitamente (restore de BD), no
        # guardamos nada: la cola actual pertenece a la BD anterior y no
        # debe persistir para la nueva instancia.
        if getattr(self, "_skip_save", False):
            log.info("save_and_cleanup omitido — sesión limpiada para restart")
            try:
                if hasattr(self.playback_controller, 'media_player'):
                    self.playback_controller.media_player.stop()
            except Exception:
                pass
            return

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
