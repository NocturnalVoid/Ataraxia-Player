# -*- coding: utf-8 -*-
import subprocess
from src.utils.subprocess_helpers import quiet_kwargs
import os
import re
from PyQt6.QtCore import QObject, QThread, pyqtSignal

class ConversionWorker(QThread):
    """Hilo secundario que ejecuta FFmpeg para la conversión e inyección de carátulas."""
    progress_updated = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, conversion_data: dict, ffmpeg_path: str):
        super().__init__()
        self.data = conversion_data
        self.ffmpeg_path = ffmpeg_path
        self._is_cancelled = False
        self.process = None

    def run(self):
        input_path = self.data["input_path"]
        output_path = self.data["output_path"]
        settings = self.data["settings"]
        out_ext = os.path.splitext(output_path)[1].lower()

        # 2. CONSTRUCCIÓN DEL COMANDO FFMPEG
        command = [self.ffmpeg_path, "-y", "-i", input_path]
        
        # --- LÓGICA UNIVERSAL DE CARÁTULAS ---
        cover_path = settings.get("cover_path")
        usar_caratula = False
        
        # Clasificamos cómo procesaremos la imagen
        formatos_ffmpeg_nativos = [".mp3", ".flac", ".m4a"]
        formatos_mutagen = [".opus", ".ogg"]
        
        if cover_path and os.path.exists(cover_path) and "default_audio_icon.png" not in cover_path:
            usar_caratula = True

        if usar_caratula and out_ext in formatos_ffmpeg_nativos:
            command.extend(["-i", cover_path])
            command.extend([
                "-c:a", settings.get("codec", "libmp3lame"),
                "-map", "0:a:0", # Tomamos el audio
                "-map", "1:v:0"  # Tomamos la imagen
            ])
            
            if out_ext == ".mp3":
                # Estándar ID3v2 APIC para MP3
                command.extend([
                    "-c:v", "mjpeg", 
                    "-id3v2_version", "3", 
                    "-metadata:s:v", "title=Album cover",
                    "-metadata:s:v", "comment=Cover (front)"
                ])
            else:
                # Estándar Attached Picture para FLAC y M4A
                command.extend([
                    "-c:v", "mjpeg", 
                    "-disposition:v", "attached_pic"
                ])
        else:
            # Para Opus, OGG, WAV, o si no hay carátula: Forzamos "Solo Audio" (-vn)
            command.extend([
                "-vn", 
                "-c:a", settings.get("codec", "libmp3lame")
            ])

        # Configuración de Calidad (Bitrate): no se aplica en formatos sin pérdida
        if settings.get("bitrate") and out_ext not in ('.flac', '.wav'):
            command.extend(["-b:a", settings["bitrate"]])

        # Metadatos de Texto (Manuales o Heredados)
        tiene_metadatos_manuales = False
        if settings.get("title"):
            command.extend(["-metadata", f"title={settings['title']}"])
            tiene_metadatos_manuales = True
        if settings.get("artist"):
            command.extend(["-metadata", f"artist={settings['artist']}"])
            tiene_metadatos_manuales = True
        if settings.get("album"):
            command.extend(["-metadata", f"album={settings['album']}"])
            tiene_metadatos_manuales = True
            
        if not tiene_metadatos_manuales:
            # Si el usuario no escribió nada, heredamos los metadatos del archivo original
            command.extend(["-map_metadata", "0"])

        # Salida
        command.append(output_path)

        try:
            # 3. EJECUCIÓN
            self.process = subprocess.Popen(
                command, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                universal_newlines=True, encoding='utf-8', errors='ignore',
                **quiet_kwargs()
            )

            duration_secs = self._get_duration(input_path)

            for line in self.process.stderr:
                if self._is_cancelled:
                    self.process.terminate()
                    self.error.emit("Conversión cancelada.")
                    self._cleanup_temp_files(output_path, settings)
                    return

                time_match = re.search(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})", line)
                if time_match and duration_secs > 0:
                    h, m, s = float(time_match.group(1)), float(time_match.group(2)), float(time_match.group(3))
                    current_secs = h * 3600 + m * 60 + s
                    progress = int((current_secs / duration_secs) * 100)
                    self.progress_updated.emit(min(progress, 99))

            self.process.wait()
            
            if self.process.returncode == 0:
                # --- POST-PROCESAMIENTO MÁGICO PARA OPUS Y OGG ---
                if usar_caratula and out_ext in formatos_mutagen:
                    self._inject_ogg_opus_cover(output_path, cover_path)
                # -------------------------------------------------
                
                self.progress_updated.emit(100)
                self.finished.emit(f"Audio extraído y carátula incrustada en:\n{output_path}")
            else:
                self.error.emit(f"FFmpeg falló (Código {self.process.returncode})")

        except FileNotFoundError:
            self.error.emit("FFmpeg no encontrado. Revisa preferencias.")
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if cover_path and "default_audio_icon.png" not in cover_path:
                 self._cleanup_temp_files(None, settings)

    def _inject_ogg_opus_cover(self, audio_path: str, cover_path: str):
        """Inyecta la carátula en formato Base64 para archivos OPUS y OGG usando Mutagen."""
        try:
            import base64
            import mutagen
            from mutagen.flac import Picture

            with open(cover_path, 'rb') as img:
                pic_data = img.read()

            # Creamos el bloque de imagen que usan los contenedores de Vorbis/Opus
            pic = Picture()
            pic.data = pic_data
            pic.type = 3 # 3 = Portada frontal principal
            pic.mime = "image/jpeg" if cover_path.lower().endswith(('.jpg', '.jpeg')) else "image/png"
            pic.desc = "Cover"

            # Opus/Ogg requieren que el bloque de la imagen esté codificado en Base64
            pic_b64 = base64.b64encode(pic.write()).decode('ascii')

            audio = mutagen.File(audio_path)
            if audio is not None:
                audio['metadata_block_picture'] = [pic_b64]
                audio.save()
        except Exception as e:
            print(f"Advertencia: No se pudo inyectar la carátula en OPUS/OGG: {e}")

    def _get_duration(self, filepath) -> float:
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filepath]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    universal_newlines=True, **quiet_kwargs())
            return float(result.stdout.strip())
        except:
            return 0.0

    def _cleanup_temp_files(self, output_to_remove, settings):
        if output_to_remove and os.path.exists(output_to_remove):
            try: os.remove(output_to_remove)
            except: pass
            
        cover_path = settings.get("cover_path")
        if cover_path and "default_audio_icon.png" not in cover_path and os.path.exists(cover_path):
            try: os.remove(cover_path)
            except: pass

    def cancel(self):
        self._is_cancelled = True

class MediaConverter(QObject):
    def __init__(self):
        super().__init__()
        self.ffmpeg_path = "ffmpeg"
        self.worker = None

    def start_worker(self, conversion_data: dict):
        self.worker = ConversionWorker(conversion_data, self.ffmpeg_path)
        self.worker.start()

    def cancel_worker(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()