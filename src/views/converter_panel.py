# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QComboBox, QProgressBar, QFileDialog, 
                             QMessageBox, QGroupBox, QGridLayout, QLineEdit)
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, pyqtSignal
import os
import tempfile
from src.models.metadata_manager import MetadataManager

class ConverterPanel(QWidget):
    """
    Vista (Frontend) del módulo de conversión multimedia.
    Incluye previsualización de carátula extraída de video con fallback a placeholder.
    """
    
    start_conversion_requested = pyqtSignal(dict)
    cancel_conversion_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.selected_input_path = ""
        self.placeholder_cover_path = os.path.join(os.getcwd(), "assets", "default_audio_icon.png")
        self.extracted_temp_cover_path = os.path.join(tempfile.gettempdir(), "ataraxia_temp_cover.png")
        self.current_cover_path = self.placeholder_cover_path

        # Info del archivo origen (se rellena al cargar)
        self._source_duration_sec = 0.0
        self._source_bitrate_kbps = 0

        # Drag & Drop
        self.setAcceptDrops(True)
        self._drag_active = False   # controla el borde visual durante el drag

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 1. Grupo: Selección de Archivo Fuente
        group_source = QGroupBox("1. Archivo de Origen")
        source_layout = QVBoxLayout()
        source_layout.setSpacing(6)

        self.btn_select_file = QPushButton("Examinar Archivo (Video/Audio)...")
        self.lbl_selected_file = QLabel("Ningún archivo seleccionado")
        self.lbl_selected_file.setStyleSheet("color: gray; font-style: italic;")
        self.lbl_selected_file.setWordWrap(True)

        # Info del archivo origen (duración · bitrate · tamaño)
        self.lbl_source_info = QLabel("")
        self.lbl_source_info.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        self.lbl_source_info.setVisible(False)

        self.btn_select_file.clicked.connect(self._open_file_dialog)

        source_layout.addWidget(self.btn_select_file)
        source_layout.addWidget(self.lbl_selected_file)
        source_layout.addWidget(self.lbl_source_info)
        group_source.setLayout(source_layout)
        main_layout.addWidget(group_source)

        # 2. Grupo: Configuración de Salida
        group_settings = QGroupBox("2. Formato de Salida y Calidad")
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(8)

        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Convertir a:"))
        self.combo_format = QComboBox()
        self.combo_format.addItems(["MP3", "WAV", "FLAC", "AAC", "OGG", "OPUS"])
        self.combo_format.currentIndexChanged.connect(self._on_output_format_changed)
        self.combo_format.currentIndexChanged.connect(self._update_bitrate_options)
        self.combo_format.currentIndexChanged.connect(self._update_size_estimate)
        format_layout.addWidget(self.combo_format)

        bitrate_layout = QHBoxLayout()
        bitrate_layout.addWidget(QLabel("Calidad (Bitrate max):"))
        self.combo_bitrate = QComboBox()
        self.combo_bitrate.addItems(["128k", "192k", "256k", "320k"])
        self.combo_bitrate.setCurrentText("192k")
        self.combo_bitrate.currentIndexChanged.connect(self._update_size_estimate)
        bitrate_layout.addWidget(self.combo_bitrate)

        # Estimación de tamaño final
        self.lbl_size_estimate = QLabel("")
        self.lbl_size_estimate.setStyleSheet("color: #9e9e9e; font-size: 11px; padding-left: 4px;")
        self.lbl_size_estimate.setVisible(False)

        # Carpeta destino (persistente vía QSettings)
        from PyQt6.QtCore import QSettings
        self.settings = QSettings("Ataraxia", "Player")

        dest_layout = QHBoxLayout()
        dest_layout.addWidget(QLabel("Guardar en:"))
        self.txt_output_dir = QLineEdit()
        self.txt_output_dir.setPlaceholderText("(Misma carpeta que el archivo de origen)")
        self.txt_output_dir.setText(self.settings.value("converter_output_dir", "", type=str))
        self.txt_output_dir.setReadOnly(True)
        self.txt_output_dir.setMinimumHeight(28)
        dest_layout.addWidget(self.txt_output_dir, stretch=1)

        self.btn_pick_output_dir = QPushButton("Elegir…")
        self.btn_pick_output_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pick_output_dir.clicked.connect(self._pick_output_dir)
        dest_layout.addWidget(self.btn_pick_output_dir)

        self.btn_clear_output_dir = QPushButton("Por defecto")
        self.btn_clear_output_dir.setToolTip("Usar la misma carpeta que el archivo de origen")
        self.btn_clear_output_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_output_dir.clicked.connect(self._clear_output_dir)
        dest_layout.addWidget(self.btn_clear_output_dir)

        settings_layout.addLayout(format_layout)
        settings_layout.addLayout(bitrate_layout)
        settings_layout.addWidget(self.lbl_size_estimate)
        settings_layout.addLayout(dest_layout)
        group_settings.setLayout(settings_layout)
        main_layout.addWidget(group_settings)

        # 3. Grupo: Metadatos y Carátula
        self.group_metadata = QGroupBox("3. Metadatos y Carátula")
        metadata_main_layout = QHBoxLayout()
        metadata_main_layout.setSpacing(20)

        # --- Columna izquierda: campos de texto compactos ---
        from PyQt6.QtWidgets import QFormLayout
        texts_layout = QFormLayout()
        texts_layout.setSpacing(10)
        texts_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        texts_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.txt_title  = QLineEdit()
        self.txt_artist = QLineEdit()
        self.txt_album  = QLineEdit()

        self.txt_title.setPlaceholderText("Ej. Bohemian Rhapsody")
        self.txt_artist.setPlaceholderText("Ej. Queen")
        self.txt_album.setPlaceholderText("Ej. A Night at the Opera")

        for txt in (self.txt_title, self.txt_artist, self.txt_album):
            txt.setMinimumHeight(30)

        texts_layout.addRow("Título:",  self.txt_title)
        texts_layout.addRow("Artista:", self.txt_artist)
        texts_layout.addRow("Álbum:",   self.txt_album)

        texts_container = QWidget()
        texts_container.setLayout(texts_layout)
        metadata_main_layout.addWidget(texts_container, stretch=1)

        # --- Columna derecha: carátula más grande + botones siempre visibles ---
        cover_container = QWidget()
        cover_container.setFixedWidth(150)
        # Altura mínima = carátula (130) + 3 botones × ~30px + spacings
        cover_container.setMinimumHeight(130 + 3 * 32 + 6 * 4)
        cover_layout = QVBoxLayout(cover_container)
        cover_layout.setContentsMargins(0, 0, 0, 0)
        cover_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        cover_layout.setSpacing(6)

        self.lbl_cover_preview = QLabel()
        self.lbl_cover_preview.setFixedSize(130, 130)
        self.lbl_cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Borde en color neutral: funciona tanto en fondo blanco como negro
        self.lbl_cover_preview.setStyleSheet(
            "QLabel { border: 1px solid #999; border-radius: 6px; background-color: palette(base); }"
        )
        self.lbl_cover_preview.setScaledContents(False)
        cover_layout.addWidget(self.lbl_cover_preview, alignment=Qt.AlignmentFlag.AlignHCenter)

        # CSS neutral: gris medio como borde funciona en ambos temas
        self._cover_btn_css = """
            QPushButton {
                padding: 6px 10px;
                font-size: 11px;
                border-radius: 4px;
                border: 1px solid #888;
                background-color: palette(button);
                color: palette(button-text);
                text-align: center;
            }
            QPushButton:hover:enabled {
                background-color: rgba(124, 77, 255, 50);
                border-color: #7c4dff;
            }
            QPushButton:pressed:enabled {
                background-color: rgba(124, 77, 255, 90);
            }
            QPushButton:disabled {
                color: #999;
                border-color: #bbb;
                background-color: transparent;
            }
        """

        self.btn_change_cover = QPushButton(" Cambiar")
        self.btn_change_cover.setIcon(QIcon("assets/library/edit.svg"))
        self.btn_change_cover.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_change_cover.setStyleSheet(self._cover_btn_css)
        self.btn_change_cover.setMinimumHeight(30)
        self.btn_change_cover.setEnabled(False)
        self.btn_change_cover.clicked.connect(self._choose_custom_cover)
        cover_layout.addWidget(self.btn_change_cover)

        self.btn_remove_cover = QPushButton(" Quitar")
        self.btn_remove_cover.setIcon(QIcon("assets/library/trash.svg"))
        self.btn_remove_cover.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove_cover.setStyleSheet(self._cover_btn_css)
        self.btn_remove_cover.setMinimumHeight(30)
        self.btn_remove_cover.setEnabled(False)
        self.btn_remove_cover.clicked.connect(self._remove_cover)
        cover_layout.addWidget(self.btn_remove_cover)

        self.btn_restore_cover = QPushButton(" Restaurar")
        self.btn_restore_cover.setIcon(QIcon("assets/library/stats_refresh_dark.svg"))
        self.btn_restore_cover.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restore_cover.setStyleSheet(self._cover_btn_css)
        self.btn_restore_cover.setMinimumHeight(30)
        self.btn_restore_cover.setEnabled(False)
        self.btn_restore_cover.clicked.connect(self._restore_original_cover)
        cover_layout.addWidget(self.btn_restore_cover)

        cover_layout.addStretch()

        self._update_cover_preview()

        metadata_main_layout.addWidget(cover_container)
        self.group_metadata.setLayout(metadata_main_layout)
        main_layout.addWidget(self.group_metadata)

        # 4. Grupo: Controles y Progreso
        group_action = QGroupBox("4. Procesamiento")
        action_layout = QVBoxLayout()
        action_layout.setSpacing(10)

        self.bar_progress = QProgressBar()
        self.bar_progress.setRange(0, 100)
        self.bar_progress.setValue(0)
        self.bar_progress.setTextVisible(True)
        self.bar_progress.setFormat("Listo para convertir")
        self.bar_progress.setMinimumHeight(24)
        self.bar_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #888;
                border-radius: 4px;
                background-color: palette(base);
                text-align: center;
                font-weight: bold;
                color: palette(text);
            }
            QProgressBar::chunk {
                background-color: #7c4dff;
                border-radius: 3px;
            }
        """)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        # Botón principal: púrpura de marca (se ve bien contra cualquier fondo)
        self._start_css_idle = """
            QPushButton {
                font-weight: bold;
                border-radius: 6px;
                font-size: 13px;
                background-color: #7c4dff;
                color: white;
                border: 1px solid #7c4dff;
            }
            QPushButton:hover:enabled { background-color: #9575cd; border-color: #9575cd; }
            QPushButton:pressed:enabled { background-color: #5e35b1; }
            QPushButton:disabled { background-color: #bbb; color: #eee; border-color: #bbb; }
        """
        # Botón cancelar: borde gris medio + texto del tema + hover rojizo
        self._cancel_css_idle = """
            QPushButton {
                font-weight: bold;
                border-radius: 6px;
                font-size: 13px;
                background-color: palette(button);
                color: palette(button-text);
                border: 1px solid #888;
            }
            QPushButton:hover:enabled {
                background-color: rgba(229, 115, 115, 50);
                border-color: #e57373;
                color: #c62828;
            }
            QPushButton:pressed:enabled { background-color: rgba(229, 115, 115, 100); }
            QPushButton:disabled { color: #999; border-color: #bbb; }
        """

        self.btn_start = QPushButton(" Empezar Conversión")
        self.btn_start.setIcon(QIcon("assets/library/rocket.svg"))
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setFixedSize(200, 42)
        self.btn_start.setStyleSheet(self._start_css_idle)

        self.btn_cancel = QPushButton(" Cancelar")
        self.btn_cancel.setIcon(QIcon("assets/library/cancel.svg"))
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setFixedSize(200, 42)
        self.btn_cancel.setStyleSheet(self._cancel_css_idle)

        self.btn_start.clicked.connect(self._request_start)
        self.btn_cancel.clicked.connect(self._request_cancel)

        buttons_layout.addWidget(self.btn_start)
        buttons_layout.addSpacing(15)
        buttons_layout.addWidget(self.btn_cancel)
        buttons_layout.addStretch()

        action_layout.addWidget(self.bar_progress)
        action_layout.addLayout(buttons_layout)
        group_action.setLayout(action_layout)
        main_layout.addWidget(group_action)

    # --- LÓGICA INTERNA DE LA VISTA ---

    def _open_file_dialog(self):
        """Abre el explorador y delega la carga al método reutilizable _load_file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Archivo Multimedia", "",
            "Multimedia (*.mp4 *.mkv *.avi *.mp3 *.wav *.flac *.m4a *.ogg *.opus *.aac *.webm);;Todos (*.*)"
        )
        if file_path:
            self._load_file(file_path)

    def _load_file(self, file_path: str):
        """Carga un archivo (venga del diálogo o de drag & drop) y actualiza toda la UI."""
        self.selected_input_path = file_path
        self.lbl_selected_file.setText(os.path.basename(file_path))

        # Limpiar carátula anterior
        if os.path.exists(self.extracted_temp_cover_path):
            try: os.remove(self.extracted_temp_cover_path)
            except: pass

        # Analizar archivo con ffprobe
        codec, bitrate, es_video_stream, duration = self._analyze_media_with_ffprobe(file_path)
        self._source_duration_sec = duration
        self._source_bitrate_kbps = bitrate

        # Tamaño del archivo en disco
        try:
            size_bytes = os.path.getsize(file_path)
        except OSError:
            size_bytes = 0

        # Mostrar info del archivo origen
        info_parts = []
        if duration > 0:
            info_parts.append(self._format_duration(duration))
        info_parts.append(f"{codec.upper()}" if codec != "unknown" else "audio")
        if bitrate > 0:
            info_parts.append(f"{bitrate} kbps")
        if size_bytes > 0:
            info_parts.append(self._format_size(size_bytes))
        self.lbl_source_info.setText("   ·   ".join(info_parts))
        self.lbl_source_info.setVisible(True)

        # ¿Es un VIDEO real o es un AUDIO con carátula?
        video_extensions = ('.mp4', '.mkv', '.avi', '.webm', '.mov', '.wmv')
        es_video_real = file_path.lower().endswith(video_extensions)

        cover_found = False

        if es_video_real:
            self.txt_title.setText(os.path.basename(file_path))
            if self._extract_frame_from_video(file_path, second=5):
                cover_found = True
        else:
            mm = MetadataManager()
            meta = mm.extract_metadata(file_path)
            self.txt_title.setText(meta.get("title", os.path.basename(file_path)))
            self.txt_artist.setText(meta.get("artist", ""))
            self.txt_album.setText(meta.get("album", ""))

            extracted = mm.extract_cover_art(file_path, self.extracted_temp_cover_path)
            if extracted != "assets/default_cover.png" and os.path.exists(extracted):
                cover_found = True

        if cover_found:
            self.current_cover_path = self.extracted_temp_cover_path
        else:
            self.current_cover_path = self.placeholder_cover_path

        self._update_cover_preview()
        self._on_output_format_changed()
        self._update_bitrate_options()
        self._update_size_estimate()

    def _extract_frame_from_video(self, video_path, second=5) -> bool:
        import subprocess
        from src.utils.subprocess_helpers import quiet_kwargs
        command = [
            "ffmpeg", "-y", "-i", video_path, "-ss", f"00:00:0{second}", 
            "-vframes", "1", "-update", "1", self.extracted_temp_cover_path
        ]
        try:
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5, check=True, **quiet_kwargs())
            return os.path.exists(self.extracted_temp_cover_path)
        except:
            return False

    def _update_cover_preview(self):
        if os.path.exists(self.current_cover_path):
            pixmap = QPixmap(self.current_cover_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(
                    100, 100, 
                    Qt.AspectRatioMode.KeepAspectRatio, 
                    Qt.TransformationMode.SmoothTransformation
                )
                self.lbl_cover_preview.setPixmap(scaled_pixmap)
                return
                
        self.lbl_cover_preview.setText("🎵")

    def _reset_cover_to_placeholder(self):
        self.current_cover_path = self.placeholder_cover_path
        self._update_cover_preview()
        self._on_output_format_changed()

        if hasattr(self.window(), 'show_status_message'):
            self.window().show_status_message("Usando icono de música predeterminado.")

    def _on_output_format_changed(self):
        """Regla de negocio: Permitir incrustar carátulas solo en formatos compatibles."""
        import os
        formato = self.combo_format.currentText().upper()
        formatos_con_caratula = ["MP3", "FLAC", "OGG", "OPUS", "AAC", "M4A"]
        soporta_caratula = formato in formatos_con_caratula
        hay_archivo_cargado = bool(self.selected_input_path)

        self.lbl_cover_preview.setVisible(soporta_caratula)

        # Cambiar y Quitar sólo tienen sentido si el formato soporta carátula Y hay archivo cargado
        self.btn_change_cover.setEnabled(soporta_caratula and hay_archivo_cargado)
        self.btn_remove_cover.setEnabled(soporta_caratula and hay_archivo_cargado)

        # Restaurar sólo si además existe una original extraída distinta de la actual
        tiene_original = (
            hasattr(self, 'extracted_temp_cover_path')
            and os.path.exists(self.extracted_temp_cover_path)
            and self.current_cover_path != self.extracted_temp_cover_path
        )
        self.btn_restore_cover.setEnabled(
            soporta_caratula and hay_archivo_cargado and tiene_original
        )

    def _request_start(self):
        """Valida, recopila datos (incluida carátula si es compatible) y emite señal."""
        if not self.selected_input_path:
            self.show_error_message("Por favor, selecciona un archivo de origen primero.")
            return

        # Advertencias de calidad: dejar al usuario decidir con información completa
        if not self._confirm_quality_concerns():
            return

        formato_destino = self.combo_format.currentText().lower()
        bitrate = self.combo_bitrate.currentText()

        import os
        base_name = os.path.splitext(os.path.basename(self.selected_input_path))[0]
        custom_dir = self.txt_output_dir.text().strip()
        if custom_dir and os.path.isdir(custom_dir):
            output_path = os.path.join(custom_dir, f"{base_name}.{formato_destino}")
        else:
            base_path = os.path.splitext(self.selected_input_path)[0]
            output_path = f"{base_path}.{formato_destino}"

        # Verificación: si el archivo destino ya existe, consultar al usuario
        if os.path.exists(output_path):
            resolved = self._resolve_output_conflict(output_path)
            if resolved is None:
                return  # usuario canceló
            output_path = resolved

        codecs = {
            "mp3": "libmp3lame", 
            "wav": "pcm_s16le", 
            "flac": "flac", 
            "aac": "aac", 
            "ogg": "libvorbis",
            "opus": "libopus"
        }
        
        formatos_con_caratula = ["mp3", "flac", "ogg", "opus", "aac", "m4a"]
        tiene_caratula = formato_destino in formatos_con_caratula
        
        conversion_data = {
            "input_path": self.selected_input_path,
            "output_path": output_path,
            "settings": {
                "codec": codecs.get(formato_destino, "libmp3lame"),
                "bitrate": bitrate,
                "title": self.txt_title.text().strip(),
                "artist": self.txt_artist.text().strip(),
                "album": self.txt_album.text().strip(),
                # --- SOLUCIÓN: Pasamos la carátula si el formato lo soporta ---
                "cover_path": self.current_cover_path if tiene_caratula else None
            }
        }
        
        self.start_conversion_requested.emit(conversion_data) 

    def _request_cancel(self):
        self.cancel_conversion_requested.emit()

    def update_progress_bar(self, value: int):
        self.bar_progress.setValue(value)
        self.bar_progress.setFormat(f"Convirtiendo... {value}%")

    def show_conversion_started(self):
        self.btn_start.setEnabled(False)
        self.btn_select_file.setEnabled(False)
        self.combo_format.setEnabled(False)
        self.combo_bitrate.setEnabled(False)
        self.group_metadata.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.bar_progress.setValue(0)
        self.bar_progress.setFormat("Convirtiendo... 0%")

    def show_conversion_finished(self, message: str = "Conversión completada"):
        self.bar_progress.setValue(100)
        self.bar_progress.setFormat("Conversión completada ✓")
        self.reset_form()
        QMessageBox.information(self, "Éxito", message)

    def show_error_message(self, message: str):
        QMessageBox.warning(self, "Atención", message)

    def reset_form(self):
        self.btn_start.setEnabled(True)
        self.btn_select_file.setEnabled(True)
        self.combo_format.setEnabled(True)
        self.combo_bitrate.setEnabled(True)
        self.group_metadata.setEnabled(True)

        self.txt_title.clear()
        self.txt_artist.clear()
        self.txt_album.clear()

        # Limpiar info del archivo y la estimación (no la carpeta destino: es persistente)
        self.selected_input_path = ""
        self.lbl_selected_file.setText("Ningún archivo seleccionado")
        self.lbl_source_info.setVisible(False)
        self.lbl_size_estimate.setVisible(False)
        self._source_duration_sec = 0.0
        self._source_bitrate_kbps = 0

        self._reset_cover_to_placeholder()

        self.btn_cancel.setEnabled(False)
        self.bar_progress.setValue(0)
        self.bar_progress.setFormat("Listo para convertir")
        
    def _analyze_media_with_ffprobe(self, filepath: str) -> tuple:
        import subprocess
        from src.utils.subprocess_helpers import quiet_kwargs
        codec = "unknown"
        bitrate_kbps = 320
        es_video = False
        duration_sec = 0.0

        try:
            cmd_video = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries", "stream=nb_read_packets", "-of", "default=noprint_wrappers=1:nokey=1", filepath]
            res_video = subprocess.run(cmd_video, stdout=subprocess.PIPE, text=True, timeout=2, **quiet_kwargs())
            if res_video.stdout.strip().isdigit() and int(res_video.stdout.strip()) > 0:
                es_video = True

            cmd_codec = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", filepath]
            res_codec = subprocess.run(cmd_codec, stdout=subprocess.PIPE, text=True, timeout=2, **quiet_kwargs())
            if res_codec.stdout:
                codec = res_codec.stdout.strip().lower()

            cmd_bitrate = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=bit_rate", "-of", "default=noprint_wrappers=1:nokey=1", filepath]
            res_bitrate = subprocess.run(cmd_bitrate, stdout=subprocess.PIPE, text=True, timeout=2, **quiet_kwargs())
            bitrate_str = res_bitrate.stdout.strip()

            if not bitrate_str or bitrate_str == "N/A":
                cmd_bitrate_fmt = ["ffprobe", "-v", "error", "-show_entries", "format=bit_rate", "-of", "default=noprint_wrappers=1:nokey=1", filepath]
                res_bitrate_fmt = subprocess.run(cmd_bitrate_fmt, stdout=subprocess.PIPE, text=True, timeout=2, **quiet_kwargs())
                bitrate_str = res_bitrate_fmt.stdout.strip()

            if bitrate_str and bitrate_str != "N/A" and bitrate_str.isdigit():
                bitrate_kbps = int(bitrate_str) // 1000
            else:
                bitrate_kbps = 128 if codec in ['aac', 'opus', 'vorbis'] else 320

            # Duración en segundos
            cmd_duration = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filepath]
            res_duration = subprocess.run(cmd_duration, stdout=subprocess.PIPE, text=True, timeout=2, **quiet_kwargs())
            dur_str = res_duration.stdout.strip()
            try:
                duration_sec = float(dur_str)
            except (ValueError, TypeError):
                duration_sec = 0.0

        except Exception as e:
            print(f"Error analizando con ffprobe: {e}")

        return codec, bitrate_kbps, es_video, duration_sec

    # --- Helpers de formato e info ---

    def _format_duration(self, seconds: float) -> str:
        """123.45 → '2:03', 3723 → '1:02:03'."""
        total = int(seconds)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def _format_size(self, size_bytes: int) -> str:
        """Formatea un tamaño en bytes a KB / MB / GB."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.1f} KB"
        if size_bytes < 1024 ** 3:
            return f"{size_bytes / 1024 ** 2:.1f} MB"
        return f"{size_bytes / 1024 ** 3:.2f} GB"

    def _update_size_estimate(self):
        """Calcula y muestra el tamaño aproximado del archivo resultante."""
        duration = getattr(self, '_source_duration_sec', 0.0)
        if not self.selected_input_path or duration <= 0:
            self.lbl_size_estimate.setVisible(False)
            return

        formato = self.combo_format.currentText().lower()

        # Formatos sin pérdida: estimación basada en tasa típica
        if formato == "wav":
            # PCM 16-bit estéreo 44.1 kHz ≈ 1411 kbps
            estimated_bytes = int(duration * 1411 * 1000 / 8)
        elif formato == "flac":
            # FLAC típicamente 50–60% del WAV
            estimated_bytes = int(duration * 800 * 1000 / 8)
        else:
            # Con pérdida: usar el bitrate seleccionado
            try:
                kbps = int(self.combo_bitrate.currentText().replace("k", ""))
            except ValueError:
                kbps = 192
            estimated_bytes = int(duration * kbps * 1000 / 8)

        self.lbl_size_estimate.setText(
            f"Tamaño estimado del archivo final: ~{self._format_size(estimated_bytes)}"
        )
        self.lbl_size_estimate.setVisible(True)

    def _pick_output_dir(self):
        """Permite al usuario elegir una carpeta destino y la guarda en QSettings."""
        folder = QFileDialog.getExistingDirectory(
            self, "Seleccionar Carpeta Destino",
            self.txt_output_dir.text() or ""
        )
        if folder:
            self.txt_output_dir.setText(folder)
            self.settings.setValue("converter_output_dir", folder)

    def _clear_output_dir(self):
        """Vuelve al comportamiento por defecto: misma carpeta del origen."""
        self.txt_output_dir.clear()
        self.settings.remove("converter_output_dir")

    # --- Control de calidad (upscaling) ---

    # Conjuntos canónicos usados en varios lugares
    _LOSSY_EXTS    = {'.mp3', '.aac', '.ogg', '.opus', '.m4a', '.wma', '.webm'}
    _LOSSLESS_EXTS = {'.flac', '.wav'}
    _ALL_BITRATES  = ["128k", "192k", "256k", "320k"]

    def _is_input_lossy(self) -> bool:
        if not self.selected_input_path:
            return False
        ext = os.path.splitext(self.selected_input_path)[1].lower()
        return ext in self._LOSSY_EXTS

    def _update_bitrate_options(self):
        """
        Limita los bitrates disponibles cuando el destino es lossy y el origen también:
        no tiene sentido elegir un bitrate mayor al original (introduce pérdida extra
        sin mejorar la calidad).
        """
        current = self.combo_bitrate.currentText()
        formato = self.combo_format.currentText().lower()
        destino_lossy = formato in {"mp3", "aac", "ogg", "opus"}

        # Si el destino es lossless, la lista de bitrates no aplica (oculta o la dejamos igual)
        if not destino_lossy:
            self.combo_bitrate.blockSignals(True)
            self.combo_bitrate.clear()
            self.combo_bitrate.addItems(self._ALL_BITRATES)
            self.combo_bitrate.setCurrentText(current if current in self._ALL_BITRATES else "192k")
            self.combo_bitrate.blockSignals(False)
            return

        source_kbps = getattr(self, '_source_bitrate_kbps', 0)
        if not self._is_input_lossy() or source_kbps <= 0:
            # Origen lossless o desconocido: todos los bitrates tienen sentido
            allowed = list(self._ALL_BITRATES)
        else:
            # Origen lossy: limitar al bitrate del original (redondeo hacia arriba al valor estándar)
            allowed = [b for b in self._ALL_BITRATES if int(b.replace("k", "")) <= source_kbps]
            if not allowed:
                # Archivo con bitrate muy bajo (ej. 64 kbps): al menos 128k disponible
                allowed = ["128k"]

        self.combo_bitrate.blockSignals(True)
        self.combo_bitrate.clear()
        self.combo_bitrate.addItems(allowed)
        # Intentar conservar la selección previa si sigue siendo válida
        if current in allowed:
            self.combo_bitrate.setCurrentText(current)
        else:
            self.combo_bitrate.setCurrentIndex(len(allowed) - 1)  # el máximo permitido
        self.combo_bitrate.blockSignals(False)

    def _confirm_quality_concerns(self) -> bool:
        """
        Muestra un diálogo explicativo si la conversión no mejora (o empeora) la calidad.
        Retorna True si el usuario decide continuar, False si cancela.
        """
        in_ext  = os.path.splitext(self.selected_input_path)[1].lower()
        out_ext = "." + self.combo_format.currentText().lower()

        # Caso 1: lossy → lossless (sin pérdida "virgen" imposible de recuperar)
        if in_ext in self._LOSSY_EXTS and out_ext in self._LOSSLESS_EXTS:
            return self._show_quality_warning(
                titulo="Conversión sin mejora real",
                mensaje=(
                    "Vas a convertir un archivo <b>con pérdida</b> "
                    f"({in_ext.upper()}) a un formato <b>sin pérdida</b> "
                    f"({out_ext.upper()}).<br><br>"
                    "Esto <b>no recupera</b> la calidad original — la información "
                    "ya perdida en la compresión no puede reconstruirse. El archivo "
                    "resultante será varias veces más grande sin sonar mejor."
                )
            )

        # Caso 2: lossy → lossy con bitrate superior al original
        source_kbps = getattr(self, '_source_bitrate_kbps', 0)
        if (in_ext in self._LOSSY_EXTS and out_ext in {'.mp3', '.aac', '.ogg', '.opus'}
                and source_kbps > 0):
            try:
                out_kbps = int(self.combo_bitrate.currentText().replace("k", ""))
            except ValueError:
                out_kbps = 0
            if out_kbps > source_kbps:
                return self._show_quality_warning(
                    titulo="Bitrate superior al original",
                    mensaje=(
                        f"El archivo original está en <b>{source_kbps} kbps</b>, "
                        f"pero vas a convertirlo a <b>{out_kbps} kbps</b>.<br><br>"
                        "Un bitrate mayor <b>no mejora</b> una grabación ya comprimida; "
                        "solo agranda el archivo e introduce una nueva ronda de pérdida "
                        "por re-encoding."
                    )
                )

        return True   # nada que advertir

    def _show_quality_warning(self, titulo: str, mensaje: str) -> bool:
        """Diálogo genérico reutilizable con opción 'Continuar de todas formas'."""
        box = QMessageBox(self)
        box.setWindowTitle(titulo)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(mensaje)
        btn_ok     = box.addButton("Continuar de todas formas", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_cancel)
        box.exec()
        return box.clickedButton() == btn_ok

    # --- Resolución de conflicto de archivo destino ---

    def _resolve_output_conflict(self, output_path: str):
        """
        El archivo destino ya existe. Pregunta al usuario qué hacer.
        Retorna:
          - str con la nueva ruta a usar (sobrescribir → misma; renombrar → con sufijo)
          - None si el usuario cancela.
        """
        filename = os.path.basename(output_path)

        box = QMessageBox(self)
        box.setWindowTitle("El archivo ya existe")
        box.setIcon(QMessageBox.Icon.Question)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            f"Ya existe un archivo llamado <b>{filename}</b> en esa carpeta.<br><br>"
            "¿Qué deseas hacer?"
        )
        btn_overwrite = box.addButton("Sobrescribir",  QMessageBox.ButtonRole.DestructiveRole)
        btn_rename    = box.addButton("Renombrar",     QMessageBox.ButtonRole.AcceptRole)
        btn_cancel    = box.addButton("Cancelar",      QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_rename)
        box.exec()

        clicked = box.clickedButton()
        if clicked == btn_cancel:
            return None
        if clicked == btn_overwrite:
            return output_path
        # Renombrar: encontrar el siguiente sufijo libre
        base, ext = os.path.splitext(output_path)
        i = 1
        while True:
            candidate = f"{base} ({i}){ext}"
            if not os.path.exists(candidate):
                return candidate
            i += 1

    # --- Manejo de caratulas

    def _choose_custom_cover(self):
        """Permite al usuario seleccionar una imagen de su PC."""
        from PyQt6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Imagen de Carátula",
            "",
            "Imágenes (*.png *.jpg *.jpeg);;Todos los archivos (*.*)"
        )
        if file_path:
            self.current_cover_path = file_path
            self._update_cover_preview()
            self._on_output_format_changed()   # recalcula estado de Restaurar

    def _remove_cover(self):
        """Quita la carátula actual y pone el icono por defecto (para generar audios sin imagen)."""
        self.current_cover_path = self.placeholder_cover_path
        self._update_cover_preview()
        self._on_output_format_changed()

    def _restore_original_cover(self):
        """Vuelve a cargar la carátula original incrustada en el archivo origen."""
        import os
        if hasattr(self, 'extracted_temp_cover_path') and os.path.exists(self.extracted_temp_cover_path):
            self.current_cover_path = self.extracted_temp_cover_path
            self._update_cover_preview()
            self._on_output_format_changed()

    # --- Drag & Drop ---

    _ACCEPTED_DROP_EXTS = (
        '.mp3', '.wav', '.flac', '.ogg', '.m4a', '.opus', '.aac',
        '.mp4', '.mkv', '.avi', '.webm', '.mov', '.wmv', '.wma', '.mka'
    )

    def dragEnterEvent(self, event):
        # Rechazar drops mientras hay una conversión en curso
        if not self.btn_start.isEnabled():
            event.ignore()
            return

        if not event.mimeData().hasUrls():
            event.ignore()
            return

        urls = event.mimeData().urls()
        if len(urls) != 1:   # solo aceptamos un archivo a la vez
            event.ignore()
            return

        url = urls[0]
        if url.isLocalFile() and url.toString().lower().endswith(self._ACCEPTED_DROP_EXTS):
            event.acceptProposedAction()
            self._set_drag_feedback(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drag_feedback(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._set_drag_feedback(False)
        urls = event.mimeData().urls()
        if urls:
            filepath = urls[0].toLocalFile()
            if filepath:
                self._load_file(filepath)
        event.acceptProposedAction()

    def _set_drag_feedback(self, active: bool):
        """Dibuja un borde púrpura alrededor del panel mientras hay un drag encima."""
        if active == self._drag_active:
            return
        self._drag_active = active
        if active:
            self.setStyleSheet(
                "ConverterPanel { border: 2px dashed #7c4dff; border-radius: 6px; }"
            )
        else:
            self.setStyleSheet("")