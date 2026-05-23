# -*- coding: utf-8 -*-
import os

class M3UManager:
    """Gestor de entrada/salida para archivos de listas de reproducción (.m3u)."""
    
    @staticmethod
    def export_to_m3u(file_path: str, playlist_name: str, filepaths: list) -> bool:
        """Crea un archivo .m3u estándar a partir de una lista de rutas."""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                f.write(f"#PLAYLIST:{playlist_name}\n")
                
                for track_path in filepaths:
                    if os.path.exists(track_path):
                        f.write(f"{track_path}\n")
            return True
        except Exception as e:
            print(f"Error exportando M3U: {e}")
            return False

    @staticmethod
    def import_from_m3u(file_path: str) -> list:
        """Lee un archivo .m3u y devuelve una lista con las rutas válidas que encuentre."""
        tracks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    
                    # Ignorar metadatos y líneas vacías
                    if line and not line.startswith("#"):
                        # Si es una ruta absoluta válida
                        if os.path.exists(line):
                            tracks.append(line)
                        else:
                            # Intento de resolver ruta relativa al archivo .m3u
                            base_dir = os.path.dirname(file_path)
                            full_path = os.path.join(base_dir, line)
                            if os.path.exists(full_path):
                                tracks.append(os.path.normpath(full_path))
        except Exception as e:
            print(f"Error importando M3U: {e}")
            
        return tracks