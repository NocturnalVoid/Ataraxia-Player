# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QPushButton, QHBoxLayout)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon

class StatsPanel(QWidget):
    """
    Vista (Frontend) para mostrar las estadísticas de reproducción con iconos vectoriales.
    """
    def __init__(self):
        super().__init__()
        self.is_dark_theme = True # Estado inicial por defecto
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- TÍTULO CON ICONO DE TROFEO ---
        title_container = QHBoxLayout()
        title_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.icon_trophy = QLabel()
        # Nota: Ya no le pasamos el Pixmap fijo aquí, update_theme_icons lo hará al final
        
        self.lbl_title = QLabel(" Top 10 Canciones Más Escuchadas")
        self.lbl_title.setStyleSheet("font-size: 22px; font-weight: bold; margin: 15px 0px;")
        
        title_container.addWidget(self.icon_trophy)
        title_container.addWidget(self.lbl_title)
        layout.addLayout(title_container)

        # --- BOTÓN DE ACTUALIZAR CON ICONO DINÁMICO ---
        self.btn_refresh = QPushButton(" Actualizar Estadísticas")
        self.btn_refresh.setIconSize(QSize(20, 20))
        self.btn_refresh.setStyleSheet("padding: 8px; font-weight: bold; font-size: 14px;")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.btn_refresh)

        # --- CONFIGURACIÓN DE LA TABLA ---
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Título", "Artista", "Álbum", "Reproducciones"])
        
        # Estilos y comportamiento
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        
        layout.addWidget(self.table)
        
        # Carga inicial de iconos de tema
        self.update_theme_icons(True)

    def update_theme_icons(self, is_dark_mode: bool):
        """Cambia el icono del botón, las celdas, el trofeo y ajusta el CSS dinámicamente."""
        self.is_dark_theme = is_dark_mode
        
        # --- NUEVO: CSS Dinámico para la tabla ---
        if is_dark_mode:
            self.table.setStyleSheet("""
                QTableWidget { gridline-color: #333; alternate-background-color: #2d2d30; background-color: #1e1e1e; color: white; }
                QTableWidget::item:selected { background-color: #37373d; color: white; }
            """)
        else:
            self.table.setStyleSheet("""
                QTableWidget { gridline-color: #ddd; alternate-background-color: #f9f9f9; background-color: #ffffff; color: black; }
                QTableWidget::item:selected { background-color: #d1c4e9; color: black; }
            """)
        # -----------------------------------------

        # 1. Rotar icono del trofeo del título
        trophy_icon_path = "assets/library/trophy_dark.svg" if is_dark_mode else "assets/library/trophy_light.svg"
        self.icon_trophy.setPixmap(QIcon(trophy_icon_path).pixmap(32, 32))

        # 2. Rotar icono del botón de refresco
        refresh_icon_path = "assets/library/stats_refresh_light.svg" if is_dark_mode else "assets/library/stats_refresh_dark.svg"
        self.btn_refresh.setIcon(QIcon(refresh_icon_path))
        
        # 3. Definir iconos para las celdas
        song_icon_path = "assets/library/song_dark.svg" if is_dark_mode else "assets/library/song_light.svg"
        song_icon = QIcon(song_icon_path)
        artist_icon = QIcon("assets/library/artist.svg")
        album_icon = QIcon("assets/library/album.svg")
        play_icon = QIcon("assets/library/stats_play.svg")

        # 4. Aplicar a las cabeceras
        self.table.horizontalHeaderItem(0).setIcon(song_icon)
        self.table.horizontalHeaderItem(1).setIcon(artist_icon)
        self.table.horizontalHeaderItem(2).setIcon(album_icon)
        self.table.horizontalHeaderItem(3).setIcon(play_icon)

        # 5. Actualizar iconos de las filas existentes
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setIcon(song_icon)
            self.table.item(row, 1).setIcon(artist_icon)
            self.table.item(row, 2).setIcon(album_icon)

    def populate_table(self, data: list):
        """Dibuja las filas inyectando los iconos vectoriales correspondientes."""
        self.table.setRowCount(0)
        
        icon_path = "assets/library/song_dark.svg" if self.is_dark_theme else "assets/library/song_light.svg"
        song_icon = QIcon(icon_path)
        artist_icon = QIcon("assets/library/artist.svg")
        album_icon = QIcon("assets/library/album.svg")
        
        for row_idx, row_data in enumerate(data):
            self.table.insertRow(row_idx)
            artista, album, titulo, reproducciones = row_data

            # Crear celdas con iconos
            item_titulo = QTableWidgetItem(song_icon, str(titulo))
            item_artista = QTableWidgetItem(artist_icon, str(artista))
            item_album = QTableWidgetItem(album_icon, str(album))
            
            item_rep = QTableWidgetItem(str(reproducciones))
            item_rep.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = item_rep.font()
            font.setBold(True)
            item_rep.setFont(font)

            self.table.setItem(row_idx, 0, item_titulo)
            self.table.setItem(row_idx, 1, item_artista)
            self.table.setItem(row_idx, 2, item_album)
            self.table.setItem(row_idx, 3, item_rep)