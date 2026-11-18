"""Packaging: version, resources, smoke test, loopback bind, job object, About, log, build checks."""
from __future__ import annotations

import ctypes
import os
import re
import struct
import subprocess
import sys
import time
import tomllib
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMenu

from app import smoke, winjob
from app.main import MainWindow
from app.main import main as app_main
from app.session import Session
from pqsse import applog, paths
from pqsse.cloud.core import CloudCore
from pqsse.cloud.server import make_server
from pqsse.core.keystore import MemoryVault
from pqsse.gpu import runtime as gpu_runtime
from pqsse.pqbackend import FAST_PARAMS
from pqsse.version import get_version

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_helpers  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_version_has_one_source():
    with open(ROOT / "pyproject.toml", "rb") as handle:
        declared = tomllib.load(handle)["project"]["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", declared)
    assert get_version() == declared
    assert build_helpers.read_version() == declared


def test_version_flag_writes_report(tmp_path):
    report = tmp_path / "out" / "version.txt"
    assert app_main(["--version", "--report", str(report)]) == 0
    assert report.read_text(encoding="utf-8").strip() == get_version()


def test_resources_resolve_from_source_and_frozen(tmp_path, monkeypatch):
    assert paths.resource("pyproject.toml").is_file()
    assert paths.resource("assets/pqsse.ico").is_file()
    assert not paths.frozen()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.frozen()
    assert paths.resource("assets/pqsse.ico") == tmp_path / "assets" / "pqsse.ico"
    assert get_version() == "0.0.0"                     # no bundled pyproject.toml in this fake bundle
    assert paths.install_dir() == Path(sys.executable).resolve().parent


def test_icon_file_has_all_sizes():
    data = (ROOT / "assets" / "pqsse.ico").read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    assert (reserved, kind) == (0, 1)
    sizes = {data[6 + 16 * i] or 256 for i in range(count)}
    assert sizes == {16, 24, 32, 48, 64, 128, 256}


def test_cloud_server_binds_to_loopback_only():
    core = CloudCore(MemoryVault(), FAST_PARAMS)
    server = make_server(core, "127.0.0.1", 0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()
    for host in ("0.0.0.0", "", "::", "192.168.1.10"):
        with pytest.raises(ValueError):
            make_server(core, host, 0)


def test_cloud_entry_point_never_binds_elsewhere():
    """The cloud process passes the literal 127.0.0.1 and offers no option to change it."""
    source = (ROOT / "pqsse" / "cloud" / "__main__.py").read_text(encoding="utf-8")
    assert 'make_server(core, "127.0.0.1"' in source
    assert "--host" not in source and "--bind" not in source


def test_smoke_test_passes_and_leaves_no_data(tmp_path):
    before = os.environ.get("PQSSE_DATA_DIR")
    report = tmp_path / "smoke.txt"
    assert smoke.run_smoke(report) == 0
    text = report.read_text(encoding="utf-8")
    assert "RESULT: PASS (14 of 14 steps" in text
    assert "FAIL" not in text
    for step in ("Cloud binds to 127.0.0.1 only", "Setup and pairing", "Join", "BuildIndex and Publish",
                 "TokenGen, Search, Verify", "Decrypt", "Revoke", "Cloud database holds no plaintext"):
        assert f"PASS  {step}" in text
    assert os.environ.get("PQSSE_DATA_DIR") == before
    assert not list(paths.base_dir().glob("*.sqlite"))       # nothing was written to the active data folder


def test_smoke_test_reports_failure(monkeypatch, tmp_path):
    """A broken step gives exit code 1 and a FAIL line; the test is not allowed to hide errors."""
    def broken(self, passphrase):
        raise RuntimeError("cloud did not start")

    monkeypatch.setattr(Session, "start_cloud", broken)
    report = tmp_path / "smoke.txt"
    assert smoke.run_smoke(report) == 1
    text = report.read_text(encoding="utf-8")
    assert "FAIL  Cloud child process: RuntimeError" in text
    assert "RESULT: FAIL" in text


@pytest.mark.skipif(sys.platform != "win32", reason="Windows job objects")
def test_job_object_ends_the_child_when_the_handle_closes():
    job = winjob.create()
    assert job is not None
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        assert winjob.assign(job, child)
        assert child.poll() is None
        ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(job))      # what Windows does when the app ends
        deadline = time.time() + 10
        while child.poll() is None and time.time() < deadline:
            time.sleep(0.05)
        assert child.poll() is not None
    finally:
        if child.poll() is None:
            child.kill()


def test_about_dialog_shows_version_data_folder_and_licenses(qapp):
    window = MainWindow(Session(), sync=True)
    try:
        dialog = window.show_about(execute=False)
        assert dialog.values["Version"].text() == get_version()
        assert dialog.values["Data folder"].text() == str(paths.base_dir())
        assert any(k in dialog.values["Post-quantum backend"].text() for k in ("(native)", "pure Python", "liboqs"))
        assert dialog.values["GPU"].text()
        assert "MIT License" in dialog.licenses.toPlainText()
        assert dialog.data_button.text() == "Open data folder"
        menu_texts = [a.text() for menu in window.menuBar().findChildren(QMenu) for a in menu.actions()]
        assert "Open log folder" in menu_texts and "About PQ-SSE Desktop" in menu_texts
    finally:
        window.close()


def test_log_file_is_written_under_the_data_folder():
    path = applog.setup(hook_exceptions=False)
    try:
        assert path == paths.base_dir() / "logs" / "app.log"
        applog.log.info("packaging test line")
        assert applog.setup(hook_exceptions=False) == path           # second call adds no second handler
        assert sum(1 for h in applog.log.handlers if hasattr(h, "baseFilename")) == 1
    finally:
        applog.shutdown()
    assert "packaging test line" in path.read_text(encoding="utf-8")


def test_gpu_runtime_hook_is_inert_from_source():
    assert gpu_runtime.prepare() == ""
    assert gpu_runtime.bundled_dir() == ""


def test_secret_scan_finds_databases_and_keys(tmp_path, capsys):
    clean = tmp_path / "clean"
    (clean / "_internal").mkdir(parents=True)
    (clean / "PQ-SSE-Desktop.exe").write_bytes(b"MZ")
    assert build_helpers.main(["scan", str(clean)]) == 0
    for name in ("owner.sqlite", "server.key", "cert.pem", "settings.json", "owner.pqpub"):
        dirty = tmp_path / ("dirty_" + name.replace(".", "_"))
        dirty.mkdir()
        (dirty / name).write_bytes(b"x")
        assert build_helpers.main(["scan", str(dirty)]) == 1
    capsys.readouterr()


def test_no_long_dash_in_packaging_files(capsys):
    targets = [str(ROOT / name) for name in ("installer", "scripts", ".github", "docs", "LICENSE", "PACKAGING_PLAN.md",
                                             "build_windows.ps1", "build_release.ps1") if (ROOT / name).exists()]
    assert build_helpers.main(["emdash", *targets]) == 0
    capsys.readouterr()


def test_checksums_and_zip_helpers(tmp_path, capsys):
    payload = tmp_path / "payload"
    (payload / "sub").mkdir(parents=True)
    (payload / "a.txt").write_text("hello", encoding="utf-8")
    (payload / "sub" / "b.txt").write_text("world", encoding="utf-8")
    release = tmp_path / "release"
    assert build_helpers.main(["zip", str(payload), str(release / "p.zip"), "Top Folder"]) == 0
    import zipfile

    with zipfile.ZipFile(release / "p.zip") as archive:
        assert sorted(archive.namelist()) == ["Top Folder/a.txt", "Top Folder/sub/b.txt"]
    assert build_helpers.main(["checksums", str(release)]) == 0
    line = (release / "SHA256SUMS.txt").read_text(encoding="ascii").strip()
    assert line == f"{build_helpers.sha256(release / 'p.zip')}  p.zip"
    capsys.readouterr()
