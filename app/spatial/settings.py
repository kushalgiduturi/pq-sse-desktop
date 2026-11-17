"""Appearance settings of the spatial UI and what Windows says about animations and theme."""
from __future__ import annotations

import ctypes
import sys

THEMES = ("system", "dark", "light")
TEXT_SCALES = {"small": 0.9, "normal": 1.0, "large": 1.25, "larger": 1.5, "largest": 2.0}
DEFAULTS = {"theme": "system", "detail_level": 1}
_SPI_GETCLIENTAREAANIMATION = 0x1042


def windows_animations_enabled() -> bool:
    """The Windows setting "Show animations in Windows". True on other systems or on error."""
    if sys.platform != "win32":
        return True
    try:
        value = ctypes.c_int(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(_SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(value), 0)
        return bool(value.value) if ok else True
    except (AttributeError, OSError):
        return True


def windows_prefers_dark() -> bool:
    """The Windows app theme (Settings, Personalization, Colors). False on other systems or on error."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return int(winreg.QueryValueEx(key, "AppsUseLightTheme")[0]) == 0
    except OSError:
        return False
