# -*- coding: utf-8 -*-
import os
import re
import bisect

class LyricsParser:
    """
    Motor inteligente para leer letras de canciones.
    Soporta formato .LRC (estándar de audio), .SRT (video) y .TXT (texto plano).
    """
    def __init__(self):
        self.lines = []       # Guarda el texto puro de cada línea
        self.timestamps = []  # Guarda en qué milisegundo ocurre cada línea
        self.is_synced = False # True si tiene tiempos, False si es texto plano
        self.current_file = ""

    def load_file(self, audio_filepath: str):
        """Busca un archivo de letras asociado al audio y lo procesa."""
        self.lines.clear()
        self.timestamps.clear()
        self.is_synced = False
        self.current_file = ""

        if not audio_filepath: return

        # Construir rutas posibles (ej. cancion.mp3 -> cancion.lrc)
        base_path = os.path.splitext(audio_filepath)[0]
        lrc_path = f"{base_path}.lrc"
        srt_path = f"{base_path}.srt"
        txt_path = f"{base_path}.txt"

        # Prioridad de lectura: 1. LRC, 2. SRT, 3. TXT
        if os.path.exists(lrc_path):
            self._parse_lrc(lrc_path)
            self.current_file = lrc_path
        elif os.path.exists(srt_path):
            self._parse_srt(srt_path)
            self.current_file = srt_path
        elif os.path.exists(txt_path):
            self._parse_txt(txt_path)
            self.current_file = txt_path

    def load_from_text(self, content: str, is_synced: bool = True):
        """
        Carga letras directamente desde un string (sin leer archivo).
        Útil cuando las letras vienen de una API y no están en disco.

        is_synced=True: se intenta parsear como LRC. Si no hay timestamps válidos,
        se usa como texto plano automáticamente.
        """
        self.lines.clear()
        self.timestamps.clear()
        self.is_synced = False
        self.current_file = "<api>"

        if not content or not content.strip():
            return

        if is_synced:
            # Intentar parseo LRC en memoria
            self.is_synced = True
            lrc_regex = re.compile(r'\[(\d{2,}):(\d{2}[\.:]\d{2,3})\](.*)')
            for line in content.splitlines():
                match = lrc_regex.search(line)
                if match:
                    mins = int(match.group(1))
                    secs_parts = match.group(2).replace(':', '.').split('.')
                    secs = int(secs_parts[0])
                    ms = int(secs_parts[1].ljust(3, '0')[:3])
                    total_ms = (mins * 60 * 1000) + (secs * 1000) + ms
                    text = match.group(3).strip()
                    if text:
                        self.timestamps.append(total_ms)
                        self.lines.append(text)

            # Si el contenido venía marcado como sync pero no tenía timestamps
            # reales, lo tratamos como texto plano
            if not self.timestamps:
                self.is_synced = False
                self.lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        else:
            self.lines = [ln.strip() for ln in content.splitlines() if ln.strip()]

    def _parse_lrc(self, filepath: str):
        """Extrae tiempos del formato LRC: [01:22.50] Letra de la canción"""
        self.is_synced = True
        # Regex para atrapar [minutos:segundos.milisegundos]
        lrc_regex = re.compile(r'\[(\d{2,}):(\d{2}[\.:]\d{2,3})\](.*)')
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    match = lrc_regex.search(line)
                    if match:
                        mins = int(match.group(1))
                        # Reemplazar coma/puntos y calcular milisegundos
                        secs_parts = match.group(2).replace(':', '.').split('.')
                        secs = int(secs_parts[0])
                        ms = int(secs_parts[1].ljust(3, '0')[:3]) # Normalizar a 3 dígitos
                        
                        total_ms = (mins * 60 * 1000) + (secs * 1000) + ms
                        text = match.group(3).strip()
                        
                        if text: # Evitamos guardar líneas de tiempo vacías
                            self.timestamps.append(total_ms)
                            self.lines.append(text)
        except Exception as e:
            print(f"Error leyendo LRC: {e}")
            self.is_synced = False

    def _parse_srt(self, filepath: str):
        """Extrae tiempos del formato SRT: 00:01:22,500 --> 00:01:25,000"""
        self.is_synced = True
        # Regex para atrapar el tiempo inicial de un bloque SRT
        srt_time_regex = re.compile(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->')
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().split('\n\n') # SRT separa bloques por doble salto de línea
                
                for block in content:
                    lines = block.split('\n')
                    if len(lines) >= 3:
                        # La línea 1 suele ser el tiempo (después del número de bloque)
                        time_line = lines[1]
                        text = " ".join(lines[2:]).strip() # Unir el resto como texto
                        
                        match = srt_time_regex.search(time_line)
                        if match and text:
                            h, m, s, ms = map(int, match.groups())
                            total_ms = (h * 3600 * 1000) + (m * 60 * 1000) + (s * 1000) + ms
                            
                            self.timestamps.append(total_ms)
                            self.lines.append(text)
        except Exception as e:
            print(f"Error leyendo SRT: {e}")
            self.is_synced = False

    def _parse_txt(self, filepath: str):
        """Lee texto plano sin sincronización."""
        self.is_synced = False
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                # Evitamos guardar miles de líneas vacías
                self.lines = [line.strip() for line in f.readlines() if line.strip()]
        except Exception as e:
            print(f"Error leyendo TXT: {e}")

    def get_state_at_time(self, current_ms: int) -> tuple:
        """
        Devuelve (lista_de_lineas, indice_actual, esta_sincronizado)
        Ideal para el efecto Karaoke.
        """
        if not self.lines:
            return ([], -1, False)
            
        if not self.is_synced:
            return (self.lines, -1, False)

        # Búsqueda binaria: O(log n) en vez de O(n)
        # bisect_right da el primer índice mayor a current_ms; retrocedemos 1 para la línea activa
        idx = bisect.bisect_right(self.timestamps, current_ms) - 1
        current_index = idx if idx >= 0 else -1

        return (self.lines, current_index, True)