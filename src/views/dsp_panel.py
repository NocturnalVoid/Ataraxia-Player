# -*- coding: utf-8 -*-
import json
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QSlider, QComboBox, QGroupBox, QGridLayout, 
                             QPushButton, QInputDialog, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings

class DSPPanel(QWidget):
    """Panel de control para Procesamiento Digital de Señales y Ecualizador."""
    
    dsp_settings_changed = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.settings = QSettings("Ataraxia", "Player")
        self._is_updating_ui = False
        self.eq_bands = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
        self.eq_sliders = []
        
        # Cargar presets base y personalizados
        self._default_presets = [
            "Normal (Plano)", "Rock", "Pop", "Graves Potentes (Bass Boost)",
            "Voz Clara", "Nightcore (Rápido y Agudo)", "Slowed & Reverb (Lento con mucho eco)"
        ]
        self.custom_presets = self._load_custom_presets()
        self._setup_ui()

    def _load_custom_presets(self):
        presets_json = self.settings.value("custom_dsp_presets", "{}")
        try: return json.loads(presets_json)
        except: return {}

    def _save_custom_presets(self):
        self.settings.setValue("custom_dsp_presets", json.dumps(self.custom_presets))

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- 1. SECCIÓN DE PRESETS ---
        group_presets = QGroupBox("1. Perfiles de Audio y Ecualización")
        preset_layout = QHBoxLayout() 
        
        self.combo_presets = QComboBox()
        self.combo_presets.addItems(self._default_presets)
        for cp in self.custom_presets.keys():
            self.combo_presets.addItem(cp)
        self.combo_presets.addItem("Personalizado")
        self.combo_presets.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_presets.currentIndexChanged.connect(self._on_preset_selected)
        
        self.btn_save_preset = QPushButton("💾 Guardar")
        self.btn_save_preset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_preset.clicked.connect(self._save_current_as_preset)
        
        self.btn_del_preset = QPushButton("🗑️ Eliminar")
        self.btn_del_preset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del_preset.setEnabled(False) 
        self.btn_del_preset.clicked.connect(self._delete_current_preset)
        
        preset_layout.addWidget(self.combo_presets, stretch=1)
        preset_layout.addWidget(self.btn_save_preset)
        preset_layout.addWidget(self.btn_del_preset)
        group_presets.setLayout(preset_layout)
        main_layout.addWidget(group_presets)

        # --- 2. ECUALIZADOR GRÁFICO ---
        group_eq = QGroupBox("2. Ecualizador Gráfico")
        eq_layout = QHBoxLayout()
        eq_layout.setSpacing(15)

        for freq in self.eq_bands:
            band_layout = QVBoxLayout()
            band_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            lbl_gain = QLabel("0")
            lbl_gain.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_gain.setStyleSheet("font-size: 10px; color: gray;")
            
            slider = QSlider(Qt.Orientation.Vertical)
            slider.setRange(-15, 15)
            slider.setValue(0)
            slider.setTickPosition(QSlider.TickPosition.TicksBothSides)
            slider.setTickInterval(5)
            slider.setMinimumHeight(130)
            slider.setCursor(Qt.CursorShape.PointingHandCursor)
            
            freq_str = f"{freq//1000}k" if freq >= 1000 else str(freq)
            lbl_freq = QLabel(freq_str)
            lbl_freq.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_freq.setStyleSheet("font-weight: bold; font-size: 11px;")

            band_layout.addWidget(lbl_gain)
            band_layout.addWidget(slider)
            band_layout.addWidget(lbl_freq)
            
            # SOLUCIÓN: Separamos el arrastre manual de la emisión de datos
            slider.valueChanged.connect(lambda val, l=lbl_gain: self._on_eq_slider_changed(val, l))
            slider.sliderReleased.connect(self._emit_current_settings)
            
            self.eq_sliders.append(slider)
            eq_layout.addLayout(band_layout)

        group_eq.setLayout(eq_layout)
        main_layout.addWidget(group_eq)

        # --- 3. SECCIÓN DE EFECTOS MAESTROS ---
        group_effects = QGroupBox("3. Efectos y Tiempo")
        effects_layout = QGridLayout()
        effects_layout.setVerticalSpacing(15)

        self.lbl_pitch_val = QLabel("100%")
        self.slider_pitch = QSlider(Qt.Orientation.Horizontal)
        self.slider_pitch.setRange(50, 150)
        self.slider_pitch.setValue(100)
        self.slider_pitch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_pitch.valueChanged.connect(self._on_effect_slider_changed)
        self.slider_pitch.sliderReleased.connect(self._emit_current_settings)

        effects_layout.addWidget(QLabel("Velocidad (Pitch):"), 0, 0)
        effects_layout.addWidget(self.slider_pitch, 0, 1)
        effects_layout.addWidget(self.lbl_pitch_val, 0, 2)

        self.lbl_reverb_val = QLabel("0%")
        self.slider_reverb = QSlider(Qt.Orientation.Horizontal)
        self.slider_reverb.setRange(0, 100)
        self.slider_reverb.setValue(0)
        self.slider_reverb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_reverb.valueChanged.connect(self._on_effect_slider_changed)
        self.slider_reverb.sliderReleased.connect(self._emit_current_settings)

        effects_layout.addWidget(QLabel("Reverberación (Eco):"), 1, 0)
        effects_layout.addWidget(self.slider_reverb, 1, 1)
        effects_layout.addWidget(self.lbl_reverb_val, 1, 2)

        group_effects.setLayout(effects_layout)
        main_layout.addWidget(group_effects)
        main_layout.addStretch()

    # --- LÓGICA DE ACTUALIZACIÓN Y UI ---

    def _mark_as_custom(self):
        """Cambia a 'Personalizado' SÓLO si el usuario mueve un slider manualmente."""
        if not self._is_updating_ui and self.combo_presets.currentText() != "Personalizado":
            self._is_updating_ui = True
            self.combo_presets.setCurrentText("Personalizado")
            self.btn_del_preset.setEnabled(False)
            self._is_updating_ui = False

    def _on_eq_slider_changed(self, val, label):
        label.setText(f"{val:+}")
        self._mark_as_custom()

    def _on_effect_slider_changed(self):
        self.lbl_pitch_val.setText(f"{self.slider_pitch.value()}%")
        self.lbl_reverb_val.setText(f"{self.slider_reverb.value()}%")
        self._mark_as_custom()

    def _set_eq_values(self, values: list):
        for slider, val in zip(self.eq_sliders, values):
            slider.setValue(val)

    def _on_preset_selected(self, index: int):
        if self._is_updating_ui: return
        
        preset = self.combo_presets.currentText()
        self.btn_del_preset.setEnabled(preset in self.custom_presets)
        
        if preset == "Personalizado": return

        self._is_updating_ui = True

        if preset in self.custom_presets:
            data = self.custom_presets[preset]
            self.slider_pitch.setValue(data.get("pitch", 100))
            self.slider_reverb.setValue(data.get("reverb", 0))
            self._set_eq_values(data.get("eq", [0]*10))
        else:
            self.slider_pitch.setValue(100)
            self.slider_reverb.setValue(0)
            self._set_eq_values([0]*10)
            
            if preset == "Rock": self._set_eq_values([4, 3, 0, -2, -3, -2, 1, 3, 4, 5])
            elif preset == "Pop": self._set_eq_values([-2, -1, 0, 2, 4, 4, 2, 0, -1, -2])
            elif preset == "Graves Potentes (Bass Boost)": self._set_eq_values([7, 6, 4, 1, 0, 0, 0, 0, 0, 0])
            elif preset == "Voz Clara": self._set_eq_values([-3, -2, -1, 1, 4, 5, 4, 2, 0, -2])
            elif preset == "Nightcore (Rápido y Agudo)":
                self.slider_pitch.setValue(125)
                self._set_eq_values([0, 0, 0, 0, 0, 1, 2, 3, 4, 4])
            elif preset == "Slowed & Reverb (Lento con mucho eco)":
                self.slider_pitch.setValue(75)
                self.slider_reverb.setValue(80)
                self._set_eq_values([3, 2, 1, 0, 0, 0, -1, -2, -2, -3])

        self.lbl_pitch_val.setText(f"{self.slider_pitch.value()}%")
        self.lbl_reverb_val.setText(f"{self.slider_reverb.value()}%")

        self._is_updating_ui = False
        self._emit_current_settings()

    def _emit_current_settings(self):
        eq_gains = [slider.value() for slider in self.eq_sliders]
        settings = {
            "pitch_multiplier": self.slider_pitch.value() / 100.0,
            "reverb_level": self.slider_reverb.value() / 100.0,
            "eq_bands": self.eq_bands,
            "eq_gains": eq_gains
        }
        self.dsp_settings_changed.emit(settings)

    # --- LÓGICA DE GUARDADO Y ELIMINACIÓN ---
    def _save_current_as_preset(self):
        name, ok = QInputDialog.getText(self, "Guardar Preset", "Nombre de tu nuevo perfil:")
        if ok and name.strip():
            name = name.strip()
            if name in self._default_presets or name == "Personalizado":
                QMessageBox.warning(self, "Acción Inválida", "Ese nombre está reservado por el sistema.")
                return

            self.custom_presets[name] = {
                "pitch": self.slider_pitch.value(),
                "reverb": self.slider_reverb.value(),
                "eq": [s.value() for s in self.eq_sliders]
            }
            self._save_custom_presets()

            if self.combo_presets.findText(name) == -1:
                idx = self.combo_presets.count() - 1
                self.combo_presets.insertItem(idx, name)

            self._is_updating_ui = True
            self.combo_presets.setCurrentText(name)
            self.btn_del_preset.setEnabled(True)
            self._is_updating_ui = False

    def _delete_current_preset(self):
        name = self.combo_presets.currentText()
        if name in self.custom_presets:
            respuesta = QMessageBox.question(self, "Eliminar", f"¿Eliminar permanentemente el preset '{name}'?")
            if respuesta == QMessageBox.StandardButton.Yes:
                del self.custom_presets[name]
                self._save_custom_presets()

                self._is_updating_ui = True
                idx = self.combo_presets.findText(name)
                self.combo_presets.removeItem(idx)
                self.combo_presets.setCurrentText("Normal (Plano)")
                self._is_updating_ui = False

                self._on_preset_selected(self.combo_presets.currentIndex())