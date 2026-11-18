"""Make key files readable by this account only, and check that they are.

Windows: ``icacls`` removes inherited entries and grants full control to the current user alone (a user
can do this to files and folders they own; no administrator rights are needed). Elsewhere: mode 0600 for
files and 0700 for folders. Administrators and the operating system can still read any file: this
limits other ordinary accounts on the same computer, nothing more.
"""
from __future__ import annotations

import getpass
import os
import stat
import subprocess
import sys
from pathlib import Path

# principals that may appear on a private file besides the user (Windows): the system and administrators
_ALLOWED_OTHERS = ("NT AUTHORITY\\SYSTEM", "BUILTIN\\Administrators")


def _windows_user() -> str:
    domain = os.environ.get("USERDOMAIN", "")
    user = getpass.getuser()
    return f"{domain}\\{user}" if domain else user


def _icacls(*args: str) -> subprocess.CompletedProcess:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(["icacls", *args], capture_output=True, text=True, timeout=30, creationflags=flags)


def restrict(path: str | Path) -> bool:
    """Limit a file or folder to the current account. Returns False when it could not be done (and leaves it)."""
    path = Path(path)
    if not path.exists():
        return False
    if sys.platform == "win32":
        grant = f"{_windows_user()}:(OI)(CI)F" if path.is_dir() else f"{_windows_user()}:F"
        result = _icacls(str(path), "/inheritance:r", "/grant:r", grant)
        return result.returncode == 0
    try:
        path.chmod(0o700 if path.is_dir() else 0o600)
        return True
    except OSError:
        return False


def is_private(path: str | Path) -> tuple[bool, str]:
    """(True, "") when only this account (and the system) can read the path; otherwise (False, who else can)."""
    path = Path(path)
    if sys.platform == "win32":
        result = _icacls(str(path))
        if result.returncode != 0:
            return False, "could not read the permissions"
        me = _windows_user().lower()
        others = []
        for line in result.stdout.splitlines():
            text = line.replace(str(path), "", 1).strip()
            if ":" not in text or text.startswith("Successfully"):
                continue
            who = text.split(":", 1)[0].strip()
            if who.lower() != me and who not in _ALLOWED_OTHERS:
                others.append(who)
        return (not others), ", ".join(others)
    mode = path.stat().st_mode
    open_bits = mode & (stat.S_IRWXG | stat.S_IRWXO)
    return open_bits == 0, "" if open_bits == 0 else f"mode {oct(mode & 0o777)}"
