# -*- coding: utf-8 -*-
"""
OSIntegrationManager
────────────────────
Integración con el sistema operativo:

  · Linux: MPRIS2 (D-Bus) — controles multimedia del escritorio
  · Windows: SMTC — teclas multimedia y widget de "Ahora suena"
  · Bandeja del sistema (señales tray_* del MainWindow)
  · Drag & Drop de archivos sobre el reproductor
  · Apertura por línea de comandos (single-instance IPC)
"""
import os
import sys

from PyQt6.QtMultimedia import QMediaPlayer

from src.utils.logger import get_logger

log = get_logger(__name__)


class OSIntegrationManager:
    """
    No hereda de QObject porque solo conecta señales existentes.
    Mantiene referencias al media_manager (MPRIS o SMTC) para evitar GC.
    """

    def __init__(self, playback_controller, player_view, main_window):
        self.playback_controller = playback_controller
        self.player_view         = player_view
        self.main_window         = main_window
        self.media_manager       = None   # Se rellena en setup_native_integration()

        self._setup_tray_and_dnd()
        self._setup_native_integration()

    # ── Bandeja + drag&drop ─────────────────────────────────────────────

    def _setup_tray_and_dnd(self):
        """Conecta las acciones del tray icon con el controlador de reproducción."""
        self.main_window.tray_play_requested.connect(self.playback_controller.handle_play_pause)
        self.main_window.tray_next_requested.connect(self.playback_controller.play_next)
        self.main_window.tray_prev_requested.connect(self.playback_controller.play_prev)
        self.player_view.file_dropped.connect(self.play_dropped_file)

    # ── MPRIS / SMTC ────────────────────────────────────────────────────

    def _setup_native_integration(self):
        """Detecta el SO y levanta el adaptador nativo adecuado."""
        try:
            if sys.platform.startswith("linux"):
                from src.models.mpris_manager import MprisManager
                self.media_manager = MprisManager()
                self._wire_media_manager(self.media_manager.adaptor)
                log.info("Integración MPRIS2 activada")
            elif sys.platform == "win32":
                from src.models.smtc_manager import SmtcManager
                self.media_manager = SmtcManager()
                self._wire_media_manager(self.media_manager)
                log.info("Integración SMTC activada")
        except Exception:
            log.exception("No se pudo activar la integración nativa del SO")
            self.media_manager = None

    def _wire_media_manager(self, manager):
        """Conecta las señales del adaptador con el motor de reproducción."""
        manager.play_pause_requested.connect(self.playback_controller.handle_play_pause)
        manager.next_requested.connect(self.playback_controller.play_next)
        manager.prev_requested.connect(self.playback_controller.play_prev)

        self.player_view.play_toggled.connect(
            lambda: manager.update_status(
                self.playback_controller.media_player.playbackState()
                == QMediaPlayer.PlaybackState.PlayingState
            )
        )
        self.playback_controller.metadata_ready_for_os.connect(manager.update_metadata)

    # ── Drag & drop + línea de comandos ─────────────────────────────────

    def play_dropped_file(self, filepath: str):
        """
        Maneja un archivo arrastrado sobre la portada del reproductor o
        pasado por línea de comandos (single-instance IPC).
        """
        valid_ext = (
            ".mp3", ".wav", ".flac", ".ogg", ".m4a",
            ".opus", ".aac", ".webm", ".wma", ".mka"
        )
        if not os.path.isfile(filepath) or not filepath.lower().endswith(valid_ext):
            self.main_window.show_status_message(
                "Formato no soportado o archivo no encontrado."
            )
            return

        # Reproducir la pista aislada (no como parte de playlist)
        self.playback_controller.play_queue([filepath], 0)

        filename = os.path.basename(filepath)
        self.main_window.show_status_message(f"Reproduciendo: {filename}")
        self.main_window.showNormal()
        self.main_window.activateWindow()

    # ── Shutdown ordenado ───────────────────────────────────────────────

    def hard_shutdown(self):
        """Apaga recursos del SO: tray, IPC socket."""
        try:
            if hasattr(self.main_window, "tray_icon"):
                self.main_window.tray_icon.hide()
                self.main_window.tray_icon.deleteLater()
        except Exception:
            log.exception("Error limpiando tray")
