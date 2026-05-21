# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, 
                             QSplitter, QStatusBar, QFileDialog, QApplication,
                             QTabWidget, QSystemTrayIcon, QMenu, QStyle, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent
from PyQt6.QtGui import QAction, QIcon
from src.views.stats_panel import StatsPanel

class MainWindow(QMainWindow):
    open_preferences_requested = pyqtSignal()
    theme_changed = pyqtSignal(bool) 
    force_quit_requested = pyqtSignal() 
    tray_play_requested = pyqtSignal()
    tray_next_requested = pyqtSignal()
    tray_prev_requested = pyqtSignal()
    
    # --- NUEVA SEÑAL GLOBAL ---
    mini_player_requested = pyqtSignal()

    def __init__(self, library_panel, playlist_panel, player_panel, converter_panel, dsp_panel):
        super().__init__() 
        self.library_panel = library_panel
        self.playlist_panel = playlist_panel
        self.player_panel = player_panel
        self.converter_panel = converter_panel
        self.dsp_panel = dsp_panel 
        
        self.player_panel.fullscreen_requested.connect(self._handle_fullscreen)
        
        self._setup_ui()
        self._setup_tray()
        self._is_quitting = False
        self.set_theme(False)

        self._cursor_hidden = False
        self.cursor_timer = QTimer(self)
        self.cursor_timer.setInterval(5000) 
        self.cursor_timer.timeout.connect(self._hide_cursor)
        
        QApplication.instance().installEventFilter(self)

    def _setup_ui(self):
        QApplication.instance().setApplicationName("Ataraxia Player")
        
        self.setWindowTitle("ATARAXIA Desktop Audio Manager")
        self.setWindowIcon(QIcon("assets/icons/ataraxia.svg"))
        self.setMinimumSize(950, 650)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.stats_view = StatsPanel()

        # Panel de cola de reproducción (nuevo)
        from src.views.queue_panel import QueuePanel
        self.queue_panel = QueuePanel()

        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(self.library_panel, QIcon("assets/library/folder.svg"), "Biblioteca")
        self.left_tabs.addTab(self.playlist_panel, QIcon("assets/library/playlist.svg"), "Playlists")
        self.left_tabs.addTab(self.queue_panel, QIcon("assets/library/song_dark.svg"), "Cola")
        self.left_tabs.addTab(self.stats_view, QIcon("assets/library/stats.svg"), "Estadísticas")
        self.left_tabs.setStyleSheet("QTabBar::tab { padding: 8px 15px; font-weight: bold; font-size: 12px; }")

        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(self.player_panel, QIcon("assets/library/song_light.svg"), "Reproductor")
        self.right_tabs.addTab(self.converter_panel, QIcon("assets/library/gear.svg"), "Convertidor FFmpeg")
        self.right_tabs.addTab(self.dsp_panel, QIcon("assets/library/equalizer.svg"), "Motor DSP")

        self.btn_theme = QPushButton("☀️ Modo Día")
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.setCheckable(True) 
        self.btn_theme.setStyleSheet("QPushButton { border: none; padding: 5px 15px; font-weight: bold; background: transparent; }")
        self.btn_theme.toggled.connect(self._on_theme_toggled)
        
        self.right_tabs.setCornerWidget(self.btn_theme, Qt.Corner.TopRightCorner)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.left_tabs)   
        splitter.addWidget(self.right_tabs)
        
        splitter.setSizes([300, 650]) 
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        main_layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Sistema inicializado. Listo para operar.")

        self._create_menu_bar()

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        
        file_menu = menu_bar.addMenu("Archivo")
        action_add_library = file_menu.addAction("Agregar a Biblioteca...") 
        action_add_library.triggered.connect(self._change_library_folder)
        file_menu.addSeparator()
        
        action_exit = file_menu.addAction("Salir")
        action_exit.triggered.connect(self.force_quit_requested.emit)

        tools_menu = menu_bar.addMenu("Herramientas")
        # --- NUEVA ACCIÓN EN EL MENÚ ---
        action_mini = tools_menu.addAction("Activar Mini Reproductor")
        action_mini.triggered.connect(self.mini_player_requested.emit)
        tools_menu.addSeparator()
        
        action_prefs = tools_menu.addAction("Preferencias")
        action_prefs.triggered.connect(self.open_preferences_requested.emit)
        
        help_menu = menu_bar.addMenu("Ayuda")
        action_welcome = help_menu.addAction("Mostrar bienvenida")
        action_welcome.triggered.connect(lambda: self.show_welcome(first_run=False))
        help_menu.addSeparator()
        action_about = help_menu.addAction("Acerca de Ataraxia Player")
        action_about.triggered.connect(self._show_about_dialog)

    def show_welcome(self, first_run: bool = False):
        """
        Muestra el diálogo de bienvenida. Si first_run=True, ajusta el
        copy y el botón al tono de "primera vez" (más cálido, con tips
        para empezar). Si es False, es un acceso manual desde el menú.
        """
        from src.views.welcome_dialog import WelcomeDialog
        dlg = WelcomeDialog(self, first_run=first_run)
        dlg.exec()
    
    def _show_about_dialog(self):
        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtGui import QPixmap
        
        text = (
            "<h3>ATARAXIA PLAYER</h3>"
            "<p>Desktop Audio Manager<br>Desarrollado en Python & PyQt6</p>"
            "<hr>"
            "<p><b>Créditos y Recursos Abiertos:</b></p>"
            "<ul>"
            "<li><b>Iconos de Interfaz Gráfica:</b> Proporcionados por <a href='https://phosphoricons.com'>Phosphor Icons</a> bajo Licencia MIT.</li>"
            "<li><b>Emojis y Gráficos:</b> Proporcionados por el proyecto de código abierto <a href='https://openmoji.org'>OpenMoji</a>.</li>"
            "<li><b>Icono Principal (Jacaranda):</b> Generado mediante IA (Google Gemini).</li>"
            "</ul>"
        )
        
        QMessageBox.about(self, "Acerca de Ataraxia Player", text)

    def _setup_tray(self):
        from PyQt6.QtGui import QIcon
        
        self.tray_icon = QSystemTrayIcon(self)
        icon = QIcon("assets/icons/ataraxia.png")
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("Ataraxia Player") 

        tray_menu = QMenu()
        action_restore = tray_menu.addAction("Abrir Reproductor")
        action_restore.triggered.connect(self._restore_window)
        
        # --- NUEVA ACCIÓN EN LA BANDEJA ---
        action_mini_tray = tray_menu.addAction("Abrir Mini Reproductor")
        action_mini_tray.triggered.connect(self.mini_player_requested.emit)
        
        tray_menu.addSeparator()
        
        action_prev = tray_menu.addAction("⏮ Anterior")
        action_prev.triggered.connect(self.tray_prev_requested.emit)
        
        action_play = tray_menu.addAction("▶ Reproducir / Pausar")
        action_play.triggered.connect(self.tray_play_requested.emit)
        
        action_next = tray_menu.addAction("⏭ Siguiente")
        action_next.triggered.connect(self.tray_next_requested.emit)
        
        tray_menu.addSeparator()
        
        action_quit = tray_menu.addAction("Cerrar ATARAXIA PLAYER")
        action_quit.triggered.connect(self._request_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)

    def _request_quit(self):
        self._is_quitting = True
        self.close()

    def _restore_window(self):
        self.showNormal()
        self.activateWindow()
        self.tray_icon.hide()

    def _on_tray_activated(self, reason):
        from PyQt6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_window()

    def _change_library_folder(self):
        from PyQt6.QtWidgets import QFileDialog
        carpeta = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta de Música")
        if carpeta:
            self.library_panel.add_folder_requested.emit(carpeta)

    # ══════════════════════════════════════════════════════════════════
    # SISTEMA DE TEMAS: DOS PALETAS, UNA SOLA HOJA DE MÉTRICAS
    # ──────────────────────────────────────────────────────────────────
    # Ambos temas usan EXACTAMENTE los mismos padding, bordes, radius y
    # alturas.  Solo cambian los colores.  Así, al alternar entre Día y
    # Noche no se reajustan tamaños ni posiciones — todo queda firme.
    # ══════════════════════════════════════════════════════════════════

    # Tokens compartidos por ambos temas (no cambian entre claro/oscuro)
    _UI_TOKENS = {
        "btn_padding":      "6px 14px",
        "btn_radius":       "4px",
        "btn_border_width": "1px",
        "tab_padding":      "10px 20px",
        "input_padding":    "5px 8px",
        "input_radius":     "4px",
        "input_border_w":   "1px",
        "slider_groove_h":  "4px",
        "slider_handle_sz": "14px",
        "slider_handle_r":  "7px",
    }

    # Paleta Lavanda Mist — modo claro, identidad púrpura de marca
    _LIGHT_PALETTE = {
        "bg":             "#f5f3fa",   # gris-lavanda muy claro (descansa la vista)
        "surface":        "#ffffff",   # tabs activas, listas
        "surface_alt":    "#ebe7f2",   # tabs inactivas, hover suave
        "border":         "#d4cce2",   # bordes principales
        "border_subtle":  "#e4dfee",   # bordes internos
        "text":           "#1a1a2e",   # texto principal
        "text_muted":     "#6e6b7b",   # texto secundario
        "selection":      "#d1c4e9",   # filas seleccionadas, handle slider
        "btn_bg":         "#ffffff",   # botones en reposo
        "btn_bg_hover":   "#ece6f7",   # hover con tinte lavanda
        "groove":         "#d4cce2",   # barra del slider
    }

    # Paleta Noche Profunda — modo oscuro
    _DARK_PALETTE = {
        "bg":             "#1e1e1e",
        "surface":        "#252526",
        "surface_alt":    "#2d2d30",
        "border":         "#3a3a3a",
        "border_subtle":  "#333333",
        "text":           "#ffffff",
        "text_muted":     "#aaaaaa",
        "selection":      "#37373d",
        "btn_bg":         "#333333",
        "btn_bg_hover":   "#444444",
        "groove":         "#555555",
    }

    def _build_stylesheet(self, p: dict) -> str:
        """Genera el stylesheet a partir de una paleta y los tokens compartidos."""
        t = self._UI_TOKENS
        return f"""
            QMainWindow, QWidget {{
                background-color: {p['bg']};
                color: {p['text']};
            }}
            QGroupBox {{
                border: 1px solid {p['border_subtle']};
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: {p['text_muted']};
            }}
            QTreeView, QListWidget {{
                background-color: {p['surface']};
                color: {p['text']};
                border: 1px solid {p['border_subtle']};
                border-radius: {t['input_radius']};
            }}
            QTreeView::item, QListWidget::item {{
                padding: 2px 4px;
            }}
            QTreeView::item:selected, QListWidget::item:selected {{
                background-color: {p['selection']};
                color: {p['text']};
            }}
            QTabWidget::pane {{
                border: 1px solid {p['border_subtle']};
                background-color: {p['bg']};
                top: -1px;
            }}
            QTabBar::tab {{
                background: {p['surface_alt']};
                color: {p['text_muted']};
                padding: {t['tab_padding']};
                border: 1px solid {p['border_subtle']};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background: {p['bg']};
                color: {p['text']};
                border-bottom-color: {p['bg']};
            }}
            QPushButton {{
                background-color: {p['btn_bg']};
                color: {p['text']};
                border: {t['btn_border_width']} solid {p['border']};
                border-radius: {t['btn_radius']};
                padding: {t['btn_padding']};
            }}
            QPushButton:hover {{
                background-color: {p['btn_bg_hover']};
                border-color: #9575cd;
            }}
            QPushButton:pressed {{
                background-color: {p['selection']};
            }}
            QPushButton:disabled {{
                color: {p['text_muted']};
                background-color: {p['surface_alt']};
                border-color: {p['border_subtle']};
            }}
            QLineEdit, QComboBox, QTextEdit {{
                background-color: {p['surface']};
                color: {p['text']};
                border: {t['input_border_w']} solid {p['border']};
                border-radius: {t['input_radius']};
                padding: {t['input_padding']};
                selection-background-color: {p['selection']};
                selection-color: {p['text']};
            }}
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
                border-color: #9575cd;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {p['surface']};
                color: {p['text']};
                selection-background-color: {p['selection']};
                selection-color: {p['text']};
                border: 1px solid {p['border']};
            }}
            QSlider::groove:horizontal {{
                border: 1px solid {p['border_subtle']};
                height: {t['slider_groove_h']};
                background: {p['groove']};
                margin: 2px 0;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {p['selection']};
                border: 1px solid {p['selection']};
                width: {t['slider_handle_sz']};
                margin: -6px 0;
                border-radius: {t['slider_handle_r']};
            }}
            QSlider::handle:horizontal:hover {{
                background: #9575cd;
                border-color: #9575cd;
            }}
            QSlider::groove:vertical {{
                border: 1px solid {p['border_subtle']};
                width: {t['slider_groove_h']};
                background: {p['groove']};
                margin: 0 2px;
                border-radius: 2px;
            }}
            QSlider::handle:vertical {{
                background: {p['selection']};
                border: 1px solid {p['selection']};
                height: {t['slider_handle_sz']};
                margin: 0 -6px;
                border-radius: {t['slider_handle_r']};
            }}
            QSlider::handle:vertical:hover {{
                background: #9575cd;
                border-color: #9575cd;
            }}
            QScrollBar:vertical {{
                background: {p['bg']};
                width: 12px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {p['border']};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {p['text_muted']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QMenuBar {{
                background-color: {p['bg']};
                color: {p['text']};
                border-bottom: 1px solid {p['border_subtle']};
            }}
            QMenuBar::item {{
                background: transparent;
                padding: 6px 12px;
            }}
            QMenuBar::item:selected {{
                background-color: {p['surface_alt']};
            }}
            QMenu {{
                background-color: {p['surface']};
                color: {p['text']};
                border: 1px solid {p['border']};
            }}
            QMenu::item {{
                padding: 6px 20px;
            }}
            QMenu::item:selected {{
                background-color: {p['selection']};
            }}
            QStatusBar {{
                background-color: {p['bg']};
                color: {p['text_muted']};
                border-top: 1px solid {p['border_subtle']};
            }}
            QToolTip {{
                background-color: {p['surface']};
                color: {p['text']};
                border: 1px solid {p['border']};
                padding: 4px;
            }}
        """

    def set_theme(self, is_dark: bool):
        from PyQt6.QtGui import QIcon
        from PyQt6.QtCore import QSize

        self.btn_theme.blockSignals(True)
        self.btn_theme.setChecked(is_dark)
        self.btn_theme.blockSignals(False)

        app = QApplication.instance()

        current_folder = "assets/dark_theme" if is_dark else "assets/light_theme"
        self.btn_theme.setIconSize(QSize(20, 20))

        # Seleccionar paleta y generar el stylesheet desde la plantilla común
        palette = self._DARK_PALETTE if is_dark else self._LIGHT_PALETTE
        app.setStyleSheet(self._build_stylesheet(palette))

        # Botón de tema: icono + texto
        if is_dark:
            self.btn_theme.setText(" Modo Noche")
            self.btn_theme.setIcon(QIcon(f"{current_folder}/moon.svg"))
        else:
            self.btn_theme.setText(" Modo Día")
            self.btn_theme.setIcon(QIcon(f"{current_folder}/sun.svg"))

        if hasattr(self, 'player_panel'):
            self.player_panel.update_theme_icons(is_dark)

        if hasattr(self, 'library_panel'):
            self.library_panel.update_theme_icons(is_dark)

        if hasattr(self, 'playlist_panel'):
            self.playlist_panel.update_theme_icons(is_dark)

        if hasattr(self, 'stats_view') and hasattr(self.stats_view, 'update_theme_icons'):
            self.stats_view.update_theme_icons(is_dark)

        song_tab_icon = "assets/library/song_dark.svg" if is_dark else "assets/library/song_light.svg"
        self.right_tabs.setTabIcon(0, QIcon(song_tab_icon))

    def _on_theme_toggled(self, is_dark: bool):
        self.set_theme(is_dark)
        self.theme_changed.emit(is_dark)

    def _handle_fullscreen(self, is_full: bool):
        if is_full:
            self.showFullScreen()
            self.left_tabs.hide()
            self.right_tabs.tabBar().hide()
            self.cursor_timer.start() 
        else:
            self.showNormal()
            self.left_tabs.show()
            self.right_tabs.tabBar().show()
            self.cursor_timer.stop()  
            self._show_cursor()       

    def show_status_message(self, message: str, timeout_ms: int = 5000):
        self.status_bar.showMessage(message, timeout_ms)

    def closeEvent(self, event):
        from PyQt6.QtWidgets import QMessageBox, QCheckBox, QApplication
        from PyQt6.QtCore import QSettings

        # ESCUDO ANTI-CORRUPCIÓN:
        # Si hay un restore de BD en curso, IGNORAR el cierre. Cerrar la
        # app mientras se está sobrescribiendo el archivo .db puede dejar
        # la BD corrupta (escritura parcial). El restore termina solo y
        # llama a self.close() explícitamente cuando es seguro hacerlo.
        if getattr(self, '_restore_in_progress', False):
            from PyQt6.QtWidgets import QMessageBox as _QMB
            _QMB.information(
                self,
                "Restauración en progreso",
                "Espera a que termine la restauración del respaldo.\n"
                "Cerrar ahora podría corromper la base de datos."
            )
            event.ignore()
            return

        # Si la app se está reiniciando (por restore de BD u otra razón
        # interna), omitir SIEMPRE el diálogo de confirmación y aceptar
        # directamente. El usuario ya confirmó la acción que provocó el
        # reinicio — no tiene sentido preguntarle otra vez.
        if getattr(self, '_is_restarting', False):
            event.accept()
            return

        settings = QSettings("Ataraxia", "Player")

        if getattr(self, '_is_quitting', False):
            confirmar = settings.value("confirmar_salida", "si")
            
            if confirmar == "no":
                event.accept()
                self.force_quit_requested.emit() 
                QApplication.instance().quit()   
                return

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Salir de Ataraxia")
            msg_box.setText("¿Desea salir de Ataraxia Player?")
            msg_box.setIcon(QMessageBox.Icon.Question)
            
            btn_salir = msg_box.addButton("Salir", QMessageBox.ButtonRole.YesRole)
            msg_box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
            
            cb_recordar = QCheckBox("No volver a preguntar")
            msg_box.setCheckBox(cb_recordar)
            
            msg_box.exec()
            
            if msg_box.clickedButton() == btn_salir:
                if cb_recordar.isChecked():
                    settings.setValue("confirmar_salida", "no")
                event.accept()
                self.force_quit_requested.emit()
                QApplication.instance().quit() 
            else:
                self._is_quitting = False
                event.ignore()
            return

        comportamiento_guardado = settings.value("comportamiento_cerrar")
        
        if comportamiento_guardado == "bandeja":
            event.ignore()
            self.hide()
            self.tray_icon.show()
            return
        elif comportamiento_guardado == "cerrar":
            event.accept()
            self.force_quit_requested.emit()
            QApplication.instance().quit()
            return
            
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Cerrar Ataraxia")
        msg_box.setText("¿Deseas seguir escuchando en segundo plano?")
        msg_box.setInformativeText("El reproductor se minimizará a la bandeja del sistema.")
        msg_box.setIcon(QMessageBox.Icon.Question)
        
        btn_bandeja = msg_box.addButton("Segundo plano", QMessageBox.ButtonRole.YesRole)
        btn_cerrar = msg_box.addButton("Cerrar por completo", QMessageBox.ButtonRole.NoRole)
        msg_box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        
        cb_recordar = QCheckBox("No volver a preguntar")
        msg_box.setCheckBox(cb_recordar)
        
        msg_box.exec()
        
        boton_pulsado = msg_box.clickedButton()
        
        if boton_pulsado == btn_bandeja:
            if cb_recordar.isChecked():
                settings.setValue("comportamiento_cerrar", "bandeja")
            event.ignore()
            self.hide()
            self.tray_icon.show()
            
        elif boton_pulsado == btn_cerrar:
            if cb_recordar.isChecked():
                settings.setValue("comportamiento_cerrar", "cerrar")
            event.accept()
            self.force_quit_requested.emit()
            QApplication.instance().quit()
            
        else:
            event.ignore()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress):
            if self._cursor_hidden:
                self._show_cursor()
            if self.isFullScreen():
                self.cursor_timer.start()
            else:
                self.cursor_timer.stop()
        return super().eventFilter(obj, event)

    def _hide_cursor(self):
        if self.isFullScreen() and not self._cursor_hidden:
            QApplication.setOverrideCursor(Qt.CursorShape.BlankCursor)
            self._cursor_hidden = True
            self.cursor_timer.stop() 

    def _show_cursor(self):
        if self._cursor_hidden:
            QApplication.restoreOverrideCursor()
            self._cursor_hidden = False