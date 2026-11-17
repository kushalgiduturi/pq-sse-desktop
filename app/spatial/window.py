"""Create and run the spatial (Qt Quick) window."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QInputDevice
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401  (needed so the root object is a QQuickWindow)

from pqsse import paths

from ..session import Session
from .bridge import AppBridge
from .copy import DESTINATIONS, T

QML_DIR = "app/spatial/qml"


def qml_path(name: str = "Main.qml") -> Path:
    return paths.resource(QML_DIR) / name


def platform_info() -> dict:
    """What the system asks for: Windows' transparency effects switch, and a touch screen."""
    reduce_transparency = False
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                reduce_transparency = winreg.QueryValueEx(key, "EnableTransparency")[0] == 0
        except OSError:
            pass
    touch = any(d.type() == QInputDevice.DeviceType.TouchScreen for d in QInputDevice.devices())
    # for screenshots and tests of the fallbacks on a machine that has neither
    reduce_transparency = reduce_transparency or os.environ.get("PQSSE_REDUCE_TRANSPARENCY") == "1"
    touch = touch or os.environ.get("PQSSE_TOUCH") == "1"
    return {"reduceTransparency": reduce_transparency, "touch": touch}


def set_dark_title_bar(hwnd: int, dark: bool) -> None:
    """Ask DWM for the dark or light native title bar (DWMWA_USE_IMMERSIVE_DARK_MODE)."""
    if sys.platform != "win32" or not hwnd:
        return
    try:
        import ctypes

        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):          # 19 on Windows 10 builds before 20H1
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), attribute, ctypes.byref(value), 4) == 0:
                break
    except (AttributeError, OSError):
        pass


class SpatialWindow:
    """The QML engine, the bridge and the root window, kept together."""

    def __init__(self, session: Session | None = None, sync: bool = False) -> None:
        self.bridge = AppBridge(session, sync=sync)
        self.engine = QQmlApplicationEngine()
        self.warnings: list[str] = []
        self.engine.warnings.connect(lambda items: self.warnings.extend(item.toString() for item in items))
        context = self.engine.rootContext()
        context.setContextProperty("app", self.bridge)
        context.setContextProperty("events", self.bridge.events)
        context.setContextProperty("T", T)
        context.setContextProperty("DEST", DESTINATIONS)
        context.setContextProperty("platform", platform_info())
        self.engine.load(QUrl.fromLocalFile(str(qml_path())))
        roots = self.engine.rootObjects()
        if not roots:
            raise RuntimeError("The spatial window could not be loaded: " + "; ".join(self.warnings[:5]))
        self.window = roots[0]
        # The native title bar follows the theme (Windows 10 2004 and later; ignored elsewhere).
        self.bridge.settingsChanged.connect(self._theme_title_bar)
        self.window.visibleChanged.connect(self._theme_title_bar)
        self._theme_title_bar()

    def _theme_title_bar(self, *_args) -> None:
        set_dark_title_bar(int(self.window.winId()), bool(self.bridge.dark))

    def close(self) -> None:
        self.window.close()
        self.bridge.shutdown()
        self.engine.deleteLater()
