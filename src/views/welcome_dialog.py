# -*- coding: utf-8 -*-
"""
Diálogo de bienvenida — Ataraxia Player.

Se muestra automáticamente en la primera ejecución (cuando la BD aún
no existe). También se puede invocar manualmente desde el menú Ayuda
→ "Mostrar bienvenida".

Diseñado para usuarios sin experiencia previa con el reproductor:
jueces, sinodales, primeros usuarios. Tono cálido y conciso, sin
jerga técnica.

Arquitectura visual:
  - Cabecera con gradiente lavanda (identidad de marca, único color
    hardcodeado del proyecto)
  - Cuerpo con un QStackedWidget que muestra UNA feature a la vez
  - Footer con dots de progreso y botones Atrás / Siguiente
  - El resto de colores usan palette() para adaptarse a tema claro/oscuro

Iconos:
  Se buscan en assets/welcome/<nombre>.svg. Si no existen, se renderiza
  un placeholder visual gracioso para indicar que se necesita el SVG real.
  Los nombres están listados en _FEATURES más abajo.
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QWidget, QFrame, QSizePolicy
)
from PyQt6.QtGui import QPixmap, QIcon, QPainter, QColor, QFont
from PyQt6.QtCore import Qt, QSize


# ──────────────────────────────────────────────────────────────────────
# COLORES DE MARCA (solo el gradiente del header — identidad visual)
# ──────────────────────────────────────────────────────────────────────
BRAND_PURPLE       = "#5E35B1"
BRAND_PURPLE_LIGHT = "#7C4DFF"
BRAND_PURPLE_HOVER = "#9575CD"


class WelcomeDialog(QDialog):
    """Bienvenida con carrusel de páginas (una feature por página)."""

    # ── Definición de las features destacadas ────────────────────────
    # Cada entrada: (placeholder_icon_path, título, descripción)
    #
    # Los archivos SVG referenciados aquí NO existen aún en el proyecto —
    # son los nombres que el equipo debe crear en assets/welcome/. Si
    # falta cualquiera, se mostrará un placeholder visual indicando qué
    # archivo se necesita.
    _FEATURES = [
        (
            "assets/welcome/library.svg",
            "Tu biblioteca, organizada",
            "Apunta Ataraxia a tu carpeta de música y deja que indexe todo. "
            "Verás tus canciones por álbumes, artistas, géneros y años, con "
            "búsqueda instantánea."
        ),
        (
            "assets/welcome/playlists.svg",
            "Playlists y favoritos",
            "Crea listas a tu gusto, importa o exporta archivos .m3u, marca "
            "tus canciones favoritas con un clic en el corazón sobre la "
            "carátula."
        ),
        (
            "assets/welcome/sound.svg",
            "Sonido a tu medida",
            "Ecualizador de 10 bandas, ReplayGain para normalizar el volumen "
            "entre canciones y filtros DSP para experimentar con el audio."
        ),
        (
            "assets/welcome/converter.svg",
            "Convierte tus archivos",
            "Convierte entre MP3, FLAC, OGG, WAV, M4A y más con FFmpeg "
            "integrado. Sin abrir terminales, sin cargar comandos."
        ),
        (
            "assets/welcome/lyrics.svg",
            "Letras sincronizadas",
            "Activa la descarga automática en Preferencias y verás las letras "
            "en modo karaoke mientras escuchas. Soporta archivos .lrc, .srt y .txt."
        ),
        (
            "assets/welcome/covers.svg",
            "Carátulas automáticas",
            "Si una canción no trae su carátula, Ataraxia puede descargarla "
            "automáticamente (opcional, en Preferencias)."
        ),
    ]

    def __init__(self, parent=None, first_run: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Bienvenida a Ataraxia Player")
        self.setModal(True)
        self.setMinimumSize(560, 480)
        self.resize(620, 520)

        self.first_run = first_run
        self._current_page = 0

        self._setup_ui()
        self._update_page_indicator()

    # ──────────────────────────────────────────────────────────────────
    # CONSTRUCCIÓN DE LA UI
    # ──────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())
        outer.addWidget(self._build_intro(), stretch=0)
        outer.addWidget(self._build_carousel(), stretch=1)
        outer.addWidget(self._build_footer())

    # ── Header con gradient ──────────────────────────────────────────

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("welcomeHeader")
        # Aplicamos el gradient via stylesheet; este SÍ es hardcodeado a
        # propósito (es la identidad de marca, igual en claro y oscuro).
        header.setStyleSheet(
            "QFrame#welcomeHeader { "
            f"  background-color: qlineargradient("
            f"    x1:0, y1:0, x2:1, y2:0, "
            f"    stop:0 {BRAND_PURPLE}, stop:1 {BRAND_PURPLE_LIGHT}); "
            "  border: none; "
            "}"
        )
        header.setFixedHeight(110)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(16)

        # Logo de Ataraxia — se usa QIcon.pixmap() para que Qt lo renderice
        # al tamaño exacto del label, sin bordes ni upscaling borroso.
        icon_label = QLabel()
        icon_label.setFixedSize(80, 80)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")
        logo_pix = QIcon("assets/icons/ataraxia.png").pixmap(QSize(80, 80))
        if not logo_pix.isNull():
            icon_label.setPixmap(logo_pix)
        layout.addWidget(icon_label)

        # Texto del saludo (sobre fondo gradient — blanco con alpha es la única forma)
        text_block = QVBoxLayout()
        text_block.setSpacing(2)
        text_block.setContentsMargins(0, 6, 0, 0)

        greeting_text = (
            "¡Bienvenido a Ataraxia Player!" if self.first_run
            else "Ataraxia Player"
        )
        greeting = QLabel(greeting_text)
        greeting.setStyleSheet(
            "color: white; "
            "font-size: 20px; "
            "font-weight: bold; "
            "background: transparent; "
            "border: none;"
        )

        subtitle = QLabel(
            "Tu reproductor de música de escritorio, libre y a tu manera"
        )
        subtitle.setStyleSheet(
            "color: rgba(255, 255, 255, 0.88); "
            "font-size: 12px; "
            "font-style: italic; "
            "background: transparent; "
            "border: none;"
        )

        text_block.addWidget(greeting)
        text_block.addWidget(subtitle)
        text_block.addStretch()

        layout.addLayout(text_block, stretch=1)
        return header

    # ── Línea de introducción (encima del carrusel) ──────────────────

    def _build_intro(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(28, 16, 28, 8)
        layout.setSpacing(0)

        intro = QLabel(
            "Aquí tienes un resumen rápido de lo que puedes hacer:"
            if self.first_run else
            "Te recordamos lo que Ataraxia puede hacer por ti:"
        )
        intro.setStyleSheet(
            # Sin color hardcodeado: hereda del tema
            "font-size: 13px; background: transparent; border: none;"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        return wrapper

    # ── Carrusel (StackedWidget) ─────────────────────────────────────

    def _build_carousel(self) -> QWidget:
        self.stack = QStackedWidget()
        for icon_path, title, desc in self._FEATURES:
            self.stack.addWidget(self._build_feature_page(icon_path, title, desc))
        return self.stack

    def _build_feature_page(self, icon_path: str, title: str, desc: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 12, 28, 12)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Icono grande centrado (96×96) en una "burbuja" lavanda
        icon_holder = QLabel()
        icon_holder.setFixedSize(120, 120)
        icon_holder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_holder.setStyleSheet(
            f"background-color: rgba(124, 77, 255, 0.13); "
            "border: none; "
            "border-radius: 60px;"
        )

        pix = self._load_icon_or_placeholder(icon_path, size=72)
        icon_holder.setPixmap(pix)
        layout.addWidget(icon_holder, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Título
        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            "font-size: 18px; "
            "font-weight: bold; "
            "background: transparent; "
            "border: none;"
        )
        layout.addWidget(title_lbl)

        # Descripción
        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setStyleSheet(
            "font-size: 13px; "
            "background: transparent; "
            "border: none; "
            "padding: 0 30px;"
        )
        layout.addWidget(desc_lbl)

        layout.addStretch()
        return page

    def _load_icon_or_placeholder(self, path: str, size: int = 72) -> QPixmap:
        """
        Carga un icono SVG nítido al tamaño pedido.

        Problema que resuelve:
          `QPixmap(svg_path)` rasteriza el SVG a su tamaño INTRÍNSECO (muchos
          SVG tienen viewBox de 24×24 px). Al escalar ese bitmap pequeño a 72px
          con `.scaled()` el resultado es borroso porque se está ampliando un
          raster, no re-renderizando el vector.

        Solución:
          `QIcon(svg_path).pixmap(size, size)` le pide a Qt que rasterice el
          SVG directamente al tamaño final. Qt usa su motor SVG interno para
          esto, sin pasar por un bitmap intermedio pequeño, con lo cual el
          resultado es nítido a cualquier densidad de pantalla.

          Si el archivo no existe o no es un SVG válido, se dibuja un placeholder
          visual con el nombre del archivo esperado para facilitar el trabajo al
          diseñador.
        """
        if os.path.exists(path):
            icon = QIcon(path)
            if not icon.isNull():
                # pixmap() renderiza el SVG directamente al tamaño pedido:
                # no hay upscaling de bitmap, siempre nítido.
                pix = icon.pixmap(QSize(size, size))
                if not pix.isNull():
                    return pix

        # Placeholder: cuadrado con borde punteado + nombre del archivo esperado
        ph = QPixmap(size, size)
        ph.fill(Qt.GlobalColor.transparent)
        painter = QPainter(ph)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = painter.pen()
        pen.setColor(QColor(BRAND_PURPLE_LIGHT))
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRoundedRect(2, 2, size - 4, size - 4, 8, 8)

        name = os.path.basename(path).replace(".svg", "")
        painter.setPen(QColor(BRAND_PURPLE_LIGHT))
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(ph.rect(), Qt.AlignmentFlag.AlignCenter, name)

        painter.end()
        return ph

    # ── Footer con dots y navegación ─────────────────────────────────

    def _build_footer(self) -> QWidget:
        footer = QFrame()
        # Línea superior sutil para separar el carrusel del footer
        footer.setStyleSheet(
            "QFrame { border-top: 1px solid palette(mid); }"
        )
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(24, 14, 24, 16)
        layout.setSpacing(10)

        # Botón "Atrás"
        self.btn_prev = QPushButton("← Atrás")
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.setMinimumWidth(95)
        self.btn_prev.setMinimumHeight(34)
        self.btn_prev.setStyleSheet(self._secondary_btn_css())
        self.btn_prev.clicked.connect(self._go_prev)
        layout.addWidget(self.btn_prev)

        layout.addStretch()

        # Dots de progreso
        self.dots_container = QHBoxLayout()
        self.dots_container.setSpacing(6)
        self.dots_container.setContentsMargins(0, 0, 0, 0)
        self._dot_widgets = []
        for _ in self._FEATURES:
            dot = QLabel()
            dot.setFixedSize(8, 8)
            self._dot_widgets.append(dot)
            self.dots_container.addWidget(dot)
        dots_widget = QWidget()
        dots_widget.setLayout(self.dots_container)
        dots_widget.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(dots_widget)

        layout.addStretch()

        # Botón "Siguiente" / "Comenzar" (cambia en la última página)
        self.btn_next = QPushButton("Siguiente →")
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.setMinimumWidth(110)
        self.btn_next.setMinimumHeight(34)
        self.btn_next.setStyleSheet(self._primary_btn_css())
        self.btn_next.clicked.connect(self._go_next)
        layout.addWidget(self.btn_next)

        return footer

    # ──────────────────────────────────────────────────────────────────
    # ESTILOS DE BOTÓN (encapsulados aquí para que sea fácil ajustarlos)
    # ──────────────────────────────────────────────────────────────────

    def _primary_btn_css(self) -> str:
        return (
            "QPushButton {"
            f"  background-color: {BRAND_PURPLE_LIGHT}; "
            "  color: white; "
            "  border: none; "
            "  border-radius: 5px; "
            "  font-size: 13px; "
            "  font-weight: bold; "
            "  padding: 6px 16px; "
            "}"
            f"QPushButton:hover {{ background-color: {BRAND_PURPLE_HOVER}; }}"
            f"QPushButton:pressed {{ background-color: {BRAND_PURPLE}; }}"
        )

    def _secondary_btn_css(self) -> str:
        # Usa palette() para integrarse con el tema activo
        return (
            "QPushButton {"
            "  background-color: palette(button); "
            "  color: palette(button-text); "
            "  border: 1px solid palette(mid); "
            "  border-radius: 5px; "
            "  font-size: 13px; "
            "  padding: 6px 16px; "
            "}"
            "QPushButton:hover { background-color: palette(midlight); }"
            "QPushButton:pressed { background-color: palette(mid); }"
            "QPushButton:disabled { color: palette(mid); border-color: palette(mid); }"
        )

    # ──────────────────────────────────────────────────────────────────
    # NAVEGACIÓN
    # ──────────────────────────────────────────────────────────────────

    def _go_prev(self):
        if self._current_page > 0:
            self._current_page -= 1
            self.stack.setCurrentIndex(self._current_page)
            self._update_page_indicator()

    def _go_next(self):
        # Si estamos en la última página, el botón cierra el diálogo
        if self._current_page >= len(self._FEATURES) - 1:
            self.accept()
            return
        self._current_page += 1
        self.stack.setCurrentIndex(self._current_page)
        self._update_page_indicator()

    def _update_page_indicator(self):
        """Refresca dots, estado de botones y label del botón Siguiente."""
        last_page = len(self._FEATURES) - 1

        # Dots: el actual en lavanda sólido, los demás en gris claro
        for i, dot in enumerate(self._dot_widgets):
            if i == self._current_page:
                dot.setStyleSheet(
                    f"background-color: {BRAND_PURPLE_LIGHT}; "
                    "border-radius: 4px;"
                )
                dot.setFixedSize(18, 8)  # el activo es más alargado
            else:
                dot.setStyleSheet(
                    "background-color: palette(mid); "
                    "border-radius: 4px;"
                )
                dot.setFixedSize(8, 8)

        # Botón Atrás: deshabilitado en la primera página
        self.btn_prev.setEnabled(self._current_page > 0)

        # Botón Siguiente: cambia a "Comenzar" en la última página
        if self._current_page == last_page:
            self.btn_next.setText(
                "Comenzar ✓" if self.first_run else "Entendido ✓"
            )
        else:
            self.btn_next.setText("Siguiente →")

    # ──────────────────────────────────────────────────────────────────
    # NAVEGACIÓN POR TECLADO (flechas izquierda/derecha)
    # ──────────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Left:
            self._go_prev()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._go_next()
        elif key == Qt.Key.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)
