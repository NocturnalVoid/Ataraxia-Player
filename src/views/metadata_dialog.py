# -*- coding: utf-8 -*-
"""
Diálogo de edición de metadatos extendido.

Permite editar todos los campos comunes de un archivo de audio:
  - Título, artista, álbum, artista del álbum
  - Año, género
  - Número de pista (con total opcional, ej. 5/12)
  - Número de disco (con total opcional)
  - Carátula: cambiar (cargar imagen), quitar, restaurar la original

El layout sigue el estilo del documento: ancho holgado, agrupaciones
con QGroupBox para que el usuario reconozca grupos visuales, previsualización
de la carátula a la derecha. Acciones destructivas (quitar carátula)
muestran feedback inmediato.
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLineEdit, QSpinBox, QPushButton, QLabel, QGroupBox, QFileDialog,
    QDialogButtonBox, QWidget
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QSize


class MetadataDialog(QDialog):
    """
    Diálogo extendido de edición de metadatos.

    Se construye con:
        dlg = MetadataDialog(parent, current_data, cover_path=None)
        if dlg.exec():
            data = dlg.get_new_data()
            # data["cover_action"] ∈ {"keep", "replace", "remove"}
            # si "replace" → data["cover_path"] es la ruta del archivo elegido
    """

    def __init__(self, parent, current_data: dict, cover_path: str = None):
        super().__init__(parent)
        self.setWindowTitle("Editar Información de la Pista")
        self.setMinimumWidth(640)
        self.setMinimumHeight(420)

        self.current_data = current_data or {}
        # cover_path: ruta a la imagen actual (puede ser el placeholder)
        self.original_cover_path = cover_path or ""
        # Estado de la edición de carátula. Empieza en "keep" (no tocar).
        # Cambia a "replace" si se carga una imagen nueva, a "remove"
        # si se quita.
        self._cover_action = "keep"
        self._new_cover_path = ""

        self._setup_ui()
        self._load_current_values()
        self._refresh_cover_preview()

    # ──────────────────────────────────────────────────────────────────
    # CONSTRUCCIÓN DE LA UI
    # ──────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(12)

        # Dos columnas lado a lado: campos + carátula
        body = QHBoxLayout()
        body.setSpacing(16)

        body.addWidget(self._build_fields_panel(), stretch=2)
        body.addWidget(self._build_cover_panel(), stretch=1)

        outer.addLayout(body)

        # Botones inferiores estándar (Guardar / Cancelar)
        self.btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        outer.addWidget(self.btn_box)

    def _build_fields_panel(self) -> QWidget:
        """Columna izquierda: agrupaciones de campos editables."""
        panel = QWidget()
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # ── Grupo 1: información principal ────────────────────────────
        grp_main = QGroupBox("Información principal")
        form_main = QFormLayout()
        form_main.setSpacing(6)

        self.inp_title  = QLineEdit()
        self.inp_artist = QLineEdit()
        self.inp_album  = QLineEdit()
        self.inp_albumartist = QLineEdit()
        self.inp_albumartist.setPlaceholderText("Igual que el artista si se deja vacío")

        form_main.addRow("Título:", self.inp_title)
        form_main.addRow("Artista:", self.inp_artist)
        form_main.addRow("Álbum:", self.inp_album)
        form_main.addRow("Artista del álbum:", self.inp_albumartist)
        grp_main.setLayout(form_main)
        v.addWidget(grp_main)

        # ── Grupo 2: clasificación ────────────────────────────────────
        grp_class = QGroupBox("Clasificación")
        form_class = QFormLayout()
        form_class.setSpacing(6)

        self.inp_year = QSpinBox()
        self.inp_year.setRange(0, 9999)
        self.inp_year.setSpecialValueText("—")   # 0 se ve como "—" (no asignado)

        self.inp_genre = QLineEdit()
        self.inp_genre.setPlaceholderText("Ej: Rock, Jazz, Electrónica…")

        form_class.addRow("Año:", self.inp_year)
        form_class.addRow("Género:", self.inp_genre)
        grp_class.setLayout(form_class)
        v.addWidget(grp_class)

        # ── Grupo 3: numeración (pista y disco) ──────────────────────
        grp_num = QGroupBox("Numeración")
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        # Pista N de M
        self.inp_track     = QSpinBox(); self.inp_track.setRange(0, 999); self.inp_track.setSpecialValueText("—")
        self.inp_track_tot = QSpinBox(); self.inp_track_tot.setRange(0, 999); self.inp_track_tot.setSpecialValueText("—")
        grid.addWidget(QLabel("Pista:"),                  0, 0)
        grid.addWidget(self.inp_track,                    0, 1)
        grid.addWidget(QLabel(" de "),                    0, 2)
        grid.addWidget(self.inp_track_tot,                0, 3)

        # Disco N de M
        self.inp_disc      = QSpinBox(); self.inp_disc.setRange(0, 99); self.inp_disc.setSpecialValueText("—")
        self.inp_disc_tot  = QSpinBox(); self.inp_disc_tot.setRange(0, 99); self.inp_disc_tot.setSpecialValueText("—")
        grid.addWidget(QLabel("Disco:"),                  1, 0)
        grid.addWidget(self.inp_disc,                     1, 1)
        grid.addWidget(QLabel(" de "),                    1, 2)
        grid.addWidget(self.inp_disc_tot,                 1, 3)
        grid.setColumnStretch(4, 1)
        grp_num.setLayout(grid)
        v.addWidget(grp_num)

        v.addStretch()
        return panel

    def _build_cover_panel(self) -> QWidget:
        """Columna derecha: previsualización y controles de carátula."""
        panel = QGroupBox("Carátula")
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)

        self.lbl_cover = QLabel()
        self.lbl_cover.setMinimumSize(QSize(200, 200))
        self.lbl_cover.setMaximumSize(QSize(260, 260))
        self.lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cover.setStyleSheet(
            "border: 1px solid palette(mid); "
            "border-radius: 4px; "
            "background-color: palette(base);"
        )
        layout.addWidget(self.lbl_cover, alignment=Qt.AlignmentFlag.AlignCenter)

        # Indicador del estado actual (qué se va a hacer al guardar)
        self.lbl_cover_status = QLabel("Sin cambios")
        self.lbl_cover_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cover_status.setStyleSheet("color: palette(text); font-size: 11px;")
        layout.addWidget(self.lbl_cover_status)

        # Botones de acción
        btn_change = QPushButton(" Cambiar…")
        btn_change.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_change.clicked.connect(self._on_change_cover)

        btn_remove = QPushButton(" Quitar")
        btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_remove.clicked.connect(self._on_remove_cover)

        btn_restore = QPushButton(" Restaurar")
        btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_restore.setToolTip("Vuelve a la carátula original (deshace cualquier cambio en esta sesión)")
        btn_restore.clicked.connect(self._on_restore_cover)

        layout.addWidget(btn_change)
        layout.addWidget(btn_remove)
        layout.addWidget(btn_restore)

        layout.addStretch()
        return panel

    # ──────────────────────────────────────────────────────────────────
    # CARGA DE VALORES INICIALES
    # ──────────────────────────────────────────────────────────────────

    def _load_current_values(self):
        d = self.current_data
        self.inp_title.setText(str(d.get("title", "") or ""))
        self.inp_artist.setText(str(d.get("artist", "") or ""))
        self.inp_album.setText(str(d.get("album", "") or ""))
        self.inp_albumartist.setText(str(d.get("albumartist", "") or ""))
        self.inp_genre.setText(str(d.get("genre", "") or ""))

        # Año: 0 muestra "—" gracias a setSpecialValueText
        try:
            year_val = int(d.get("year", 0) or 0)
        except (TypeError, ValueError):
            year_val = 0
        self.inp_year.setValue(year_val)

        # Pista y total
        track_val, track_tot = self._split_pair(d.get("tracknumber", ""))
        self.inp_track.setValue(track_val)
        self.inp_track_tot.setValue(track_tot)

        # Disco y total
        disc_val, disc_tot = self._split_pair(d.get("discnumber", ""))
        self.inp_disc.setValue(disc_val)
        self.inp_disc_tot.setValue(disc_tot)

    @staticmethod
    def _split_pair(value) -> tuple:
        """
        Convierte 'N/M' o 'N' o int → (int, int).
        Retorna (0, 0) si no se puede parsear.
        """
        if not value:
            return (0, 0)
        s = str(value)
        try:
            if '/' in s:
                a, b = s.split('/', 1)
                return (int(a.strip() or 0), int(b.strip() or 0))
            return (int(s.strip()), 0)
        except (TypeError, ValueError):
            return (0, 0)

    # ──────────────────────────────────────────────────────────────────
    # ACCIONES DE CARÁTULA
    # ──────────────────────────────────────────────────────────────────

    def _refresh_cover_preview(self):
        """Renderiza la previsualización según el estado actual del diálogo."""
        if self._cover_action == "replace" and self._new_cover_path:
            self._render_pixmap_from_path(self._new_cover_path)
            self.lbl_cover_status.setText("Carátula nueva pendiente de guardar")
            self.lbl_cover_status.setStyleSheet("color: #5E35B1; font-size: 11px; font-style: italic;")
        elif self._cover_action == "remove":
            self.lbl_cover.setPixmap(QPixmap())
            self.lbl_cover.setText("(sin carátula)")
            self.lbl_cover_status.setText("Se eliminará al guardar")
            self.lbl_cover_status.setStyleSheet("color: #c2185b; font-size: 11px; font-style: italic;")
        else:
            self._render_pixmap_from_path(self.original_cover_path)
            self.lbl_cover_status.setText("Sin cambios")
            self.lbl_cover_status.setStyleSheet("color: palette(text); font-size: 11px;")

    def _render_pixmap_from_path(self, path: str):
        if not path or not os.path.exists(path):
            self.lbl_cover.setPixmap(QPixmap())
            self.lbl_cover.setText("(sin carátula)")
            return
        pix = QPixmap(path)
        if pix.isNull():
            self.lbl_cover.setPixmap(QPixmap())
            self.lbl_cover.setText("(no se pudo cargar)")
            return
        scaled = pix.scaled(
            self.lbl_cover.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.lbl_cover.setPixmap(scaled)
        self.lbl_cover.setText("")

    def _on_change_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar carátula",
            "",
            "Imágenes (*.jpg *.jpeg *.png);;Todos los archivos (*)"
        )
        if not path:
            return
        self._cover_action = "replace"
        self._new_cover_path = path
        self._refresh_cover_preview()

    def _on_remove_cover(self):
        self._cover_action = "remove"
        self._new_cover_path = ""
        self._refresh_cover_preview()

    def _on_restore_cover(self):
        """Revierte cualquier cambio en esta sesión y vuelve al estado original."""
        self._cover_action = "keep"
        self._new_cover_path = ""
        self._refresh_cover_preview()

    # ──────────────────────────────────────────────────────────────────
    # API PÚBLICA — datos resultantes
    # ──────────────────────────────────────────────────────────────────

    def get_new_data(self) -> dict:
        """
        Retorna un diccionario con todos los campos editables. Las claves
        de campos numéricos se construyen como string "N/M" si hay total,
        o solo "N" si no.

        Campos de carátula:
          - cover_action: "keep" | "replace" | "remove"
          - cover_path: ruta del archivo nuevo (solo si action == "replace")
        """
        track_str = self._join_pair(self.inp_track.value(), self.inp_track_tot.value())
        disc_str  = self._join_pair(self.inp_disc.value(),  self.inp_disc_tot.value())

        year_value = self.inp_year.value()

        return {
            "title":        self.inp_title.text().strip(),
            "artist":       self.inp_artist.text().strip(),
            "album":        self.inp_album.text().strip(),
            "albumartist":  self.inp_albumartist.text().strip(),
            "genre":        self.inp_genre.text().strip(),
            "year":         year_value,
            "tracknumber":  track_str,
            "discnumber":   disc_str,
            "cover_action": self._cover_action,
            "cover_path":   self._new_cover_path,
        }

    @staticmethod
    def _join_pair(value: int, total: int) -> str:
        """(5, 12) → '5/12';  (5, 0) → '5';  (0, _) → ''"""
        if value <= 0:
            return ""
        if total > 0:
            return f"{value}/{total}"
        return str(value)
