# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QListWidget, QListWidgetItem, QInputDialog, 
                             QFileDialog, QMessageBox, QMenu, QCheckBox)
from PyQt6.QtCore import pyqtSignal, Qt, QEvent, QSettings
from PyQt6.QtGui import QIcon
import os

class PlaylistPanel(QWidget):
    create_playlist_requested = pyqtSignal(str)
    playlist_selected = pyqtSignal(int)
    track_selected = pyqtSignal(list, int, int) 
    
    import_m3u_requested = pyqtSignal(str) 
    export_m3u_requested = pyqtSignal(int, str) 
    delete_playlist_requested = pyqtSignal(int)
    
    songs_reordered = pyqtSignal(int, list)
    remove_song_requested = pyqtSignal(int, int)
    edit_metadata_requested = pyqtSignal(str)
    play_next_requested = pyqtSignal(str)       # filepath: reproducir a continuación
    add_to_queue_requested = pyqtSignal(str)    # filepath: añadir al final de la cola
    toggle_favorite_requested = pyqtSignal(str) # filepath: alternar favorito

    def __init__(self):
        super().__init__()
        self.current_playlist_id = -1 
        self.active_playlist_id = -1  
        self.is_dark_theme = True
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- HEADER PLAYLISTS ---
        header_layout = QHBoxLayout()
        self.lbl_title = QLabel("Mis Playlists")
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        header_layout.addWidget(self.lbl_title)

        self.btn_import = QPushButton(" Importar")
        self.btn_import.setIcon(QIcon("assets/library/folder.svg")) 
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.clicked.connect(self._prompt_import_m3u)
        header_layout.addWidget(self.btn_import)

        self.btn_new = QPushButton(" Nueva")
        self.btn_new.setIcon(QIcon("assets/library/plus.svg"))
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.clicked.connect(self._prompt_new_playlist)
        header_layout.addWidget(self.btn_new)
        
        self.btn_delete = QPushButton(" Eliminar")
        self.btn_delete.setIcon(QIcon("assets/library/trash.svg")) 
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setEnabled(False) 
        self.btn_delete.clicked.connect(self._prompt_delete_playlist) 
        header_layout.addWidget(self.btn_delete)

        layout.addLayout(header_layout)

        self.list_playlists = QListWidget()
        self.list_playlists.currentItemChanged.connect(self._on_playlist_changed)
        self.list_playlists.installEventFilter(self)
        layout.addWidget(self.list_playlists)

        # --- HEADER CANCIONES ---
        songs_header_layout = QHBoxLayout()
        self.lbl_songs = QLabel("Canciones de la Playlist")
        self.lbl_songs.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        songs_header_layout.addWidget(self.lbl_songs)

        self.btn_export = QPushButton(" Exportar M3U")
        self.btn_export.setIcon(QIcon("assets/library/gear.svg")) 
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.setEnabled(False) 
        self.btn_export.clicked.connect(self._prompt_export_m3u)
        songs_header_layout.addWidget(self.btn_export)

        layout.addLayout(songs_header_layout)

        self.list_songs = QListWidget()
        self.list_songs.itemDoubleClicked.connect(self._on_song_double_clicked)
        self.list_songs.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        
        self.original_drop_event = self.list_songs.dropEvent
        self.list_songs.dropEvent = self._custom_drop_event
        
        self.list_songs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_songs.customContextMenuRequested.connect(self._show_song_context_menu)
        # Instalamos el espía de eventos para detectar la tecla Supr
        self.list_songs.installEventFilter(self)
        layout.addWidget(self.list_songs)

    # --- NUEVO: GESTOR DE EVENTOS DE TECLADO ---
    def eventFilter(self, source, event):
        """Intercepta las teclas presionadas dentro de las listas."""
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Delete:
            # Si presiona Supr en la lista de playlists
            if source is self.list_playlists and self.list_playlists.currentItem():
                self._prompt_delete_playlist()
                return True
            # Si presiona Supr en la lista de canciones
            elif source is self.list_songs and self.list_songs.currentItem():
                self._prompt_remove_selected_song()
                return True
        return super().eventFilter(source, event)

    def _custom_drop_event(self, event):
        self.original_drop_event(event) 
        if self.current_playlist_id != -1:
            new_order = [self.list_songs.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list_songs.count())]
            self.songs_reordered.emit(self.current_playlist_id, new_order)

    def _show_song_context_menu(self, position):
        item = self.list_songs.itemAt(position)
        if not item: return

        self.list_songs.setCurrentItem(item)
        filepath = item.data(Qt.ItemDataRole.UserRole)

        menu = QMenu()

        # Cola de reproducción (siempre disponibles)
        if filepath:
            act_play_next = menu.addAction(
                QIcon("assets/library/song_dark.svg"), "Reproducir a continuación"
            )
            act_play_next.triggered.connect(
                lambda _chk, fp=filepath: self.play_next_requested.emit(fp)
            )
            act_add_queue = menu.addAction(
                QIcon("assets/library/plus.svg"), "Añadir a la cola"
            )
            act_add_queue.triggered.connect(
                lambda _chk, fp=filepath: self.add_to_queue_requested.emit(fp)
            )

            menu.addSeparator()

            act_favorite = menu.addAction(
                QIcon("assets/library/heart_full.svg"), "Alternar favorito  (Ctrl+D)"
            )
            act_favorite.triggered.connect(
                lambda _chk, fp=filepath: self.toggle_favorite_requested.emit(fp)
            )

            menu.addSeparator()

        # Editar información (siempre disponible)
        edit_action = menu.addAction(QIcon("assets/library/edit.svg"), "Editar Información")

        # "Quitar de esta playlist" solo para playlists manuales (no smart)
        eliminar_action = None
        if self.current_playlist_id >= 0:
            eliminar_action = menu.addAction(
                QIcon("assets/library/trash.svg"), "Quitar de esta playlist"
            )

        action = menu.exec(self.list_songs.mapToGlobal(position))

        if eliminar_action is not None and action == eliminar_action:
            self._prompt_remove_selected_song()
        elif action == edit_action:
            if filepath:
                self.edit_metadata_requested.emit(filepath)

    # --- DIÁLOGOS Y ADVERTENCIAS CON CHECKBOX ---
    def _prompt_remove_selected_song(self):
        """Muestra la advertencia para borrar una canción específica."""
        item = self.list_songs.currentItem()
        if not item or self.current_playlist_id == -1: return

        settings = QSettings("Ataraxia", "Player")
        if settings.value("skip_song_remove_warning", False, type=bool):
            self._execute_remove_song(item)
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("Quitar Canción")
        msg.setText(f"¿Deseas quitar '{item.text()}' de esta playlist?")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        cb = QCheckBox("No volver a preguntar")
        msg.setCheckBox(cb)

        if msg.exec() == QMessageBox.StandardButton.Yes:
            if cb.isChecked():
                settings.setValue("skip_song_remove_warning", True)
            self._execute_remove_song(item)

    def _execute_remove_song(self, item):
        id_reg = item.data(Qt.ItemDataRole.UserRole + 1)
        self.remove_song_requested.emit(self.current_playlist_id, id_reg)

    def _prompt_delete_playlist(self): 
        """Muestra la advertencia para borrar una playlist completa."""
        if self.current_playlist_id == -1: return
        
        settings = QSettings("Ataraxia", "Player")
        if settings.value("skip_playlist_delete_warning", False, type=bool):
            self._execute_delete_playlist()
            return
            
        msg = QMessageBox(self)
        msg.setWindowTitle("Eliminar Playlist")
        msg.setText("¿Estás seguro de que quieres eliminar esta playlist?\n(Las canciones seguirán en tu biblioteca principal)")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        cb = QCheckBox("No volver a preguntar")
        msg.setCheckBox(cb)

        if msg.exec() == QMessageBox.StandardButton.Yes:
            if cb.isChecked():
                settings.setValue("skip_playlist_delete_warning", True)
            self._execute_delete_playlist()

    def _execute_delete_playlist(self):
        self.delete_playlist_requested.emit(self.current_playlist_id)
        self.btn_delete.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.current_playlist_id = -1
        self.list_songs.clear()

    # --- MÉTODOS DE ACTUALIZACIÓN ---
    def _prompt_import_m3u(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Importar Playlist", "", "Archivos de Playlist (*.m3u *.m3u8)")
        if file_path: self.import_m3u_requested.emit(file_path)

    def _prompt_export_m3u(self):
        if self.current_playlist_id == -1: return
        playlist_name = "Playlist"
        for i in range(self.list_playlists.count()):
            item = self.list_playlists.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == self.current_playlist_id:
                playlist_name = item.data(Qt.ItemDataRole.ToolTipRole) 
                break
        file_path, _ = QFileDialog.getSaveFileName(self, "Exportar Playlist", f"{playlist_name}.m3u", "Archivo M3U (*.m3u)")
        if file_path: self.export_m3u_requested.emit(self.current_playlist_id, file_path)

    def update_playlists(self, playlists: list):
        self.list_playlists.clear()
        
        # 1. Inyectar Colecciones Inteligentes (Textos limpios, sin emojis de texto)
        smart_collections = [
            (-1, "Las más escuchadas"),
            (-2, "Novedades"),
            (-3, "Popurrí Aleatorio"),
            (-4, "Favoritos"),
        ]
        
        for p_id, p_name in smart_collections:
            item = QListWidgetItem(p_name)
            item.setData(Qt.ItemDataRole.UserRole, p_id)
            item.setData(Qt.ItemDataRole.ToolTipRole, p_name) 
            self._apply_playlist_style(item, p_id)
            self.list_playlists.addItem(item)
            
        # Separador visual
        if playlists:
            separator = QListWidgetItem("--- Tus Playlists ---")
            separator.setFlags(Qt.ItemFlag.NoItemFlags) 
            self.list_playlists.addItem(separator)

        # 2. Cargar playlists normales
        for p_id, p_name in playlists:
            item = QListWidgetItem(p_name)
            item.setData(Qt.ItemDataRole.UserRole, p_id)
            item.setData(Qt.ItemDataRole.ToolTipRole, p_name)
            self._apply_playlist_style(item, p_id)
            self.list_playlists.addItem(item)

    def _apply_playlist_style(self, item, p_id):
        # Escudo contra el separador visual
        if p_id is None:
            return

        font = item.font()
        clean_title = item.data(Qt.ItemDataRole.ToolTipRole) or item.text() 
        
        is_smart = p_id < 0 
        
        # --- NUEVO: Enrutamiento dinámico de SVGs para listas inteligentes ---
        smart_icon_path = "assets/library/stats.svg" # Fallback por defecto
        if p_id == -1:
            smart_icon_path = "assets/library/fire.svg"
        elif p_id == -2:
            smart_icon_path = "assets/library/sparkles.svg"
        elif p_id == -3:
            smart_icon_path = "assets/library/dice.svg"
        elif p_id == -4:
            smart_icon_path = "assets/library/heart_full.svg"
        
        if p_id == getattr(self, 'active_playlist_id', -1):
            item.setText(f"{clean_title} (Sonando)")
            item.setIcon(QIcon(smart_icon_path if is_smart else "assets/library/song_dark.svg"))
            font.setBold(True)
        elif p_id == getattr(self, 'current_playlist_id', -1):
            item.setText(clean_title)
            item.setIcon(QIcon(smart_icon_path if is_smart else "assets/library/open_folder.svg"))
            font.setBold(False)
        else:
            item.setText(clean_title)
            item.setIcon(QIcon(smart_icon_path if is_smart else "assets/library/folder.svg"))
            font.setBold(False)
            
        item.setFont(font)

    def set_active_playlist(self, playlist_id: int):
        self.active_playlist_id = playlist_id
        for i in range(self.list_playlists.count()):
            item = self.list_playlists.item(i)
            self._apply_playlist_style(item, item.data(Qt.ItemDataRole.UserRole))

    def _on_playlist_changed(self, current_item, previous_item):
        # Si la lista se limpia por una actualización, evitamos crasheos
        if not current_item:
            return
            
        p_id = current_item.data(Qt.ItemDataRole.UserRole)
        # Escudo por si se selecciona el separador visual con el teclado
        if p_id is None:
            return
            
        self.current_playlist_id = p_id
        
        # Habilitar/Deshabilitar botones según si es lista inteligente (<0) o normal (>=0)
        self.btn_delete.setEnabled(p_id >= 0) 
        self.btn_export.setEnabled(True)
        
        self.playlist_selected.emit(p_id)
        
        for i in range(self.list_playlists.count()):
            it = self.list_playlists.item(i)
            self._apply_playlist_style(it, it.data(Qt.ItemDataRole.UserRole))

    def _prompt_new_playlist(self):
        nombre, ok = QInputDialog.getText(self, "Nueva Playlist", "Nombre:")
        if ok and nombre.strip(): self.create_playlist_requested.emit(nombre.strip())

    def _on_song_double_clicked(self, item):
        index = self.list_songs.row(item)
        queue = [self.list_songs.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list_songs.count())]
        if queue: self.track_selected.emit(queue, index, self.current_playlist_id)

    def highlight_song(self, index: int):
        if self.current_playlist_id == self.active_playlist_id and self.active_playlist_id != -1:
            self.list_songs.setCurrentRow(index)
        else:
            self.list_songs.clearSelection()

    def update_theme_icons(self, is_dark_mode: bool):
        self.is_dark_theme = is_dark_mode
        icon_path = "assets/library/song_dark.svg" if is_dark_mode else "assets/library/song_light.svg"
        song_icon = QIcon(icon_path)
        for i in range(self.list_songs.count()):
            item = self.list_songs.item(i)
            item.setIcon(song_icon)

    def update_songs(self, songs: list):
        self.list_songs.clear()
        icon_path = "assets/library/song_dark.svg" if self.is_dark_theme else "assets/library/song_light.svg"
        song_icon = QIcon(icon_path)
        for id_reg, title, path in songs: 
            item = QListWidgetItem(title)
            item.setIcon(song_icon)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setData(Qt.ItemDataRole.UserRole + 1, id_reg) 
            self.list_songs.addItem(item)