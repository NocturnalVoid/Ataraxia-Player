# -*- coding: utf-8 -*-
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QSlider, QTextEdit, QGridLayout, QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QShortcut, QKeySequence, QIcon
from src.views.visualizer_widget import VisualizerWidget

class PlayerPanel(QWidget):
    
    play_toggled = pyqtSignal()
    next_clicked = pyqtSignal()
    prev_clicked = pyqtSignal()
    slider_moved = pyqtSignal(int)
    
    track_index_changed = pyqtSignal(int)
    volume_changed = pyqtSignal(int)
    
    loop_mode_changed = pyqtSignal(int)     
    shuffle_mode_changed = pyqtSignal(bool) 
    fullscreen_requested = pyqtSignal(bool)
    file_dropped = pyqtSignal(str)
    audio_mode_changed = pyqtSignal(str)
    
    mini_player_requested = pyqtSignal()
    fetch_lyrics_requested = pyqtSignal()
    favorite_toggled = pyqtSignal(bool)   # emite el nuevo estado (True = favorito)

    def __init__(self):
        super().__init__()
        self.loop_state = 0 
        self.is_shuffle = False
        self.is_fullscreen = False 
        self.is_playing = False
        self.current_image_path = "assets/default_audio_icon.svg"
        self.current_theme = "dark_theme" 
        
        self.is_lyrics_visible = False
        self.is_visualizer_visible = False
        self._last_lyric_index = -1
        # Flag para detectar si ya cargamos las letras no-sincronizadas
        # actuales. Evita repintar el QTextEdit en cada tick del sync_timer
        # (lo cual reseteaba el scroll y hacía imposible leer textos largos).
        self._unsynced_lyrics_loaded = False

        # Modo compacto: se actualiza por resizeEvent. Empieza en NORMAL.
        self._compact_mode = self._MODE_NORMAL
        
        self.setAcceptDrops(True) 
        
        self.btn_css_inactive = """
            QPushButton { border-radius: 22px; border: 1.5px solid #777; background-color: transparent; }
            QPushButton:hover { background-color: rgba(209, 196, 233, 80); border: 1.5px solid #d1c4e9; }
            QPushButton:pressed { background-color: rgba(209, 196, 233, 150); }
        """
        self.btn_css_active = """
            QPushButton { border-radius: 22px; border: 1.5px solid #d1c4e9; background-color: #d1c4e9; }
            QPushButton:hover { background-color: #b39ddb; border: 1.5px solid #b39ddb; }
            QPushButton:pressed { background-color: #9575cd; }
        """
        
        self._setup_ui()
        self._setup_shortcuts()
        self._pre_mute_volume = 80
        self.is_muted = False
        
        self.update_theme_icons(is_dark_mode=True)

    def _setup_ui(self):
        # 1. Contenedor Maestro (Sin centrar, para permitir anclajes en las esquinas)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)

        # --- BARRA SUPERIOR ABSOLUTA (Botones de utilidad) ---
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.addStretch() # Empuja los botones a la derecha

        # Botón "Buscar letras online"
        self.btn_fetch_lyrics = QPushButton("", self)
        self.btn_fetch_lyrics.setFixedSize(45, 45)
        self.btn_fetch_lyrics.setIconSize(QSize(22, 22))
        self.btn_fetch_lyrics.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fetch_lyrics.setToolTip("Buscar letras en línea (lrclib.net)")
        self.btn_fetch_lyrics.setStyleSheet(self.btn_css_inactive)
        self.btn_fetch_lyrics.clicked.connect(self.fetch_lyrics_requested.emit)
        top_bar.addWidget(self.btn_fetch_lyrics)

        self.btn_miniplayer = QPushButton("", self)
        # Aplicamos el mismo tamaño, icono y CSS que los controles multimedia
        self.btn_miniplayer.setFixedSize(45, 45)
        self.btn_miniplayer.setIconSize(QSize(24, 24))
        self.btn_miniplayer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_miniplayer.setToolTip("Desacoplar Mini Reproductor")
        self.btn_miniplayer.setStyleSheet(self.btn_css_inactive) 
        self.btn_miniplayer.clicked.connect(self.mini_player_requested.emit)
        
        top_bar.addWidget(self.btn_miniplayer)
        outer_layout.addLayout(top_bar)
        # -------------------------------------------

        # 2. Contenedor Secundario (Centrado, para el Reproductor en sí)
        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter) 

        self.cover_container = QWidget(self)
        overlay_layout = QGridLayout(self.cover_container)
        overlay_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_cover = QLabel(self.cover_container)
        self.lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addWidget(self.lbl_cover, 0, 0)

        # ══════════════════════════════════════════════════════════════════
        # BOTÓN DE FAVORITO
        # Superpuesto en la esquina superior-derecha de la carátula.
        # - Transparente por defecto (no se ve)
        # - Aparece al pasar el cursor por cualquier parte del cover
        # - Si la pista es favorita, siempre visible con relleno rojo
        # - Los mismos estilos funcionan en modo claro y oscuro (fondo semi-
        #   transparente negro, que se ve bien sobre cualquier imagen)
        # ══════════════════════════════════════════════════════════════════
        self.btn_favorite = QPushButton("", self.cover_container)
        self.btn_favorite.setFixedSize(36, 36)
        self.btn_favorite.setIconSize(QSize(22, 22))
        self.btn_favorite.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_favorite.setToolTip("Añadir a favoritos")
        self.btn_favorite.clicked.connect(self._on_favorite_clicked)
        self.btn_favorite.setIcon(QIcon("assets/library/heart_empty.svg"))
        self.btn_favorite.raise_()
        self._is_favorite = False
        self._is_hover_over_cover = False
        self._favorite_visible = False    # Controla si la pista está cargada
        self._apply_favorite_style()

        # Habilitar hover tracking en el contenedor y el label del cover
        self.cover_container.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.lbl_cover.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.cover_container.installEventFilter(self)
        self.lbl_cover.installEventFilter(self)
        self.btn_favorite.installEventFilter(self)

        self.text_lyrics = QTextEdit(self.cover_container)
        self.text_lyrics.setReadOnly(True)
        self.text_lyrics.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_lyrics.setStyleSheet("""
            QTextEdit {
                background-color: rgba(10, 10, 10, 190); 
                border: none; 
                padding: 20px;
            }
            QScrollBar:vertical { width: 10px; background: transparent; }
            QScrollBar::handle:vertical { background: #555; border-radius: 5px; }
        """)
        self.text_lyrics.hide()
        overlay_layout.addWidget(self.text_lyrics, 0, 0)

        self.visualizer = VisualizerWidget(self.cover_container)
        self.visualizer.hide()
        overlay_layout.addWidget(self.visualizer, 0, 0)

        main_layout.addWidget(self.cover_container)

        self.lbl_title = QLabel("Titulo de la pista", self)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        self.lbl_artist_album = QLabel("Artista - Album", self)
        self.lbl_artist_album.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_artist_album.setStyleSheet("font-size: 14px; color: gray;")
        
        main_layout.addWidget(self.lbl_title)
        main_layout.addWidget(self.lbl_artist_album)

        time_layout = QHBoxLayout()
        self.lbl_time_current = QLabel("00:00", self)
        self.lbl_time_total = QLabel("00:00", self)
        
        self.slider_progress = QSlider(Qt.Orientation.Horizontal, self)
        self.slider_progress.setRange(0, 100)
        self.slider_progress.sliderReleased.connect(self._on_slider_released)
        
        time_layout.addWidget(self.lbl_time_current)
        time_layout.addWidget(self.slider_progress)
        time_layout.addWidget(self.lbl_time_total)
        main_layout.addLayout(time_layout)

        bottom_layout = QHBoxLayout()
        
        # --- LADO IZQUIERDO: Botón visualizador (espejo del volumen en la derecha) ---
        self.btn_visualizer = QPushButton("", self)
        self.btn_visualizer.setFixedSize(45, 45)
        self.btn_visualizer.setIconSize(QSize(24, 24))
        self.btn_visualizer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_visualizer.setStyleSheet(self.btn_css_inactive)
        self.btn_visualizer.setToolTip("Visualizador de audio")
        self.btn_visualizer.clicked.connect(self._toggle_visualizer)

        # Guardamos referencia: el modo compacto necesita modificar su ancho
        self.left_widget = QWidget()
        self.left_widget.setFixedWidth(140)
        left_layout = QHBoxLayout(self.left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        left_layout.addWidget(self.btn_visualizer)
        
        bottom_layout.addWidget(self.left_widget)
        bottom_layout.addStretch() 
        
        # Guardamos referencia al controls_layout: el modo compacto reduce su spacing
        self.controls_layout = QHBoxLayout()
        self.controls_layout.setSpacing(15)
        
        self.btn_shuffle = QPushButton("", self)
        self.btn_loop = QPushButton("", self)
        self.btn_prev = QPushButton("", self)
        self.btn_play = QPushButton("", self)
        self.btn_next = QPushButton("", self) 
        self.btn_lyrics = QPushButton("", self)
        self.btn_fullscreen = QPushButton("", self)
        
        botones = [self.btn_shuffle, self.btn_loop, self.btn_prev, self.btn_play, 
                   self.btn_next, self.btn_lyrics, self.btn_fullscreen]
                   
        for btn in botones:
            btn.setFixedSize(45, 45) 
            btn.setIconSize(QSize(24, 24)) 
            btn.setCursor(Qt.CursorShape.PointingHandCursor) 
            btn.setStyleSheet(self.btn_css_inactive) 
        
        self.btn_prev.clicked.connect(self.prev_clicked.emit)
        self.btn_play.clicked.connect(self.play_toggled.emit)
        self.btn_next.clicked.connect(self.next_clicked.emit)
        self.btn_shuffle.clicked.connect(self._toggle_shuffle)
        self.btn_loop.clicked.connect(self._toggle_loop)
        self.btn_lyrics.clicked.connect(self._toggle_lyrics)
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        
        for btn in botones:
            self.controls_layout.addWidget(btn)
            
        bottom_layout.addLayout(self.controls_layout)
        bottom_layout.addStretch()
        
        # Guardamos referencia al volume_widget: el modo compacto reduce su ancho
        self.volume_widget = QWidget()
        self.volume_widget.setFixedWidth(140)
        volume_layout = QHBoxLayout(self.volume_widget)
        volume_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_volume = QPushButton("", self)
        self.btn_volume.setFixedSize(24, 24)
        self.btn_volume.setIconSize(QSize(24, 24))
        self.btn_volume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_volume.setStyleSheet("border: none; background: transparent;")
        self.btn_volume.clicked.connect(self._toggle_mute)
        
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80) 
        self.volume_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.volume_slider.valueChanged.connect(self._on_volume_slider_changed)
        
        volume_layout.addWidget(self.btn_volume)
        volume_layout.addWidget(self.volume_slider)

        bottom_layout.addWidget(self.volume_widget)
        
        main_layout.addLayout(bottom_layout)

        # 3. Anidamos el Reproductor Centrado dentro del Contenedor Maestro
        outer_layout.addLayout(main_layout)

        self._render_cover()      

    # ══════════════════════════════════════════════════════════════════
    # MODO COMPACTO (RESPONSIVO)
    # ══════════════════════════════════════════════════════════════════
    # Cuando el panel del reproductor queda con muy poco ancho (pantalla
    # dividida, ventana encogida), los botones de 45×45 con spacing de
    # 15px desbordan visualmente. Aplicamos tres niveles que comprimen
    # progresivamente CADA componente que ocupa horizontal:
    #
    #   - NORMAL    (≥ 480px): tamaños originales
    #   - COMPACT   (340–479px): botones a 36×36, spacing reducido,
    #                            laterales más estrechos
    #   - ULTRA     (< 340px): botones a 30×30, oculta botones utilitarios
    #                          y comprime al máximo
    #
    # El umbral 480 está calibrado pensando en: 7 botones × 45px (315) +
    # 6 gaps × 15px (90) + 2 laterales × 140 (280) = 685px mínimo. Por
    # debajo de eso ya hay desbordamiento.

    COMPACT_THRESHOLD       = 480
    ULTRA_COMPACT_THRESHOLD = 340

    _MODE_NORMAL = 0
    _MODE_COMPACT = 1
    _MODE_ULTRA = 2

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = event.size().width()
        if w < self.ULTRA_COMPACT_THRESHOLD:
            new_mode = self._MODE_ULTRA
        elif w < self.COMPACT_THRESHOLD:
            new_mode = self._MODE_COMPACT
        else:
            new_mode = self._MODE_NORMAL
        if new_mode != self._compact_mode:
            self._compact_mode = new_mode
            self._apply_compact_mode(new_mode)

    def _apply_compact_mode(self, mode: int):
        """
        Ajusta TODOS los componentes que ocupan espacio horizontal en la
        barra inferior, no solo los tamaños de los botones. Sin esto, los
        widgets con setFixedWidth siguen ocupando su ancho original y
        empujan los botones a amontonarse.
        """
        # Parámetros por modo
        if mode == self._MODE_ULTRA:
            btn_size, icon_size = 30, 16
            ctrl_spacing = 4
            lateral_width = 50            # solo cabe el botón visualizer/volume
            show_utility_top = False      # ocultar lupa y miniplayer
            show_visualizer = False       # ocultar visualizer en ultra para liberar espacio
        elif mode == self._MODE_COMPACT:
            btn_size, icon_size = 36, 20
            ctrl_spacing = 8
            lateral_width = 80
            show_utility_top = True
            show_visualizer = True
        else:  # NORMAL
            btn_size, icon_size = 45, 24
            ctrl_spacing = 15
            lateral_width = 140
            show_utility_top = True
            show_visualizer = True

        # 1) Botones centrales: shuffle, loop, prev, play, next, lyrics, fullscreen
        center_buttons = [
            getattr(self, name, None) for name in
            ("btn_shuffle", "btn_loop", "btn_prev", "btn_play",
             "btn_next", "btn_lyrics", "btn_fullscreen")
        ]
        for btn in center_buttons:
            if btn is not None:
                btn.setFixedSize(btn_size, btn_size)
                btn.setIconSize(QSize(icon_size, icon_size))

        # 2) Spacing del controls_layout (en NORMAL es 15px, en COMPACT 8px, en ULTRA 4px)
        if hasattr(self, "controls_layout") and self.controls_layout is not None:
            self.controls_layout.setSpacing(ctrl_spacing)

        # 3) Botón visualizer (izquierdo). En ultra, se oculta.
        if hasattr(self, "btn_visualizer"):
            self.btn_visualizer.setFixedSize(btn_size, btn_size)
            self.btn_visualizer.setIconSize(QSize(icon_size, icon_size))
            self.btn_visualizer.setVisible(show_visualizer)

        # 4) Barra superior: lupa + miniplayer
        for name in ("btn_fetch_lyrics", "btn_miniplayer"):
            btn = getattr(self, name, None)
            if btn is None:
                continue
            btn.setFixedSize(btn_size, btn_size)
            btn.setIconSize(QSize(icon_size - 2, icon_size - 2))
            btn.setVisible(show_utility_top)

        # 5) Widgets laterales (left_widget y volume_widget) — CRÍTICO para que
        # el stretch entre ellos pueda comprimir el centro
        if hasattr(self, "left_widget"):
            self.left_widget.setFixedWidth(lateral_width)
        if hasattr(self, "volume_widget"):
            self.volume_widget.setFixedWidth(lateral_width)
            # En ultra, ocultar el slider y dejar solo el botón de mute
            if hasattr(self, "volume_slider"):
                self.volume_slider.setVisible(mode != self._MODE_ULTRA)

        # 6) Cover: se re-renderiza al nuevo tamaño objetivo
        if hasattr(self, "current_image_path"):
            self._render_cover()

        # 7) Reposicionar el corazón sobre el cover (su posición depende del tamaño)
        if hasattr(self, "btn_favorite"):
            self._position_favorite_button()

    def update_theme_icons(self, is_dark_mode: bool):
        self.current_theme = "dark_theme" if is_dark_mode else "light_theme"
        folder = f"assets/{self.current_theme}"
        
        self.btn_prev.setIcon(QIcon(f"{folder}/prev.svg"))
        self.btn_next.setIcon(QIcon(f"{folder}/next.svg"))
        self.btn_lyrics.setIcon(QIcon(f"{folder}/lyrics.svg"))
        self.btn_shuffle.setIcon(QIcon(f"{folder}/shuffle.svg"))
        
        # El icono del pip se actualiza a su versión clara/oscura
        self.btn_miniplayer.setIcon(QIcon(f"{folder}/pip.svg")) 
        self.btn_visualizer.setIcon(QIcon(f"{folder}/visualizer.svg"))
        # El botón de buscar letras usa el icono de búsqueda (tema-agnóstico)
        self.btn_fetch_lyrics.setIcon(QIcon("assets/library/search.svg"))
        
        self._update_volume_icon()
        self._update_play_icon()
        self._update_loop_icon()
        self._update_fullscreen_icon()

    def _on_favorite_clicked(self):
        """Toggle del estado de favorito + emite la señal para persistir."""
        self._is_favorite = not self._is_favorite
        self._apply_favorite_style()
        self._update_favorite_visibility()
        self.favorite_toggled.emit(self._is_favorite)

    def set_favorite_state(self, is_favorite: bool):
        """Actualiza el corazón sin disparar la señal (útil al cambiar de pista)."""
        self._is_favorite = bool(is_favorite)
        self._apply_favorite_style()
        self._update_favorite_visibility()

    def _apply_favorite_style(self):
        """Estilo e icono según el estado con 'Glass Halo' para contrastar en fondos negros."""
        if self._is_favorite:
            # Favorito: relleno rojo siempre visible. Borde sutil.
            self.btn_favorite.setIcon(QIcon("assets/library/heart_full.svg"))
            self.btn_favorite.setToolTip("Quitar de favoritos")
            self.btn_favorite.setStyleSheet("""
                QPushButton {
                    border: 1px solid rgba(255, 255, 255, 80);
                    border-radius: 18px;
                    background-color: rgba(0, 0, 0, 100);
                }
                QPushButton:hover {
                    background-color: rgba(0, 0, 0, 160);
                    border: 1px solid rgba(255, 255, 255, 120);
                }
                QPushButton:pressed {
                    background-color: rgba(0, 0, 0, 200);
                }
            """)
        else:
            # No favorito: ícono outline blanco con Anillo de Cristal
            self.btn_favorite.setIcon(QIcon("assets/library/heart_empty.svg"))
            self.btn_favorite.setToolTip("Añadir a favoritos")
            self.btn_favorite.setStyleSheet("""
                QPushButton {
                    border: 1px solid rgba(255, 255, 255, 60); /* El anillo salvador */
                    border-radius: 18px;
                    background-color: rgba(0, 0, 0, 80);
                    color: white;
                }
                QPushButton:hover {
                    background-color: rgba(0, 0, 0, 160);
                    border: 1px solid rgba(255, 255, 255, 120);
                }
                QPushButton:pressed {
                    background-color: rgba(0, 0, 0, 210);
                }
            """)

    def show_favorite_button(self, visible: bool):
        """Indica al panel si hay una pista cargada (para decidir si mostrar el corazón)."""
        self._favorite_visible = visible
        self._update_favorite_visibility()

    def _update_favorite_visibility(self):
        """
        Decide si el botón debe estar visible, siguiendo esta lógica:
         - Si NO hay pista cargada → oculto siempre
         - Si hay un overlay tapando la carátula (letras o visualizador) → oculto
         - Si la pista es favorita → siempre visible (como indicador de estado)
         - Si no es favorita → solo visible cuando el cursor está sobre el cover
        """
        if not self._favorite_visible:
            self.btn_favorite.hide()
            return

        # Si hay un overlay tapando la cover, no tiene sentido mostrar el
        # corazón: visualmente quedaría flotando sobre las barras del
        # visualizador o sobre el texto de las letras, y permitiría clics
        # accidentales para quitar/poner el favorito.
        if self.is_lyrics_visible or self.is_visualizer_visible:
            self.btn_favorite.hide()
            return

        should_show = self._is_favorite or self._is_hover_over_cover
        if should_show:
            self._position_favorite_button()
            self.btn_favorite.show()
            self.btn_favorite.raise_()
        else:
            self.btn_favorite.hide()

    def _position_favorite_button(self):
        """Coloca el corazón exactamente en la esquina superior derecha de la imagen dibujada."""
        if not hasattr(self, 'btn_favorite') or not hasattr(self, 'cover_container'):
            return
            
        margin = 12
        pm = self.lbl_cover.pixmap()
        
        if pm and not pm.isNull():
            # Dimensiones de la imagen real (el Pixmap)
            pm_w = pm.width()
            pm_h = pm.height()
            
            # Dimensiones y posición del contenedor
            lbl_x = self.lbl_cover.x()
            lbl_y = self.lbl_cover.y()
            lbl_w = self.lbl_cover.width()
            lbl_h = self.lbl_cover.height()
            
            # Como la imagen está centrada, calculamos su posición interna exacta
            img_x = lbl_x + (lbl_w - pm_w) // 2
            img_y = lbl_y + (lbl_h - pm_h) // 2
            
            # Posicionamos restando el botón al borde derecho de la imagen
            x = img_x + pm_w - self.btn_favorite.width() - margin
            y = img_y + margin
        else:
            x = self.cover_container.width() - self.btn_favorite.width() - margin
            y = margin

        self.btn_favorite.move(x, y)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        # Detectar entrada/salida del cursor combinando label y botón
        if obj in (self.cover_container, self.lbl_cover, self.btn_favorite):
            t = event.type()
            if t in (QEvent.Type.Enter, QEvent.Type.HoverEnter, QEvent.Type.Leave, QEvent.Type.HoverLeave):
                # Es hover válido si el ratón está sobre la carátula O sobre el botón del corazón
                is_hovering = self.lbl_cover.underMouse() or self.btn_favorite.underMouse()
                
                if self._is_hover_over_cover != is_hovering:
                    self._is_hover_over_cover = is_hovering
                    self._update_favorite_visibility()
            elif t in (QEvent.Type.Resize, QEvent.Type.Show):
                self._position_favorite_button()
        return super().eventFilter(obj, event)

    def set_fetch_lyrics_state(self, state: str):
        """
        Cambia el aspecto del botón según el estado de la búsqueda.
        state ∈ {"idle", "loading", "success", "not_found", "error"}
        """
        btn = self.btn_fetch_lyrics
        if state == "idle":
            btn.setEnabled(True)
            btn.setToolTip("Buscar letras en línea (lrclib.net)")
            btn.setStyleSheet(self.btn_css_inactive)
        elif state == "loading":
            btn.setEnabled(False)
            btn.setToolTip("Buscando letras…")
            btn.setStyleSheet(self.btn_css_active)
        elif state == "success":
            btn.setEnabled(True)
            btn.setToolTip("Letras encontradas ✓")
            btn.setStyleSheet(self.btn_css_active)
        elif state == "not_found":
            btn.setEnabled(True)
            btn.setToolTip("No se encontraron letras para esta canción")
            btn.setStyleSheet(self.btn_css_inactive)
        elif state == "error":
            btn.setEnabled(True)
            btn.setToolTip("Error de red al buscar letras")
            btn.setStyleSheet(self.btn_css_inactive)

    def _update_play_icon(self):
        icon_name = "pause.svg" if self.is_playing else "play.svg"
        self.btn_play.setIcon(QIcon(f"assets/{self.current_theme}/{icon_name}"))

    def _update_loop_icon(self):
        icon_name = "loop_one.svg" if self.loop_state == 2 else "loop.svg"
        self.btn_loop.setIcon(QIcon(f"assets/{self.current_theme}/{icon_name}"))

    def _update_fullscreen_icon(self):
        icon_name = "fullscreen_exit.svg" if self.is_fullscreen else "fullscreen.svg"
        self.btn_fullscreen.setIcon(QIcon(f"assets/{self.current_theme}/{icon_name}"))

    def _on_mode_changed(self, text: str):
        if text == "Normal":
            self.combo_mode.setStyleSheet("")
        else:
            self.combo_mode.setStyleSheet("background-color: #d1c4e9; color: black; font-weight: bold;")
        self.slider_progress.setEnabled(True)
        self.slider_progress.setStyleSheet("")
        self.audio_mode_changed.emit(text)

    def _setup_shortcuts(self):
        self.shortcut_space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self.shortcut_space.activated.connect(self.play_toggled.emit)
        self.shortcut_f = QShortcut(QKeySequence(Qt.Key.Key_F), self)
        self.shortcut_f.activated.connect(self._toggle_fullscreen)
        self.shortcut_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.shortcut_esc.activated.connect(self._force_exit_fullscreen)
        self.shortcut_right = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self.shortcut_right.activated.connect(self._step_forward)
        self.shortcut_left = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self.shortcut_left.activated.connect(self._step_backward)
        # Ctrl+D: toggle favorito (estándar en muchos players)
        self.shortcut_fav = QShortcut(QKeySequence("Ctrl+D"), self)
        self.shortcut_fav.activated.connect(self._on_favorite_clicked)

    def _step_forward(self):
        if self.slider_progress.maximum() > 0 and self.slider_progress.isEnabled():
            nuevo_valor = min(self.slider_progress.value() + 10, self.slider_progress.maximum())
            self.slider_progress.setValue(nuevo_valor)
            self.slider_moved.emit(nuevo_valor)

    def _step_backward(self):
        if self.slider_progress.maximum() > 0 and self.slider_progress.isEnabled():
            nuevo_valor = max(self.slider_progress.value() - 10, 0)
            self.slider_progress.setValue(nuevo_valor)
            self.slider_moved.emit(nuevo_valor)

    def _force_exit_fullscreen(self):
        if self.is_fullscreen:
            self._toggle_fullscreen()

    def _toggle_loop(self):
        self.loop_state = (self.loop_state + 1) % 3
        if self.loop_state == 0:
            self.btn_loop.setStyleSheet(self.btn_css_inactive) 
        else:
            self.btn_loop.setStyleSheet(self.btn_css_active) 
        self._update_loop_icon()
        self.loop_mode_changed.emit(self.loop_state)

    def _toggle_shuffle(self):
        self.is_shuffle = not self.is_shuffle
        if self.is_shuffle:
            self.btn_shuffle.setStyleSheet(self.btn_css_active)
        else:
            self.btn_shuffle.setStyleSheet(self.btn_css_inactive)
        self.shuffle_mode_changed.emit(self.is_shuffle)

    def _toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.btn_fullscreen.setStyleSheet(self.btn_css_active)
            self.lbl_title.setStyleSheet("font-size: 32px; font-weight: bold;") 
            self.lbl_artist_album.setStyleSheet("font-size: 20px; color: gray;")
            self.btn_miniplayer.hide() # Ocultamos el PIP en pantalla completa
        else:
            self.btn_fullscreen.setStyleSheet(self.btn_css_inactive)
            self.lbl_title.setStyleSheet("font-size: 18px; font-weight: bold;") 
            self.lbl_artist_album.setStyleSheet("font-size: 14px; color: gray;")
            self.btn_miniplayer.show()
            
        self._update_fullscreen_icon()
        self._render_cover() 
        self.fullscreen_requested.emit(self.is_fullscreen)

    def _toggle_lyrics(self):
        self.is_lyrics_visible = not self.is_lyrics_visible
        if self.is_lyrics_visible:
            if self.is_visualizer_visible:
                self.is_visualizer_visible = False
                self.btn_visualizer.setStyleSheet(self.btn_css_inactive)
                self.visualizer.stop()
                self.visualizer.hide()
            self.btn_lyrics.setStyleSheet(self.btn_css_active)
            self.text_lyrics.show()
        else:
            self.btn_lyrics.setStyleSheet(self.btn_css_inactive)
            self.text_lyrics.hide()
        # Al cambiar el estado de overlays, recalcular visibilidad del corazón
        self._update_favorite_visibility()

    def _toggle_visualizer(self):
        self.is_visualizer_visible = not self.is_visualizer_visible
        if self.is_visualizer_visible:
            # Apagar letras si estaban activas
            if self.is_lyrics_visible:
                self.is_lyrics_visible = False
                self.btn_lyrics.setStyleSheet(self.btn_css_inactive)
                self.text_lyrics.hide()
            self.btn_visualizer.setStyleSheet(self.btn_css_active)
            self.visualizer.set_playing(self.is_playing)
            self.visualizer.show()
            self.visualizer.start()
        else:
            self.btn_visualizer.setStyleSheet(self.btn_css_inactive)
            self.visualizer.stop()
            self.visualizer.hide()
        # Al cambiar el estado de overlays, recalcular visibilidad del corazón
        self._update_favorite_visibility()

    def update_metadata(self, title: str, artist: str, album: str):
        t = str(title) if title else "Desconocido"
        a = str(artist) if artist else "Desconocido"
        al = str(album) if album else "Desconocido"
        self.lbl_title.setText(t)
        self.lbl_artist_album.setText(f"{a} - {al}")

    def set_cover_image(self, image_path: str):
        if image_path and os.path.exists(image_path):
            self.current_image_path = image_path
        else:
            self.current_image_path = "assets/default_audio_icon.svg"
        self._render_cover()
        self._last_lyric_index = -1 
        # Al cambiar de canción, las letras unsynced anteriores ya no aplican.
        # El próximo tick volverá a pintarlas (una sola vez) para la nueva pista.
        self._unsynced_lyrics_loaded = False

    def _render_cover(self):
        # Determinar el tamaño objetivo según el modo compacto
        if self.is_fullscreen:
            target_size = 700
        elif self._compact_mode == self._MODE_ULTRA:
            target_size = 220
        elif self._compact_mode == self._MODE_COMPACT:
            target_size = 300
        else:
            target_size = 400

        # Para archivos SVG (placeholder de metadatos vacíos), usamos QIcon.pixmap
        # que renderiza el vector directamente al tamaño pedido — nítido a
        # cualquier resolución, sin upscaling de bitmap.
        # Para PNG/JPG (covers reales), QIcon también funciona y es más eficiente:
        # internamente respeta el tamaño nativo si es similar al pedido y aplica
        # escalado de calidad cuando difiere.
        if self.current_image_path.lower().endswith(".svg"):
            pix = QIcon(self.current_image_path).pixmap(QSize(target_size, target_size))
        else:
            # Mantener el camino de bitmap original para PNG/JPG, descartando
            # explícitamente el original tras escalar para liberar memoria.
            original = QPixmap(self.current_image_path)
            if not original.isNull():
                pix = original.scaled(
                    target_size, target_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            else:
                pix = QPixmap()
            original = None

        if not pix.isNull():
            self.lbl_cover.setPixmap(pix)
        else:
            # Último recurso: usar el album.svg interno
            fallback = QIcon("assets/library/album.svg").pixmap(QSize(200, 200))
            self.lbl_cover.setPixmap(fallback)

        self._position_favorite_button()

    def update_progress_bar(self, current_seconds: int, total_seconds: int):
        if total_seconds > 0:
            self.slider_progress.setMaximum(total_seconds)
            if not self.slider_progress.isSliderDown() and self.slider_progress.isEnabled():
                self.slider_progress.setValue(current_seconds)
        self.visualizer.set_position(current_seconds * 1000)
        def format_time(secs):
            m, s = divmod(secs, 60)
            return f"{m:02d}:{s:02d}"
        self.lbl_time_current.setText(format_time(current_seconds))
        self.lbl_time_total.setText(format_time(total_seconds))

    def update_lyrics_karaoke(self, lines: list, current_index: int, is_synced: bool):
        if not self.is_lyrics_visible:
            return
            
        if not lines:
            if self.text_lyrics.toPlainText() != "No hay letra disponible.":
                self.text_lyrics.setHtml("<br><br><br><center><h3 style='color: white;'>No hay letra disponible.</h3></center>")
                # Reset del flag por si antes había unsynced cargadas
                self._unsynced_lyrics_loaded = False
            return
            
        if not is_synced:
            # Letras de tipo .txt: NO hay karaoke, el usuario lee libremente.
            # Solo pintamos UNA VEZ por canción. Si seguimos llamando a
            # setHtml() en cada tick del sync_timer, Qt resetea el scroll
            # al inicio y se vuelve imposible leer textos largos.
            if not self._unsynced_lyrics_loaded:
                html = f"<center><span style='color: white; font-size: 18px;'>{'<br><br>'.join(lines)}</span></center>"
                self.text_lyrics.setHtml(html)
                self._unsynced_lyrics_loaded = True
            return
            
        # A partir de aquí, letras sincronizadas (.lrc, .srt) en modo karaoke
        # Cualquier render previo no-sincronizado deja de aplicar
        self._unsynced_lyrics_loaded = False

        if self._last_lyric_index == current_index:
            return 
            
        self._last_lyric_index = current_index
        
        html = "<center><br><br><br>" 
        for i, line in enumerate(lines):
            if i == current_index:
                html += f"<span style='color: white; font-size: 26px; font-weight: bold;'>{line}</span><br><br>"
            elif i < current_index:
                html += f"<span style='color: #666666; font-size: 18px;'>{line}</span><br><br>"
            else:
                html += f"<span style='color: #aaaaaa; font-size: 18px;'>{line}</span><br><br>"
        html += "<br><br><br></center>"
        
        self.text_lyrics.setHtml(html)
        
        scrollbar = self.text_lyrics.verticalScrollBar()
        max_scroll = scrollbar.maximum()
        if max_scroll > 0 and len(lines) > 0:
            target_pos = int((current_index / len(lines)) * max_scroll)
            scrollbar.setValue(target_pos)

    def set_play_state(self, is_playing: bool):
        self.is_playing = is_playing
        self.visualizer.set_playing(is_playing)
        self._update_play_icon()

    def set_track(self, filepath: str):
        """Notifies the visualizer that a new track has been loaded."""
        self.visualizer.load_track(filepath)

    def set_loop_state(self, mode: int):
        """Actualiza el estado del bucle impulsado desde el controlador (sin emitir señal)."""
        self.loop_state = mode
        self.btn_loop.setStyleSheet(
            self.btn_css_active if mode != 0 else self.btn_css_inactive
        )
        self._update_loop_icon()
    
    def _on_slider_released(self):
        valor_segundos = self.slider_progress.value()
        self.slider_moved.emit(valor_segundos)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            valid_exts = ('.mp3', '.wav', '.flac', '.ogg', '.m4a', '.opus', '.aac', '.webm', '.mka', '.wma')
            
            if url.isLocalFile() and url.toString().lower().endswith(valid_exts):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        url = event.mimeData().urls()[0]
        filepath = url.toLocalFile()
        self.file_dropped.emit(filepath)

    def _toggle_mute(self):
        if self.is_muted:
            self.is_muted = False
            restore_val = self._pre_mute_volume if self._pre_mute_volume > 0 else 50
            self.volume_slider.setValue(restore_val)
        else:
            self.is_muted = True
            self._pre_mute_volume = self.volume_slider.value()
            self.volume_slider.setValue(0)
            
        self._update_volume_icon()

    def _on_volume_slider_changed(self, value: int):
        if value > 0 and self.is_muted:
            self.is_muted = False
            
        self._update_volume_icon()
        self.volume_changed.emit(value)

    def _update_volume_icon(self):
        folder = f"assets/{self.current_theme}"
        val = self.volume_slider.value()

        if self.is_muted:
            icon_name = "volume_mute.svg"
        elif val == 0:
            icon_name = "volume_none.svg"
        elif val <= 49:
            icon_name = "volume_low.svg"
        else:
            icon_name = "volume_all.svg"

        self.btn_volume.setIcon(QIcon(f"{folder}/{icon_name}"))