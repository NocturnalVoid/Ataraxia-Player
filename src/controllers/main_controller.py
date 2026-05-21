# -*- coding: utf-8 -*-
"""
MainController
──────────────
Orquestador de alto nivel de Ataraxia Player.

Responsabilidades (reducidas tras el refactor de coordinadores):
  · Instanciar modelos, vistas y la MainWindow
  · Instanciar los coordinadores de dominio y cablearlos entre sí:
      - LibraryCoordinator     → src/controllers/library_coordinator.py
      - PlaylistCoordinator    → src/controllers/playlist_coordinator.py
      - PlaybackController     → src/controllers/playback_controller.py
      - ConversionController   → src/controllers/conversion_controller.py
      - SessionManager         → src/utils/session_manager.py
      - OSIntegrationManager   → src/utils/os_integration_manager.py
  · Integración del Mini Player (monkey-patching de sincronización)
  · Apertura de diálogo de Preferencias
  · Cierre ordenado de la aplicación

Cualquier lógica específica de dominio (escaneo, búsqueda, playlists, letras,
etc.) NO debe añadirse aquí — va en el coordinador correspondiente.
"""
from PyQt6.QtWidgets import QApplication

from src.models.media_converter   import MediaConverter
from src.models.metadata_manager  import MetadataManager
from src.models.lyrics_parser     import LyricsParser
from src.models.playlist          import Playlist
from src.models.database_manager  import DatabaseManager
from src.models.db_maintenance import DatabaseMaintenance

from src.views.library_panel      import LibraryPanel
from src.views.playlist_panel     import PlaylistPanel
from src.views.player_panel       import PlayerPanel
from src.views.converter_panel    import ConverterPanel
from src.views.main_window        import MainWindow
from src.views.dsp_panel          import DSPPanel
from src.views.preferences_dialog import PreferencesDialog
from src.views.mini_player        import MiniPlayer

from src.controllers.playback_controller    import PlaybackController
from src.controllers.conversion_controller  import ConversionController
from src.controllers.library_coordinator    import LibraryCoordinator
from src.controllers.playlist_coordinator   import PlaylistCoordinator
from src.controllers.queue_coordinator      import QueueCoordinator

from src.utils.session_manager        import SessionManager
from src.utils.os_integration_manager import OSIntegrationManager
from src.utils.logger                 import get_logger

log = get_logger(__name__)


class MainController:

    def __init__(self):
        log.info("Inicializando MainController")

        # ── 1. Modelos ───────────────────────────────────────────────────
        # Detectar si es la primera ejecución ANTES de crear el DatabaseManager,
        # porque el propio constructor crea el archivo .db si no existe.
        # Usamos la misma lógica de path que usa DatabaseManager para no
        # duplicar conocimiento sobre dónde se guarda.
        import os, sys
        app_name = "AtaraxiaPlayer"
        if sys.platform == "win32":
            base_path = os.environ.get("APPDATA", os.path.expanduser("~"))
        else:
            base_path = os.environ.get("XDG_DATA_HOME",
                                       os.path.join(os.path.expanduser("~"), ".local", "share"))
        db_file = os.path.join(base_path, app_name, "ataraxia.db")
        self._is_first_run = not os.path.exists(db_file)

        self.db_manager      = DatabaseManager()
        self.db_maintenance = DatabaseMaintenance(self.db_manager)
        self.db_maintenance.run_scheduled_maintenance()

        # Nota: el bloqueo exclusivo del archivo .db lo gestiona el propio
        # DatabaseManager en su __init__ (vía src.utils.db_lock.DatabaseLock).
        # Se libera con self.db_manager.release_lock() durante el cierre
        # ordenado, sin necesidad de mantener una referencia separada aquí.

        # Si la BD está vacía (ya sea porque es la primera ejecución, porque
        # el usuario la borró manualmente, o porque se restauró una BD vacía),
        # limpiar la cover persistente en disco y la sesión guardada en
        # QSettings. Sin esto, la app mostraría la última carátula y la
        # última cola reproducida incluso con una BD que no las referencia,
        # dando lugar a "pistas fantasma".
        try:
            with self.db_manager.get_connection() as _c:
                _count = _c.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
            if _count == 0:
                import os as _os
                _cover = _os.path.join("assets", "current_cover.jpg")
                if _os.path.exists(_cover):
                    _os.remove(_cover)
                    log.info("Cover persistente limpiada (BD vacía al arrancar)")
                from PyQt6.QtCore import QSettings as _QS
                _qs = _QS("Ataraxia", "Player")
                _qs.remove("saved_queue")
                _qs.remove("saved_index")
                _qs.remove("active_playlist_id")
                log.info("Sesión de QSettings limpiada (BD vacía al arrancar)")
        except Exception:
            log.exception("No se pudo comprobar/limpiar estado inicial (continuando)")

        self.converter_model = MediaConverter()
        self.metadata_model  = MetadataManager()
        self.lyrics_model    = LyricsParser()
        self.playlist_model  = Playlist(self.db_manager)

        # ── 2. Vistas ────────────────────────────────────────────────────
        self.library_view   = LibraryPanel()
        self.playlist_view  = PlaylistPanel()
        self.player_view    = PlayerPanel()
        self.converter_view = ConverterPanel()
        self.dsp_view       = DSPPanel()

        # ── 3. Ventana principal ─────────────────────────────────────────
        self.main_window = MainWindow(
            self.library_view, self.playlist_view, self.player_view,
            self.converter_view, self.dsp_view
        )
        self.stats_view = self.main_window.stats_view

        # ── 4. Controladores de reproducción y conversión ────────────────
        self.playback_controller = PlaybackController(
            view=self.player_view,
            playlist_model=self.playlist_model,
            metadata_manager=self.metadata_model,
            lyrics_parser=self.lyrics_model,
            db_manager=self.db_manager,
        )
        self.playback_controller.track_played_halfway.connect(
            self.db_manager.increment_play_count
        )
        self.playback_controller.loop_mode_override.connect(
            self.player_view.set_loop_state
        )

        self.conversion_controller = ConversionController(
            view=self.converter_view,
            converter_model=self.converter_model,
        )

        # ── 5. Session Manager (persistencia entre ejecuciones) ──────────
        self.session = SessionManager(self.playback_controller, self.main_window)

        # ── 6. Integración con el SO (MPRIS/SMTC, tray, drag&drop) ───────
        self.os_integration = OSIntegrationManager(
            self.playback_controller, self.player_view, self.main_window
        )

        # ── 7. Coordinators de dominio ───────────────────────────────────
        self.library_coordinator = LibraryCoordinator(
            library_view=self.library_view,
            stats_view=self.stats_view,
            playback_controller=self.playback_controller,
            metadata_model=self.metadata_model,
            db_manager=self.db_manager,
            lyrics_model=self.lyrics_model,
            player_view=self.player_view,
            main_window=self.main_window,
            playlist_view=self.playlist_view,
            get_active_playlist_id=self.session.get_active_playlist_id,
        )

        self.playlist_coordinator = PlaylistCoordinator(
            playlist_view=self.playlist_view,
            library_view=self.library_view,
            playback_controller=self.playback_controller,
            playlist_model=self.playlist_model,
            db_manager=self.db_manager,
            main_window=self.main_window,
            get_active_playlist_id=self.session.get_active_playlist_id,
            set_active_playlist_id=self.session.set_active_playlist_id,
        )

        # Coordinador de la cola de reproducción (vista nueva: tab "Cola")
        self.queue_coordinator = QueueCoordinator(
            queue_panel=self.main_window.queue_panel,
            playback_controller=self.playback_controller,
            metadata_model=self.metadata_model,
            main_window=self.main_window,
        )

        # Cuando se reproduce desde la biblioteca, se desactiva la playlist activa
        self.library_coordinator.play_library_queue.connect(self._play_library_queue)
        # Cuando se modifica una playlist, puede afectar la cola en vivo
        self.library_coordinator.library_refreshed.connect(
            self.playlist_coordinator.load_playlists_from_db
        )

        # ── 8. Mini Player (PiP) ─────────────────────────────────────────
        self._setup_mini_player()

        # ── 9. Conexiones globales varias ────────────────────────────────
        self.main_window.open_preferences_requested.connect(self._open_preferences_dialog)
        self.dsp_view.dsp_settings_changed.connect(self.playback_controller.set_dsp_settings)
        self.converter_view.start_conversion_requested.connect(
            lambda _: self.main_window.show_status_message("Iniciando conversión en segundo plano…")
        )
        self.main_window.force_quit_requested.connect(self._hard_shutdown)
        self.playlist_view.edit_metadata_requested.connect(
            self.library_coordinator._open_metadata_editor
        )

        # ── 10. Carga inicial y restauración de sesión ───────────────────
        self.library_coordinator.initial_load()
        self.playlist_coordinator.load_playlists_from_db()

        # Tema
        saved_theme = self.session.get_saved_theme()
        self.main_window.set_theme(saved_theme)
        self.main_window.theme_changed.connect(self.session.save_theme)

        # Cola de reproducción anterior
        self.session.restore_playback_session(self.playlist_view)

    # ══════════════════════════════════════════════════════════════════════
    # MINI PLAYER (Picture-in-Picture)
    # ══════════════════════════════════════════════════════════════════════

    def _setup_mini_player(self):
        """Instancia y sincroniza el mini player con el panel principal."""
        self.mini_player = MiniPlayer()

        # A) Controles del mini → señales del panel principal
        self.mini_player.play_pause_requested.connect(self.player_view.play_toggled.emit)
        self.mini_player.next_requested.connect(self.player_view.next_clicked.emit)
        self.mini_player.prev_requested.connect(self.player_view.prev_clicked.emit)
        self.mini_player.seek_requested.connect(self.player_view.slider_moved.emit)
        self.mini_player.shuffle_requested.connect(self.player_view.btn_shuffle.click)
        self.mini_player.loop_requested.connect(self.player_view.btn_loop.click)

        # Apertura y cierre
        self.main_window.mini_player_requested.connect(self._show_mini_player)
        self.player_view.mini_player_requested.connect(self._show_mini_player)
        self.mini_player.close_requested.connect(self._hide_mini_player)
        self.main_window.theme_changed.connect(self.mini_player.update_theme)

        # Sincronización de estados entre player panel y mini
        self.player_view.shuffle_mode_changed.connect(self.mini_player.set_shuffle_state)
        self.player_view.loop_mode_changed.connect(self.mini_player.set_loop_state)
        self.playback_controller.loop_mode_override.connect(self.mini_player.set_loop_state)

        # Sincronización bidireccional mediante monkey-patching de métodos de player_view
        orig_play_state = self.player_view.set_play_state
        def sync_play_state(is_playing: bool):
            orig_play_state(is_playing)
            self.mini_player.set_play_state(is_playing)
        self.player_view.set_play_state = sync_play_state

        orig_progress = self.player_view.update_progress_bar
        def sync_progress(current: int, total: int):
            orig_progress(current, total)
            self.mini_player.update_progress(current, total)
        self.player_view.update_progress_bar = sync_progress

        orig_metadata = self.player_view.update_metadata
        def sync_metadata(title: str, artist: str, album: str):
            orig_metadata(title, artist, album)
            self.mini_player.update_metadata(title, artist, self.player_view.current_image_path)
        self.player_view.update_metadata = sync_metadata

        orig_cover = self.player_view.set_cover_image
        def sync_cover(image_path: str):
            orig_cover(image_path)
            title = self.player_view.lbl_title.text()
            artist_album = self.player_view.lbl_artist_album.text()
            artist = artist_album.split(' - ')[0] if ' - ' in artist_album else "Desconocido"
            self.mini_player.update_metadata(title, artist, image_path)
        self.player_view.set_cover_image = sync_cover

    def _show_mini_player(self):
        """Oculta la ventana principal y muestra el mini player sincronizado."""
        self.main_window.hide()

        title = self.player_view.lbl_title.text()
        artist_album = self.player_view.lbl_artist_album.text()
        artist = artist_album.split(' - ')[0] if ' - ' in artist_album else "Desconocido"

        self.mini_player.update_metadata(title, artist, self.player_view.current_image_path)
        self.mini_player.set_play_state(self.player_view.is_playing)
        self.mini_player.set_shuffle_state(self.player_view.is_shuffle)
        self.mini_player.set_loop_state(self.player_view.loop_state)
        self.mini_player.update_theme(self.main_window.btn_theme.isChecked())
        self.mini_player.show()

    def _hide_mini_player(self):
        """Oculta el mini player y restaura la ventana principal."""
        self.mini_player.hide()
        self.main_window.showNormal()
        self.main_window.activateWindow()

    # ══════════════════════════════════════════════════════════════════════
    # ORQUESTACIÓN DE REPRODUCCIÓN ENTRE BIBLIOTECA Y PLAYLISTS
    # ══════════════════════════════════════════════════════════════════════

    def _play_library_queue(self, queue: list, start_index: int):
        """Reproducir desde biblioteca → desactiva la playlist activa."""
        self.session.set_active_playlist_id(-1)
        self.playlist_view.set_active_playlist(-1)
        self.playback_controller.play_queue(queue, start_index)

    # ══════════════════════════════════════════════════════════════════════
    # APERTURA DE APLICACIÓN Y DIÁLOGOS
    # ══════════════════════════════════════════════════════════════════════

    def run(self):
        """Muestra la ventana y restaura el resaltado visual si había sesión."""
        self.main_window.show()
        if self.playback_controller.current_queue:
            self.library_coordinator._sync_visual_highlighting(
                self.playback_controller.current_index
            )
        # En primera ejecución, mostrar la bienvenida sobre la ventana ya visible.
        # Usamos QTimer.singleShot(0, ...) para que se muestre DESPUÉS de que
        # la ventana principal se haya renderizado al menos una vez.
        if self._is_first_run:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(150, lambda: self.main_window.show_welcome(first_run=True))

    def _open_preferences_dialog(self):
        dialog = PreferencesDialog(self.main_window)
        # El restore necesita orquestación a nivel del controller (liberar
        # el lock del archivo, ejecutar el reemplazo, y reiniciar la app).
        dialog.restore_requested.connect(self._handle_restore_request)
        dialog.exec()

    def _handle_restore_request(self, backup_path: str):
        """
        Orquesta el restore de forma SEGURA y ATÓMICA:

          1) Activar flag _restore_in_progress que BLOQUEA cualquier cierre
             durante el proceso. Si el usuario intenta cerrar (X, Alt+F4,
             menú Salir), closeEvent muestra un aviso y rechaza el cierre.
          2) Mostrar diálogo modal de progreso sin botón de cancelar.
          3) Pausar reproducción y liberar handles del motor de audio.
          4) Esperar a que el motor libere físicamente los handles.
          5) Liberar lock de la BD.
          6) Ejecutar el reemplazo del archivo (operación crítica).
          7) Limpiar cover y sesión guardada.
          8) Solo después de éxito completo: activar _is_restarting (para
             que el cierre no pregunte) y desactivar _restore_in_progress.
          9) Lanzar nueva instancia y cerrar la actual.

        Si cualquier paso falla, el flag _restore_in_progress se libera
        para que el usuario pueda cerrar la app manualmente.
        """
        log.info("Procesando solicitud de restore desde %s", backup_path)

        from PyQt6.QtWidgets import (
            QProgressDialog, QApplication, QMessageBox
        )
        from PyQt6.QtCore import Qt as _Qt, QEventLoop, QTimer, QUrl

        # ─ Paso 1: Activar escudo anti-cierre ───────────────────────────
        # _restore_in_progress hace que closeEvent rechace el cierre y
        # muestre un aviso al usuario. Esto es lo que previene la
        # corrupción cuando alguien intenta cerrar a mitad de proceso.
        self.main_window._restore_in_progress = True

        # ─ Paso 2: Diálogo modal de progreso (sin botón de cancelar) ────
        progress = QProgressDialog(
            "Restaurando base de datos…\n\nNo cierres la aplicación.",
            "",            # texto del botón cancelar vacío...
            0, 0,          # rango 0..0 = indeterminado
            self.main_window
        )
        progress.setWindowTitle("Restauración en curso")
        progress.setWindowModality(_Qt.WindowModality.ApplicationModal)
        progress.setCancelButton(None)   # ...y lo quitamos del todo
        progress.setMinimumDuration(0)
        progress.setWindowFlag(_Qt.WindowType.WindowCloseButtonHint, False)
        progress.setWindowFlag(_Qt.WindowType.CustomizeWindowHint, True)
        progress.setWindowFlag(_Qt.WindowType.WindowTitleHint, True)
        progress.show()
        QApplication.processEvents()

        def _abort_with_error(title: str, message: str):
            """Helper: limpia estado tras fallo y muestra error al usuario."""
            try:
                progress.close()
            except Exception:
                pass
            # Quitar escudo y notificar
            self.main_window._restore_in_progress = False
            QMessageBox.critical(self.main_window, title, message)

        try:
            # ─ Paso 3: Pausar reproducción ──────────────────────────────
            try:
                if hasattr(self, "playback_controller"):
                    self.playback_controller.media_player.stop()
                    # Limpiar source para forzar liberación de handles
                    self.playback_controller.media_player.setSource(QUrl())
            except Exception:
                log.exception("Error parando media_player (continuando)")

            QApplication.processEvents()

            # ─ Paso 4: Esperar a que el motor de audio libere recursos ──
            # QMediaPlayer en Windows mantiene handles brevemente tras
            # stop(). Sin esta espera, el restore puede fallar con
            # "archivo en uso" o, peor, dejar el .db en estado parcial.
            loop = QEventLoop()
            QTimer.singleShot(500, loop.quit)
            loop.exec()

            # ─ Paso 5: Borrar cover persistente y liberar lock ──────────
            import os
            try:
                cover_path = "assets/current_cover.jpg"
                if os.path.exists(cover_path):
                    os.remove(cover_path)
            except Exception:
                log.exception("No se pudo borrar la carátula persistente")

            try:
                self.db_manager.release_lock()
            except Exception:
                log.exception("Error liberando lock antes del restore")

            QApplication.processEvents()

            # ─ Paso 6: Restore real (PUNTO CRÍTICO) ─────────────────────
            # Si falla aquí, la BD original puede haber quedado en estado
            # intermedio. db_maintenance.restore_from_backup crea un
            # backup de emergencia ANTES de sobrescribir, por lo que es
            # recuperable manualmente.
            ok = self.db_maintenance.restore_from_backup(backup_path)

            if not ok:
                # Falló: reacquirir lock, notificar, NO reiniciar
                log.error("Restore falló — notificando al usuario")
                try:
                    self.db_manager._db_lock.acquire()
                except Exception:
                    pass
                _abort_with_error(
                    "Error al restaurar",
                    "No se pudo restaurar el respaldo. Tu base de datos "
                    "actual no fue modificada (o se conservó un backup de "
                    "emergencia). Revisa el log para más detalles."
                )
                return

            # ─ Paso 7: Limpiar sesión guardada ──────────────────────────
            try:
                self.session.clear_saved_session()
            except Exception:
                log.exception("Error limpiando sesión")

            # ─ Paso 8: Activar _is_restarting + desactivar escudo ───────
            # A partir de aquí el cierre es seguro y deseado.
            self.main_window._is_restarting = True
            self.main_window._restore_in_progress = False

            # ─ Paso 9: Lanzar nueva instancia ───────────────────────────
            import sys
            from PyQt6.QtCore import QProcess, QCoreApplication

            log.info("Reiniciando aplicación tras restore exitoso")
            if getattr(sys, "frozen", False):
                program = sys.executable
                restart_args = sys.argv[1:]
            else:
                program = sys.executable
                restart_args = sys.argv

            started = QProcess.startDetached(program, restart_args)
            if not started:
                # No pudimos lanzar la nueva instancia. La BD ya fue
                # restaurada con éxito, así que el usuario debe reiniciar
                # manualmente. No tratamos esto como error crítico.
                log.warning("startDetached falló — pidiendo al usuario que reinicie")
                progress.close()
                QMessageBox.information(
                    self.main_window,
                    "Restauración completada",
                    "La base de datos fue restaurada correctamente.\n\n"
                    "Por favor, cierra y vuelve a abrir Ataraxia Player "
                    "para ver los cambios."
                )
                return

            # ─ Paso 10: Cerrar instancia actual ─────────────────────────
            progress.close()
            QApplication.processEvents()

            self.main_window.close()
            QCoreApplication.quit()

        except Exception:
            log.exception("Fallo inesperado durante restore")
            _abort_with_error(
                "Error inesperado",
                "Ocurrió un error inesperado durante la restauración. "
                "Revisa el log para más detalles."
            )

    # ══════════════════════════════════════════════════════════════════════
    # CIERRE ORDENADO
    # ══════════════════════════════════════════════════════════════════════

    # Delegación: el IPC handler lo setea el main.py después de instanciar el controller
    @property
    def ipc_handler(self):
        return getattr(self, "_ipc_handler", None)

    @ipc_handler.setter
    def ipc_handler(self, value):
        self._ipc_handler = value

    def _play_dropped_file(self, filepath: str):
        """Punto de entrada público: drag&drop o archivo por línea de comandos."""
        self.os_integration.play_dropped_file(filepath)

    def _hard_shutdown(self):
        """Limpieza total al presionar 'Salir' desde el menú o la bandeja."""
        log.info("Hard shutdown solicitado")

        # Si la app está en proceso de reinicio (restore de BD), el cierre
        # ya fue desencadenado por QCoreApplication.quit() desde
        # _handle_restore_request. No repetimos la lógica de cleanup ni
        # llamamos de nuevo a main_window.close() para evitar el doble
        # closeEvent que mostraría el diálogo de "¿cerrar o segundo plano?".
        if getattr(self.main_window, '_is_restarting', False):
            log.info("Hard shutdown ignorado — la app está reiniciando")
            return

        # Guardado de sesión + cleanup del motor de audio
        self.session.save_and_cleanup()

        # Cleanup de OS (tray, sockets IPC)
        self.os_integration.hard_shutdown()

        # Mini player
        if hasattr(self, "mini_player"):
            self.mini_player.hide()
            self.mini_player.deleteLater()

        # IPC handler (socket)
        import os
        if self.ipc_handler and getattr(self.ipc_handler, "server", None):
            self.ipc_handler.server.close()
            self.ipc_handler.server.deleteLater()
            try:
                os.remove("/tmp/AtaraxiaPlayer_IPC")
            except Exception:
                pass

        # Liberar lock exclusivo de la BD. A partir de aquí el archivo
        # ataraxia.db queda manipulable externamente como antes de abrir.
        try:
            self.db_manager.release_lock()
        except Exception:
            log.exception("No se pudo liberar el lock de la BD")

        self.main_window.close()

        app = QApplication.instance()
        if app is not None:
            app.quit()
