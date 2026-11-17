"""The Quiet glass style guide window (python -m app --styleguide).

It needs no data folder and no session: it only shows the tokens and components.
"""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401  (so the root object is a QQuickWindow)

from pqsse import paths

from .copy import STYLEGUIDE

QML = "app/spatial/qml/quiet/StyleGuide.qml"


class StyleGuide:
    def __init__(self, dark: bool = True) -> None:
        self.engine = QQmlApplicationEngine()
        self.warnings: list[str] = []
        self.engine.warnings.connect(lambda items: self.warnings.extend(item.toString() for item in items))
        self.engine.rootContext().setContextProperty("SG", STYLEGUIDE)
        self.engine.load(QUrl.fromLocalFile(str(paths.resource(QML))))
        roots = self.engine.rootObjects()
        if not roots:
            raise RuntimeError("The style guide could not be loaded: " + "; ".join(self.warnings[:5]))
        self.window = roots[0]
        self.window.setProperty("dark", dark)


def run(app, args: list[str]) -> int:
    guide = StyleGuide(dark="--light" not in args)
    for line in guide.warnings:
        print("QML:", line)
    return app.exec()
