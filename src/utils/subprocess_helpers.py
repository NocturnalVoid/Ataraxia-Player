# -*- coding: utf-8 -*-
"""
Helper para invocar subprocesos (FFmpeg, FFprobe...) sin que Windows
abra una ventana negra de CMD al ejecutarlos.

Problema que resuelve:
  Cuando la app se empaqueta con `pyinstaller --noconsole`, no hay
  consola padre. Cada llamada a subprocess.run() / Popen() que ejecute
  un programa de consola (como ffmpeg.exe) abre una ventana nueva de
  CMD, lo que arruina la experiencia de usuario.

  Para evitarlo, hay que pasar a Popen el argumento `creationflags`
  con la bandera `CREATE_NO_WINDOW`. Pero esta bandera solo existe en
  Windows, así que en otros sistemas operativos (Linux, macOS) hay que
  pasar simplemente 0.

Uso:
    from src.utils.subprocess_helpers import quiet_kwargs

    subprocess.run(cmd, **quiet_kwargs(), stdout=subprocess.PIPE, ...)
    subprocess.Popen(cmd, **quiet_kwargs(), stderr=subprocess.PIPE, ...)

El helper solo añade los kwargs necesarios; no impide pasar cualquier
otro kwarg de subprocess (stdout, stderr, timeout, check, etc.).
"""
from __future__ import annotations
import subprocess
import sys


def quiet_kwargs() -> dict:
    """
    Retorna los kwargs que hay que pasar a subprocess.run / Popen para
    que el proceso hijo no abra una ventana de consola en Windows.

    En Linux / macOS retorna un dict vacío (es no-op).
    En Windows retorna {'creationflags': CREATE_NO_WINDOW}.
    """
    if sys.platform.startswith("win"):
        # CREATE_NO_WINDOW = 0x08000000 (disponible desde Python 3.7)
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}
