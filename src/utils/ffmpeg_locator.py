# -*- coding: utf-8 -*-
"""
Localizador de binarios FFmpeg.

Estrategia de búsqueda (por orden de prioridad):

  1. Junto al ejecutable de la app (caso instalador con FFmpeg embebido
     en una subcarpeta 'ffmpeg/'). Cubre el caso típico de distribución
     con Inno Setup en Windows.

  2. En el directorio raíz del proyecto (modo desarrollo: junto a main.py).

  3. En el PATH del sistema (instalación manual del usuario, distribuciones
     Linux donde ffmpeg viene como paquete del sistema).

  4. En rutas conocidas de instalaciones por paquete en Linux/macOS.

Si nada se encuentra, devuelve el nombre simple ("ffmpeg" / "ffprobe")
para que subprocess al menos lo intente y falle con un error claro.
"""
import os
import sys
import shutil
from src.utils.logger import get_logger

log = get_logger(__name__)

# Cache para no repetir la búsqueda en cada invocación
_BINARY_CACHE: dict = {}


def _candidate_paths_for(binary_name: str):
    """
    Genera las rutas candidatas a probar, por orden de prioridad.
    `binary_name` debe ser 'ffmpeg' o 'ffprobe' (sin extensión).
    """
    is_windows = sys.platform.startswith("win")
    exe_suffix = ".exe" if is_windows else ""
    fname = binary_name + exe_suffix

    # ─ 1) Junto al ejecutable de la app (caso instalador) ─────────────
    # En .exe compilado con PyInstaller, sys.executable es el .exe del
    # usuario, no Python. El instalador colocó ffmpeg en una subcarpeta
    # 'ffmpeg/' al lado.
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
        yield os.path.join(app_dir, "ffmpeg", fname)
        # También probamos en el mismo directorio (por si lo movió el usuario)
        yield os.path.join(app_dir, fname)

    # ─ 2) En el directorio raíz del proyecto (desarrollo) ─────────────
    # Cuando se ejecuta como 'python main.py', el cwd está en la raíz.
    # Si el desarrollador tiene una copia de ffmpeg ahí dentro, la usa.
    yield os.path.join(os.getcwd(), "ffmpeg", fname)

    # ─ 3) En el PATH del sistema ──────────────────────────────────────
    found_in_path = shutil.which(binary_name)
    if found_in_path:
        yield found_in_path

    # ─ 4) Rutas conocidas en Linux/macOS ──────────────────────────────
    if not is_windows:
        for prefix in ("/usr/bin", "/usr/local/bin", "/opt/homebrew/bin"):
            yield os.path.join(prefix, binary_name)


def get_ffmpeg_path() -> str:
    """Retorna la ruta absoluta al ejecutable de ffmpeg, o 'ffmpeg' si no se encuentra."""
    return _resolve_binary("ffmpeg")


def get_ffprobe_path() -> str:
    """Retorna la ruta absoluta al ejecutable de ffprobe, o 'ffprobe' si no se encuentra."""
    return _resolve_binary("ffprobe")


def _resolve_binary(binary_name: str) -> str:
    """
    Busca el binario en las rutas candidatas y cachea el resultado.
    Si no encuentra ninguna ruta válida, devuelve el nombre simple
    para que subprocess al menos genere un error claro de "no encontrado".
    """
    if binary_name in _BINARY_CACHE:
        return _BINARY_CACHE[binary_name]

    for candidate in _candidate_paths_for(binary_name):
        if candidate and os.path.isfile(candidate):
            log.info("FFmpeg resolver: %s → %s", binary_name, candidate)
            _BINARY_CACHE[binary_name] = candidate
            return candidate

    # Fallback: nombre simple (subprocess intentará buscarlo en PATH)
    log.warning(
        "FFmpeg resolver: NO se encontró %s en rutas conocidas. "
        "Se usará el nombre simple, lo que requiere que esté en PATH.",
        binary_name
    )
    _BINARY_CACHE[binary_name] = binary_name
    return binary_name


def is_ffmpeg_available() -> bool:
    """
    Verifica si FFmpeg está disponible para usar. Útil para mostrar un
    aviso al usuario en la UI si la instalación está incompleta.
    """
    path = get_ffmpeg_path()
    return os.path.isfile(path) or shutil.which(path) is not None
