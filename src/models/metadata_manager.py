# -*- coding: utf-8 -*-
import os
from mutagen import File
from mutagen.id3 import APIC
import requests
import urllib.parse

class MetadataManager:
    def __init__(self):
        self.supported_formats = (
            '.mp3', '.flac', '.wav', '.m4a', '.ogg', 
            '.opus', '.aac', '.webm', '.mka', '.wma'
        )

    def _read_audio_tags(self, file_path: str) -> dict | None:
        """
        Helper interno: abre el archivo con mutagen y devuelve un dict con todos
        los tags normalizados. Retorna None si el archivo no es soportado.
        El número de pista se normaliza de "1/12" a 1 de forma segura.
        """
        audio = File(file_path, easy=True)
        if audio is None:
            return None

        # Helper local: obtiene el primer valor de un tag de mutagen-easy.
        # Necesario porque audio.get('campo', [default]) NO usa el default cuando
        # la clave existe pero contiene una lista vacía (caso real con archivos
        # de Deemix y otros taggers que crean frames vacíos).
        def first(key: str, default: str = "") -> str:
            try:
                values = audio.get(key)
                if not values:
                    return default
                value = values[0]
                if value is None:
                    return default
                return str(value).strip() or default
            except (IndexError, TypeError, AttributeError):
                return default

        track_str = first('tracknumber', '0')
        try:
            track_num = int(track_str.split('/')[0]) if track_str else 0
        except (ValueError, AttributeError):
            track_num = 0

        # Año: puede venir como "2003", "2003-04-12" o "2003/04/12"
        year_raw = first('date', '0')
        try:
            year = int(year_raw[:4]) if year_raw else 0
        except (ValueError, TypeError):
            year = 0

        return {
            "title":        first('title',  os.path.basename(file_path)),
            "artist":       first('artist', 'Artista Desconocido'),
            "album":        first('album',  'Álbum Desconocido'),
            "tracknumber":  track_str,
            "track_num":    track_num,
            "duration":     int(audio.info.length) if hasattr(audio.info, 'length') else 0,
            "genre":        first('genre', ''),
            "year":         year,
        }

    def extract_metadata(self, file_path: str) -> dict:
        try:
            tags = self._read_audio_tags(file_path)
            if tags is None:
                raise ValueError("Archivo no soportado")
            return {
                "title":       tags["title"],
                "artist":      tags["artist"],
                "album":       tags["album"],
                "tracknumber": tags["tracknumber"],
                "duration":    tags["duration"],
            }
        except Exception:
            return {
                "title":    os.path.basename(file_path),
                "artist":   "Desconocido",
                "album":    "Desconocido",
                "duration": 0,
            }

    def extract_cover_art(self, file_path: str, output_path: str = "assets/current_cover.jpg") -> str:
        """Extrae la imagen incrustada de MP3, FLAC, OPUS, OGG y M4A."""
        try:
            audio = File(file_path)
            if audio is None:
                return "assets/default_cover.png"

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 1. Método para MP3 (Etiquetas ID3 APIC)
            if hasattr(audio, 'tags') and audio.tags:
                for tag in audio.tags.values():
                    if isinstance(tag, APIC):
                        with open(output_path, 'wb') as img: 
                            img.write(tag.data)
                        return output_path

            # 2. Método para FLAC (Tienen el atributo nativo .pictures)
            if hasattr(audio, 'pictures') and audio.pictures:
                with open(output_path, 'wb') as img: 
                    img.write(audio.pictures[0].data)
                return output_path

            # 3. Método para OPUS / OGG (La imagen viene encriptada en Base64)
            if hasattr(audio, 'tags') and audio.tags and 'metadata_block_picture' in audio.tags:
                import base64
                from mutagen.flac import Picture
                
                # Extraemos el texto Base64 y lo decodificamos a bytes
                pic_data_b64 = audio.tags['metadata_block_picture'][0]
                pic_bytes = base64.b64decode(pic_data_b64)
                
                # Usamos la clase Picture de FLAC para interpretar esos bytes
                pic = Picture(pic_bytes)
                with open(output_path, 'wb') as img: 
                    img.write(pic.data)
                return output_path
                
            # 4. Método para M4A / MP4 (Etiqueta 'covr')
            if hasattr(audio, 'tags') and audio.tags and 'covr' in audio.tags:
                covr_data = audio.tags['covr'][0]
                data_to_write = covr_data if isinstance(covr_data, bytes) else getattr(covr_data, 'data', b'')
                if data_to_write:
                    with open(output_path, 'wb') as img: 
                        img.write(data_to_write)
                    return output_path

        except Exception as e:
            print(f"Error extrayendo carátula de {file_path}: {e}")
            pass
            
        return "assets/default_cover.png"

    def scan_directory_to_db(self, directory: str, db_manager):
        from src.utils.logger import get_logger
        log = get_logger(__name__)
        log.info("Iniciando escaneo en: %s", directory)
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            for root, dirs, files in os.walk(directory):
                for file_name in files:
                    if file_name.lower().endswith(self.supported_formats):
                        file_path = os.path.join(root, file_name)
                        self._process_and_save_track(file_path, cursor)
            conn.commit()
            log.info("Escaneo finalizado y guardado en la base de datos.")

    def _process_and_save_track(self, file_path: str, cursor):
        from src.utils.logger import get_logger
        log = get_logger(__name__)
        try:
            tags = self._read_audio_tags(file_path)
            if tags is None:
                return

            title        = tags["title"]
            artist       = tags["artist"]
            album        = tags["album"]
            duration     = tags["duration"]
            track_number = tags["track_num"]
            genre        = tags["genre"]
            year         = tags["year"]

            cursor.execute("INSERT OR IGNORE INTO artists (name) VALUES (?)", (artist,))
            cursor.execute("SELECT id FROM artists WHERE name = ?", (artist,))
            artist_id = cursor.fetchone()[0]

            cursor.execute("INSERT OR IGNORE INTO albums (title, artist_id) VALUES (?, ?)", (album, artist_id))
            cursor.execute("SELECT id FROM albums WHERE title = ? AND artist_id = ?", (album, artist_id))
            album_id = cursor.fetchone()[0]

            cursor.execute("""
                INSERT OR IGNORE INTO songs
                    (title, filepath, duration, track_number, genre, year, album_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (title, file_path, duration, track_number, genre, year, album_id))

            # Fill in missing track metadata for songs already in the library
            cursor.execute("""
                UPDATE songs
                SET track_number = ?, genre = ?, year = ?
                WHERE filepath = ? AND (track_number IS NULL OR track_number = 0)
            """, (track_number, genre, year, file_path))

        except Exception:
            # log.exception captura el traceback completo automáticamente
            log.exception("Error procesando archivo de audio: %s", file_path)

    def get_library_tree(self, db_manager) -> dict:
        library_data = {}
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ar.name, al.title, s.track_number, s.title, s.filepath
                FROM songs s
                JOIN albums  al ON s.album_id  = al.id
                JOIN artists ar ON al.artist_id = ar.id
                ORDER BY ar.name, al.title, s.track_number, s.title
            """)
            rows = cursor.fetchall()

            for artist, album, track_number, title, path in rows:
                if artist not in library_data:
                    library_data[artist] = {}
                if album not in library_data[artist]:
                    library_data[artist][album] = []
                library_data[artist][album].append((track_number, title, path))

        return library_data

    def save_metadata(self, file_path: str, new_data: dict) -> bool:
        """Inyecta los nuevos metadatos en el archivo físico. Soporta multi-formato gracias a easy=True."""
        try:
            audio = File(file_path, easy=True)
            if audio is None:
                return False
            
            if "title" in new_data: audio['title'] = new_data["title"]
            if "artist" in new_data: audio['artist'] = new_data["artist"]
            if "album" in new_data: audio['album'] = new_data["album"]
            if "tracknumber" in new_data: audio['tracknumber'] = new_data["tracknumber"]
            
            audio.save()
            return True
        except Exception as e:
            print(f"Error guardando metadatos físicos en {file_path}: {e}")
            return False

    def fetch_and_embed_cover(self, filepath: str, title: str, artist: str, api_url: str) -> bool:
        """
        Descarga una carátula de la API y la incrusta físicamente en el archivo de audio.
        Retorna True si tuvo éxito, False en caso contrario.
        """
        if not title or not artist or title == "Desconocido" or artist == "Artista Desconocido":
            return False

        # 1. Seguridad: Usamos nuestro propio extractor para evitar "falsos positivos" de Deemix
        # Si el extractor nos devuelve algo distinto a la imagen por defecto, significa que SÍ tiene carátula.
        cover_actual = self.extract_cover_art(filepath)
        if cover_actual != "assets/default_cover.png":
            return False

        # 2. Formatear la consulta segura para URL
        query = urllib.parse.quote(f"{artist} {title}")
        url = api_url.replace("{query}", query)

        # --- Reporte en consola de lo que Ataraxia va a buscar ---
        print(f"\n[API BUSCANDO] -> {artist} - {title}")
        print(f"[API URL] -> {url}")

        try:
            # 3. Llamada a la API
            response = requests.get(url, timeout=5)
            
            # --- Reporte del servidor ---
            print(f"[API RESPUESTA HTTP] -> Código {response.status_code}")
            
            if response.status_code != 200:
                return False
                
            data = response.json()
            resultados = data.get('resultCount', 0)
            print(f"[API RESULTADOS] -> Encontró {resultados} coincidencia(s)")
            
            if resultados > 0:
                # Extraemos la imagen que nos da Apple
                img_url_low_res = data['results'][0].get('artworkUrl100', '')
                if not img_url_low_res: return False
                
                # Truco para forzar calidad 600x600 en lugar de 100x100
                img_url_high_res = img_url_low_res.replace('100x100bb', '600x600bb')
                img_data = requests.get(img_url_high_res, timeout=5).content
                
                # 4. Incrustar físicamente en el archivo de audio
                exito = self._embed_image_to_file(filepath, img_data)
                
                if exito:
                    print("[API ÉXITO] -> ¡Carátula incrustada en el archivo correctamente!")
                else:
                    print("[API ERROR] -> Falló la inyección de bytes en el archivo físico.")
                
                return exito
            else:
                return False
                
        except Exception as e:
            print(f"[API ERROR CRÍTICO] -> {e}")
            return False

    def _embed_image_to_file(self, filepath: str, img_data: bytes) -> bool:
        """Incrusta la imagen si el archivo está libre, si no, guarda en caché."""
        # Primero, guardamos una copia en la caché siempre
        cache_name = os.path.basename(filepath) + ".jpg"
        cache_path = os.path.join("assets/covers_cache", cache_name)
        with open(cache_path, 'wb') as f:
            f.write(img_data)

        try:
            ext = os.path.splitext(filepath)[1].lower()
            
            if ext == '.mp3':
                from mutagen.id3 import ID3
                audio = ID3(filepath)
                audio.add(APIC(
                    encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img_data
                ))
                audio.save(v2_version=3)
                return True
                
            elif ext == '.flac':
                from mutagen.flac import FLAC, Picture
                audio = FLAC(filepath)
                pic = Picture()
                pic.type = 3
                pic.mime = "image/jpeg"
                pic.desc = "Cover"
                pic.data = img_data
                audio.add_picture(pic)
                audio.save()
                return True
                
            # --- NUEVO: Soporte para OPUS y OGG (Requiere Base64) ---
            elif ext in ['.opus', '.ogg']:
                import base64
                from mutagen.flac import Picture
                
                audio = File(filepath)
                if audio is None: return False
                
                pic = Picture()
                pic.type = 3
                pic.mime = "image/jpeg"
                pic.desc = "Cover"
                pic.data = img_data
                
                # Codificar a Base64
                pic_b64 = base64.b64encode(pic.write()).decode('ascii')
                audio['metadata_block_picture'] = [pic_b64]
                audio.save()
                return True
                
            # --- NUEVO: Soporte para M4A / MP4 ---
            elif ext in ['.m4a', '.mp4']:
                from mutagen.mp4 import MP4, MP4Cover
                audio = MP4(filepath)
                audio['covr'] = [MP4Cover(img_data, imageformat=MP4Cover.FORMAT_JPEG)]
                audio.save()
                return True
                
        except Exception as e:
            print(f"[AVISO] Archivo ocupado, se usará caché temporal: {e}")
            return True # Retornamos True porque al menos ya tenemos la imagen en caché