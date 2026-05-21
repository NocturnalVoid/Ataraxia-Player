# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QSlider, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize
from PyQt6.QtGui import QIcon, QPixmap, QCursor
import os

class MiniPlayer(QWidget):
    play_pause_requested = pyqtSignal()
    next_requested = pyqtSignal()
    prev_requested = pyqtSignal()
    seek_requested = pyqtSignal(int)
    close_requested = pyqtSignal() 
    
    shuffle_requested = pyqtSignal()
    loop_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.is_dark_theme = True
        self.old_pos = None 
        self.is_playing = False 
        self.is_shuffle = False
        self.loop_state = 0
        self._setup_window()
        self._setup_ui()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.Window | 
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool 
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(320, 130)

    def _setup_ui(self):
        self.container = QWidget(self)
        self.container.setObjectName("CajaPrincipal") # <-- AÑADE ESTA LÍNEA
        self.container.setGeometry(0, 0, 320, 130)

        main_layout = QHBoxLayout(self.container)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        self.lbl_cover = QLabel()
        self.lbl_cover.setFixedSize(90, 90)
        self.lbl_cover.setStyleSheet("background-color: #333; border-radius: 8px;")
        self.lbl_cover.setScaledContents(True)
        
        # --- SOLUCIÓN MATEMÁTICA: Margen superior forzado ---
        cover_layout = QVBoxLayout()
        cover_layout.setContentsMargins(0, 10, 0, 0) # Empuja exactamente 10px hacia abajo
        cover_layout.addWidget(self.lbl_cover)
        cover_layout.addStretch() # Evita que se estire hacia abajo
        
        main_layout.addLayout(cover_layout)
        # ----------------------------------------------------

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.btn_close = QPushButton("✖")
        self.btn_close.setObjectName("mini_close")
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.setToolTip("Cerrar Mini Player")
        self.btn_close.clicked.connect(self._on_close_clicked)
        # Selector específico por objectName → gana a cualquier regla global QPushButton
        self.btn_close.setStyleSheet("""
            QPushButton#mini_close {
                border: none;
                background: transparent;
                color: #888888;
                font-weight: bold;
                font-size: 14px;
                padding: 0;
            }
            QPushButton#mini_close:hover {
                color: #ff5555;
                background: transparent;
            }
            QPushButton#mini_close:pressed {
                color: #ff3333;
                background: transparent;
            }
        """)
        top_bar.addWidget(self.btn_close)
        right_layout.addLayout(top_bar)

        self.lbl_title = QLabel("Ataraxia Player")
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        
        self.lbl_artist = QLabel("Mini Reproductor")
        self.lbl_artist.setStyleSheet("font-size: 11px; color: #888888;")

        right_layout.addWidget(self.lbl_title)
        right_layout.addWidget(self.lbl_artist)

        self.progress_bar = QSlider(Qt.Orientation.Horizontal)
        self.progress_bar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.progress_bar.setFixedHeight(12)
        # Sincronizado para evitar crasheos de FFmpeg
        self.progress_bar.sliderReleased.connect(self._on_slider_released)
        right_layout.addWidget(self.progress_bar)

        # CSS de botones circulares — selector específico por objectName para no
        # ser alcanzados por el stylesheet global de la app (QPushButton {...}).
        self.btn_css_inactive = """
            QPushButton#mini_ctrl {
                border: none;
                border-radius: 16px;
                background: transparent;
                padding: 0;
            }
            QPushButton#mini_ctrl:hover { background-color: rgba(209, 196, 233, 80); }
            QPushButton#mini_ctrl:pressed { background-color: rgba(209, 196, 233, 150); }
        """
        self.btn_css_active = """
            QPushButton#mini_ctrl {
                border: none;
                border-radius: 16px;
                background-color: rgba(209, 196, 233, 150);
                padding: 0;
            }
            QPushButton#mini_ctrl:hover { background-color: rgba(144, 202, 249, 180); }
            QPushButton#mini_ctrl:pressed { background-color: rgba(100, 181, 246, 200); }
        """
        # Versión para el botón play (más grande, radio 19)
        self._btn_css_play = self.btn_css_inactive.replace("16px", "19px")

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(6)
        controls_layout.addStretch()

        self.btn_shuffle = QPushButton()
        self.btn_prev    = QPushButton()
        self.btn_play    = QPushButton()
        self.btn_next    = QPushButton()
        self.btn_loop    = QPushButton()

        botones = [self.btn_shuffle, self.btn_prev, self.btn_play, self.btn_next, self.btn_loop]

        for btn in botones:
            btn.setObjectName("mini_ctrl")
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setFixedSize(32, 32)
            btn.setStyleSheet(self.btn_css_inactive)
            controls_layout.addWidget(btn)

        self.btn_play.setFixedSize(38, 38)
        self.btn_play.setStyleSheet(self._btn_css_play)

        self.btn_shuffle.clicked.connect(self.shuffle_requested.emit)
        self.btn_prev.clicked.connect(self.prev_requested.emit)
        self.btn_play.clicked.connect(self.play_pause_requested.emit)
        self.btn_next.clicked.connect(self.next_requested.emit)
        self.btn_loop.clicked.connect(self.loop_requested.emit)

        controls_layout.addStretch() 
        
        right_layout.addLayout(controls_layout)
        main_layout.addLayout(right_layout)
        self.update_theme(self.is_dark_theme)

    def update_theme(self, is_dark: bool):
        self.is_dark_theme = is_dark
        folder = "assets/dark_theme" if is_dark else "assets/light_theme"
        
        if is_dark:
            bg_color = "rgba(30, 30, 30, 0.95)" 
            text_color = "#ffffff"
        else:
            bg_color = "rgba(240, 240, 240, 0.95)"
            text_color = "#000000"

        self.container.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_color};
                color: {text_color};
                border-radius: 12px;
                border: 1px solid rgba(128, 128, 128, 0.3);
            }}
        """)
        
        self.btn_shuffle.setIcon(QIcon(f"{folder}/shuffle.svg"))
        self.btn_prev.setIcon(QIcon(f"{folder}/prev.svg"))
        self.btn_next.setIcon(QIcon(f"{folder}/next.svg"))
        
        icon_play = "pause.svg" if self.is_playing else "play.svg"
        self.btn_play.setIcon(QIcon(f"{folder}/{icon_play}"))
        
        icon_loop = "loop_one.svg" if self.loop_state == 2 else "loop.svg"
        self.btn_loop.setIcon(QIcon(f"{folder}/{icon_loop}"))
        
        sz = QSize(18, 18)
        self.btn_shuffle.setIconSize(sz)
        self.btn_prev.setIconSize(sz)
        self.btn_next.setIconSize(sz)
        self.btn_loop.setIconSize(sz)
        self.btn_play.setIconSize(QSize(24, 24))

    def set_play_state(self, is_playing: bool):
        self.is_playing = is_playing
        folder = "assets/dark_theme" if self.is_dark_theme else "assets/light_theme"
        icon_name = "pause.svg" if is_playing else "play.svg"
        self.btn_play.setIcon(QIcon(f"{folder}/{icon_name}"))

    def set_shuffle_state(self, is_shuffle: bool):
        self.is_shuffle = is_shuffle
        self.btn_shuffle.setStyleSheet(self.btn_css_active if is_shuffle else self.btn_css_inactive)

    def set_loop_state(self, state: int):
        self.loop_state = state
        folder = "assets/dark_theme" if self.is_dark_theme else "assets/light_theme"
        icon_loop = "loop_one.svg" if state == 2 else "loop.svg"
        self.btn_loop.setIcon(QIcon(f"{folder}/{icon_loop}"))

        if state == 0:
            self.btn_loop.setStyleSheet(self.btn_css_inactive)
        else:
            self.btn_loop.setStyleSheet(self.btn_css_active)

    def update_metadata(self, title: str, artist: str, cover_path: str):
        self.lbl_title.setText(title[:30] + "..." if len(title) > 30 else title)
        self.lbl_artist.setText(artist[:35] + "..." if len(artist) > 35 else artist)
        
        if cover_path and os.path.exists(cover_path):
            self.lbl_cover.setPixmap(QPixmap(cover_path))
        else:
            self.lbl_cover.setPixmap(QPixmap("assets/default_cover.png"))

    def update_progress(self, current: int, total: int):
        self.progress_bar.setMaximum(total)
        # Sincronizado para evitar el efecto de "Tira y Afloja" al manipular la barra
        if not self.progress_bar.isSliderDown():
            self.progress_bar.blockSignals(True)
            self.progress_bar.setValue(current)
            self.progress_bar.blockSignals(False)

    def _on_slider_released(self):
        valor = self.progress_bar.value()
        self.seek_requested.emit(valor)

    def _on_close_clicked(self):
        self.hide()
        self.close_requested.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if not self.old_pos: return
        delta = QPoint(event.globalPosition().toPoint() - self.old_pos)
        self.move(self.x() + delta.x(), self.y() + delta.y())
        self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None