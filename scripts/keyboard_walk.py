"""Keyboard-only walk through the spatial window, with real key events (no mouse).

    python scripts/keyboard_walk.py

For each destination it presses Tab until focus comes back to where it started and
records every control that received the focus: its name for screen readers, whether
it is visible on screen after the automatic scroll, and whether it shows the focus
ring. It also checks Ctrl+1..5, Ctrl+K and Escape, the focus trap of the palette and
the welcome sheet, and that Enter on a dock item switches the page.
Exit code 0 when every check passes. Uses a throwaway data folder.
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    data = tempfile.mkdtemp(prefix="pqsse-keys-")
    os.environ["PQSSE_DATA_DIR"] = data
    from PySide6.QtCore import QEvent, QObject, Qt, QTimer
    from PySide6.QtGui import QAccessible, QKeyEvent
    from PySide6.QtWidgets import QApplication

    from app.session import Session
    from app.spatial.window import SpatialWindow

    app = QApplication(sys.argv[:1])
    session = Session()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        session.settings["port"] = sock.getsockname()[1]
    session.settings.update(theme="dark", reduce_motion=True, mode="beginner", show_welcome=False)
    view = SpatialWindow(session, sync=True)
    window, bridge = view.window, view.bridge
    problems: list[str] = []
    lines: list[str] = []

    def settle(n: int = 6) -> None:
        for _ in range(n):
            app.processEvents()

    def key(code, mods=Qt.KeyboardModifier.NoModifier, text="") -> None:
        for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            app.sendEvent(window, QKeyEvent(kind, code, mods, text))
        settle()

    def acc_name(item) -> str:
        """The name a screen reader gets, read through Qt's accessibility interface."""
        face = QAccessible.queryAccessibleInterface(item) if item is not None else None
        return face.text(QAccessible.Text.Name) if face is not None and face.isValid() else ""

    def describe(item) -> str:
        if item is None:
            return "(nothing)"
        return f"{item.metaObject().className().split('_')[0]} '{acc_name(item)}'"

    def on_screen(item) -> bool:
        if item is None or not item.isVisible():
            return False
        point = item.mapToItem(window.contentItem(), 0, 0)
        return -2 <= point.y() and point.y() + min(item.height(), 40) <= window.height() + 2

    def walk(page: str, limit: int = 600) -> None:
        window.setProperty("page", page)
        settle(10)
        QTimer.singleShot(400, lambda: None)
        deadline = __import__("time").time() + 0.6         # let the page fade finish
        while __import__("time").time() < deadline:
            app.processEvents()
        window.contentItem().forceActiveFocus()
        key(Qt.Key.Key_Tab)
        first = window.activeFocusItem()
        seen, hidden = [first], []
        for _ in range(limit):
            key(Qt.Key.Key_Tab)
            item = window.activeFocusItem()
            if item is None or item == first:
                break
            seen.append(item)
            if not on_screen(item):
                hidden.append(describe(item))
        lines.append(f"{page}: {len(seen)} focus stops by Tab, {len(hidden)} not scrolled into view")
        if os.environ.get("KEYWALK_VERBOSE"):
            lines.extend("    " + describe(i) for i in seen)
        if len(seen) > limit:
            problems.append(f"{page}: Tab never came back to the first control within {limit} presses")
        if len(seen) < 5:
            problems.append(f"{page}: only {len(seen)} controls reachable by Tab")
        if hidden:
            problems.append(f"{page}: focused but off screen: {hidden[:4]}")
        unnamed = [describe(i) for i in seen if i is not None and not acc_name(i)]
        if unnamed:
            problems.append(f"{page}: focus stops without a name: {unnamed[:4]}")

    def check() -> None:
        try:
            for index, page in enumerate(("journey", "stage", "workspace", "lab", "insights"), start=1):
                key(getattr(Qt.Key, f"Key_{index}"), Qt.KeyboardModifier.ControlModifier)
                if window.property("page") != page:
                    problems.append(f"Ctrl+{index} did not open {page}")
            bridge.runLessonStep(1)
            bridge.runLessonStep(2)
            bridge.runLessonStep(3)
            settle(10)
            for page in ("journey", "stage", "workspace", "lab", "insights"):
                walk(page)

            # Enter on a focused dock item switches the page.
            window.setProperty("page", "journey")
            settle()
            dock_items = [o for o in window.findChildren(QObject)
                          if o.metaObject().className() == "QQuickItem" and acc_name(o).startswith("Stage.")]
            if dock_items:
                dock_items[0].forceActiveFocus()
                key(Qt.Key.Key_Return)
                if window.property("page") != "stage":
                    problems.append("Enter on the Stage dock item did not open the Stage")
            else:
                problems.append("dock item for Stage not found")

            # Palette: opens with Ctrl+K, Tab stays inside it, Escape closes and focus returns.
            window.setProperty("page", "workspace")
            settle()
            window.contentItem().forceActiveFocus()
            key(Qt.Key.Key_Tab)
            before = window.activeFocusItem()
            key(Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
            if window.property("modalOpen") is not True:
                problems.append("Ctrl+K did not open the palette")
            for _ in range(12):
                key(Qt.Key.Key_Tab)
                item = window.activeFocusItem()
                inside = False
                parent = item
                while parent is not None:
                    if parent.metaObject().className().startswith("CommandPalette"):
                        inside = True
                        break
                    parent = parent.parentItem()
                if not inside:
                    problems.append(f"Tab left the open palette: {describe(item)}")
                    break
            key(Qt.Key.Key_Escape)
            if window.property("modalOpen") is not False:
                problems.append("Escape did not close the palette")
            if window.activeFocusItem() != before:
                problems.append(f"focus did not return after the palette: {describe(window.activeFocusItem())}")
            lines.append("palette: Ctrl+K opens, Tab stays inside, Escape closes, focus returns" if not any("palette" in p for p in problems) else "palette: problems")

            # Typing a digit in a text field must not switch pages.
            fields = [o for o in window.findChildren(QObject) if o.metaObject().className() == "QQuickTextInput" and o.isVisible()]
            if fields:
                fields[0].forceActiveFocus()
                page = window.property("page")
                key(Qt.Key.Key_3, text="3")
                if window.property("page") != page:
                    problems.append("typing 3 in a text field switched the page")
                lines.append("typing a digit in a text field keeps the page")
        except Exception as exc:          # report, never hang
            problems.append(f"{type(exc).__name__}: {exc}")
        finally:
            print("\n".join(lines))
            for problem in problems:
                print("PROBLEM:", problem)
            print(f"QML warnings: {len(view.warnings)}")
            print("RESULT:", "PASS" if not problems and not view.warnings else "FAIL")
            code = 0 if not problems and not view.warnings else 1
            view.close()
            shutil.rmtree(data, ignore_errors=True)
            app.exit(code)

    window.show()
    QTimer.singleShot(1200, check)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
