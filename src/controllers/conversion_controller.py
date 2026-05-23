# -*- coding: utf-8 -*-
from PyQt6.QtCore import QObject

class ConversionController(QObject):
    """
    Controlador para el panel de conversión. 
    Conecta las señales visuales de la UI con el hilo de ejecución de FFmpeg.
    """
    def __init__(self, view, converter_model):
        super().__init__()
        self.view = view
        self.model = converter_model

        # 1. Escuchar a la vista
        self.view.start_conversion_requested.connect(self._on_start_requested)
        self.view.cancel_conversion_requested.connect(self._on_cancel_requested)

    def _on_start_requested(self, conversion_data: dict):
        """Inicia el proceso y conecta las señales dinámicas del hilo."""
        self.view.show_conversion_started()
        
        self.model.start_worker(conversion_data)
        
        # Conectar las respuestas del hilo de vuelta a la vista
        self.model.worker.progress_updated.connect(self.view.update_progress_bar)
        self.model.worker.finished.connect(self._on_conversion_success)
        self.model.worker.error.connect(self._on_conversion_error)

    def _on_cancel_requested(self):
        """Envía la orden de abortar al modelo."""
        self.model.cancel_worker()

    def _on_conversion_success(self, msg: str):
        self.view.show_conversion_finished(msg)

    def _on_conversion_error(self, err_msg: str):
        self.view.reset_form()
        self.view.show_error_message(err_msg)