# -*- coding: utf-8 -*-
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, pyqtClassInfo, pyqtProperty
from PyQt6.QtDBus import QDBusConnection, QDBusAbstractAdaptor, QDBusMessage, QDBusObjectPath
import os

# =====================================================================
# 1. INTERFAZ RAÍZ (El contrato XML ahora está completo)
# =====================================================================
@pyqtClassInfo("D-Bus Interface", "org.mpris.MediaPlayer2")
@pyqtClassInfo("D-Bus Introspection", """
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/>
    <method name="Quit"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="Fullscreen" type="b" access="readwrite"/>
    <property name="CanSetFullscreen" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
""")
class MprisRootAdaptor(QDBusAbstractAdaptor):
    def __init__(self, parent):
        super().__init__(parent)

    @pyqtSlot()
    def Raise(self): pass
    @pyqtSlot()
    def Quit(self): pass

    @pyqtProperty(bool)
    def CanQuit(self): return False
    @pyqtProperty(bool)
    def Fullscreen(self): return False
    @Fullscreen.setter
    def Fullscreen(self, val): pass
    @pyqtProperty(bool)
    def CanSetFullscreen(self): return False
    @pyqtProperty(bool)
    def CanRaise(self): return False
    @pyqtProperty(bool)
    def HasTrackList(self): return False
    @pyqtProperty(str)
    def Identity(self): return "Ataraxia Player"
    @pyqtProperty(str)
    def DesktopEntry(self): return "ataraxia"
    @pyqtProperty(list)
    def SupportedUriSchemes(self): return ["file"]
    @pyqtProperty(list)
    def SupportedMimeTypes(self): return ["audio/mpeg", "audio/x-wav", "audio/flac"]

# =====================================================================
# 2. INTERFAZ DEL REPRODUCTOR (El contrato XML ahora está completo)
# =====================================================================
@pyqtClassInfo("D-Bus Interface", "org.mpris.MediaPlayer2.Player")
@pyqtClassInfo("D-Bus Introspection", """
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/>
    <method name="Previous"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Play"/>
    <method name="Pause"/>
    <method name="Seek">
      <arg name="Offset" type="x" direction="in"/>
    </method>
    <method name="SetPosition">
      <arg name="TrackId" type="o" direction="in"/>
      <arg name="Position" type="x" direction="in"/>
    </method>
    <method name="OpenUri">
      <arg name="Uri" type="s" direction="in"/>
    </method>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="Rate" type="d" access="readwrite"/>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="Volume" type="d" access="readwrite"/>
    <property name="Position" type="x" access="read"/>
    <property name="MinimumRate" type="d" access="read"/>
    <property name="MaximumRate" type="d" access="read"/>
    <property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanSeek" type="b" access="read"/>
    <property name="CanControl" type="b" access="read"/>
  </interface>
""")
class MprisPlayerAdaptor(QDBusAbstractAdaptor):
    play_pause_requested = pyqtSignal()
    next_requested = pyqtSignal()
    prev_requested = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self._status = "Stopped"
        self._metadata = {}

    @pyqtSlot()
    def PlayPause(self): self.play_pause_requested.emit()
    @pyqtSlot()
    def Next(self): self.next_requested.emit()
    @pyqtSlot()
    def Previous(self): self.prev_requested.emit()
    @pyqtSlot()
    def Play(self): self.play_pause_requested.emit()
    @pyqtSlot()
    def Pause(self): self.play_pause_requested.emit()
    @pyqtSlot()
    def Stop(self): pass

    @pyqtSlot('qlonglong')
    def Seek(self, offset): pass
    @pyqtSlot(QDBusObjectPath, 'qlonglong')
    def SetPosition(self, track_id, position): pass
    @pyqtSlot(str)
    def OpenUri(self, uri): pass

    @pyqtProperty(bool)
    def CanGoNext(self): return True
    @pyqtProperty(bool)
    def CanGoPrevious(self): return True
    @pyqtProperty(bool)
    def CanPlay(self): return True
    @pyqtProperty(bool)
    def CanPause(self): return True
    @pyqtProperty(bool)
    def CanControl(self): return True
    @pyqtProperty(bool)
    def CanSeek(self): return False

    @pyqtProperty(float)
    def Rate(self): return 1.0
    @Rate.setter
    def Rate(self, value): pass
    
    @pyqtProperty(float)
    def MinimumRate(self): return 1.0
    @pyqtProperty(float)
    def MaximumRate(self): return 1.0
    
    @pyqtProperty(float)
    def Volume(self): return 1.0
    @Volume.setter
    def Volume(self, value): pass

    @pyqtProperty('qlonglong')
    def Position(self): return 0

    @pyqtProperty(str)
    def PlaybackStatus(self): return self._status
    
    @pyqtProperty('QVariantMap')
    def Metadata(self): return self._metadata

    def update_status(self, is_playing: bool):
        self._status = "Playing" if is_playing else "Paused"
        self._notify_properties_changed({"PlaybackStatus": self._status})

    def update_metadata(self, title: str, artist: str, album: str, art_path: str):
        art_url = f"file://{os.path.abspath(art_path)}" if os.path.exists(art_path) else ""
        self._metadata = {
            "mpris:trackid": QDBusObjectPath("/org/mpris/MediaPlayer2/ataraxia/TrackList/NoTrack"),
            "xesam:title": title,
            "xesam:artist": [artist], 
            "xesam:album": album,
            "mpris:artUrl": art_url
        }
        self._notify_properties_changed({"Metadata": self._metadata})

    def _notify_properties_changed(self, changed_props: dict):
        try:
            msg = QDBusMessage.createSignal(
                "/org/mpris/MediaPlayer2",
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged"
            )
            msg.setArguments(["org.mpris.MediaPlayer2.Player", changed_props, []])
            QDBusConnection.sessionBus().send(msg)
        except Exception:
            pass

class MprisManager(QObject):
    def __init__(self):
        super().__init__()
        self.root_adaptor = MprisRootAdaptor(self)
        self.adaptor = MprisPlayerAdaptor(self)
        
        bus = QDBusConnection.sessionBus()
        bus.registerService("org.mpris.MediaPlayer2.ataraxia")
        bus.registerObject("/org/mpris/MediaPlayer2", self)