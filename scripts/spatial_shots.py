"""Open the spatial window on throwaway data, run real lesson steps, visit every page and
save screenshots to docs/design/screens (for the design critique and for bug hunting).

    python scripts/spatial_shots.py [--steps 8] [--out docs/design/screens] [--prefix m4]

The data folder is a temporary one. Prints every QML warning and exits with 1 if there was one.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "design" / "screens")
    parser.add_argument("--prefix", default="shot")
    parser.add_argument("--light", action="store_true")
    parser.add_argument("--reduce-motion", action="store_true")
    args = parser.parse_args()
    data = tempfile.mkdtemp(prefix="pqsse-shots-")
    os.environ["PQSSE_DATA_DIR"] = data

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from app.session import Session
    from app.spatial.window import SpatialWindow

    app = QApplication(sys.argv[:1])
    session = Session()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        session.settings["port"] = sock.getsockname()[1]
    session.settings.update(theme="light" if args.light else "dark", reduce_motion=args.reduce_motion, mode="beginner")
    view = SpatialWindow(session, sync=True)
    window, bridge = view.window, view.bridge
    args.out.mkdir(parents=True, exist_ok=True)
    plan: list = []

    def shot(name: str) -> None:
        window.grabWindow().save(str(args.out / f"{args.prefix}-{name}.png"))

    def page(key: str) -> None:
        window.setProperty("page", key)

    for index in range(1, args.steps + 1):
        plan.append(lambda i=index: bridge.runLessonStep(i))
    plan += [lambda: page("journey"), lambda: shot("journey"),
             lambda: page("stage"), lambda: shot("stage"),
             lambda: window.setProperty("inspectIndex", next((r["index"] for r in bridge.events.records if r["kind"] == "build_index"), 0)),
             lambda: window.setProperty("inspectorOpen", True), None, None, None, lambda: shot("inspector-encrypt"),
             lambda: window.setProperty("inspectIndex", next((r["index"] for r in bridge.events.records if r["kind"] == "search"), 0)),
             None, None, None, lambda: shot("inspector-search"),
             lambda: window.setProperty("inspectorOpen", False),
             lambda: page("workspace"), lambda: bridge.setRole("alice"), None, lambda: shot("workspace-alice"),
             lambda: bridge.setRole("bob"), None, lambda: shot("workspace-bob"),
             lambda: bridge.setRole("cloud"), None, lambda: shot("workspace-cloud"),
             lambda: page("lab"), lambda: shot("lab"), lambda: page("insights"), lambda: shot("insights")]

    def step() -> None:
        if not plan:
            warnings = list(view.warnings)
            errors = bridge.last_error
            view.close()
            shutil.rmtree(data, ignore_errors=True)
            for line in warnings[:40]:
                print("QML:", line)
            print(f"{len(warnings)} QML warning(s); last bridge error: {errors}")
            app.exit(1 if warnings else 0)
            return
        action = plan.pop(0)
        if action is not None:
            action()
        QTimer.singleShot(650, step)

    QTimer.singleShot(1200, step)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
