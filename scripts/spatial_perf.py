"""Performance check of the spatial UI: frame times on the Stage while the Step Inspector
replays a real encryption (BuildIndex) in a loop.

    python scripts/spatial_perf.py [--seconds 8] [--report file]
    set QT_QUICK_BACKEND=software     to measure without the GPU renderer

Thresholds (fail = exit code 1). They were set on the development PC (RTX 4060 Laptop
GPU, 60 Hz screen) with room to spare, see SPATIAL_PLAN.md:
    GPU renderer:       at least 50 frames per second, 95 % of frames within 25 ms
    software renderer:  95 % of frames drawn within 50 ms each. There the app reduces
                        motion by itself and draws only when something changes, so the
                        time between frames is idle time; the drawing time per frame is
                        what shows whether the window stays responsive.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LIMITS = {"gpu": (50.0, 25.0), "software": (30.0, 50.0)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()
    data = tempfile.mkdtemp(prefix="pqsse-perf-")
    os.environ["PQSSE_DATA_DIR"] = data

    from PySide6.QtCore import QObject, QTimer
    from PySide6.QtWidgets import QApplication

    from app.session import Session
    from app.spatial.window import SpatialWindow

    app = QApplication(sys.argv[:1])
    session = Session()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        session.settings["port"] = sock.getsockname()[1]
    session.settings.update(theme="dark", reduce_motion=False, show_welcome=False)
    started = time.perf_counter()
    view = SpatialWindow(session, sync=True)
    window, bridge = view.window, view.bridge
    startup_ms = (time.perf_counter() - started) * 1000
    stamps: list[float] = []
    draw_start: list[float] = []
    draws: list[float] = []
    result = {"code": 1}

    def begin() -> None:
        for index in range(1, 6):                      # cloud, keys, groups, join, build and publish: all real
            bridge.runLessonStep(index)
        window.setProperty("page", "stage")
        target = next(r["index"] for r in bridge.events.records if r["kind"] == "build_index")
        window.setProperty("inspectIndex", target)
        window.setProperty("inspectorOpen", True)
        QTimer.singleShot(1500, measure)

    def inspector():
        return next(o for o in window.findChildren(QObject) if o.metaObject().className().startswith("Inspector"))

    def measure() -> None:
        panel = inspector()
        replay = QTimer(window)
        replay.timeout.connect(lambda: panel.metaObject().invokeMethod(panel, "replay"))
        replay.start(3000)
        panel.metaObject().invokeMethod(panel, "replay")
        window.frameSwapped.connect(lambda: stamps.append(time.perf_counter()))
        if window.property("software"):           # same thread as the GUI: safe to time each frame
            window.beforeRendering.connect(lambda: draw_start.append(time.perf_counter()))
            window.afterRendering.connect(lambda: draws.append((time.perf_counter() - draw_start[-1]) * 1000) if draw_start else None)
        QTimer.singleShot(int(args.seconds * 1000), finish)

    def finish() -> None:
        software = bool(window.property("software"))
        gaps = sorted((b - a) * 1000 for a, b in zip(stamps, stamps[1:]))
        fps_limit, p95_limit = LIMITS["software" if software else "gpu"]
        if software and len(draws) >= 10:
            draws.sort()
            p95 = draws[int(len(draws) * 0.95)]
            ok = p95 <= p95_limit
            result["code"] = 0 if ok else 1
            text = (f"Spatial UI performance, Stage with the Step Inspector replaying BuildIndex\n"
                    f"renderer: software (motion reduced automatically, frames drawn on demand), window {window.width()} x {window.height()}, "
                    f"QML warnings: {len(view.warnings)}\n"
                    f"window created in {startup_ms:.0f} ms\n"
                    f"frames drawn: {len(draws)} in {args.seconds:.0f} s\n"
                    f"drawing time per frame ms: mean {statistics.mean(draws):.2f}, median {statistics.median(draws):.2f}, "
                    f"p95 {p95:.2f} (limit: at most {p95_limit:.0f}), max {draws[-1]:.2f}\n"
                    f"RESULT: {'PASS' if ok else 'FAIL'}\n")
        elif len(gaps) < 20:
            text = f"FAIL: only {len(gaps)} frames were drawn\n"
        else:
            total = sum(gaps) / 1000
            fps = len(gaps) / total
            p95 = gaps[int(len(gaps) * 0.95)]
            ok = fps >= fps_limit and p95 <= p95_limit
            result["code"] = 0 if ok else 1
            text = (f"Spatial UI performance, Stage with the Step Inspector replaying BuildIndex\n"
                    f"renderer: {'software' if software else 'GPU scene graph'}, window {window.width()} x {window.height()}, "
                    f"screen {app.primaryScreen().refreshRate():.0f} Hz, QML warnings: {len(view.warnings)}\n"
                    f"window created in {startup_ms:.0f} ms\n"
                    f"frames: {len(gaps)} in {total:.1f} s = {fps:.1f} fps (limit: at least {fps_limit:.0f})\n"
                    f"frame time ms: mean {statistics.mean(gaps):.2f}, median {statistics.median(gaps):.2f}, "
                    f"p95 {p95:.2f} (limit: at most {p95_limit:.0f}), max {gaps[-1]:.2f}\n"
                    f"RESULT: {'PASS' if ok else 'FAIL'}\n")
        print(text)
        if args.report:
            args.report.write_text(text, encoding="utf-8")
        view.close()
        shutil.rmtree(data, ignore_errors=True)
        app.exit(result["code"])

    QTimer.singleShot(800, begin)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
