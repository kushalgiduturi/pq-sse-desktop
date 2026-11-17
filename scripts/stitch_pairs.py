"""Stitch before and after screenshots side by side (before left, after right).

    python scripts/stitch_pairs.py docs/design/restyle/before docs/design/restyle/after docs/design/restyle/compare
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QImage, QPainter


def main() -> int:
    before, after, out = (Path(p) for p in sys.argv[1:4])
    out.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication([])  # noqa: F841  (QPainter needs it)
    count = 0
    for left in sorted(before.glob("*.png")):
        right = after / left.name
        if not right.exists():
            continue
        a, b = QImage(str(left)), QImage(str(right))
        canvas = QImage(a.width() + b.width() + 24, max(a.height(), b.height()), QImage.Format_RGB32)
        canvas.fill(0x808080)
        painter = QPainter(canvas)
        painter.drawImage(0, 0, a)
        painter.drawImage(a.width() + 24, 0, b)
        painter.end()
        canvas.save(str(out / left.name))
        count += 1
    print(f"{count} pairs saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
