"""Draw the app icon (a padlock with a magnifier) and write assets/pqsse.ico.

    python scripts/make_icon.py [output.ico]

The picture is drawn with Qt from the numbers below, so the icon can be rebuilt at any
time. The .ico holds 16, 24, 32, 48, 64, 128 and 256 pixel images (256 as PNG, the
others as 32 bit bitmaps, which every Windows version reads).
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)
BACKGROUND = "#1f4e79"
LOCK = "#ffffff"
KEYHOLE = "#1f4e79"
LENS_RING = "#f2b01e"
LENS_GLASS = "#cfe6fb"


def draw(size: int) -> QImage:
    """Draw the icon on a 100 x 100 grid scaled to ``size`` pixels."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(size / 100.0, size / 100.0)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(BACKGROUND))
    painter.drawRoundedRect(QRectF(2, 2, 96, 96), 20, 20)

    shackle = QPen(QColor(LOCK), 9)
    shackle.setCapStyle(Qt.PenCapStyle.FlatCap)
    painter.setPen(shackle)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(27, 46)
    path.lineTo(27, 34)
    path.arcTo(QRectF(27, 16, 30, 34), 180, -180)
    path.lineTo(57, 46)
    painter.drawPath(path)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(LOCK))
    painter.drawRoundedRect(QRectF(16, 44, 52, 40), 7, 7)
    painter.setBrush(QColor(KEYHOLE))
    painter.drawEllipse(QPointF(42, 60), 5.5, 5.5)
    painter.drawRoundedRect(QRectF(39.5, 60, 5, 13), 2, 2)

    handle = QPen(QColor(LENS_RING), 9)
    handle.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(handle)
    painter.drawLine(QPointF(77, 81), QPointF(89, 93))
    painter.setPen(QPen(QColor(LENS_RING), 6))
    painter.setBrush(QColor(LENS_GLASS))
    painter.drawEllipse(QPointF(66, 70), 15, 15)
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def bmp_bytes(image: QImage) -> bytes:
    """32 bit bitmap as stored inside an .ico: header, pixel rows bottom-up, empty mask."""
    size = image.width()
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    stride = image.bytesPerLine()
    raw = bytes(image.constBits())
    rows = [raw[y * stride:y * stride + size * 4] for y in range(size)]
    pixels = b"".join(reversed(rows))
    mask = bytes(((size + 31) // 32) * 4) * size
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(pixels) + len(mask), 0, 0, 0, 0)
    return header + pixels + mask


def build_ico() -> bytes:
    images = [(size, png_bytes(draw(size)) if size >= 256 else bmp_bytes(draw(size))) for size in SIZES]
    offset = 6 + 16 * len(images)
    directory = struct.pack("<HHH", 0, 1, len(images))
    body = b""
    for size, data in images:
        directory += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset + len(body))
        body += data
    return directory + body


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "assets" / "pqsse.ico"
    app = QGuiApplication.instance() or QGuiApplication([])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_ico())
    draw(256).save(str(out.with_suffix(".png")), "PNG")
    print(f"Wrote {out} ({out.stat().st_size} bytes, sizes {', '.join(str(s) for s in SIZES)}) and {out.with_suffix('.png').name}")
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
