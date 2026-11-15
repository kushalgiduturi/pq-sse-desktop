"""Rotating log file: %LOCALAPPDATA%\\PQ-SSE-Desktop\\logs\\app.log

What is logged: start and stop, version, engine, the cloud child's start and stop, and
errors with their technical text. Never passphrases, keys, search words or document text.
"""
from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import paths

LOGGER_NAME = "pqsse"
MAX_BYTES = 1_000_000
BACKUPS = 3

log = logging.getLogger(LOGGER_NAME)
log.addHandler(logging.NullHandler())


def log_file() -> Path:
    return paths.logs_dir() / "app.log"


def setup(hook_exceptions: bool = True) -> Path:
    """Attach the rotating file handler (once) and return the log file path."""
    path = log_file()
    for handler in list(log.handlers):
        if isinstance(handler, RotatingFileHandler):
            if Path(handler.baseFilename) == path:
                return path
            log.removeHandler(handler)
            handler.close()
    try:
        handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
    except OSError:
        return path                      # a log file must never stop the program from starting
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    if hook_exceptions:
        sys.excepthook = _excepthook
        threading.excepthook = lambda args: _excepthook(args.exc_type, args.exc_value, args.exc_traceback)
    return path


def shutdown() -> None:
    """Close the log file (used by tests and at exit)."""
    for handler in list(log.handlers):
        if isinstance(handler, RotatingFileHandler):
            log.removeHandler(handler)
            handler.close()


def _excepthook(exc_type, exc, tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        return
    log.error("Unhandled error", exc_info=(exc_type, exc, tb))
