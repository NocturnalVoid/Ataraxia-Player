# -*- coding: utf-8 -*-
from PyQt6.QtCore import QObject, pyqtSignal
import os

class SmtcManager(QObject):
    """
    Integración nativa con Windows System Media Transport Controls (SMTC).
    Controla las teclas físicas y el panel multimedia del sistema operativo.
    """
    play_pause_requested = pyqtSignal()
    next_requested = pyqtSignal()
    prev_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._player = None
        try:
            from winsdk.windows.media.playback import MediaPlayer
            
            # En Windows, para acceder al SMTC necesitamos instanciar un reproductor nativo.
            # Lo usaremos de forma "fantasma" únicamente como puente de comunicación.
            self._player = MediaPlayer()
            self._player.command_manager.is_enabled = True

            self.smtc = self._player.system_media_transport_controls
            self.smtc.is_play_enabled = True
            self.smtc.is_pause_enabled = True
            self.smtc.is_next_enabled = True
            self.smtc.is_previous_enabled = True

            # Conectamos las pulsaciones del hardware de Windows a nuestras señales de PyQt
            self._player.command_manager.add_play_received(self._on_play)
            self._player.command_manager.add_pause_received(self._on_pause)
            self._player.command_manager.add_next_received(self._on_next)
            self._player.command_manager.add_previous_received(self._on_prev)
        except ImportError:
            print("Librería winsdk no encontrada. SMTC de Windows desactivado.")

    def _on_play(self, sender, args):
        args.handled = True
        self.play_pause_requested.emit()

    def _on_pause(self, sender, args):
        args.handled = True
        self.play_pause_requested.emit()

    def _on_next(self, sender, args):
        args.handled = True
        self.next_requested.emit()

    def _on_prev(self, sender, args):
        args.handled = True
        self.prev_requested.emit()

    def update_status(self, is_playing: bool):
        """Avisa a Windows si el reproductor está en Play o Pause."""
        if not self._player: return
        from winsdk.windows.media import MediaPlaybackStatus
        
        self.smtc.playback_status = (
            MediaPlaybackStatus.PLAYING if is_playing 
            else MediaPlaybackStatus.PAUSED
        )

    def update_metadata(self, title: str, artist: str, album: str, art_path: str):
        """Envía la carátula y textos al panel de control de volumen de Windows."""
        if not self._player: return
        from winsdk.windows.media import MediaPlaybackType
        
        updater = self.smtc.display_updater
        updater.type = MediaPlaybackType.MUSIC
        updater.music_properties.title = title
        updater.music_properties.artist = artist
        updater.music_properties.album_artist = artist

        # Windows exige un formato estricto (URI absoluta) para leer las imágenes locales
        if art_path and os.path.exists(art_path):
            from winsdk.windows.storage.streams import RandomAccessStreamReference
            from winsdk.windows.foundation import Uri
            
            # Normalizamos la ruta (reemplazamos \ por /) y creamos el URI
            uri_str = f"file:///{os.path.abspath(art_path).replace(os.sep, '/')}"
            updater.thumbnail = RandomAccessStreamReference.create_from_uri(Uri(uri_str))
        else:
            updater.thumbnail = None

        updater.update()