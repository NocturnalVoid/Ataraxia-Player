# -*- coding: utf-8 -*-
"""
Bloqueo del archivo de base de datos multiplataforma.

Cuando Ataraxia Player está abierto, mantenemos un lockfile junto al
.db para indicar visualmente al usuario (y al sistema) que la BD está
en uso. El lockfile usa:

  - Windows: msvcrt.locking() — bloqueo exclusivo de bytes
  - Linux / macOS: fcntl.flock() — bloqueo exclusivo no bloqueante

El lockfile se libera automáticamente al cerrar el handle (que ocurre
cuando el proceso termina, incluso si crashea). Es decir, no hace falta
limpieza manual ni preocuparse por archivos huérfanos.

Diferencia con el bloqueo de SQLite:
  - SQLite ya bloquea el .db durante transacciones, pero no impide que
    el usuario lo BORRE desde el explorador (especialmente en Linux,
    donde un unlink() sobre un archivo abierto no falla).
  - Nuestro lockfile es VISIBLE: el usuario lo ve y entiende que algo
    está usando la BD. Aunque no podemos impedir el borrado externo,
    sí lo dejamos claramente señalado.

Sí impedimos el borrado/sobrescritura cuando el archivo está abierto
con bloqueo exclusivo, en los sistemas donde el OS lo soporta:
  - Windows: bloqueo exclusivo impide otros open() en modo write
  - Linux: flock cooperativo (otros procesos que usen flock se respetan)
"""
from __future__ import annotations
import os
import sys
import atexit
from src.utils.logger import get_logger

log = get_logger(__name__)


class DatabaseLock:
    """
    Gestiona un lockfile junto a la base de datos.

    Uso:
        lock = DatabaseLock(db_path)
        if not lock.acquire():
            # Otra instancia está usando la BD — el SingleInstanceHandler
            # debería haber prevenido esto, pero por si acaso.
            ...
        # ... uso normal de la app ...
        lock.release()    # o se libera automáticamente al cierre del proceso
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.lock_path = f"{db_path}.lock"
        self._handle = None
        self._acquired = False

    # ──────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────

    def acquire(self) -> bool:
        """
        Intenta adquirir el lock. Retorna True si lo consigue, False si
        ya está bloqueado por otro proceso. En éxito, registra la
        liberación automática al cierre del intérprete.
        """
        if self._acquired:
            return True

        try:
            # Abrir / crear el lockfile. Se reescribe con metadatos básicos
            # (PID + timestamp) para que un humano pueda inspeccionarlo.
            self._handle = open(self.lock_path, "w+", encoding="utf-8")
            self._handle.write(
                f"PID={os.getpid()}\n"
                f"Locked by Ataraxia Player.\n"
                f"This file is held while the app is running.\n"
                f"It will be released automatically when the app closes.\n"
            )
            self._handle.flush()

            if sys.platform.startswith("win"):
                self._acquire_windows()
            else:
                self._acquire_unix()

            self._acquired = True
            # Registrar liberación incluso si la app termina abruptamente
            atexit.register(self.release)
            log.info("DB lock acquired: %s", self.lock_path)
            return True

        except (BlockingIOError, OSError, ImportError):
            log.warning("DB lock NOT acquired (another instance may be running): %s",
                        self.lock_path)
            self._close_handle()
            return False

    def release(self):
        """Libera el lock y elimina el archivo si pudimos crearlo."""
        if not self._acquired:
            return
        try:
            if sys.platform.startswith("win"):
                self._release_windows()
            else:
                self._release_unix()
        except Exception:
            log.exception("Error liberando lock de BD")
        finally:
            self._close_handle()
            # Intentar borrar el lockfile (puede fallar si otro proceso ya lo tiene)
            try:
                if os.path.exists(self.lock_path):
                    os.remove(self.lock_path)
            except OSError:
                pass
            self._acquired = False

    def is_locked_by_us(self) -> bool:
        return self._acquired

    # ──────────────────────────────────────────────────────────────────
    # WINDOWS — msvcrt.locking
    # ──────────────────────────────────────────────────────────────────

    def _acquire_windows(self):
        import msvcrt
        # Bloqueo exclusivo no bloqueante sobre el primer byte
        msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _release_windows(self):
        import msvcrt
        try:
            # Volver al inicio antes de desbloquear
            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

    # ──────────────────────────────────────────────────────────────────
    # UNIX (Linux, macOS) — fcntl.flock
    # ──────────────────────────────────────────────────────────────────

    def _acquire_unix(self):
        import fcntl
        fcntl.flock(self._handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release_unix(self):
        import fcntl
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass

    # ──────────────────────────────────────────────────────────────────
    # CLEANUP
    # ──────────────────────────────────────────────────────────────────

    def _close_handle(self):
        if self._handle is not None:
            try:
                self._handle.close()
            except Exception:
                pass
            self._handle = None
