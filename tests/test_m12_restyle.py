"""Quiet glass restyle: craft floor, contrast, blur budget at runtime, fonts, style guide, smoke."""
from __future__ import annotations

import shutil
import socket
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtQuick import QQuickItem
from PySide6.QtWidgets import QApplication

from app.session import Session
from app.spatial.window import SpatialWindow

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_contrast  # noqa: E402
import craft_check  # noqa: E402

PAGES = ("journey", "stage", "workspace", "lab", "insights")


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def new_session(theme: str = "dark") -> Session:
    session = Session()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        session.settings["port"] = sock.getsockname()[1]
    session.settings.update(theme=theme, show_welcome=False)
    return session


def test_craft_floor_is_clean():
    assert craft_check.check() == []


def test_craft_check_catches_violations(tmp_path, monkeypatch):
    qml = tmp_path / "qml"
    qml.mkdir()
    for name in ("Theme.qml", "Main.qml"):
        shutil.copy(craft_check.QML / name, qml / name)
    (qml / "Bad.qml").write_text(
        'import QtQuick\nItem {\n'
        '    Rectangle { color: "#ff0000" }\n'
        '    Text { text: "x"; font.capitalization: Font.AllUppercase }\n'
        '    Rectangle { width: 3; height: parent.height; color: Theme.accent }\n'
        '    StoryBar { Surface { depth: 3 } }\n'
        '}\n', encoding="utf-8")
    monkeypatch.setattr(craft_check, "QML", qml)
    found = "\n".join(craft_check.check())
    for expected in ("color literal", "eyebrow", "accent or status bar", "nested"):
        assert expected in found, expected


def test_contrast_on_composites_both_themes():
    lines, failures = check_contrast.check()
    assert len(lines) > 500 and failures == []
    assert any(line.startswith("dark") for line in lines) and any(line.startswith("light") for line in lines)


def test_fonts_bundled_with_licenses():
    fonts = ROOT / "app" / "spatial" / "fonts"
    for name in ("Onest-Variable.ttf", "ShareTechMono-Regular.ttf", "OFL-Onest.txt", "OFL-ShareTechMono.txt"):
        assert (fonts / name).is_file() and (fonts / name).stat().st_size > 1000, name
    spec = (ROOT / "build_windows.ps1").read_text(encoding="utf-8")
    assert "app\\spatial\\fonts" in spec and "app/spatial/fonts" in spec, "the fonts folder must be bundled"


def blur_layers(window, actual: bool) -> list[str]:
    """Visible Surfaces (the top bar, dock and inspector are Surfaces too) that blur, or would
    blur on the GPU renderer (blur on, depth 2 to 4). On the software or offscreen renderer
    nothing is actually blurred, so the budget is checked on the surfaces that ask for blur."""
    out = []
    for item in window.findChildren(QQuickItem):
        depth = item.property("depth")
        if depth is None or item.property("blurred") is None or not item.isVisible() or item.opacity() <= 0.01:
            continue
        wants = item.property("blur") is True and int(depth) >= 2
        if (item.property("blurred") is True) if actual else wants:
            out.append(item.metaObject().className())
    return out


def test_at_most_three_blurred_layers_at_runtime(qapp):
    view = SpatialWindow(new_session(), sync=True)
    try:
        view.window.resize(1440, 900)
        view.window.show()
        wait(600)
        closed = blur_layers(view.window, actual=False)
        view.window.setProperty("inspectorOpen", True)
        wait(700)
        opened = blur_layers(view.window, actual=False)
        assert len(closed) == 3, closed               # panel, top bar, dock
        assert len(opened) == 3, opened               # panel, top bar, inspector (the dock gives up its blur)
        if view.window.property("software"):
            assert blur_layers(view.window, actual=True) == []
        else:
            assert len(blur_layers(view.window, actual=True)) == 3
    finally:
        view.close()
        wait(100)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_all_destinations_load_in_both_themes(qapp, theme):
    view = SpatialWindow(new_session(theme), sync=True)
    try:
        view.window.resize(1280, 800)
        view.window.show()
        wait(400)
        assert view.bridge.dark is (theme == "dark")
        for page in PAGES:
            view.window.setProperty("page", page)
            wait(350)
            assert view.window.property("page") == page
        view.window.setProperty("inspectorOpen", True)
        wait(400)
        assert view.warnings == []
    finally:
        view.close()
        wait(100)


def test_style_guide_loads_without_warnings(qapp):
    from app.spatial.styleguide import StyleGuide

    guide = StyleGuide(dark=False)
    try:
        wait(300)
        guide.window.setProperty("dark", True)
        wait(200)
        assert guide.warnings == []
    finally:
        guide.window.close()
        guide.engine.deleteLater()
