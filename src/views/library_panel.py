# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTreeView,
                              QLabel, QPushButton, QFileDialog, QMenu,
                              QLineEdit, QComboBox)
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QIcon
from PyQt6.QtCore import pyqtSignal, Qt

FilePathRole = Qt.ItemDataRole.UserRole + 1

# ── View mode constants ───────────────────────────────────────────────
VIEW_SONGS   = "songs"
VIEW_ALBUMS  = "albums"
VIEW_ARTISTS = "artists"
VIEW_GENRE   = "genre"
VIEW_YEAR    = "year"


class LibraryPanel(QWidget):

    track_selected          = pyqtSignal(list, int)
    add_folder_requested    = pyqtSignal(str)
    add_to_playlist_requested = pyqtSignal(int, str)
    play_next_requested       = pyqtSignal(str)   # filepath: reproducir a continuación
    add_to_queue_requested    = pyqtSignal(str)   # filepath: añadir al final de la cola
    toggle_favorite_requested = pyqtSignal(str)   # filepath: alternar favorito
    search_query_changed    = pyqtSignal(str)
    edit_metadata_requested = pyqtSignal(str)
    remove_song_requested   = pyqtSignal(str)
    clean_library_requested = pyqtSignal()
    refresh_library_requested = pyqtSignal()    # rescanea todas las carpetas raíz
    library_view_requested  = pyqtSignal(str)   # emitted when the user switches view

    # ── Pill button styles ────────────────────────────────────────────
    _PILL_INACTIVE = """
        QPushButton {
            border-radius: 11px;
            border: 1px solid #555;
            background-color: transparent;
            padding: 3px 11px;
            font-size: 12px;
        }
        QPushButton:hover {
            background-color: rgba(209, 196, 233, 60);
            border-color: #d1c4e9;
        }
    """
    _PILL_ACTIVE = """
        QPushButton {
            border-radius: 11px;
            border: 1px solid #d1c4e9;
            background-color: #d1c4e9;
            padding: 3px 11px;
            font-size: 12px;
            font-weight: bold;
            color: #1a1a2e;
        }
        QPushButton:hover { background-color: #b39ddb; border-color: #b39ddb; }
    """

    def __init__(self):
        super().__init__()
        self.available_playlists   = []
        self.is_dark_theme         = True
        self._current_mode         = VIEW_ARTISTS
        # Data stores — only one is populated at a time
        self._artist_data          = {}   # {artist: {album: [(tn, title, fp)]}}
        self._grouped_data         = {}   # {group:          [(tn, title, fp)]}
        self._flat_data            = []   # [(tn, title, fp)]
        self._setup_ui()

    # ── UI construction ───────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- Top bar: title + action buttons ---
        top_bar = QHBoxLayout()
        self.lbl_title = QLabel("Biblioteca Local")
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        top_bar.addWidget(self.lbl_title)

        self.btn_add = QPushButton(" Agregar Carpeta")
        self.btn_add.setIcon(QIcon("assets/library/plus.svg"))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self._choose_folder)
        top_bar.addWidget(self.btn_add)

        # Actualizar — rescanea todas las carpetas raíz registradas para
        # detectar archivos nuevos o cambios desde el último escaneo
        self.btn_refresh = QPushButton(" Actualizar")
        self.btn_refresh.setIcon(QIcon("assets/library/stats_refresh_dark.svg"))
        self.btn_refresh.setToolTip("Reescanea las carpetas conocidas para detectar archivos nuevos o modificados")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_library_requested.emit)
        top_bar.addWidget(self.btn_refresh)

        self.btn_clean = QPushButton(" Limpiar")
        self.btn_clean.setToolTip("Elimina archivos fantasma de la base de datos (canciones cuyo archivo ya no existe)")
        self.btn_clean.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clean.clicked.connect(self.clean_library_requested.emit)
        top_bar.addWidget(self.btn_clean)

        layout.addLayout(top_bar)

        # --- Search bar ---
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Buscar canción, artista o álbum...")
        self.search_bar.addAction(
            QIcon("assets/library/search.svg"),
            QLineEdit.ActionPosition.LeadingPosition
        )
        self.search_bar.setStyleSheet(
            "padding: 5px; margin: 5px; border-radius: 4px; border: 1px solid #555;"
        )
        self.search_bar.textChanged.connect(self.search_query_changed.emit)
        layout.addWidget(self.search_bar)

        # --- View pills + sort combo ---
        pills_bar = QHBoxLayout()
        pills_bar.setSpacing(6)
        pills_bar.setContentsMargins(5, 2, 5, 2)

        views = [
            (VIEW_SONGS,   "Canciones"),
            (VIEW_ALBUMS,  "Álbumes"),
            (VIEW_ARTISTS, "Artistas"),
            (VIEW_GENRE,   "Género"),
            (VIEW_YEAR,    "Año"),
        ]
        self._pill_buttons = {}
        for mode, label in views:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                self._PILL_ACTIVE if mode == self._current_mode else self._PILL_INACTIVE
            )
            btn.clicked.connect(lambda _checked, m=mode: self._on_pill_clicked(m))
            pills_bar.addWidget(btn)
            self._pill_buttons[mode] = btn

        pills_bar.addStretch()

        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["Ordenar: Pista", "Ordenar: Nombre"])
        self.combo_sort.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_sort.setStyleSheet(
            "padding: 3px 6px; border-radius: 4px; border: 1px solid #555; font-size: 12px;"
        )
        self.combo_sort.currentIndexChanged.connect(self._build_tree)
        pills_bar.addWidget(self.combo_sort)

        layout.addLayout(pills_bar)

        # --- Tree view ---
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.tree_view.doubleClicked.connect(self._on_item_double_clicked)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self._show_context_menu)

        self.model = QStandardItemModel()
        self.tree_view.setModel(self.model)
        layout.addWidget(self.tree_view)

    # ── Pill interaction ──────────────────────────────────────────────

    def _on_pill_clicked(self, mode: str):
        if mode == self._current_mode:
            return
        self._current_mode = mode
        for m, btn in self._pill_buttons.items():
            btn.setStyleSheet(self._PILL_ACTIVE if m == mode else self._PILL_INACTIVE)
        self.library_view_requested.emit(mode)

    # ── Public populate API ───────────────────────────────────────────

    def populate_tree(self, data: dict):
        """Backward-compatible entry point for artist-tree data (used by search)."""
        self._artist_data = data
        # If we are in non-artists mode during a search, switch display to artists
        # so the hierarchy context is visible; pills remain unchanged.
        self._build_tree()

    def populate_library(self, data, mode: str):
        """Unified populate called by the controller for each view mode."""
        self._current_mode = mode
        for m, btn in self._pill_buttons.items():
            btn.setStyleSheet(self._PILL_ACTIVE if m == mode else self._PILL_INACTIVE)

        if mode == VIEW_ARTISTS:
            self._artist_data  = data
        elif mode == VIEW_SONGS:
            self._flat_data    = data
        else:
            self._grouped_data = data

        self._build_tree()

    # ── Tree construction ─────────────────────────────────────────────

    def _build_tree(self):
        self.model.clear()
        mode = self._current_mode

        # During an active search, populate_tree is called with artists data;
        # render it regardless of selected pill so context is preserved.
        if self.search_bar.text().strip() and self._artist_data:
            self._build_artists(self._artist_data)
            self.lbl_title.setText("Biblioteca Local")
            return

        if mode == VIEW_ARTISTS:
            self._build_artists(self._artist_data)
        elif mode == VIEW_SONGS:
            self._build_flat(self._flat_data)
        else:
            self._build_grouped(self._grouped_data, mode)

        self.lbl_title.setText("Biblioteca Local")

    def _song_icon(self) -> QIcon:
        path = "assets/library/song_dark.svg" if self.is_dark_theme else "assets/library/song_light.svg"
        return QIcon(path)

    def _sorted_tracks(self, tracks: list) -> list:
        by_name = (self.combo_sort.currentIndex() == 1)
        if by_name:
            return sorted(tracks, key=lambda x: x[1].lower())
        return sorted(tracks, key=lambda x: (x[0], x[1].lower()))

    def _make_song_item(self, track_num: int, title: str, filepath: str) -> QStandardItem:
        display = f"{track_num:02d} – {title}" if track_num > 0 else title
        item = QStandardItem(display)
        item.setIcon(self._song_icon())
        item.setData(filepath, FilePathRole)
        return item

    # Artists view (2 levels: artist → album → song)
    def _build_artists(self, data: dict):
        for artist_name in sorted(data.keys()):
            artist_item = QStandardItem(artist_name)
            artist_item.setIcon(QIcon("assets/library/artist.svg"))
            artist_item.setSelectable(False)

            for album_name in sorted(data[artist_name].keys()):
                album_item = QStandardItem(album_name)
                album_item.setIcon(QIcon("assets/library/album.svg"))
                album_item.setSelectable(False)

                for tn, title, fp in self._sorted_tracks(data[artist_name][album_name]):
                    album_item.appendRow(self._make_song_item(tn, title, fp))

                artist_item.appendRow(album_item)

            self.model.appendRow(artist_item)

    # Albums / Genre / Year view (1 level: group → song)
    def _build_grouped(self, data: dict, mode: str):
        if mode == VIEW_ALBUMS:
            group_icon = QIcon("assets/library/album.svg")
        elif mode == VIEW_GENRE:
            group_icon = QIcon("assets/library/playlist.svg")
        else:  # year
            group_icon = QIcon("assets/library/stats.svg")

        for group_name in sorted(data.keys(), key=lambda k: (k == "Unknown Genre" or k == "Unknown Year", k)):
            group_item = QStandardItem(str(group_name))
            group_item.setIcon(group_icon)
            group_item.setSelectable(False)

            for tn, title, fp in self._sorted_tracks(data[group_name]):
                group_item.appendRow(self._make_song_item(tn, title, fp))

            self.model.appendRow(group_item)

    # Songs view (flat: just songs at root level)
    def _build_flat(self, songs: list):
        for tn, title, fp in self._sorted_tracks(songs):
            self.model.appendRow(self._make_song_item(tn, title, fp))

    # ── Double-click → play queue ─────────────────────────────────────

    def _on_item_double_clicked(self, index):
        filepath = self.model.data(index, FilePathRole)
        if not filepath:
            return

        queue       = []
        start_index = 0
        parent_idx  = index.parent()

        if not parent_idx.isValid():
            # Flat view — collect all root-level songs
            root = self.model.invisibleRootItem()
            for i in range(root.rowCount()):
                fp = self.model.item(i).data(FilePathRole)
                if fp:
                    queue.append(fp)
                    if fp == filepath:
                        start_index = len(queue) - 1
        else:
            # 1-level or 2-level — collect siblings under the same parent
            for i in range(self.model.rowCount(parent_idx)):
                sibling = self.model.index(i, 0, parent_idx)
                fp = self.model.data(sibling, FilePathRole)
                if fp:
                    queue.append(fp)
                    if fp == filepath:
                        start_index = len(queue) - 1

        if queue:
            self.track_selected.emit(queue, start_index)

    # ── Highlight playing track ───────────────────────────────────────

    def highlight_song(self, filepath: str):
        if not filepath or not self.model:
            return
        self.tree_view.collapseAll()

        def _search(parent_item):
            for row in range(parent_item.rowCount()):
                child = parent_item.child(row)
                if child and child.data(FilePathRole) == filepath:
                    return child
                if child:
                    found = _search(child)
                    if found:
                        return found
            return None

        item = _search(self.model.invisibleRootItem())
        if not item:
            return

        # Expand all ancestor nodes
        idx = item.index()
        parent = idx.parent()
        while parent.isValid():
            self.tree_view.expand(parent)
            parent = parent.parent()

        self.tree_view.setCurrentIndex(idx)
        self.tree_view.scrollTo(idx)

    # ── Theme ─────────────────────────────────────────────────────────

    def update_theme_icons(self, is_dark_mode: bool):
        self.is_dark_theme = is_dark_mode
        song_icon = self._song_icon()
        if self.model:
            self._apply_song_icon_recursive(self.model.invisibleRootItem(), song_icon)

    def _apply_song_icon_recursive(self, parent: QStandardItem, icon: QIcon):
        for row in range(parent.rowCount()):
            child = parent.child(row)
            if child:
                if child.data(FilePathRole):  # it's a song
                    child.setIcon(icon)
                else:
                    self._apply_song_icon_recursive(child, icon)

    # ── Misc ──────────────────────────────────────────────────────────

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta de Música")
        if folder:
            self.add_folder_requested.emit(folder)

    def update_status(self, msg: str):
        self.lbl_title.setText(msg)

    def update_available_playlists(self, playlists: list):
        self.available_playlists = playlists

    # ── Context menu ─────────────────────────────────────────────────

    def _show_context_menu(self, position):
        index    = self.tree_view.indexAt(position)
        if not index.isValid():
            return
        filepath = self.model.data(index, FilePathRole)
        if not filepath:
            return

        menu = QMenu()

        # Reproducir a continuación / añadir a la cola (nuevos)
        act_play_next = menu.addAction(QIcon("assets/library/song_dark.svg"), "Reproducir a continuación")
        act_play_next.triggered.connect(
            lambda _chk, fp=filepath: self.play_next_requested.emit(fp)
        )
        act_add_queue = menu.addAction(QIcon("assets/library/plus.svg"), "Añadir a la cola")
        act_add_queue.triggered.connect(
            lambda _chk, fp=filepath: self.add_to_queue_requested.emit(fp)
        )

        menu.addSeparator()

        # Favorito (nuevo)
        act_favorite = menu.addAction(
            QIcon("assets/library/heart_full.svg"), "Alternar favorito  (Ctrl+D)"
        )
        act_favorite.triggered.connect(
            lambda _chk, fp=filepath: self.toggle_favorite_requested.emit(fp)
        )

        menu.addSeparator()

        add_menu = menu.addMenu(QIcon("assets/library/plus.svg"), "Agregar a Playlist")
        if not self.available_playlists:
            add_menu.addAction("No hay playlists creadas").setEnabled(False)
        else:
            for p_id, p_name in self.available_playlists:
                act = add_menu.addAction(QIcon("assets/library/playlist.svg"), p_name)
                act.triggered.connect(
                    lambda _chk, pid=p_id, fp=filepath: self.add_to_playlist_requested.emit(pid, fp)
                )

        edit_action = menu.addAction(QIcon("assets/library/edit.svg"), "Editar Información")

        menu.addSeparator()
        remove_action = menu.addAction(QIcon("assets/library/trash.svg"), "Eliminar de la Biblioteca")
        remove_action.triggered.connect(
            lambda _chk, fp=filepath: self.remove_song_requested.emit(fp)
        )

        action = menu.exec(self.tree_view.viewport().mapToGlobal(position))
        if action == edit_action:
            self.edit_metadata_requested.emit(filepath)
