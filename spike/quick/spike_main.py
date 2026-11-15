"""Milestone 0 spike: Qt Quick window driven by a real encryption event.

    python spike/quick/spike_main.py                         open the window (Space = encrypt again, 1 / 2 = pages)
    python spike/quick/spike_main.py --measure 8 --report r.txt [--grab shot.png]
    set QT_QUICK_BACKEND=software                            run without the GPU

--measure runs the encryption replay and the page transition in a loop for N seconds,
records the time between frames, writes a report and exits. The encryption is real
(AES-256-GCM from the cryptography package); the animation is a slow replay of it.
The key never leaves this file and is never sent to QML.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface  # noqa: F401  (needed so the root object is a QQuickWindow)

HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
PLAIN = "Invoice 1042, MRI scanner"


class Spike(QObject):
    encrypted = Signal(str, str, str)
    goto = Signal(int)
    tagsChanged = Signal()

    def __init__(self, reduce_motion: bool) -> None:
        super().__init__()
        self._reduce = reduce_motion
        self._tags: list[str] = []

    @Property(bool, constant=True)
    def reduceMotion(self) -> bool:
        return self._reduce

    @Property(list, notify=tagsChanged)
    def tags(self) -> list[str]:
        return self._tags

    @Slot()
    def encrypt(self) -> None:
        key = AESGCM.generate_key(256)
        nonce = os.urandom(12)
        start = time.perf_counter()
        sealed = AESGCM(key).encrypt(nonce, PLAIN.encode(), b"spike")
        micros = (time.perf_counter() - start) * 1e6
        del key
        self._tags = ["AES-256-GCM", f"nonce {len(nonce)} bytes", "tag 16 bytes",
                      f"{len(PLAIN)} bytes in, {len(sealed)} bytes out"]
        self.tagsChanged.emit()
        caption = (f"The real encryption took {micros:.0f} microseconds. This is a replay at slow speed. "
                   "The padlock is a picture for AES-256-GCM; the stored result is the scrambled bytes.")
        self.encrypted.emit(PLAIN, sealed.hex(), caption)


def frame_report(stamps: list[float], label: str) -> str:
    gaps = [(b - a) * 1000 for a, b in zip(stamps, stamps[1:])]
    if len(gaps) < 10:
        return f"{label}: too few frames ({len(gaps)})\n"
    gaps.sort()
    total = sum(gaps) / 1000
    p95 = gaps[int(len(gaps) * 0.95)]
    p99 = gaps[int(len(gaps) * 0.99)]
    slow = sum(1 for g in gaps if g > 20.0)
    return (f"{label}\n"
            f"  frames: {len(gaps)} in {total:.1f} s = {len(gaps) / total:.1f} fps\n"
            f"  frame time ms: mean {statistics.mean(gaps):.2f}, median {statistics.median(gaps):.2f}, "
            f"p95 {p95:.2f}, p99 {p99:.2f}, max {gaps[-1]:.2f}\n"
            f"  frames slower than 20 ms: {slow} ({100 * slow / len(gaps):.1f} %)\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measure", type=float, default=0.0)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--grab", type=Path, default=None)
    parser.add_argument("--reduce-motion", action="store_true")
    args = parser.parse_args(argv)

    app = QGuiApplication(sys.argv[:1])
    spike = Spike(args.reduce_motion)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("spike", spike)
    engine.load(QUrl.fromLocalFile(str(HERE / "Spike.qml")))
    if not engine.rootObjects():
        text = "FAIL: the QML file did not load\n"
        if args.report:
            args.report.write_text(text, encoding="utf-8")
        return 1
    window = engine.rootObjects()[0]
    started = time.perf_counter()

    if args.measure > 0:
        stamps: list[float] = []
        window.frameSwapped.connect(lambda: stamps.append(time.perf_counter()))
        first_frame: list[float] = []
        window.frameSwapped.connect(lambda: first_frame or first_frame.append(time.perf_counter() - started))
        step = {"n": 0}

        def tick() -> None:
            step["n"] += 1
            if step["n"] % 2:
                spike.goto.emit(1 if (step["n"] // 2) % 2 == 0 else 0)
            else:
                spike.encrypt()

        ticker = QTimer()
        ticker.timeout.connect(tick)
        ticker.start(1400)

        def finish() -> None:
            ticker.stop()
            backend = os.environ.get("QT_QUICK_BACKEND") or "default (GPU scene graph)"
            api = window.rendererInterface().graphicsApi()
            text = (f"Qt Quick spike, packaged: {'yes' if getattr(sys, 'frozen', False) else 'no'}\n"
                    f"backend: {backend}, graphics API: {api.name}, window {window.width()} x {window.height()}, "
                    f"screen refresh {app.primaryScreen().refreshRate():.0f} Hz\n"
                    f"time to first frame: {first_frame[0] * 1000:.0f} ms\n"
                    + frame_report(stamps[5:], "encryption replay + page transitions, every frame after warm-up"))
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(text, encoding="utf-8")
            if sys.stdout is not None:
                print(text)
            if not args.grab:
                app.quit()
                return
            spike.goto.emit(0)
            spike.encrypt()
            QTimer.singleShot(3300, lambda: (window.grabWindow().save(str(args.grab)), app.quit()))

        def finish_safely() -> None:
            try:
                finish()
            except Exception as exc:           # a measuring run must always end
                if args.report:
                    args.report.write_text(f"FAIL: {type(exc).__name__}: {exc}\n", encoding="utf-8")
                print(f"FAIL: {type(exc).__name__}: {exc}")
                app.exit(1)

        QTimer.singleShot(int(args.measure * 1000), finish_safely)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
