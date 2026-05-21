# -*- coding: utf-8 -*-
"""
QueuePanel
──────────
Vista de la cola de reproducción actual:
  · Lista de pistas con título + artista; la pista actual resaltada
  · Drag & drop interno para reordenar
  · Clic derecho: eliminar, limpiar cola, reproducir ahora
  · Doble clic: saltar directamente a esa pista
"""
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QAbstractItemView, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QAction, QColor, QBrush


class QueuePanel(QWidget):
    """Panel visible de la cola de reproducción."""

    # Emisión: el usuario hizo doble clic para saltar a una pista específica
    jump_to_index_requested = pyqtSignal(int)
    # Emisión: el usuario reordenó la cola con drag&drop
    reorder_requested = pyqtSignal(list)
    # Emisión: el usuario pidió borrar la pista en el índice dado
    remove_at_requested = pyqtSignal(int)
    # Emisión: el usuario pidió limpiar toda la cola (excepto actual)
    clear_queue_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._current_index = -1
        # Mapa para saber cuál filepath corresponde a cuál posición en el widget,
        # porque el drag&drop reordena internamente la QListWidget
        self._filepath_at = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header: contador + botón limpiar
        header = QHBoxLayout()
        self.lbl_count = QLabel("Cola vacía")
        self.lbl_count.setStyleSheet("font-weight: bold;")
        header.addWidget(self.lbl_count)
        header.addStretch()

        self.btn_clear = QPushButton(" Limpiar cola")
        self.btn_clear.setIcon(QIcon("assets/library/trash.svg"))
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setToolTip("Vaciar cola (mantiene la canción actual)")
        self.btn_clear.clicked.connect(self.clear_queue_requested.emit)
        header.addWidget(self.btn_clear)

        layout.addLayout(header)

        # Lista principal con drag&drop interno
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._on_double_clicked)
        # Cuando el usuario suelta después de drag&drop
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)

        layout.addWidget(self.list_widget)

    # ── API pública ─────────────────────────────────────────────────────

    def update_queue(self, filepaths: list, current_index: int,
                     metadata_provider=None):
        """
        Rellena la cola. `metadata_provider` es una función
        (filepath) -> dict con claves 'title', 'artist', para no acoplar
        este panel al MetadataManager.
        """
        self._current_index = current_index
        self._filepath_at = list(filepaths)

        # Bloquear señales de rowsMoved mientras repopulamos
        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        for i, fp in enumerate(filepaths):
            display = self._format_row(fp, i, metadata_provider)
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, fp)
            # Tooltip completo con ruta
            item.setToolTip(fp)
            self._apply_row_style(item, i)
            self.list_widget.addItem(item)

        self.list_widget.blockSignals(False)

        n = len(filepaths)
        if n == 0:
            self.lbl_count.setText("Cola vacía")
        elif n == 1:
            self.lbl_count.setText("1 pista en cola")
        else:
            self.lbl_count.setText(f"{n} pistas en cola  ·  pista {current_index + 1} de {n}")

    def _format_row(self, filepath: str, index: int, metadata_provider) -> str:
        marker = "▶ " if index == self._current_index else "   "
        if metadata_provider is not None:
            try:
                meta = metadata_provider(filepath) or {}
                title = meta.get("title") or os.path.splitext(os.path.basename(filepath))[0]
                artist = meta.get("artist") or "Desconocido"
                return f"{marker}{title}  —  {artist}"
            except Exception:
                pass
        return f"{marker}{os.path.basename(filepath)}"

    def _apply_row_style(self, item: QListWidgetItem, index: int):
        font = item.font()
        if index == self._current_index:
            font.setBold(True)
            # Ligero énfasis usando el color lavanda de marca
            item.setForeground(QBrush(QColor("#7c4dff")))
        else:
            font.setBold(False)
        item.setFont(font)

    # ── Slots internos ──────────────────────────────────────────────────

    def _on_double_clicked(self, item: QListWidgetItem):
        row = self.list_widget.row(item)
        if row >= 0:
            self.jump_to_index_requested.emit(row)

    def _on_rows_moved(self, _parent, _start, _end, _dest_parent, _dest_row):
        # Reconstruir el orden nuevo a partir del widget
        new_order = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            fp = item.data(Qt.ItemDataRole.UserRole)
            if fp:
                new_order.append(fp)
        self.reorder_requested.emit(new_order)

    def _show_context_menu(self, position):
        item = self.list_widget.itemAt(position)
        if not item:
            return
        row = self.list_widget.row(item)

        menu = QMenu(self)

        act_jump = QAction("▶ Reproducir ahora", self)
        act_jump.triggered.connect(lambda: self.jump_to_index_requested.emit(row))
        menu.addAction(act_jump)

        act_remove = QAction("✕ Quitar de la cola", self)
        act_remove.triggered.connect(lambda: self.remove_at_requested.emit(row))
        menu.addAction(act_remove)

        menu.addSeparator()
        act_clear = QAction("🧹 Limpiar cola", self)
        act_clear.triggered.connect(self.clear_queue_requested.emit)
        menu.addAction(act_clear)

        menu.exec(self.list_widget.mapToGlobal(position))
