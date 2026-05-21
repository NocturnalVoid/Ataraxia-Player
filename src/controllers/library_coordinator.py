# -*- coding: utf-8 -*-
"""
LibraryCoordinator
──────────────────
Gestiona el dominio de la **biblioteca musical**:

  · Escaneo de carpetas (indexado + ReplayGain + carátulas automáticas)
  · Cambio entre vistas (Canciones, Álbumes, Artistas, Género, Año)
  · Búsqueda, limpieza de archivos fantasma, edición de metadatos
  · Descarga JIT de carátulas para la pista actual
  · Descarga de letras (manual vía botón + automática opt-in)
  · Resaltado visual sincronizado con la reproducción
  · Estadísticas de escucha

Se inyecta con los modelos y vistas que necesita. Todas las señales se conectan
desde aquí (no desde el MainController), y toda la lógica de biblioteca vive
exclusivamente en este archivo.
"""
import os

from PyQt6.QtCore import QObject, QThread, pyqtSignal, QSettings
from PyQt6.QtWidgets import QMessageBox

from src.utils.logger import get_logger

log = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Hilos de background
# ══════════════════════════════════════════════════════════════════════════

class DatabaseScannerThread(QThread):
    """Escanea una carpeta, la indexa en SQLite y aplica ReplayGain/carátulas."""
    scan_success = pyqtSignal()

    def __init__(self, folder_path, metadata_model, db_manager):
        super().__init__()
        self.folder_path    = folder_path
        self.metadata_model = metadata_model
        self.db_manager     = db_manager

    def run(self):
        self.metadata_model.scan_directory_to_db(self.folder_path, self.db_manager)
        # Señal intermedia: la UI puede refrescar la biblioteca casi al instante
        self.scan_success.emit()

        # Post-procesamiento: ReplayGain + carátulas API (opt-in)
        settings = QSettings("Ataraxia", "Player")
        auto_cover = settings.value("enable_auto_cover", False, type=bool)
        api_url    = settings.value("cover_api_url", "")
        do_rg      = settings.value("enable_normalization", True, type=bool)

        try:
            all_files = self.db_manager.get_all_filepaths()
            for fp in all_files:
                if not os.path.exists(fp):
                    continue

                # Autocompletado de carátulas
                if auto_cover and api_url:
                    cover = self.metadata_model.extract_cover_art(fp)
                    if cover == "assets/default_cover.png":
                        meta = self.metadata_model.extract_metadata(fp)
                        try:
                            self.metadata_model.fetch_and_embed_cover(
                                fp, meta.get("title", ""), meta.get("artist", ""), api_url
                            )
                        except Exception:
                            log.exception("Fallo descargando carátula para %s", fp)

                # Cálculo de ReplayGain si aún no se ha hecho
                if do_rg:
                    gain = self.db_manager.get_replay_gain(fp)
                    if gain == 0.0:
                        try:
                            self.metadata_model.compute_replay_gain(fp, self.db_manager)
                        except Exception:
                            log.exception("Fallo calculando ReplayGain para %s", fp)
        except Exception:
            log.exception("Error en post-procesamiento del escaneo")

        # Señal final: hay más datos refrescables (carátulas descargadas)
        self.scan_success.emit()
        log.info("Escaneo de biblioteca completado")


class CoverDownloaderThread(QThread):
    """Descarga carátula en tiempo real cuando se reproduce una pista sin ella."""
    cover_downloaded = pyqtSignal(str)

    def __init__(self, filepath, title, artist, api_url, metadata_manager):
        super().__init__()
        self.filepath         = filepath
        self.title            = title
        self.artist           = artist
        self.api_url          = api_url
        self.metadata_manager = metadata_manager

    def run(self):
        try:
            ok = self.metadata_manager.fetch_and_embed_cover(
                self.filepath, self.title, self.artist, self.api_url
            )
            if ok:
                self.cover_downloaded.emit(self.filepath)
        except Exception:
            log.exception("CoverDownloaderThread falló para %s", self.filepath)


class LyricsDownloaderThread(QThread):
    """
    Descarga letras desde lrclib.net sin bloquear la UI.
    Emite lyrics_ready(status, content, is_synced, filepath) donde
    status ∈ {"found", "not_found", "error"}.
    """
    lyrics_ready = pyqtSignal(str, str, bool, str)

    def __init__(self, filepath, title, artist, album, duration):
        super().__init__()
        self.filepath = filepath
        self.title    = title
        self.artist   = artist
        self.album    = album
        self.duration = duration

    def run(self):
        try:
            from src.models.lyrics_api import LyricsApiClient
            client = LyricsApiClient()
            result = client.fetch(self.title, self.artist, self.album, self.duration)
            self.lyrics_ready.emit(
                result.status, result.content, result.is_synced, self.filepath
            )
        except Exception:
            log.exception("LyricsDownloaderThread falló para %s", self.filepath)
            self.lyrics_ready.emit("error", "", False, self.filepath)


# ══════════════════════════════════════════════════════════════════════════
# Coordinator
# ══════════════════════════════════════════════════════════════════════════

class LibraryCoordinator(QObject):

    # Señales que el MainController puede conectar para reaccionar
    library_refreshed   = pyqtSignal()       # la BD se actualizó → refrescar dependientes
    play_library_queue  = pyqtSignal(list, int)   # queue, start_index

    def __init__(self, library_view, stats_view, playback_controller,
                 metadata_model, db_manager, lyrics_model, player_view,
                 main_window, playlist_view, get_active_playlist_id):
        super().__init__()
        self.library_view        = library_view
        self.stats_view          = stats_view
        self.playback_controller = playback_controller
        self.metadata_model      = metadata_model
        self.db_manager          = db_manager
        self.lyrics_model        = lyrics_model
        self.player_view         = player_view
        self.main_window         = main_window
        self.playlist_view       = playlist_view
        self._get_active_playlist_id = get_active_playlist_id
        self.settings            = QSettings("Ataraxia", "Player")

        # Hilos background (protegidos de garbage collection)
        self._jit_cover_threads  = []
        self._lyrics_threads     = []
        self._scanner_thread     = None
        self._refresh_thread     = None
        self._refresh_queue      = []
        self._refresh_total      = 0
        self._refresh_done       = 0

        self._connect_signals()

    # ── Conexiones de señales ────────────────────────────────────────────

    def _connect_signals(self):
        # Librería
        self.library_view.add_folder_requested.connect(self._start_scanning)
        self.library_view.clean_library_requested.connect(self._clean_library)
        self.library_view.refresh_library_requested.connect(self._refresh_library)
        self.library_view.remove_song_requested.connect(self._remove_song_from_library)
        self.library_view.edit_metadata_requested.connect(self._open_metadata_editor)
        self.library_view.track_selected.connect(self._play_library_queue)
        self.library_view.search_query_changed.connect(self._handle_library_search)
        self.library_view.library_view_requested.connect(self._on_library_view_changed)

        # Cola (desde biblioteca)
        self.library_view.play_next_requested.connect(
            self.playback_controller.insert_after_current
        )
        self.library_view.add_to_queue_requested.connect(
            self.playback_controller.append_to_queue
        )
        self.library_view.toggle_favorite_requested.connect(self._toggle_favorite_by_path)

        # Cola (desde playlists) — las conectamos aquí para centralizar
        self.playlist_view.play_next_requested.connect(
            self.playback_controller.insert_after_current
        )
        self.playlist_view.add_to_queue_requested.connect(
            self.playback_controller.append_to_queue
        )
        self.playlist_view.toggle_favorite_requested.connect(self._toggle_favorite_by_path)

        # Player (letras, resaltado, favoritos)
        self.player_view.track_index_changed.connect(self._sync_visual_highlighting)
        self.player_view.fetch_lyrics_requested.connect(self._fetch_lyrics_now)
        self.player_view.favorite_toggled.connect(self._on_favorite_toggled)

        # Stats
        self.stats_view.btn_refresh.clicked.connect(self._refresh_stats)

    # ── API pública ──────────────────────────────────────────────────────

    def initial_load(self):
        """Carga la biblioteca al arranque y refresca estadísticas."""
        self._load_library_from_db()
        self._refresh_stats()

    # ── Escaneo ──────────────────────────────────────────────────────────

    def _start_scanning(self, folder_path: str):
        # Registrar la carpeta en la BD para que pueda ser reescaneada
        # más adelante con el botón "Actualizar biblioteca"
        try:
            self.db_manager.add_library_folder(folder_path)
        except Exception:
            log.exception("No se pudo registrar la carpeta %s en library_folders", folder_path)

        self.main_window.show_status_message(f"Escaneando: {folder_path}...")
        self._scanner_thread = DatabaseScannerThread(
            folder_path, self.metadata_model, self.db_manager
        )
        self._scanner_thread.scan_success.connect(self._on_scan_finished)
        self._scanner_thread.start()

    def _refresh_library(self):
        """
        Reescanea todas las carpetas raíz registradas para detectar
        archivos nuevos o cambios. Si no hay ninguna registrada (por
        ejemplo, biblioteca vacía o BD heredada de una versión vieja),
        avisa al usuario en lugar de no hacer nada.
        """
        folders = []
        try:
            folders = self.db_manager.get_library_folders()
        except Exception:
            log.exception("Fallo leyendo library_folders")

        if not folders:
            self.main_window.show_status_message(
                "No hay carpetas para actualizar. Usa «Agregar Carpeta» primero."
            )
            return

        # Encadenamos los escaneos: cada uno lanza el siguiente al terminar.
        # Esto evita lanzar N hilos simultáneos que se peleen por la BD.
        self._refresh_queue = list(folders)
        self._refresh_total = len(folders)
        self._refresh_done = 0
        self._refresh_next_folder()

    def _refresh_next_folder(self):
        if not self._refresh_queue:
            # Terminamos todo el ciclo
            self.main_window.show_status_message(
                f"Biblioteca actualizada ({self._refresh_total} carpeta(s))."
            )
            self._load_library_from_db()
            self.library_refreshed.emit()
            return

        next_folder = self._refresh_queue.pop(0)
        self._refresh_done += 1
        self.main_window.show_status_message(
            f"Actualizando ({self._refresh_done}/{self._refresh_total}): {next_folder}..."
        )
        self._refresh_thread = DatabaseScannerThread(
            next_folder, self.metadata_model, self.db_manager
        )
        self._refresh_thread.scan_success.connect(self._refresh_next_folder)
        self._refresh_thread.start()

    def _on_scan_finished(self):
        self._load_library_from_db()
        self.main_window.show_status_message("Base de datos actualizada correctamente.")
        self.library_refreshed.emit()

    # ── Vistas y búsqueda ────────────────────────────────────────────────

    def _load_library_from_db(self):
        self._on_library_view_changed(self.library_view._current_mode)

    def _on_library_view_changed(self, mode: str):
        from src.views.library_panel import (VIEW_SONGS, VIEW_ALBUMS,
                                              VIEW_ARTISTS, VIEW_GENRE, VIEW_YEAR)
        if mode == VIEW_ARTISTS:
            data = self.metadata_model.get_library_tree(self.db_manager)
        elif mode == VIEW_SONGS:
            data = self.db_manager.get_songs_flat()
        elif mode == VIEW_ALBUMS:
            data = self.db_manager.get_songs_by_album()
        elif mode == VIEW_GENRE:
            data = self.db_manager.get_songs_by_genre()
        elif mode == VIEW_YEAR:
            data = self.db_manager.get_songs_by_year()
        else:
            data = self.metadata_model.get_library_tree(self.db_manager)

        self.library_view.populate_library(data, mode)

    def _handle_library_search(self, query: str):
        if not query.strip():
            self._load_library_from_db()
        else:
            filtered_data = self.db_manager.search_tracks(query)
            self.library_view.populate_tree(filtered_data)
            self.library_view.tree_view.expandAll()

    # ── Reproducción desde biblioteca ────────────────────────────────────

    def _play_library_queue(self, queue: list, start_index: int):
        """Reenvía la intención al MainController vía señal (él decide cómo integrar)."""
        self.play_library_queue.emit(queue, start_index)

    # ── Limpieza y eliminación ───────────────────────────────────────────

    def _clean_library(self):
        paths = self.db_manager.get_all_filepaths()
        removed = 0
        for fp in paths:
            if not os.path.exists(fp):
                self.db_manager.remove_song(fp)
                removed += 1

        if removed > 0:
            self._load_library_from_db()
            self.library_refreshed.emit()
            self.main_window.show_status_message(
                f"Limpieza completada: {removed} canciones fantasma eliminadas."
            )
        else:
            self.main_window.show_status_message(
                "Biblioteca en orden: no hay archivos fantasma."
            )

    def _remove_song_from_library(self, filepath: str):
        skip = self.settings.value("skip_song_remove_warning", False, type=bool)

        if not skip:
            from PyQt6.QtWidgets import QCheckBox
            filename = os.path.basename(filepath)
            msg = QMessageBox(self.main_window)
            msg.setWindowTitle("Eliminar canción")
            msg.setText(f"¿Eliminar '{filename}' de la biblioteca?")
            msg.setInformativeText("El archivo físico NO se borra del disco.")
            msg.setIcon(QMessageBox.Icon.Question)
            btn_yes = msg.addButton("Eliminar", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
            cb = QCheckBox("No volver a preguntar")
            msg.setCheckBox(cb)
            msg.exec()

            if msg.clickedButton() != btn_yes:
                return
            if cb.isChecked():
                self.settings.setValue("skip_song_remove_warning", True)

        self.db_manager.remove_song(filepath)
        self._load_library_from_db()
        self.library_refreshed.emit()
        self.main_window.show_status_message("Canción eliminada de la biblioteca.")

    # ── Editor de metadatos ──────────────────────────────────────────────

    def _open_metadata_editor(self, filepath: str):
        """
        Abre el diálogo de edición de metadatos extendido. Persiste cambios al
        archivo, refresca la BD, y si la canción está sonando, refresca el panel.
        """
        from src.views.metadata_dialog import MetadataDialog
        current_meta  = self.metadata_model.extract_metadata(filepath)
        current_cover = self.metadata_model.extract_cover_art(filepath)

        dialog = MetadataDialog(self.main_window, current_meta, current_cover)
        if not dialog.exec():
            return

        new_data = dialog.get_new_data()

        try:
            # ── 1) Guardar campos de texto en el archivo ────────────────
            self.metadata_model.save_metadata(filepath, new_data)

            # ── 2) Procesar la carátula según la acción elegida ─────────
            action = new_data.get("cover_action", "keep")
            if action == "replace":
                cover_src = new_data.get("cover_path", "")
                if cover_src and os.path.exists(cover_src):
                    try:
                        with open(cover_src, "rb") as f:
                            img_bytes = f.read()
                        # Reutilizamos el helper que ya sabe inyectar en todos
                        # los formatos soportados (MP3, FLAC, OPUS, OGG, M4A)
                        self.metadata_model._embed_image_to_file(filepath, img_bytes)
                    except Exception:
                        log.exception("No se pudo aplicar la carátula nueva a %s", filepath)
            elif action == "remove":
                try:
                    self.metadata_model.remove_cover_from_file(filepath)
                except Exception:
                    log.exception("No se pudo quitar la carátula de %s", filepath)
            # action == "keep" → no hacer nada con la carátula

            # ── 3) Reflejar cambios en la BD ────────────────────────────
            try:
                track_value = int(self._parse_first_number(new_data.get("tracknumber")) or 0)
            except (TypeError, ValueError):
                track_value = 0
            try:
                year_value = int(new_data.get("year") or 0)
            except (TypeError, ValueError):
                year_value = 0

            self.db_manager.update_song_metadata(
                filepath,
                new_data.get("title",  current_meta.get("title", "")),
                new_data.get("artist", current_meta.get("artist", "")),
                new_data.get("album",  current_meta.get("album", "")),
                track_number=track_value,
                genre=new_data.get("genre", current_meta.get("genre", "")),
                year=year_value,
            )

            # ── 4) Refrescar UI ─────────────────────────────────────────
            self._reset_player_panel_if_active(filepath)
            self._load_library_from_db()
            self.library_refreshed.emit()
            self.main_window.show_status_message("Metadatos actualizados.")
        except Exception:
            log.exception("Fallo guardando metadatos de %s", filepath)
            self.main_window.show_status_message(
                "Error al guardar metadatos. Revisa el log."
            )

    @staticmethod
    def _parse_first_number(value) -> int:
        """Extrae el primer número de un string como '5/12' o '5'. Devuelve 0 si no se puede."""
        if value is None:
            return 0
        try:
            s = str(value).strip()
            if not s:
                return 0
            if '/' in s:
                s = s.split('/', 1)[0]
            return int(s)
        except (TypeError, ValueError):
            return 0


    def _reset_player_panel_if_active(self, edited_filepath: str):
        """
        Si la canción que se acaba de editar es la que está cargada en el
        reproductor (sonando o pausada), refresca el panel con los metadatos
        recién guardados y la nueva carátula (si la hay). La reproducción
        NO se interrumpe.
        """
        queue = self.playback_controller.current_queue
        index = self.playback_controller.current_index
        if not queue or index < 0 or index >= len(queue):
            return

        try:
            same_path = os.path.normcase(os.path.abspath(queue[index])) == \
                        os.path.normcase(os.path.abspath(edited_filepath))
        except Exception:
            same_path = (queue[index] == edited_filepath)

        if not same_path:
            return

        # Releer metadatos y carátula desde el archivo (ya están persistidos)
        try:
            new_meta = self.metadata_model.extract_metadata(edited_filepath)
            new_cover = self.metadata_model.extract_cover_art(edited_filepath)
        except Exception:
            log.exception("No se pudieron releer metadatos de %s tras edición",
                          edited_filepath)
            return

        self.player_view.update_metadata(
            new_meta.get("title", ""),
            new_meta.get("artist", ""),
            new_meta.get("album", ""),
        )
        self.player_view.set_cover_image(new_cover)


    # ── Resaltado visual sincronizado ────────────────────────────────────

    def _sync_visual_highlighting(self, index: int):
        # Highlight en el panel de playlist si hay una playlist activa,
        # limpiarlo si la reproducción viene de biblioteca directa
        if self._get_active_playlist_id() != -1:
            self.playlist_view.highlight_song(index)
        else:
            self.playlist_view.highlight_song(-1)

        # Highlight en la biblioteca + JIT covers/lyrics + estado del corazón
        queue = self.playback_controller.current_queue
        if queue and 0 <= index < len(queue):
            filepath = queue[index]
            self.library_view.highlight_song(filepath)
            self._check_and_fetch_cover_jit(filepath)
            # Reset del botón de letras al estado neutro
            self.player_view.set_fetch_lyrics_state("idle")
            # Auto-descarga de letras si está activa
            self._check_and_fetch_lyrics_jit(filepath)
            # Refrescar el corazón según el estado persistido de la nueva pista
            is_fav = self.db_manager.is_favorite(filepath)
            self.player_view.set_favorite_state(is_fav)
            self.player_view.show_favorite_button(True)
        else:
            self.player_view.show_favorite_button(False)

    def _on_favorite_toggled(self, is_favorite: bool):
        """Persiste el nuevo estado de favorito de la pista actual."""
        info = self._current_track_info()
        if info is None:
            return
        filepath = info[0]
        ok = self.db_manager.set_favorite(filepath, is_favorite)
        if not ok:
            log.warning("set_favorite falló: pista no está en BD (%s)", filepath)
            return
        self.main_window.show_status_message(
            "Añadido a favoritos ♥" if is_favorite else "Quitado de favoritos"
        )
        self._refresh_favorites_view_if_active()

    def _toggle_favorite_by_path(self, filepath: str):
        """
        Alterna el favorito de una pista específica (usado desde menús contextuales).
        Sincroniza el corazón del PlayerPanel si la pista toggeada es la actual.
        """
        new_state = not self.db_manager.is_favorite(filepath)
        ok = self.db_manager.set_favorite(filepath, new_state)
        if not ok:
            log.warning("toggle_favorite_by_path: pista no está en BD (%s)", filepath)
            self.main_window.show_status_message(
                "Esa pista no está en la biblioteca."
            )
            return

        # Si es la pista que está sonando, actualizar el corazón visual
        info = self._current_track_info()
        if info is not None and info[0] == filepath:
            self.player_view.set_favorite_state(new_state)

        self.main_window.show_status_message(
            "Añadido a favoritos ♥" if new_state else "Quitado de favoritos"
        )
        self._refresh_favorites_view_if_active()

    def _refresh_favorites_view_if_active(self):
        """Si el usuario está viendo la smart playlist 'Favoritos', la recarga."""
        if self.playlist_view.current_playlist_id == -4:
            songs = self.db_manager.get_favorite_songs()
            self.playlist_view.update_songs(songs)

    # ── JIT Covers ───────────────────────────────────────────────────────

    def _check_and_fetch_cover_jit(self, filepath: str):
        auto_cover = self.settings.value("enable_auto_cover", False, type=bool)
        api_url    = self.settings.value("cover_api_url", "")
        if not auto_cover or not api_url:
            return
        # Si extract_cover_art devuelve algo distinto al placeholder (es decir,
        # la canción YA tiene carátula incrustada), no descargamos.
        # Detectamos el placeholder por nombre de archivo, no por path literal:
        # en Windows el separador puede ser "\" pero en otros sitios "/".
        cover_now = self.metadata_model.extract_cover_art(filepath) or ""
        if "default_cover" not in os.path.basename(cover_now):
            return

        meta = self.metadata_model.extract_metadata(filepath)
        title  = meta.get("title", "")
        artist = meta.get("artist", "")

        # Limpiar hilos muertos
        self._jit_cover_threads = [t for t in self._jit_cover_threads if t.isRunning()]

        thread = CoverDownloaderThread(filepath, title, artist, api_url, self.metadata_model)
        thread.cover_downloaded.connect(self._on_jit_cover_downloaded)
        self._jit_cover_threads.append(thread)
        thread.start()

    def _on_jit_cover_downloaded(self, filepath: str):
        queue = self.playback_controller.current_queue
        idx   = self.playback_controller.current_index
        if queue and 0 <= idx < len(queue) and queue[idx] == filepath:
            cover = self.metadata_model.extract_cover_art(filepath)
            self.player_view.set_cover_image(cover)

    # ── Letras (manual + JIT) ────────────────────────────────────────────

    def _current_track_info(self):
        queue = self.playback_controller.current_queue
        idx   = self.playback_controller.current_index
        if not queue or not (0 <= idx < len(queue)):
            return None
        filepath = queue[idx]
        meta = self.metadata_model.extract_metadata(filepath) or {}
        return (
            filepath,
            (meta.get("title") or "").strip(),
            (meta.get("artist") or "").strip(),
            (meta.get("album") or "").strip(),
            int(meta.get("duration", 0) or 0),
        )

    def _fetch_lyrics_now(self):
        info = self._current_track_info()
        if info is None:
            self.main_window.show_status_message("No hay ninguna pista cargada.")
            return

        filepath, title, artist, album, duration = info
        if not title or not artist:
            self.main_window.show_status_message(
                "Faltan metadatos (título/artista) para buscar letras."
            )
            return

        if not self._confirm_lyrics_first_use():
            return

        self._lyrics_threads = [t for t in self._lyrics_threads if t.isRunning()]
        self.player_view.set_fetch_lyrics_state("loading")
        self.main_window.show_status_message(f"Buscando letras de '{title}'…")

        thread = LyricsDownloaderThread(filepath, title, artist, album, duration)
        thread.lyrics_ready.connect(self._on_lyrics_downloaded)
        self._lyrics_threads.append(thread)
        thread.start()

    def _confirm_lyrics_first_use(self) -> bool:
        if self.settings.value("skip_lyrics_first_use_dialog", False, type=bool):
            return True

        from PyQt6.QtWidgets import QCheckBox
        box = QMessageBox(self.main_window)
        box.setWindowTitle("Búsqueda de letras en línea")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(
            "Ataraxia consultará a lrclib.net — un servicio open-source y gratuito — "
            "enviando el título y artista de la canción para obtener las letras.\n\n"
            "Los resultados se guardan en una caché local temporal (máximo 200 entradas, "
            "rotación automática). Puedes limpiar la caché cuando quieras desde Preferencias.\n\n"
            "¿Deseas continuar?"
        )
        btn_yes = box.addButton("Buscar", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_yes)

        cb = QCheckBox("No volver a mostrar este mensaje")
        box.setCheckBox(cb)
        box.exec()

        if box.clickedButton() != btn_yes:
            return False
        if cb.isChecked():
            self.settings.setValue("skip_lyrics_first_use_dialog", True)
        return True

    def _on_lyrics_downloaded(self, status: str, content: str,
                              is_synced: bool, filepath: str):
        info = self._current_track_info()
        if info is None or info[0] != filepath:
            return

        if status == "found":
            self.lyrics_model.load_from_text(content, is_synced=is_synced)
            pos_ms = self.playback_controller.media_player.position()
            lines, idx, synced_flag = self.lyrics_model.get_state_at_time(pos_ms)
            self.player_view.update_lyrics_karaoke(lines, idx, synced_flag)
            self.player_view.set_fetch_lyrics_state("success")
            self.main_window.show_status_message(
                "Letras cargadas" + (" (sincronizadas)" if is_synced else " (texto plano)")
            )
        elif status == "not_found":
            self.player_view.set_fetch_lyrics_state("not_found")
            self.main_window.show_status_message("No se encontraron letras para esta canción.")
        else:
            self.player_view.set_fetch_lyrics_state("error")
            self.main_window.show_status_message("No se pudo conectar con el servicio de letras.")

    def _check_and_fetch_lyrics_jit(self, filepath: str):
        """
        Auto-descarga letras desde lrclib.net si:
          - La opción "enable_auto_lyrics" está activa en Preferencias
          - La canción no tiene archivos .lrc/.srt/.txt locales al lado
          - Hay metadatos mínimos (title + artist) para consultar la API

        Histórico: antes había un short-circuit "if self.lyrics_model.lines: return"
        que pretendía evitar descargas redundantes, pero introdujo un bug. Como
        track_index_changed se emite ANTES de que load_track limpie el modelo
        de letras (ver playback_controller, líneas 269/443/449), el modelo aún
        contenía las letras de la canción anterior cuando se ejecutaba este check,
        cancelando la descarga para casi todas las canciones de la sesión.

        La forma correcta es comprobar si EL ARCHIVO de la canción actual tiene
        letras locales asociadas — eso sí cubre el caso de "no descargar si ya
        hay un .lrc al lado del .mp3" sin depender del estado transitorio del
        modelo.
        """
        if not self.settings.value("enable_auto_lyrics", False, type=bool):
            return

        # Si hay archivo de letras local junto al audio, no descargar.
        # Misma prioridad que usa lyrics_parser.load_file: .lrc → .srt → .txt
        base = os.path.splitext(filepath)[0]
        if any(os.path.exists(f"{base}{ext}") for ext in (".lrc", ".srt", ".txt")):
            return

        meta = self.metadata_model.extract_metadata(filepath) or {}
        title    = (meta.get("title")  or "").strip()
        artist   = (meta.get("artist") or "").strip()
        album    = (meta.get("album")  or "").strip()
        duration = int(meta.get("duration", 0) or 0)
        if not title or not artist:
            return

        self._lyrics_threads = [t for t in self._lyrics_threads if t.isRunning()]
        thread = LyricsDownloaderThread(filepath, title, artist, album, duration)
        thread.lyrics_ready.connect(self._on_lyrics_downloaded)
        self._lyrics_threads.append(thread)
        thread.start()

    # ── Stats ────────────────────────────────────────────────────────────

    def _refresh_stats(self):
        try:
            top = self.db_manager.get_top_played(limit=10)
            self.stats_view.populate_table(top)
        except Exception:
            log.exception("Error al refrescar estadísticas")
