"""Create and run the spatial (Qt Quick) window."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401  (needed so the root object is a QQuickWindow)

from pqsse import paths

from ..session import Session
from .bridge import AppBridge
from .copy import DESTINATIONS, T

QML_DIR = "app/spatial/qml"


def qml_path(name: str = "Main.qml") -> Path:
    return paths.resource(QML_DIR) / name


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
        self.engine.load(QUrl.fromLocalFile(str(qml_path())))
        roots = self.engine.rootObjects()
        if not roots:
            raise RuntimeError("The spatial window could not be loaded: " + "; ".join(self.warnings[:5]))
        self.window = roots[0]

    def close(self) -> None:
        self.window.close()
        self.bridge.shutdown()
        self.engine.deleteLater()
