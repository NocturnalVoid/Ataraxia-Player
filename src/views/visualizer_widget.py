# -*- coding: utf-8 -*-
import math
import random
import struct
import subprocess

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QBrush

from src.utils.logger import get_logger
from src.utils.subprocess_helpers import quiet_kwargs

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# AudioAnalyzer — background thread
# Decodes audio via FFmpeg, splits into 5 frequency bands with IIR filters,
# and emits RMS energy arrays (one per band, 25 frames/sec resolution).
# ─────────────────────────────────────────────────────────────────────────────

class AudioAnalyzer(QThread):

    # Emit 5 lists (one per band).  Each list: float energy values, 25/sec.
    analysis_done = pyqtSignal(list)

    SAMPLE_RATE    = 4000     # Hz  — enough for 5-band analysis up to 2 kHz
    WINDOW_MS      = 40       # ms per energy frame  → 25 frames / second
    FRAMES_PER_SEC = 1000 // WINDOW_MS               # = 25
    # Lowpass cutoff frequencies that define band boundaries (Hz)
    CUTOFFS        = [80, 250, 600, 1400]             # → 5 bands

    def __init__(self, filepath: str, parent=None):
        super().__init__(parent)
        self._filepath = filepath
        self._cancelled = False
        self._process = None

    def cancel(self):
        """Marca el hilo como cancelado y mata el proceso FFmpeg si está activo.
        Mucho más seguro que QThread.terminate() (que puede dejar subprocess zombies)."""
        self._cancelled = True
        if self._process is not None:
            try:
                self._process.kill()
            except Exception:
                pass

    # ── IIR helper ────────────────────────────────────────────────────────────

    def _alpha(self, cutoff_hz: float) -> float:
        dt = 1.0 / self.SAMPLE_RATE
        return dt / (dt + 1.0 / (2.0 * math.pi * cutoff_hz))

    def _lowpass(self, samples: list, alpha: float) -> list:
        """Single-pole IIR low-pass filter."""
        out  = []
        prev = 0.0
        for s in samples:
            prev += alpha * (s - prev)
            out.append(prev)
        return out

    # ── Energy helpers ────────────────────────────────────────────────────────

    def _rms_windows(self, samples: list) -> list:
        win = int(self.SAMPLE_RATE * self.WINDOW_MS / 1000)  # 160 samples
        out = []
        for start in range(0, len(samples), win):
            chunk = samples[start : start + win]
            if chunk:
                rms = math.sqrt(sum(x * x for x in chunk) / len(chunk))
                out.append(rms)
        return out

    def _normalize(self, values: list) -> list:
        """
        Scale so the 90th-percentile peak hits 0.82.
        Preserves internal dynamics (quiet vs loud parts within the song).
        """
        if not values:
            return values
        sorted_v = sorted(values)
        p90 = sorted_v[int(len(sorted_v) * 0.90)] or 1e-9
        scale = 0.82 / p90
        return [min(v * scale, 1.0) for v in values]

    # ── Decode ────────────────────────────────────────────────────────────────

    def _decode(self) -> list:
        """Decodifica con FFmpeg. Si cancel() es llamado desde fuera, mata el proceso."""
        cmd = [
            "ffmpeg", "-v", "quiet",
            "-i", self._filepath,
            "-f", "s16le", "-ac", "1",
            "-ar", str(self.SAMPLE_RATE),
            "-vn", "pipe:1",
        ]
        try:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                **quiet_kwargs()
            )
            raw, _ = self._process.communicate(timeout=90)

            if self._cancelled or not raw:
                return []
            n    = len(raw) // 2
            ints = struct.unpack(f"<{n}h", raw)
            return [s / 32768.0 for s in ints]
        except subprocess.TimeoutExpired:
            log.warning("AudioAnalyzer FFmpeg timeout (90s) for %s", self._filepath)
            try: self._process.kill()
            except Exception: pass
            return []
        except Exception:
            if not self._cancelled:   # errores silenciosos al cancelar son esperados
                log.exception("AudioAnalyzer decode failed for %s", self._filepath)
            return []
        finally:
            self._process = None

    # ── Main ─────────────────────────────────────────────────────────────────

    def run(self):
        samples = self._decode()
        if not samples:
            self.analysis_done.emit([])
            return

        # 4 independent lowpass filters applied to the same signal
        alphas = [self._alpha(fc) for fc in self.CUTOFFS]
        lps    = [self._lowpass(samples, a) for a in alphas]

        n = len(samples)

        # 5 bands as differences between adjacent lowpass outputs
        raw_bands = [
            lps[0],                                           # 0 – 80 Hz
            [lps[1][i] - lps[0][i] for i in range(n)],      # 80 – 250 Hz
            [lps[2][i] - lps[1][i] for i in range(n)],      # 250 – 600 Hz
            [lps[3][i] - lps[2][i] for i in range(n)],      # 600 – 1400 Hz
            [samples[i] - lps[3][i] for i in range(n)],     # 1400 Hz +
        ]

        result = []
        for band in raw_bands:
            abs_band = [abs(x) for x in band]
            energy   = self._rms_windows(abs_band)
            result.append(self._normalize(energy))

        self.analysis_done.emit(result)


# ─────────────────────────────────────────────────────────────────────────────
# VisualizerWidget
# ─────────────────────────────────────────────────────────────────────────────

class VisualizerWidget(QWidget):
    """
    48-bar spectrum visualizer driven by REAL multi-band audio energy.

    Independence system
    ───────────────────
    • 5 frequency bands (sub-bass → highs) from IIR filter cascade
    • Each bar belongs to one band — different bands react to completely
      different musical content (kick vs voice vs cymbal)
    • Per-bar random time offset ±120 ms  — bars in the same band still
      show staggered responses to transients
    • Per-bar amplitude multiplier 0.75–1.25  — persistent height variety
    • Per-bar sinusoidal variation ±12 % of actual energy — organic life

    Visual design
    ─────────────
    • Thin rectangular bars (≤ 8 px), 4 px gap
    • Gradient: deep purple base → lavender tip
    • Subtle reflection below baseline (fades to transparent)
    • 60 fps, asymmetric lerp: rise 0.42, fall 0.13
    """

    NUM_BARS  = 48
    NUM_BANDS = 5
    FPS       = 60
    LERP_UP   = 0.42
    LERP_DOWN = 0.13
    MAX_BAR_W = 8     # px — caps width so bars stay thin even on wide widgets
    GAP       = 4     # px between bars

    # Number of bars allocated to each frequency band (must sum to NUM_BARS)
    BAND_BARS = [5, 9, 10, 14, 10]   # sub, bass, lo-mid, mid, high

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._is_playing  = False
        self._position_ms = 0
        self._anim_time   = 0.0

        # Energy data (5 lists, one per band)
        self._band_energies  = []
        self._has_real_data  = False
        self._analyzer       = None

        self._heights = [0.0] * self.NUM_BARS
        self._targets = [0.0] * self.NUM_BARS

        # ── Precompute per-bar personality (fixed seed → consistent across runs) ──
        rng = random.Random(13)

        # Which band each bar belongs to
        self._bar_to_band = []
        for band_idx, count in enumerate(self.BAND_BARS):
            self._bar_to_band.extend([band_idx] * count)

        # Position of each bar within its band (0-based)
        self._bar_in_band  = []
        counts = [0] * self.NUM_BANDS
        for bar in range(self.NUM_BARS):
            b = self._bar_to_band[bar]
            self._bar_in_band.append(counts[b])
            counts[b] += 1

        # Time offset in energy-frames (float, ± a few frames)
        self._bar_frame_offset = [rng.uniform(-3.0, 3.0) for _ in range(self.NUM_BARS)]

        # Amplitude multiplier (persistent height variety)
        self._bar_amplitude = [rng.uniform(0.75, 1.25) for _ in range(self.NUM_BARS)]

        # Sinusoidal variation parameters
        self._phases = [rng.uniform(0.0, math.tau) for _ in range(self.NUM_BARS)]
        self._speeds = [rng.uniform(3.0, 7.0)      for _ in range(self.NUM_BARS)]

        self._timer = QTimer(self)
        self._timer.setInterval(1000 // self.FPS)   # ≈ 16 ms
        self._timer.timeout.connect(self._tick)

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self._heights = [0.0] * self.NUM_BARS
        self._targets = [0.0] * self.NUM_BARS
        self.update()

    def set_playing(self, is_playing: bool):
        self._is_playing = is_playing

    def set_position(self, position_ms: int):
        self._position_ms = position_ms

    def load_track(self, filepath: str):
        """Kicks off background analysis for the new track."""
        if self._analyzer and self._analyzer.isRunning():
            self._analyzer.cancel()
            # Espera limpia: al haber matado el subprocess, el hilo retorna casi de inmediato
            if not self._analyzer.wait(1500):
                log.warning("AudioAnalyzer no terminó en 1.5s — continuando de todos modos")
            # Liberar la referencia explícitamente. El analyzer terminado retiene
            # internamente las grandes listas de samples (~20M floats por canción
            # de 4 min) hasta ser recolectado. Soltarlo ya permite que GC libere
            # esa memoria antes de lanzar el nuevo analyzer.
            self._analyzer = None

        self._has_real_data = False
        self._band_energies = []

        self._analyzer = AudioAnalyzer(filepath, self)
        self._analyzer.analysis_done.connect(self._on_analysis_done)
        self._analyzer.start()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_analysis_done(self, band_data: list):
        if band_data and len(band_data) == self.NUM_BANDS:
            self._band_energies = band_data
            self._has_real_data = True
        else:
            log.debug("Analysis returned no data — using fallback animation")
            self._has_real_data = False

    # ── Animation loop ────────────────────────────────────────────────────────

    def _tick(self):
        self._anim_time += 1.0 / self.FPS

        if self._is_playing:
            if self._has_real_data:
                self._compute_targets_real()
            else:
                self._compute_targets_fallback()
        else:
            self._targets = [0.0] * self.NUM_BARS

        for i in range(self.NUM_BARS):
            diff  = self._targets[i] - self._heights[i]
            speed = self.LERP_UP if diff > 0 else self.LERP_DOWN
            self._heights[i] += diff * speed

        self.update()

    def _band_energy_at(self, band_idx: int, frame_offset: float) -> float:
        """Returns energy for a band at the current playback position + offset."""
        data = self._band_energies[band_idx]
        if not data:
            return 0.05
        fps   = AudioAnalyzer.FRAMES_PER_SEC
        frame = self._position_ms * fps / 1000.0 + frame_offset
        frame = max(0.0, min(frame, len(data) - 1))
        # Linear interpolation between adjacent frames
        lo  = int(frame)
        hi  = min(lo + 1, len(data) - 1)
        frac = frame - lo
        return data[lo] * (1 - frac) + data[hi] * frac

    def _compute_targets_real(self):
        t = self._anim_time
        for i in range(self.NUM_BARS):
            band  = self._bar_to_band[i]
            base  = self._band_energy_at(band, self._bar_frame_offset[i])
            base  = max(0.0, base * self._bar_amplitude[i])

            # Sinusoidal variation proportional to real energy
            # → quiet passages stay quiet even with variation applied
            var   = math.sin(t * self._speeds[i] + self._phases[i]) * 0.12
            var  *= max(base, 0.08)

            self._targets[i] = max(0.02, min(base + var, 1.0))

    def _compute_targets_fallback(self):
        """Used while FFmpeg is still analyzing — more dynamic than before."""
        t = self._anim_time
        for i in range(self.NUM_BARS):
            x  = i / (self.NUM_BARS - 1)
            # Distinct waves at different speeds, phased per bar
            w1 = math.sin(t * 4.0  + self._phases[i]) * 0.28
            w2 = math.sin(t * 7.5  + x * math.pi * 5) * 0.22
            w3 = math.sin(t * self._speeds[i] + self._phases[i] * 1.8) * 0.22
            w4 = abs(math.sin(t * 2.1 + i * 0.4)) * 0.18
            env = 0.25 + 0.75 * math.sin(x * math.pi)
            self._targets[i] = max(0.04, min((w1 + w2 + w3 + w4 + 0.10) * env, 1.0))

    # ── Rendering ─────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # crisp rectangles

        w = self.width()
        h = self.height()

        painter.fillRect(0, 0, w, h, QColor(10, 10, 10, 190))

        if w == 0 or h == 0:
            painter.end()
            return

        n         = self.NUM_BARS
        gap       = self.GAP
        bar_w_nat = max(2, (w - gap * (n - 1)) // n)
        bar_w     = min(bar_w_nat, self.MAX_BAR_W)   # enforce thin cap

        # Center the bar group in the widget
        total_w  = bar_w * n + gap * (n - 1)
        x_start  = (w - total_w) // 2

        max_bar_h  = int(h * 0.80)
        baseline_y = int(h * 0.87)

        painter.setPen(Qt.PenStyle.NoPen)

        for i, height_ratio in enumerate(self._heights):
            bar_h = int(height_ratio * max_bar_h)
            if bar_h < 1:
                continue

            x = x_start + i * (bar_w + gap)
            y = baseline_y - bar_h

            # ── Main bar ──
            grad = QLinearGradient(x, baseline_y, x, y)
            grad.setColorAt(0.0,  QColor(74,  20, 140, 255))   # deep purple
            grad.setColorAt(0.40, QColor(103, 58, 183, 255))   # mid purple
            grad.setColorAt(0.80, QColor(179, 157, 219, 255))  # light lavender
            grad.setColorAt(1.0,  QColor(225, 215, 245, 255))  # near-white tip

            painter.setBrush(QBrush(grad))
            painter.drawRect(x, y, bar_w, bar_h)

            # ── Reflection ──
            ref_h = max(1, int(bar_h * 0.15))
            grad_r = QLinearGradient(x, baseline_y, x, baseline_y + ref_h)
            grad_r.setColorAt(0.0, QColor(103, 58, 183, 40))
            grad_r.setColorAt(1.0, QColor(103, 58, 183, 0))
            painter.setBrush(QBrush(grad_r))
            painter.drawRect(x, baseline_y, bar_w, ref_h)

        painter.end()
