# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, 
                             QDialogButtonBox, QGroupBox, QLabel, QTabWidget,
                             QWidget, QPushButton, QMessageBox, QCheckBox)
from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QIcon

class PreferencesDialog(QDialog):
    # Emitida cuando el usuario confirma que quiere restaurar un respaldo.
    # Argumento: path del archivo .db a restaurar.
    # El MainController la escucha para orquestar lock-release + restore +
    # reinicio automático de la app, ya que el dialog por sí solo no puede
    # tocar el lock ni reiniciar el proceso.
    restore_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferencias de Ataraxia Player")
        # 620px garantiza que los botones de Operaciones + sus labels
        # descriptivos quepan en una sola línea sin amontonarse.
        self.setMinimumWidth(620)
        self.setMinimumHeight(420)
        
        self.settings = QSettings("Ataraxia", "Player")
        
        self._setup_ui()
        self._load_current_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        
        self.tab_system = QWidget()
        self.tab_behavior = QWidget()
        self.tab_maintenance = QWidget()

        self.tabs.addTab(self.tab_system, QIcon("assets/library/gear.svg"), "Sistema")
        self.tabs.addTab(self.tab_behavior, QIcon("assets/library/behavior.svg"), "Comportamiento")
        self.tabs.addTab(self.tab_maintenance, QIcon("assets/library/stats_refresh_dark.svg"), "Mantenimiento")
        
        layout.addWidget(self.tabs)

        # ==========================================
        # PESTAÑA 1: SISTEMA Y CONVERSIÓN
        # ==========================================
        system_layout_main = QVBoxLayout(self.tab_system)
        
        system_group = QGroupBox("Configuración de FFmpeg")
        system_layout = QFormLayout()
        self.ffmpeg_input = QLineEdit()
        self.ffmpeg_input.setPlaceholderText("Ej: ffmpeg o C:/ruta/ffmpeg.exe")
        system_layout.addRow("Ruta de FFmpeg:", self.ffmpeg_input)
        system_group.setLayout(system_layout)
        system_layout_main.addWidget(system_group)

        audio_group = QGroupBox("Motor de Audio Avanzado")
        audio_layout = QVBoxLayout()
        self.chk_normalization = QCheckBox("Normalización de Audio (ReplayGain Inteligente)")
        self.chk_normalization.setToolTip("Nivela el volumen en segundo plano. NO consume procesador extra al reproducir.")
        self.chk_crossfade = QCheckBox("Crossfade (Transición Suave de 5s)")
        self.chk_crossfade.setToolTip("Desvanece el final de una pista cruzándose con el inicio de la siguiente.")
        audio_layout.addWidget(self.chk_normalization)
        audio_layout.addWidget(self.chk_crossfade)
        audio_group.setLayout(audio_layout)
        system_layout_main.addWidget(audio_group)

        # --- NUEVO GRUPO: Metadatos y Red ---
        net_group = QGroupBox("Metadatos y Red")
        net_layout = QVBoxLayout()

        self.chk_auto_cover = QCheckBox("Habilitar autocompletado de carátulas (Requiere Internet)")
        self.chk_auto_cover.setToolTip("Busca en Internet carátulas para las canciones que no tienen.")
        self.chk_auto_cover.toggled.connect(self._on_auto_cover_toggled)

        self.lbl_api = QLabel("URL de la API REST (Usa {query} como comodín para 'Artista Titulo'):")
        self.lbl_api.setStyleSheet("color: gray; font-size: 11px;")

        self.txt_api_url = QLineEdit()
        self.txt_api_url.setPlaceholderText("https://itunes.apple.com/search?term={query}&entity=song&limit=1")

        net_layout.addWidget(self.chk_auto_cover)
        net_layout.addWidget(self.lbl_api)
        net_layout.addWidget(self.txt_api_url)

        # Separador visual
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(128, 128, 128, 60); margin-top: 8px; margin-bottom: 4px;")
        net_layout.addWidget(sep)

        # Letras de canciones (lrclib.net)
        self.chk_auto_lyrics = QCheckBox("Descargar letras automáticamente al cambiar de pista")
        self.chk_auto_lyrics.setToolTip(
            "Si la canción no tiene archivo .lrc ni letras en caché, se buscarán\n"
            "automáticamente en lrclib.net al reproducirla."
        )
        self.chk_auto_lyrics.toggled.connect(self._on_auto_lyrics_toggled)
        net_layout.addWidget(self.chk_auto_lyrics)

        self.lbl_lyrics_info = QLabel(
            "Fuente: lrclib.net (API pública, open-source). Los resultados se guardan\n"
            "en una caché local temporal (máx. 200 entradas, rotación automática)."
        )
        self.lbl_lyrics_info.setStyleSheet("color: gray; font-size: 11px; margin-left: 22px;")
        self.lbl_lyrics_info.setWordWrap(True)
        net_layout.addWidget(self.lbl_lyrics_info)

        # Botón de limpiar caché
        lyrics_btn_layout = QHBoxLayout()
        self.lbl_cache_stats = QLabel("")
        self.lbl_cache_stats.setStyleSheet("color: gray; font-size: 11px; margin-left: 22px;")
        lyrics_btn_layout.addWidget(self.lbl_cache_stats, stretch=1)

        self.btn_clear_lyrics_cache = QPushButton("Limpiar caché")
        self.btn_clear_lyrics_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_lyrics_cache.clicked.connect(self._clear_lyrics_cache)
        lyrics_btn_layout.addWidget(self.btn_clear_lyrics_cache)
        net_layout.addLayout(lyrics_btn_layout)

        net_group.setLayout(net_layout)
        system_layout_main.addWidget(net_group)

        system_layout_main.addStretch()

        # ==========================================
        # PESTAÑA 2: COMPORTAMIENTO
        # ==========================================
        behavior_layout_main = QVBoxLayout(self.tab_behavior)
        dialogs_group = QGroupBox("Gestión de Diálogos y Alertas")
        dialogs_layout = QVBoxLayout()
        
        lbl_dialogs = QLabel("Si marcaste la opción 'No volver a preguntar' al cerrar el reproductor, o al eliminar playlists y canciones, puedes restablecer esas decisiones aquí.")
        lbl_dialogs.setWordWrap(True)
        lbl_dialogs.setStyleSheet("color: gray; margin-bottom: 10px;")
        
        self.btn_reset_dialogs = QPushButton("Restablecer todas las advertencias")
        self.btn_reset_dialogs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_dialogs.clicked.connect(self._reset_dialogs)
        
        dialogs_layout.addWidget(lbl_dialogs)
        dialogs_layout.addWidget(self.btn_reset_dialogs)
        dialogs_group.setLayout(dialogs_layout)
        
        behavior_layout_main.addWidget(dialogs_group)
        behavior_layout_main.addStretch()

        # ==========================================
        # PESTAÑA 3: MANTENIMIENTO DE BASE DE DATOS
        # ==========================================
        self._setup_maintenance_tab()

        # --- BOTONES DE ACCIÓN ---
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept) 
        self.button_box.rejected.connect(self.reject) 
        
        layout.addWidget(self.button_box)

    def _on_auto_cover_toggled(self, checked: bool):
        self.txt_api_url.setEnabled(checked)
        if checked:
            QMessageBox.warning(
                self, 
                "Advertencia de Privacidad y Red",
                "Has habilitado el autocompletado de carátulas.\n\n"
                "Ataraxia se conectará a servidores externos (por defecto, iTunes) "
                "para buscar portadas de las canciones que NO tengan una incrustada.\n\n"
                "Esto consumirá ancho de banda y enviará los nombres de tus canciones a través de Internet."
            )

    def _on_auto_lyrics_toggled(self, checked: bool):
        if checked:
            QMessageBox.warning(
                self,
                "Advertencia de Privacidad y Red",
                "Has habilitado la descarga automática de letras.\n\n"
                "Al reproducir una canción sin letras locales, Ataraxia consultará "
                "lrclib.net (API pública y open-source) enviando el título y artista.\n\n"
                "Las letras se guardan en una caché local temporal (máximo 200 entradas) "
                "que puedes limpiar con el botón 'Limpiar caché' en cualquier momento. "
                "La caché no se comparte ni distribuye; es sólo para ti y para evitar "
                "consultas repetidas al servidor."
            )

    def _clear_lyrics_cache(self):
        from src.models.lyrics_api import LyricsApiClient
        client = LyricsApiClient()
        count = client.clear_cache()
        self._refresh_cache_stats()
        QMessageBox.information(
            self,
            "Caché limpiada",
            f"Se eliminaron {count} archivo(s) de la caché de letras."
        )

    def _refresh_cache_stats(self):
        from src.models.lyrics_api import LyricsApiClient
        try:
            stats = LyricsApiClient().cache_stats()
            if stats["count"] == 0:
                self.lbl_cache_stats.setText("Caché vacía")
            else:
                kb = stats["size_bytes"] / 1024
                self.lbl_cache_stats.setText(f"{stats['count']} letras en caché ({kb:.1f} KB)")
        except Exception:
            self.lbl_cache_stats.setText("")

    def _reset_dialogs(self):
        self.settings.remove("comportamiento_cerrar")
        self.settings.remove("confirmar_salida")
        self.settings.remove("skip_playlist_delete_warning")
        self.settings.remove("skip_song_remove_warning")
        
        QMessageBox.information(
            self, 
            "Diálogos Restablecidos", 
            "Todas las preferencias de advertencia han sido restablecidas.\n\nAtaraxia te volverá a preguntar qué hacer al salir, y al intentar eliminar playlists o canciones."
        )

    def _load_current_settings(self):
        ffmpeg_path = self.settings.value("ffmpeg_path", "ffmpeg")
        self.ffmpeg_input.setText(ffmpeg_path)
        self.chk_normalization.setChecked(self.settings.value("enable_normalization", True, type=bool))
        self.chk_crossfade.setChecked(self.settings.value("enable_crossfade", False, type=bool)) 
        
        # Cargar configuración de red
        auto_cover = self.settings.value("enable_auto_cover", False, type=bool)
        self.chk_auto_cover.setChecked(auto_cover)
        self.txt_api_url.setEnabled(auto_cover)
        
        default_api = "https://itunes.apple.com/search?term={query}&entity=song&limit=1"
        self.txt_api_url.setText(self.settings.value("cover_api_url", default_api))

        # Descarga de letras (opt-in, desactivado por defecto)
        self.chk_auto_lyrics.setChecked(
            self.settings.value("enable_auto_lyrics", False, type=bool)
        )
        self._refresh_cache_stats()

    # ══════════════════════════════════════════════════════════════════
    # PESTAÑA MANTENIMIENTO
    # ══════════════════════════════════════════════════════════════════

    def _setup_maintenance_tab(self):
        """
        Pestaña con utilidades de base de datos:
          - Información del estado actual (versión, tamaño, conteos)
          - Optimizar (ANALYZE) — actualiza estadísticas del query planner
          - Compactar (VACUUM) — reduce el tamaño del archivo
          - Verificar integridad — detecta corrupción
          - Exportar / restaurar respaldo
        Cada acción muestra estado mediante un label persistente al final.
        """
        layout = QVBoxLayout(self.tab_maintenance)
        layout.setSpacing(12)

        # IMPORTANTE: los QGroupBox de abajo necesitan setSizePolicy con
        # vertical = Fixed para que NO se compriman cuando el banner de
        # status (lbl_maintenance_status) aparece al final del layout.
        # Sin esto, Qt reparte el espacio entre el banner y los grupos,
        # haciendo que los textos y botones parezcan "encogerse" tras
        # ejecutar una operación (era visible especialmente tras exportar
        # respaldo, donde el banner es relativamente largo).
        from PyQt6.QtWidgets import QSizePolicy

        # --- Bloque 1: Estado actual ---
        info_group = QGroupBox("Estado de la Base de Datos")
        info_group.setSizePolicy(QSizePolicy.Policy.Preferred,
                                 QSizePolicy.Policy.Fixed)
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        self.lbl_db_version = QLabel("Versión de schema: —")
        self.lbl_db_size    = QLabel("Tamaño del archivo: —")
        self.lbl_db_counts  = QLabel("Canciones: — · Playlists: —")
        self.lbl_db_last    = QLabel("Último mantenimiento: —")

        for lbl in (self.lbl_db_version, self.lbl_db_size, self.lbl_db_counts, self.lbl_db_last):
            lbl.setStyleSheet("padding: 1px 4px;")
            info_layout.addWidget(lbl)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # --- Bloque 2: Operaciones de mantenimiento ---
        ops_group = QGroupBox("Operaciones")
        ops_group.setSizePolicy(QSizePolicy.Policy.Preferred,
                                QSizePolicy.Policy.Fixed)
        ops_layout = QVBoxLayout()
        ops_layout.setSpacing(8)

        # Optimizar (ANALYZE)
        row_analyze = QHBoxLayout()
        self.btn_analyze = QPushButton(" Optimizar consultas")
        self.btn_analyze.setIcon(QIcon("assets/library/sparkles.svg"))
        self.btn_analyze.setMinimumWidth(160)
        self.btn_analyze.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_analyze.setToolTip(
            "Recalcula estadísticas internas para acelerar las búsquedas.\n"
            "Rápido (segundos). Se recomienda cada mes."
        )
        self.btn_analyze.clicked.connect(self._on_analyze_clicked)
        row_analyze.addWidget(self.btn_analyze)
        lbl_analyze_desc = QLabel("Recalcula estadísticas para acelerar consultas")
        lbl_analyze_desc.setStyleSheet("color: gray; font-size: 11px;")
        row_analyze.addWidget(lbl_analyze_desc, stretch=1)
        ops_layout.addLayout(row_analyze)

        # Compactar (VACUUM)
        row_vacuum = QHBoxLayout()
        self.btn_vacuum = QPushButton(" Compactar archivo")
        self.btn_vacuum.setIcon(QIcon("assets/library/equalizer.svg"))
        self.btn_vacuum.setMinimumWidth(160)
        self.btn_vacuum.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_vacuum.setToolTip(
            "Recupera espacio liberado por canciones y playlists borradas.\n"
            "Puede tardar varios segundos según el tamaño de la BD."
        )
        self.btn_vacuum.clicked.connect(self._on_vacuum_clicked)
        row_vacuum.addWidget(self.btn_vacuum)
        lbl_vacuum_desc = QLabel("Recupera espacio en disco no utilizado")
        lbl_vacuum_desc.setStyleSheet("color: gray; font-size: 11px;")
        row_vacuum.addWidget(lbl_vacuum_desc, stretch=1)
        ops_layout.addLayout(row_vacuum)

        # Verificar integridad
        row_integrity = QHBoxLayout()
        self.btn_integrity = QPushButton(" Verificar integridad")
        self.btn_integrity.setIcon(QIcon("assets/library/search.svg"))
        self.btn_integrity.setMinimumWidth(160)
        self.btn_integrity.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_integrity.setToolTip(
            "Comprueba que la BD no tenga corrupción.\n"
            "Si reporta un error, restaura desde un respaldo."
        )
        self.btn_integrity.clicked.connect(self._on_integrity_clicked)
        row_integrity.addWidget(self.btn_integrity)
        lbl_integrity_desc = QLabel("Detecta posible corrupción del archivo")
        lbl_integrity_desc.setStyleSheet("color: gray; font-size: 11px;")
        row_integrity.addWidget(lbl_integrity_desc, stretch=1)
        ops_layout.addLayout(row_integrity)

        ops_group.setLayout(ops_layout)
        layout.addWidget(ops_group)

        # --- Bloque 3: Respaldo y restauración ---
        backup_group = QGroupBox("Respaldo")
        backup_group.setSizePolicy(QSizePolicy.Policy.Preferred,
                                   QSizePolicy.Policy.Fixed)
        backup_layout = QVBoxLayout()
        backup_layout.setSpacing(8)

        warning = QLabel(
            "Los respaldos contienen toda tu biblioteca, playlists, favoritos "
            "y estadísticas. Guárdalos en un lugar seguro."
        )
        warning.setStyleSheet("color: gray; font-size: 11px;")
        warning.setWordWrap(True)
        backup_layout.addWidget(warning)

        # Los botones Exportar y Restaurar en filas separadas (mismo patrón
        # que los botones de operaciones de arriba). Esto evita que se
        # amontonen cuando el diálogo es estrecho o la pestaña tiene poca
        # área útil horizontal.
        row_export = QHBoxLayout()
        self.btn_export_backup = QPushButton(" Exportar respaldo…")
        self.btn_export_backup.setIcon(QIcon("assets/library/folder.svg"))
        self.btn_export_backup.setMinimumWidth(180)
        self.btn_export_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_backup.clicked.connect(self._on_export_backup)
        row_export.addWidget(self.btn_export_backup)
        lbl_export_desc = QLabel("Guarda una copia de la BD en el lugar que elijas")
        lbl_export_desc.setStyleSheet("color: gray; font-size: 11px;")
        row_export.addWidget(lbl_export_desc, stretch=1)
        backup_layout.addLayout(row_export)

        row_restore = QHBoxLayout()
        self.btn_restore_backup = QPushButton(" Restaurar respaldo…")
        self.btn_restore_backup.setIcon(QIcon("assets/library/stats_refresh_dark.svg"))
        self.btn_restore_backup.setMinimumWidth(180)
        self.btn_restore_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restore_backup.clicked.connect(self._on_restore_backup)
        row_restore.addWidget(self.btn_restore_backup)
        lbl_restore_desc = QLabel("Reemplaza la BD actual por un respaldo anterior")
        lbl_restore_desc.setStyleSheet("color: gray; font-size: 11px;")
        row_restore.addWidget(lbl_restore_desc, stretch=1)
        backup_layout.addLayout(row_restore)
        backup_group.setLayout(backup_layout)
        layout.addWidget(backup_group)

        # --- Línea de estado persistente al final ---
        # CRÍTICO: el label SIEMPRE ocupa espacio en el layout, incluso
        # cuando no hay mensaje. Si lo escondiéramos con hide() y luego
        # apareciera tras una operación, el padre tendría que re-comprimir
        # los QGroupBox superiores para hacer hueco al label de 32px,
        # achicando visualmente los botones y textos. Manteniéndolo siempre
        # visible (con texto vacío al principio) el layout queda fijo
        # desde el primer momento.
        self.lbl_maintenance_status = QLabel("")
        self.lbl_maintenance_status.setWordWrap(False)
        self.lbl_maintenance_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.lbl_maintenance_status.setFixedHeight(32)
        self.lbl_maintenance_status.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed
        )
        # Estilo inicial transparente (label invisible pero ocupando espacio)
        self.lbl_maintenance_status.setStyleSheet(
            "padding: 6px 10px; border-radius: 4px; "
            "background-color: transparent; font-size: 11px;"
        )
        # NO ocultar — el espacio debe estar reservado desde el inicio
        layout.addWidget(self.lbl_maintenance_status)

        layout.addStretch()

        # Rellenar info al abrir
        self._refresh_db_info()

    # ─── Helpers de la pestaña ──────────────────────────────────────────

    def _get_maintenance(self):
        """Lazy import + instanciación del helper de mantenimiento."""
        from src.models.database_manager import DatabaseManager
        from src.models.db_maintenance import DatabaseMaintenance
        return DatabaseMaintenance(DatabaseManager())

    def _refresh_db_info(self):
        from datetime import datetime
        try:
            stats = self._get_maintenance().get_stats()
            self.lbl_db_version.setText(f"Versión de schema: v{stats['schema_version']}")

            size_mb = stats["size_bytes"] / 1024 / 1024
            self.lbl_db_size.setText(f"Tamaño del archivo: {size_mb:.2f} MB")

            self.lbl_db_counts.setText(
                f"Canciones: {stats['songs_count']:,}  ·  "
                f"Playlists: {stats['playlists_count']:,}"
            )

            last_a = stats.get("last_analyze_at", 0)
            last_v = stats.get("last_vacuum_at", 0)
            last_ts = max(last_a, last_v)
            if last_ts > 0:
                dt = datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M")
                self.lbl_db_last.setText(f"Último mantenimiento: {dt}")
            else:
                self.lbl_db_last.setText("Último mantenimiento: nunca")
        except Exception as e:
            self.lbl_db_version.setText(f"No se pudo leer la BD: {e}")

    def _show_status(self, message: str, success: bool = True):
        """
        Muestra un mensaje persistente al pie de la pestaña.

        El color del texto se calcula dinámicamente según la luminancia del
        fondo (verde para éxito, rojo para error) MEZCLADA con el fondo real
        del widget (que depende del tema activo: claro u oscuro).

        - Tema oscuro: el verde/rojo translúcido sobre fondo oscuro
          permanece oscuro → texto BLANCO.
        - Tema claro: el verde/rojo translúcido sobre fondo claro queda
          claro → texto NEGRO.

        Antes confiábamos en `palette(text)` o `palette(WindowText)`, pero
        Qt no recompone el contraste cuando se mezclan alphas en stylesheets:
        el resultado era texto negro sobre verde aclarado en modo oscuro
        (apenas visible).
        """
        # Fondo del mensaje (RGBA explícito)
        if success:
            bg_r, bg_g, bg_b, bg_a = 76, 175, 80, 70    # verde
        else:
            bg_r, bg_g, bg_b, bg_a = 229, 115, 115, 80  # rojo

        bg_color_css = f"rgba({bg_r}, {bg_g}, {bg_b}, {bg_a})"

        # Detectar luminancia del fondo del propio widget (no del label,
        # que aún no ha pintado): usamos el palette de la ventana
        win_bg = self.palette().color(self.backgroundRole())
        # Mezcla aproximada del bg translúcido sobre el bg del widget
        a = bg_a / 255.0
        mixed_r = int(bg_r * a + win_bg.red()   * (1 - a))
        mixed_g = int(bg_g * a + win_bg.green() * (1 - a))
        mixed_b = int(bg_b * a + win_bg.blue()  * (1 - a))

        # Fórmula de luminancia perceptual (Rec. 709)
        luminance = (0.299 * mixed_r + 0.587 * mixed_g + 0.114 * mixed_b)

        # Si la mezcla queda oscura (luminance < 128) → texto blanco;
        # si queda clara → texto negro. Esto da contraste correcto en
        # ambos temas, sin depender de palette().
        text_color = "#FFFFFF" if luminance < 128 else "#1A1A1A"

        self.lbl_maintenance_status.setStyleSheet(
            f"padding: 6px 10px; border-radius: 4px; "
            f"background-color: {bg_color_css}; color: {text_color}; "
            f"font-size: 11px; font-weight: bold;"
        )
        self.lbl_maintenance_status.setText(message)
        # No llamar a show() — el label siempre está visible, solo cambia
        # su contenido. Llamar a show() podía disparar un relayout en
        # algunos escenarios (especialmente la primera operación) que
        # achicaba los botones de los QGroupBox superiores.

    def _set_busy(self, busy: bool):
        """Deshabilita botones mientras una operación corre."""
        for btn in (self.btn_analyze, self.btn_vacuum, self.btn_integrity,
                    self.btn_export_backup, self.btn_restore_backup):
            btn.setEnabled(not busy)

    # ─── Handlers de los botones ────────────────────────────────────────

    def _on_analyze_clicked(self):
        from PyQt6.QtWidgets import QApplication
        self._set_busy(True)
        self._show_status("Optimizando consultas…", success=True)
        QApplication.processEvents()   # forzar repaint antes del bloqueo
        try:
            self._get_maintenance().analyze_now()
            self._show_status("✓ Optimización completada.", success=True)
            self._refresh_db_info()
        except Exception as e:
            self._show_status(f"✕ Error: {e}", success=False)
        finally:
            self._set_busy(False)

    def _on_vacuum_clicked(self):
        # Confirmación previa: VACUUM puede tardar
        reply = QMessageBox.question(
            self,
            "Compactar base de datos",
            "Esta operación puede tardar varios segundos.\n"
            "Durante ese tiempo la ventana no responderá.\n\n"
            "¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from PyQt6.QtWidgets import QApplication
        self._set_busy(True)
        self._show_status("Compactando archivo…", success=True)
        QApplication.processEvents()
        try:
            result = self._get_maintenance().vacuum()
            if result.get("success"):
                kb = result["saved_bytes"] / 1024
                self._show_status(
                    f"✓ Compactación completada en {result['elapsed_seconds']:.1f}s. "
                    f"Liberados {kb:.1f} KB.",
                    success=True,
                )
                self._refresh_db_info()
            else:
                self._show_status(
                    f"✕ Error: {result.get('error', 'Falló la operación')}",
                    success=False,
                )
        except Exception as e:
            self._show_status(f"✕ Error: {e}", success=False)
        finally:
            self._set_busy(False)

    def _on_integrity_clicked(self):
        from PyQt6.QtWidgets import QApplication
        self._set_busy(True)
        self._show_status("Verificando integridad…", success=True)
        QApplication.processEvents()
        try:
            result = self._get_maintenance().check_integrity()
            if not result.get("success"):
                self._show_status(
                    f"✕ Error: {result.get('error')}", success=False
                )
            elif result.get("is_healthy"):
                self._show_status("✓ La base de datos está sana.", success=True)
            else:
                self._show_status(
                    f"⚠ Se detectaron problemas: {result.get('message')}\n"
                    f"Considera restaurar desde un respaldo reciente.",
                    success=False,
                )
        except Exception as e:
            self._show_status(f"✕ Error: {e}", success=False)
        finally:
            self._set_busy(False)

    def _on_export_backup(self):
        from PyQt6.QtWidgets import QFileDialog
        from datetime import datetime
        default_name = f"ataraxia-backup-{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar respaldo de la base de datos",
            default_name,
            "Base de datos SQLite (*.db);;Todos los archivos (*)"
        )
        if not path:
            return

        self._set_busy(True)
        try:
            ok = self._get_maintenance().create_backup(path)
            if ok:
                # Mostrar solo el nombre del archivo en el banner para que el
                # label no crezca verticalmente con paths largos (lo que
                # rompía el layout del QGroupBox superior). El path completo
                # va en el tooltip para que el usuario pueda consultarlo.
                import os as _os
                _name = _os.path.basename(path)
                self._show_status(f"✓ Respaldo guardado: {_name}", success=True)
                self.lbl_maintenance_status.setToolTip(f"Ruta completa:\n{path}")
            else:
                self._show_status(
                    "✕ No se pudo crear el respaldo. Revisa permisos del destino.",
                    success=False,
                )
                self.lbl_maintenance_status.setToolTip("")
        finally:
            self._set_busy(False)

    def _on_restore_backup(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar respaldo a restaurar",
            "",
            "Base de datos SQLite (*.db);;Todos los archivos (*)"
        )
        if not path:
            return

        # Confirmación fuerte: es una operación destructiva
        reply = QMessageBox.warning(
            self,
            "Restaurar respaldo",
            "Esta acción REEMPLAZARÁ tu base de datos actual con el archivo "
            "seleccionado.\n\n"
            "Se creará un respaldo de emergencia de la BD actual antes "
            "(con sufijo .pre-restore) por si necesitas revertir.\n\n"
            "Ataraxia se reiniciará automáticamente para cargar la BD "
            "restaurada.\n\n"
            "¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Emitimos la señal y cerramos el dialog. El MainController hará
        # la orquestación real: liberar el lock, ejecutar restore_from_backup,
        # y relanzar la app. No podemos hacer eso desde aquí porque el
        # dialog no tiene acceso al lock ni al QApplication.exit().
        self.restore_requested.emit(path)
        self.accept()

    def accept(self):
        self.settings.setValue("ffmpeg_path", self.ffmpeg_input.text())
        self.settings.setValue("enable_normalization", self.chk_normalization.isChecked())
        self.settings.setValue("enable_crossfade", self.chk_crossfade.isChecked())
        self.settings.setValue("enable_auto_cover", self.chk_auto_cover.isChecked())
        self.settings.setValue("cover_api_url", self.txt_api_url.text().strip())
        self.settings.setValue("enable_auto_lyrics", self.chk_auto_lyrics.isChecked())
        super().accept()
