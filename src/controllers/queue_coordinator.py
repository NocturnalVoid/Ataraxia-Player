# -*- coding: utf-8 -*-
"""
QueueCoordinator
────────────────
Conecta el QueuePanel con el PlaybackController:
  · Cuando la cola cambia en el motor → refresca la vista
  · Cuando el usuario manipula la vista → aplica al motor
  · Maneja saltos, eliminación, reordenamiento y limpieza
"""
import os

from PyQt6.QtCore import QObject

from src.utils.logger import get_logger

log = get_logger(__name__)


class QueueCoordinator(QObject):

    def __init__(self, queue_panel, playback_controller, metadata_model,
                 main_window):
        super().__init__()
        self.queue_panel         = queue_panel
        self.playback_controller = playback_controller
        self.metadata_model      = metadata_model
        self.main_window         = main_window

        self._connect_signals()
        # Primera sincronización (en caso de que haya cola restaurada de sesión)
        self._refresh_queue_view(
            list(self.playback_controller.current_queue),
            self.playback_controller.current_index,
        )

    def _connect_signals(self):
        # Motor → vista
        self.playback_controller.queue_changed.connect(self._refresh_queue_view)

        # Cuando cambia el track_index sin cambiar la cola, seguimos refrescando
        # para que la flecha ▶ se mueva al nuevo índice
        self.playback_controller.view.track_index_changed.connect(
            self._on_track_index_changed
        )

        # Vista → motor
        self.queue_panel.jump_to_index_requested.connect(self._jump_to_index)
        self.queue_panel.reorder_requested.connect(self._reorder)
        self.queue_panel.remove_at_requested.connect(self._remove_at)
        self.queue_panel.clear_queue_requested.connect(self._clear_queue)

    # ── Motor → vista ──────────────────────────────────────────────────

    def _refresh_queue_view(self, queue: list, current_index: int):
        # Wrapping: pasamos un callable para que el QueuePanel pueda pedir
        # metadatos de cada pista sin acoplarse al MetadataManager directamente
        self.queue_panel.update_queue(
            queue, current_index, metadata_provider=self._get_metadata_cached
        )

    def _on_track_index_changed(self, new_index: int):
        # Cola no cambió, solo el índice — refrescamos para actualizar la marca ▶
        self._refresh_queue_view(
            list(self.playback_controller.current_queue),
            new_index,
        )

    # ── Cache de metadatos (para evitar leer tags en cada repintado) ───

    def _get_metadata_cached(self, filepath: str) -> dict:
        cache = getattr(self, "_meta_cache", None)
        if cache is None:
            cache = {}
            self._meta_cache = cache
        if filepath in cache:
            return cache[filepath]
        try:
            meta = self.metadata_model.extract_metadata(filepath) or {}
            cache[filepath] = meta
            # Evitar crecimiento descontrolado
            if len(cache) > 500:
                cache.pop(next(iter(cache)))
            return meta
        except Exception:
            return {}

    # ── Vista → motor ──────────────────────────────────────────────────

    def _jump_to_index(self, new_index: int):
        pc = self.playback_controller
        if not (0 <= new_index < len(pc.current_queue)):
            return
        pc.current_index = new_index
        if pc.is_shuffle:
            # Alinear el puntero de shuffle al nuevo índice lineal
            if new_index in pc.shuffle_sequence:
                pc.shuffle_index = pc.shuffle_sequence.index(new_index)
            else:
                pc._generate_shuffle_sequence(new_index)
        pc.view.track_index_changed.emit(new_index)
        pc.load_track(pc.current_queue[new_index], auto_play=True)

    def _reorder(self, new_paths: list):
        self.playback_controller.reorder_queue(new_paths)

    def _remove_at(self, index: int):
        self.playback_controller.remove_from_queue(index)

    def _clear_queue(self):
        # Solo vaciar si hay más de una pista (conservamos la actual)
        queue = self.playback_controller.current_queue
        if len(queue) <= 1:
            self.main_window.show_status_message("La cola ya está en su mínimo.")
            return
        self.playback_controller.clear_queue_except_current()
        self.main_window.show_status_message("Cola limpiada.")
