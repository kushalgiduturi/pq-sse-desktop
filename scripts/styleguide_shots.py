"""Screenshot the Quiet glass style guide in dark and light, and stitch each pair side by side.

    python scripts/styleguide_shots.py [--out docs/design/restyle/styleguide] [--size 1600x1000]

Writes dark-NN-name.png, light-NN-name.png and pair-NN-name.png (dark left, light right).
Prints every QML warning and exits with 1 if there was one.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STEPS = [("top", "top"), ("buttons", "buttons"), ("fields", "fields"), ("list", "list"),
         ("empty", "empty"), ("dialog", "dialog"), ("toast", "toast")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "design" / "restyle" / "styleguide")
    parser.add_argument("--size", default="1600x1000")
    parser.add_argument("--reduce-transparency", action="store_true")
    parser.add_argument("--prefix", default="")
    args = parser.parse_args()

    from PySide6.QtCore import Q_ARG, QEventLoop, QMetaObject, QTimer
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from app.spatial.styleguide import StyleGuide

    app = QApplication(sys.argv[:1])
    args.out.mkdir(parents=True, exist_ok=True)
    width, height = (int(v) for v in args.size.lower().split("x"))

    def wait(ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    warnings: list[str] = []
    shots: dict[str, dict[str, QImage]] = {}
    for theme in ("dark", "light"):
        guide = StyleGuide(dark=theme == "dark")
        win = guide.window
        win.setProperty("reduceTransparency", args.reduce_transparency)
        win.resize(width, height)
        win.show()
        wait(900)
        for index, (name, target) in enumerate(STEPS):
            QMetaObject.invokeMethod(win, "closeOverlays")
            if target == "top":
                QMetaObject.invokeMethod(win, "scrollTo", Q_ARG("QVariant", 0))
            elif target == "dialog":
                QMetaObject.invokeMethod(win, "scrollToSection", Q_ARG("QVariant", "overlays"))
                QMetaObject.invokeMethod(win, "openDialog")
            elif target == "toast":
                QMetaObject.invokeMethod(win, "scrollToSection", Q_ARG("QVariant", "overlays"))
                QMetaObject.invokeMethod(win, "showToast")
            else:
                QMetaObject.invokeMethod(win, "scrollToSection", Q_ARG("QVariant", target))
            wait(700)
            image = win.grabWindow()
            key = f"{index + 1:02d}-{name}"
            image.save(str(args.out / f"{args.prefix}{theme}-{key}.png"))
            shots.setdefault(key, {})[theme] = image
        warnings.extend(guide.warnings)
        win.close()
        guide.engine.deleteLater()
        wait(200)

    for key, pair in shots.items():
        dark, light = pair["dark"], pair["light"]
        canvas = QImage(dark.width() + light.width() + 24, max(dark.height(), light.height()), QImage.Format_RGB32)
        canvas.fill(0x808080)
        painter = QPainter(canvas)
        painter.drawImage(0, 0, dark)
        painter.drawImage(dark.width() + 24, 0, light)
        painter.end()
        canvas.save(str(args.out / f"{args.prefix}pair-{key}.png"))

    for line in dict.fromkeys(warnings):
        print("QML:", line)
    print(f"saved {len(shots) * 3} images to {args.out}")
    return 1 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
