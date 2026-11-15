"""Data folder layout: everything lives under %LOCALAPPDATA%\\PQ-SSE-Desktop."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "PQ-SSE-Desktop"


def frozen() -> bool:
    """True inside the packaged executable."""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Folder that holds the read-only files shipped with the program.

    Packaged app: the folder PyInstaller unpacked or installed its data to (sys._MEIPASS).
    Source tree: the project folder. Never write here: it may be read-only.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    return Path(bundled) if bundled else Path(__file__).resolve().parent.parent


def resource(relative: str) -> Path:
    """Path of a shipped read-only file, for example resource("assets/pqsse.ico")."""
    return resource_root() / relative


def install_dir() -> Path:
    """Folder of the executable (packaged app) or the project folder (source tree)."""
    return Path(sys.executable).resolve().parent if frozen() else resource_root()


_profile = ""


def set_profile(name: str) -> None:
    """Select a sub-folder of the data folder (used by the Learn Mode lesson sandbox)."""
    global _profile
    _profile = name


def base_dir() -> Path:
    """Return (and create) the base data folder. ``PQSSE_DATA_DIR`` overrides it for tests."""
    override = os.environ.get("PQSSE_DATA_DIR")
    if override:
        base = Path(override)
    else:
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        base = Path(local) / APP_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def data_dir() -> Path:
    """Folder of the active profile: the base folder, or its lesson sub-folder."""
    path = base_dir() / _profile if _profile else base_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def owner_db() -> Path:
    return data_dir() / "owner.sqlite"


def cloud_db() -> Path:
    return data_dir() / "cloud.sqlite"


def receiver_db(name: str) -> Path:
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_") or "receiver"
    return data_dir() / f"receiver_{safe}.sqlite"


def settings_file() -> Path:
    return base_dir() / "settings.json"


def logs_dir() -> Path:
    path = base_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pub_dir() -> Path:
    path = data_dir() / "pubkeys"
    path.mkdir(parents=True, exist_ok=True)
    return path
