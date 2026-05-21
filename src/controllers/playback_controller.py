# -*- coding: utf-8 -*-
import random
import os
from PyQt6.QtCore import QTimer, QUrl, QObject, Qt, pyqtSignal, QSettings
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from src.utils.logger import get_logger

log = get_logger(__name__)


class PlaybackController(QObject):
    track_played_halfway = pyqtSignal(str)
    metadata_ready_for_os = pyqtSignal(str, str, str, str)
    loop_mode_override = pyqtSignal(int)   # emitida cuando el controlador cambia el modo de bucle
    queue_changed = pyqtSignal(list, int)   # emitida al modificar la cola; (queue, current_index)

    # Tiempo mínimo entre cambios de pista (ms). Durante esta ventana, clics
    # adicionales se coalescen y solo se conserva el último pedido.
    _TRACK_CHANGE_COOLDOWN_MS = 350

    def __init__(self, view, playlist_model, metadata_manager, lyrics_parser, db_manager):
        super().__init__()
        self.settings = QSettings("Ataraxia", "Player")
        self.db_manager = db_manager
        self._has_counted_play = False
        self.view = view
        self.playlist = playlist_model
        self.metadata_manager = metadata_manager
        self.lyrics_parser = lyrics_parser
        
        self.current_queue = []
        self.current_index = -1
        self._is_changing_track = False 
        self._failed_attempts = 0

        # --- Debounce con coalescing: el último clic durante el cooldown gana ---
        self._pending_skip = 0  # +1 = next pendiente, -1 = prev pendiente, 0 = nada
        self._cooldown_timer = QTimer(self)
        self._cooldown_timer.setSingleShot(True)
        self._cooldown_timer.timeout.connect(self._on_cooldown_finished)

        # --- NUEVO: Memoria Matemática para el Shuffle ---
        self.shuffle_sequence = []
        self.shuffle_index = 0
        
        self.loop_mode = 0
        self.is_shuffle = False

        # --- Módulo DSP: Configuración y archivos temporales ---
        self.current_dsp_settings = {"pitch": 1.0, "reverb": 0.0, "eq_bands": [], "eq_gains": []}
        self._dsp_temp_path = None  # Ruta del WAV temporal activo; se borra al cambiar pista
        self._base_volume_slider = 0.8

        # --- ARQUITECTURA DE DOBLE MOTOR (CROSSFADE LIMPIO) ---
        self.players = [QMediaPlayer(), QMediaPlayer()]
        self.outputs = [QAudioOutput(), QAudioOutput()]
        self.active_idx = 0
        
        self._is_crossfading = False
        self.fade_out_player = None
        self.fade_out_output = None
        self.fade_out_filepath = None
        self.fade_out_vol = 1.0
        self.fade_in_vol = 1.0
        
        self.crossfade_timer = QTimer()
        self.crossfade_timer.timeout.connect(self._process_crossfade_tick)

        for i in range(2):
            self.players[i].setAudioOutput(self.outputs[i])
            self.outputs[i].setVolume(self._base_volume_slider)
            self.players[i].positionChanged.connect(self.update_progress_ui)
            self.players[i].durationChanged.connect(self.update_duration_ui)
            self.players[i].mediaStatusChanged.connect(self._handle_media_status)
        # ------------------------------------------------------

        self.sync_timer = QTimer()
        self.sync_timer.setInterval(500)
        self.fade_timer = QTimer()
        self.fade_timer.timeout.connect(self._process_fade_out)
        self._fade_volume = 1.0

        self.view.play_toggled.connect(self.handle_play_pause)
        self.view.next_clicked.connect(self.play_next)
        self.view.prev_clicked.connect(self.play_prev)
        self.view.slider_moved.connect(self.handle_slider_seek)
        self.view.volume_changed.connect(self.set_volume)
        
        #if hasattr(self.view, 'audio_mode_changed'):
        #    self.view.audio_mode_changed.connect(self.set_audio_mode)
        if hasattr(self.view, 'loop_mode_changed'):
            self.view.loop_mode_changed.connect(self.set_loop_mode)
        if hasattr(self.view, 'shuffle_mode_changed'):
            self.view.shuffle_mode_changed.connect(self.set_shuffle_mode)

        self.media_player.positionChanged.connect(self.update_progress_ui)
        self.media_player.durationChanged.connect(self.update_duration_ui)
        self.media_player.mediaStatusChanged.connect(self._handle_media_status)
        self.sync_timer.timeout.connect(self.sync_lyrics_tick)

    @property
    def media_player(self): return self.players[self.active_idx]

    @property
    def audio_output(self): return self.outputs[self.active_idx]

    # ==========================================================
    # LÓGICA DE BARAJA PARA SHUFFLE
    # ==========================================================
    def _generate_shuffle_sequence(self, first_index: int):
        """Genera una permutación única de la cola, forzando la canción actual a ser la primera."""
        if not self.current_queue:
            self.shuffle_sequence = []
            self.shuffle_index = -1
            return
            
        indices = list(range(len(self.current_queue)))
        if first_index in indices:
            indices.remove(first_index)
            
        random.shuffle(indices)
        self.shuffle_sequence = [first_index] + indices
        self.shuffle_index = 0

    def set_shuffle_mode(self, is_shuffle: bool):
        self.is_shuffle = is_shuffle
        if self.is_shuffle and self.current_queue:
            # Al activar, la canción que está sonando se vuelve la carta #1 de la baraja
            self._generate_shuffle_sequence(self.current_index)

    # ==========================================================
    # MOTOR DSP (PROCESAMIENTO DE EFECTOS)
    # ==========================================================
    def set_dsp_settings(self, settings: dict):
        """Recibe la matemática del panel y recarga la pista si hay cambios."""
        self.current_dsp_settings = {
            "pitch": settings.get("pitch_multiplier", 1.0),
            "reverb": settings.get("reverb_level", 0.0),
            "eq_bands": settings.get("eq_bands", []),
            "eq_gains": settings.get("eq_gains", [])
        }
        self.media_player.setPlaybackRate(1.0)
        
        if self.current_queue and self.current_index != -1:
            current_pos = self.media_player.position()
            was_playing = self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            # preserve_lyrics=True: el cambio de DSP no debe borrar las letras
            # cargadas (especialmente si vinieron de la API y no de disco).
            self.load_track(
                self.current_queue[self.current_index],
                auto_play=was_playing,
                preserve_lyrics=True
            )
            QTimer.singleShot(200, lambda: self.media_player.setPosition(current_pos))

    def _generate_experimental_track(self, filepath: str) -> str:
        """Construye un comando FFmpeg dinámico encadenando el ecualizador y los filtros."""
        import subprocess
        import tempfile
        import os
        import time
        from src.utils.subprocess_helpers import quiet_kwargs

        pitch = self.current_dsp_settings.get("pitch", 1.0)
        reverb = self.current_dsp_settings.get("reverb", 0.0)
        eq_bands = self.current_dsp_settings.get("eq_bands", [])
        eq_gains = self.current_dsp_settings.get("eq_gains", [])
        
        is_eq_flat = all(g == 0 for g in eq_gains) if eq_gains else True
        
        if pitch == 1.0 and reverb == 0.0 and is_eq_flat:
            return filepath # Modo limpio, cero procesamiento

        temp_dir = tempfile.gettempdir()
        out_path = os.path.join(temp_dir, f"ataraxia_dsp_{int(time.time()*1000)}.wav")

        filtros = []
        
        # 1. Ecualizador Gráfico: Añadimos un filtro por cada banda que no esté en 0 dB
        if not is_eq_flat:
            for freq, gain in zip(eq_bands, eq_gains):
                if gain != 0:
                    filtros.append(f"equalizer=f={freq}:width_type=o:width=1:g={gain}")

        # 2. Pitch / Velocidad
        if pitch != 1.0:
            filtros.append(f"asetrate=44100*{pitch}")
            
        # 3. Reverberación
        if reverb > 0.0:
            filtros.append(f"aecho=0.8:0.9:1000:{reverb}")
            
        cadena_filtros = ", ".join(filtros)

        command = [
            "ffmpeg", "-y", "-i", filepath,
            "-filter:a", cadena_filtros,
            "-c:a", "pcm_s16le", 
            out_path
        ]

        try:
            if hasattr(self.view.window(), 'show_status_message'):
                self.view.window().show_status_message("Aplicando Motor DSP y Ecualizador... (Procesando audio)")
            # Timeout defensivo: si FFmpeg se cuelga, no bloqueamos el hilo de la UI por siempre.
            # quiet_kwargs() evita que se abra una ventana de CMD en Windows cuando la app
            # está empaquetada con pyinstaller --noconsole.
            subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=30,
                **quiet_kwargs()
            )
            return out_path
        except subprocess.TimeoutExpired:
            log.error("DSP FFmpeg timeout (30s) para %s — usando original", filepath)
            return filepath
        except subprocess.CalledProcessError as e:
            log.error("DSP FFmpeg retornó código %s para %s", e.returncode, filepath)
            return filepath
        except Exception:
            log.exception("Error inesperado en DSP para %s", filepath)
            return filepath

    # ==========================================================
    # MODOS DE AUDIO (FFMPEG)
    # ==========================================================
    '''def set_audio_mode(self, mode: str):
        self.current_audio_mode = mode
        self.media_player.setPlaybackRate(1.0)
        
        if self.current_queue and self.current_index != -1:
            self.load_track(self.current_queue[self.current_index], auto_play=True)'''

    '''def _generate_experimental_track(self, filepath: str, mode: str) -> str:
        import subprocess
        import tempfile
        import os

        temp_dir = tempfile.gettempdir()
        out_path = os.path.join(temp_dir, f"ataraxia_{mode.lower()}_track.wav")

        rates = {"Nightcore": 1.5, "Daycore": 0.75, "Doomer": 0.5}
        multiplier = rates.get(mode, 1.0)

        command = [
            "ffmpeg", "-y", "-i", filepath,
            "-filter:a", f"asetrate=44100*{multiplier}",
            "-c:a", "pcm_s16le", 
            out_path
        ]

        try:
            if hasattr(self.view.window(), 'show_status_message'):
                self.view.window().show_status_message(f"Aplicando filtro {mode}... (Espere un momento)")
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return out_path
        except Exception as e:
            print(f"Error generando {mode}: {e}")
            return filepath'''

    # ==========================================================
    # NAVEGACIÓN Y REPRODUCCIÓN
    # ==========================================================
    def play_queue(self, filepaths: list, start_index: int = 0, auto_play: bool = True):
        self.current_queue = list(filepaths)   # copia defensiva
        self.current_index = start_index

        if self.is_shuffle and self.current_queue:
            self._generate_shuffle_sequence(start_index)

        if self.current_queue:
            self.view.track_index_changed.emit(self.current_index)
            self.load_track(self.current_queue[self.current_index], auto_play)

        self.queue_changed.emit(list(self.current_queue), self.current_index)

    # ══════════════════════════════════════════════════════════════════════
    # MANIPULACIÓN DE LA COLA (usada por QueuePanel y menús contextuales)
    # ══════════════════════════════════════════════════════════════════════

    def insert_after_current(self, filepath: str):
        """Inserta una pista para que suene inmediatamente después de la actual."""
        if not self.current_queue:
            # Si no hay cola, simplemente empezar a reproducir esta
            self.play_queue([filepath], 0)
            return
        insert_at = self.current_index + 1
        self.current_queue.insert(insert_at, filepath)
        # Si hay shuffle activo, recalcular la secuencia para que la nueva pista
        # aparezca a continuación en vez de en una posición aleatoria
        if self.is_shuffle:
            # La nueva canción queda justo después de la actual en la baraja
            self.shuffle_sequence.insert(self.shuffle_index + 1, insert_at)
            # Los índices mayores a insert_at deben desplazarse +1
            for i, idx in enumerate(self.shuffle_sequence):
                if i > self.shuffle_index + 1 and idx >= insert_at:
                    self.shuffle_sequence[i] = idx + 1
        self.queue_changed.emit(list(self.current_queue), self.current_index)

    def append_to_queue(self, filepath: str):
        """Añade una pista al final de la cola."""
        if not self.current_queue:
            self.play_queue([filepath], 0)
            return
        self.current_queue.append(filepath)
        if self.is_shuffle:
            # Añadir al final de la baraja también
            self.shuffle_sequence.append(len(self.current_queue) - 1)
        self.queue_changed.emit(list(self.current_queue), self.current_index)

    def remove_from_queue(self, queue_index: int):
        """Elimina una pista de la cola por índice. No permite borrar la actual."""
        if not (0 <= queue_index < len(self.current_queue)):
            return
        if queue_index == self.current_index:
            # Caso especial: quitar la pista que está sonando → saltar a la siguiente
            self._do_play_next(is_crossfade_trigger=False)
            # Tras el cambio, eliminar del array
            if queue_index < len(self.current_queue):
                self.current_queue.pop(queue_index)
                if self.current_index > queue_index:
                    self.current_index -= 1
            if self.is_shuffle and self.current_queue:
                self._generate_shuffle_sequence(self.current_index)
            self.queue_changed.emit(list(self.current_queue), self.current_index)
            return

        self.current_queue.pop(queue_index)
        if queue_index < self.current_index:
            self.current_index -= 1

        # Rehacer la secuencia shuffle si aplica (más simple que ajustar índices)
        if self.is_shuffle and self.current_queue:
            self._generate_shuffle_sequence(self.current_index)

        self.queue_changed.emit(list(self.current_queue), self.current_index)

    def reorder_queue(self, new_paths: list):
        """
        Reordena la cola preservando la pista actual.
        new_paths: nueva lista ordenada de rutas (debe ser permutación de la actual).
        """
        if not new_paths or not self.current_queue:
            return
        current_path = self.current_queue[self.current_index] if 0 <= self.current_index < len(self.current_queue) else None
        self.current_queue = list(new_paths)
        if current_path in self.current_queue:
            self.current_index = self.current_queue.index(current_path)
        if self.is_shuffle:
            self._generate_shuffle_sequence(self.current_index)
        self.queue_changed.emit(list(self.current_queue), self.current_index)

    def clear_queue_except_current(self):
        """Vacía la cola conservando solo la pista que está sonando."""
        if not self.current_queue or not (0 <= self.current_index < len(self.current_queue)):
            return
        current_path = self.current_queue[self.current_index]
        self.current_queue = [current_path]
        self.current_index = 0
        if self.is_shuffle:
            self.shuffle_sequence = [0]
            self.shuffle_index = 0
        self.queue_changed.emit(list(self.current_queue), self.current_index)

    def play_next(self, is_crossfade_trigger=False):
        """
        Entrada pública para 'siguiente'. Si hay un cambio en curso, guarda la
        intención (coalescing) en lugar de procesar inmediatamente. El crossfade
        bypassa el debounce porque es disparado internamente por el sistema.
        """
        if is_crossfade_trigger:
            self._do_play_next(is_crossfade_trigger=True)
            return

        if self._is_changing_track or self._cooldown_timer.isActive():
            log.debug("play_next coalesced (pending skip)")
            self._pending_skip = 1
            return

        self._do_play_next(is_crossfade_trigger=False)

    def play_prev(self):
        """Igual que play_next pero para la dirección contraria."""
        if self._is_changing_track or self._cooldown_timer.isActive():
            log.debug("play_prev coalesced (pending skip)")
            self._pending_skip = -1
            return

        self._do_play_prev()

    def _on_cooldown_finished(self):
        """Se ejecuta cuando el cooldown de cambio de pista termina.
        Si el usuario pidió algo durante la ventana, lo procesa ahora (una sola vez)."""
        pending = self._pending_skip
        self._pending_skip = 0
        if pending == 1:
            log.debug("Cooldown ended with pending=next, executing")
            self._do_play_next(is_crossfade_trigger=False)
        elif pending == -1:
            log.debug("Cooldown ended with pending=prev, executing")
            self._do_play_prev()

    def _start_cooldown(self):
        """Arranca la ventana de debounce tras un cambio de pista exitoso."""
        self._cooldown_timer.start(self._TRACK_CHANGE_COOLDOWN_MS)

    def _do_play_next(self, is_crossfade_trigger=False):
        """Lógica interna real de 'siguiente'. Asume que ya se pasó el filtro de debounce."""
        if not is_crossfade_trigger and getattr(self, '_is_crossfading', False):
            self._cancel_crossfade()

        if not self.current_queue or self._is_changing_track:
            return
        self._is_changing_track = True

        try:
            # Estándar de industria: saltar manualmente en loop-one → loop-all
            if not is_crossfade_trigger and self.loop_mode == 2:
                self.loop_mode = 1
                self.loop_mode_override.emit(1)

            if is_crossfade_trigger and self.loop_mode == 2:
                pass  # No incrementamos el índice

            elif self.is_shuffle:
                self.shuffle_index += 1
                if self.shuffle_index >= len(self.shuffle_sequence):
                    if self.loop_mode == 0:
                        # Fin de la baraja y no hay repetición: detener
                        self.shuffle_index -= 1
                        self.media_player.stop()
                        self.sync_timer.stop()
                        self.view.set_play_state(False)
                        self.media_player.setPosition(0)
                        return
                    else:
                        candidatos = list(range(len(self.current_queue)))
                        if self.current_index in candidatos:
                            candidatos.remove(self.current_index)
                        siguiente_inicio = random.choice(candidatos) if candidatos else self.current_index
                        self._generate_shuffle_sequence(siguiente_inicio)
                self.current_index = self.shuffle_sequence[self.shuffle_index]
            else:
                if self.loop_mode == 0 and self.current_index >= len(self.current_queue) - 1:
                    self.current_index = 0
                    self.view.track_index_changed.emit(self.current_index)
                    self.load_track(self.current_queue[self.current_index], auto_play=False)
                    return
                else:
                    self.current_index = (self.current_index + 1) % len(self.current_queue)

            self.view.track_index_changed.emit(self.current_index)
            self.load_track(self.current_queue[self.current_index])

        except Exception:
            log.exception("Error en _do_play_next — se libera el lock y se notifica al usuario")
            if hasattr(self.view.window(), 'show_status_message'):
                self.view.window().show_status_message("Error al cambiar de pista. Revisa el log.")
        finally:
            self._is_changing_track = False
            self._start_cooldown()

    def _do_play_prev(self):
        """Lógica interna real de 'anterior'. Asume que ya se pasó el filtro de debounce."""
        if getattr(self, '_is_crossfading', False):
            self._cancel_crossfade()

        if not self.current_queue or self._is_changing_track:
            return
        self._is_changing_track = True

        try:
            # Estándar de industria: saltar manualmente en loop-one → loop-all
            if self.loop_mode == 2:
                self.loop_mode = 1
                self.loop_mode_override.emit(1)

            # Regla UX: si han pasado 6 segundos o solo hay 1 canción, reiniciar la pista actual
            if self.media_player.position() > 6000 or len(self.current_queue) == 1:
                self.media_player.setPosition(0)
                self.media_player.play()
            else:
                if self.is_shuffle:
                    self.shuffle_index -= 1
                    if self.shuffle_index < 0:
                        if self.loop_mode != 0:
                            self.shuffle_index = len(self.shuffle_sequence) - 1
                        else:
                            self.shuffle_index = 0
                    self.current_index = self.shuffle_sequence[self.shuffle_index]
                else:
                    self.current_index = (self.current_index - 1) % len(self.current_queue)

                self.view.track_index_changed.emit(self.current_index)
                self.load_track(self.current_queue[self.current_index])

        except Exception:
            log.exception("Error en _do_play_prev — se libera el lock y se notifica al usuario")
            if hasattr(self.view.window(), 'show_status_message'):
                self.view.window().show_status_message("Error al cambiar de pista. Revisa el log.")
        finally:
            self._is_changing_track = False
            self._start_cooldown()

    def load_track(self, filepath: str, auto_play: bool = True, preserve_lyrics: bool = False):
        """
        Carga una pista en el motor de reproducción.

        preserve_lyrics=True le indica al método que NO debe recargar las
        letras desde disco (lo que borraría letras descargadas vía API que
        viven solo en memoria). Se usa cuando el reload no es por cambio
        de canción sino por un re-procesado interno (cambio de DSP, etc.).
        """
        try:
            self._load_track_impl(filepath, auto_play, preserve_lyrics)
        except Exception:
            log.exception("load_track falló para %s — intentando recuperación limpia", filepath)
            try:
                self.media_player.blockSignals(True)
                self.media_player.stop()
                self.media_player.setSource(QUrl())
                self.media_player.blockSignals(False)
            except Exception:
                log.exception("Fallo también durante el cleanup de media_player tras load_track")
            self.view.set_play_state(False)
            if hasattr(self.view.window(), 'show_status_message'):
                self.view.window().show_status_message("Error al cargar la pista. Revisa el log.")

    def _load_track_impl(self, filepath: str, auto_play: bool = True, preserve_lyrics: bool = False):
        self._has_counted_play = False 

        if not os.path.exists(filepath):
            self._failed_attempts += 1
            if self._failed_attempts >= len(self.current_queue):
                self.media_player.stop()
                self.sync_timer.stop()
                self.view.set_play_state(False)
                self.view.update_metadata("Archivos no encontrados", "Álbum vacío o eliminado", "-")
                self._failed_attempts = 0 
                return
            QTimer.singleShot(0, self.play_next)
            return

        self._failed_attempts = 0

        metadata = self.metadata_manager.extract_metadata(filepath)
        cover_path = self.metadata_manager.extract_cover_art(filepath)
        
        # Validar si hay algún efecto activo o si el ecualizador no está plano
        pitch = self.current_dsp_settings.get("pitch", 1.0)
        reverb = self.current_dsp_settings.get("reverb", 0.0)
        eq_gains = self.current_dsp_settings.get("eq_gains", [])
        is_eq_flat = all(g == 0 for g in eq_gains) if eq_gains else True
        
        if pitch != 1.0 or reverb > 0.0 or not is_eq_flat:
            title_lower = metadata.get("title", "").lower()
            palabras_prohibidas = ["slowed", "reverb", "speed up", "sped up", "nightcore", "daycore", "doomer"]
            if any(p in title_lower for p in palabras_prohibidas):
                log.info("Auto-skip: saltando pista '%s' (título indica que ya está modificada)", metadata.get('title'))
                QTimer.singleShot(0, self.play_next)
                return

        self.media_player.blockSignals(True) 
        self.media_player.stop()
        self.media_player.setSource(QUrl()) 
        self.sync_timer.stop()

        self.view.update_metadata(
            title=metadata.get("title", "Desconocido"),
            artist=metadata.get("artist", "Desconocido"),
            album=metadata.get("album", "Desconocido")
        )
        self.view.set_cover_image(cover_path)
        # Solo releer letras del disco si NO estamos preservando las actuales.
        # En recargas internas (cambio de DSP, etc.) las letras de la canción
        # actual son válidas y a veces vienen de API (lyrics_parser.load_from_text)
        # — no existen en disco y se perderían si hiciéramos load_file aquí.
        if not preserve_lyrics:
            self.lyrics_parser.load_file(filepath)

        # Notify visualizer so it can analyze the real audio energy
        if hasattr(self.view, 'set_track'):
            self.view.set_track(filepath)
        
        if hasattr(self, 'metadata_ready_for_os'):
            self.metadata_ready_for_os.emit(
                metadata.get("title", "Desconocido"),
                metadata.get("artist", "Desconocido"),
                metadata.get("album", "Desconocido"),
                cover_path
            )

        self.sync_lyrics_tick() 
        self.fade_timer.stop() 

        # Limpiar el archivo WAV temporal del DSP de la pista anterior
        if self._dsp_temp_path and os.path.exists(self._dsp_temp_path):
            try:
                os.remove(self._dsp_temp_path)
            except OSError:
                pass
            self._dsp_temp_path = None

        play_path = self._generate_experimental_track(filepath)
        # Si se generó un temporal nuevo, recordarlo para borrarlo al cambiar de pista
        if play_path != filepath:
            self._dsp_temp_path = play_path
            
        self.media_player.setSource(QUrl.fromLocalFile(play_path))
        self.media_player.setPlaybackRate(1.0) 
        self.media_player.blockSignals(False)
        self._apply_volumes() # <-- NUEVO: Aplica volumen correcto

        if auto_play:
            self.media_player.play()
            self.sync_timer.start()
            self.view.set_play_state(True)
            if hasattr(self.view.window(), 'show_status_message'):
                self.view.window().show_status_message("Reproduciendo pista actual.")
        else:
            self.view.set_play_state(False)

    def _handle_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.media_player.position() >= (self.media_player.duration() - 2000):
                
                if self.loop_mode == 2:
                    self.media_player.setPosition(0)
                    self.media_player.play()
                    
                elif self.loop_mode == 0 and not self.is_shuffle and self.current_index >= len(self.current_queue) - 1:
                    self.media_player.stop()
                    self.sync_timer.stop()
                    self.view.set_play_state(False)
                    self.media_player.setPosition(0) 
                    
                elif self.loop_mode == 0 and self.is_shuffle and self.shuffle_index >= len(self.shuffle_sequence) - 1:
                    self.media_player.stop()
                    self.sync_timer.stop()
                    self.view.set_play_state(False)
                    self.media_player.setPosition(0)
                    
                else:
                    self.play_next()
                    
    def handle_play_pause(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._fade_volume = self.audio_output.volume()
            self.fade_timer.start(15) 
        else:
            vol_real = self.view.volume_slider.value() / 100.0
            self.audio_output.setVolume(vol_real)
            self.media_player.play()
            self.sync_timer.start()
            self.view.set_play_state(True)
            
    def _process_fade_out(self):
        self._fade_volume -= 0.05
        if self._fade_volume <= 0.0:
            self.fade_timer.stop()
            self.audio_output.setVolume(0)
            self.media_player.pause()
            self.sync_timer.stop()
            self.view.set_play_state(False)
        else:
            self.audio_output.setVolume(self._fade_volume)
                
    def set_loop_mode(self, mode): self.loop_mode = mode

    def _calculate_replaygain_volume(self, filepath):
        """Calcula el volumen ideal mezclando la barra del usuario con el ReplayGain."""
        if not filepath or not hasattr(self, 'db_manager'): return self._base_volume_slider
        gain_db = self.db_manager.get_replay_gain(filepath)
        import math
        multiplier = math.pow(10, gain_db / 20.0)
        return max(0.0, min(1.0, self._base_volume_slider * multiplier))

    def _apply_volumes(self):
        """Aplica la matemática del volumen al motor activo y al fantasma (si hay cruce)."""
        filepath_active = self.current_queue[self.current_index] if self.current_queue and self.current_index != -1 else None
        vol_active = self._calculate_replaygain_volume(filepath_active)

        if self._is_crossfading:
            self.audio_output.setVolume(vol_active * self.fade_in_vol)
            if self.fade_out_output:
                vol_fade_out = self._calculate_replaygain_volume(self.fade_out_filepath)
                self.fade_out_output.setVolume(vol_fade_out * self.fade_out_vol)
        else:
            self.audio_output.setVolume(vol_active)

    def set_volume(self, value): 
        self._base_volume_slider = value / 100.0
        self._apply_volumes()

    def update_duration_ui(self, ms): self._current_duration_sec = ms // 1000

    def update_progress_ui(self, ms):
        if not self.current_queue or self.current_index < 0: return

        if self.sender() != self.media_player: return # Filtro de seguridad vital

        if hasattr(self, '_current_duration_sec'):
            self.view.update_progress_bar(ms // 1000, self._current_duration_sec)
            
        total_ms = self.media_player.duration()
        if total_ms > 0 and not getattr(self, '_has_counted_play', False):
            if ms >= (total_ms / 2):
                self._has_counted_play = True 
                if self.current_queue and 0 <= self.current_index < len(self.current_queue):
                    self.track_played_halfway.emit(self.current_queue[self.current_index])

        # --- GATILLO DEL CROSSFADE (Últimos 5 segundos) ---
        if total_ms > 0 and self.settings.value("enable_crossfade", False, type=bool):
            if (total_ms - ms) <= 5000 and not self._is_crossfading:
                is_last = not self.is_shuffle and self.current_index >= len(self.current_queue) - 1
                is_last_track = (not self.is_shuffle and self.current_index >= len(self.current_queue) - 1) or \
                                (self.is_shuffle and self.shuffle_index >= len(self.shuffle_sequence) - 1)
                
                # Gatillo: Si hay bucle activo (1 o 2) siempre dispara. Si no hay bucle, solo si no es la última.
                if self.loop_mode != 0 or not is_last_track:
                    self._start_crossfade()
    
    def handle_slider_seek(self, sec): 
        self.media_player.setPosition(sec * 1000)
        self.sync_lyrics_tick() 
    
    def sync_lyrics_tick(self):
        # --- NUEVO: Sincronización Matemática Pura ---
        current_ms = self.media_player.position()
        multiplier = self.current_dsp_settings["pitch"]
        real_ms = int(current_ms * multiplier)
        
        lines, current_index, is_synced = self.lyrics_parser.get_state_at_time(real_ms)
        self.view.update_lyrics_karaoke(lines, current_index, is_synced)

    def _start_crossfade(self):
        self._is_crossfading = True
        self.fade_out_player = self.media_player
        self.fade_out_output = self.audio_output
        self.fade_out_filepath = self.current_queue[self.current_index]

        self.fade_out_vol = 1.0
        self.fade_in_vol = 0.0

        # Cambiamos al segundo motor invisible
        self.active_idx = 1 - self.active_idx

        self.crossfade_timer.start(100) # El contador de 5 segundos
        self.play_next(is_crossfade_trigger=True) # Arranca la siguiente

    def _process_crossfade_tick(self):
        # Desvanecer motor viejo (Fade Out)
        self.fade_out_vol = max(0.0, self.fade_out_vol - 0.02)
        # Aparecer motor nuevo (Fade In)
        self.fade_in_vol = min(1.0, self.fade_in_vol + 0.02)

        self._apply_volumes()

        if self.fade_out_vol <= 0.0:
            self._cancel_crossfade()

    def _cancel_crossfade(self):
        self._is_crossfading = False
        self.crossfade_timer.stop()
        if self.fade_out_player:
            self.fade_out_player.stop()
            self.fade_out_player = None
            self.fade_out_output = None
        self.fade_in_vol = 1.0
        self._apply_volumes()

    def clear_playback(self):
        if getattr(self, '_is_crossfading', False):
            self._cancel_crossfade()
        self.sync_timer.stop()

        self.current_queue = []
        self.current_index = -1
        self.shuffle_sequence = []
        self.shuffle_index = 0
        self._is_changing_track = False

        # --- SILENCIAMIENTO TOTAL (Evita el Crash de la barra) ---
        if hasattr(self, 'players'): 
            for player in self.players:
                player.blockSignals(True)
                player.stop()
                player.setSource(QUrl())
                player.blockSignals(False)
        else:
            self.media_player.blockSignals(True)
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            self.media_player.blockSignals(False)

        self.view.set_play_state(False)
        self.view.update_metadata("Ataraxia Player", "Ninguna pista seleccionada", "-")
        self.view.set_cover_image("")
        self.view.update_progress_bar(0, 0)
        self.view.update_lyrics_karaoke([], -1, False)
        self.queue_changed.emit([], -1)