# -*- coding: utf-8 -*-
"""
Central logging configuration for Ataraxia Player.

Logs go to a rotating file in the app's data directory so the user can
attach them to bug reports without noisy stderr output.

Location:
    Linux:   ~/.local/share/AtaraxiaPlayer/ataraxia.log
    Windows: %APPDATA%\\AtaraxiaPlayer\\ataraxia.log

Usage from any module:
    from src.utils.logger import get_logger
    log = get_logger(__name__)
    log.info("Track loaded: %s", filepath)
    log.error("FFmpeg failed", exc_info=True)
"""
import logging
import logging.handlers
import os
import sys


APP_NAME = "AtaraxiaPlayer"
LOG_FILENAME = "ataraxia.log"
MAX_BYTES = 1_048_576          # 1 MB per file
BACKUP_COUNT = 3               # keep last 3 rotations (4 MB total cap)


def _resolve_log_path() -> str:
    """Same location policy as DatabaseManager for consistency."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get(
            "XDG_DATA_HOME",
            os.path.join(os.path.expanduser("~"), ".local", "share")
        )
    full_dir = os.path.join(base, APP_NAME)
    os.makedirs(full_dir, exist_ok=True)
    return os.path.join(full_dir, LOG_FILENAME)


_configured = False


def configure_logging(level: int = logging.INFO) -> str:
    """
    Must be called once at application startup (from main.py).
    Returns the path to the log file so the caller can display it
    in an 'About' / 'Diagnostics' dialog if desired.
    """
    global _configured
    if _configured:
        return _resolve_log_path()

    log_path = _resolve_log_path()

    formatter = logging.Formatter(
        "%(asctime)s  [%(levelname)-7s]  %(name)s:%(lineno)d  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove pre-existing handlers (avoid duplicate records on dev reloads)
    for h in list(root.handlers):
        root.removeHandler(h)

    root.addHandler(file_handler)

    # Also capture uncaught exceptions on the main thread
    def _excepthook(exc_type, exc_value, tb):
        root.critical("Uncaught exception", exc_info=(exc_type, exc_value, tb))
        sys.__excepthook__(exc_type, exc_value, tb)

    sys.excepthook = _excepthook

    _configured = True
    root.info("=" * 60)
    root.info("Ataraxia Player — logging initialized → %s", log_path)
    root.info("=" * 60)
    return log_path


def get_logger(name: str) -> logging.Logger:
    """Shortcut for `logging.getLogger(name)` with a clean prefix."""
    # Strip 'src.' prefix for readability
    if name.startswith("src."):
        name = name[4:]
    return logging.getLogger(name)
