"""The user-started update check against a local fake server (never the real site)."""
from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from app import issig, update_check
from app.session import Session

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import make_manifest  # noqa: E402

TOOL = make_manifest.find_issigtool()
pytestmark = pytest.mark.skipif(not TOOL, reason="ISSigTool (Inno Setup 6.5+) is not installed")


class Server:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.redirects: dict[str, str] = {}
        self.hits: list[str] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                server.hits.append(self.path)
                if self.path in server.redirects:
                    self.send_response(302)
                    self.send_header("Location", server.redirects[self.path])
                    self.end_headers()
                    return
                data = server.files.get(self.path)
                self.send_response(200 if data is not None else 404)
                self.send_header("Content-Length", str(len(data or b"")))
                self.end_headers()
                self.wfile.write(data or b"")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    work = tmp_path_factory.mktemp("update")
    key = work / "throwaway.key"
    subprocess.run([TOOL, f"--key-file={key}", "generate-private-key"], check=True, capture_output=True)
    pub = work / "pub.txt"
    subprocess.run([TOOL, f"--key-file={key}", "export-public-key", str(pub)], check=True, capture_output=True)
    server = Server()
    yield {"work": work, "key": key, "public": issig.parse_public_key(pub.read_text()), "server": server}
    server.httpd.shutdown()


def signed(env, name: str, data: bytes) -> bytes:
    folder = env["work"] / "sign"
    folder.mkdir(exist_ok=True)
    (folder / name).write_bytes(data)
    subprocess.run([TOOL, f"--key-file={env['key']}", "--quiet", "--allow-overwrite", "sign", str(folder / name)], check=True)
    return (folder / (name + ".issig")).read_bytes()


def publish(env, version: str = "9.9.9", web: bytes | None = b"MZ fake web installer", tamper_manifest: bool = False) -> dict:
    server = env["server"]
    server.files.clear()
    server.redirects.clear()
    manifest = {"schema": 1, "version": version, "released": "2030-01-02", "notes_url": "https://example.invalid/notes",
                "download_page": "https://kushalgiduturi.github.io/pq-sse-desktop/download.html", "min_os": "10.0.17763",
                "channels": {"standard": {"available": False}, "gpu": {"available": False}}, "portable": {},
                "web_setup": {"available": False}}
    if web is not None:
        manifest["web_setup"] = {"available": True, "file": "PQ-SSE-Web-Setup.exe", "url": f"{server.base}/PQ-SSE-Web-Setup.exe",
                                 "size": len(web), "sha256": hashlib.sha256(web).hexdigest()}
        server.files["/PQ-SSE-Web-Setup.exe"] = web
        server.files["/PQ-SSE-Web-Setup.exe.issig"] = signed(env, "PQ-SSE-Web-Setup.exe", web)
    data = json.dumps(manifest).encode()
    server.files["/latest.json.issig"] = signed(env, "latest.json", data)
    server.files["/latest.json"] = data.replace(b"9.9.9", b"9.9.8") if tamper_manifest else data
    return manifest


def config(env, **changes) -> update_check.Config:
    base = dict(manifest_url=env["server"].base + "/latest.json", allowed_hosts={"127.0.0.1"}, public_key=env["public"],
                insecure_hosts={"127.0.0.1"}, timeout=5.0)
    base.update(changes)
    return update_check.Config(**base)


def test_newer_and_current(env):
    publish(env, "9.9.9")
    newer = update_check.check("0.1.0", config(env))
    assert newer["status"] == "newer" and newer["version"] == "9.9.9" and newer["web_available"]
    publish(env, "0.1.0")
    assert update_check.check("0.1.0", config(env))["status"] == "current"
    assert update_check.version_tuple("0.10.0") > update_check.version_tuple("0.9.9")


def test_changed_manifest_is_refused(env):
    publish(env, tamper_manifest=True)
    result = update_check.check("0.1.0", config(env))
    assert result["status"] == "error" and "signature" in result["message"]


def test_unsigned_manifest_is_refused(env):
    publish(env)
    del env["server"].files["/latest.json.issig"]
    result = update_check.check("0.1.0", config(env))
    assert result["status"] == "error" and "HTTP 404" in result["message"]


def test_other_key_is_refused(env):
    publish(env)
    stranger = issig.PublicKey("0" * 64, "1" * 64, "2" * 64)
    result = update_check.check("0.1.0", config(env, public_key=stranger))
    assert result["status"] == "error" and "does not trust" in result["message"]


def test_redirect_to_another_host_is_refused(env):
    publish(env)
    server = env["server"]
    server.redirects["/latest.json"] = "https://evil.example/latest.json"
    result = update_check.check("0.1.0", config(env))
    assert result["status"] == "error" and "outside the official hosts" in result["message"]


def test_plain_http_is_refused(env):
    publish(env)
    result = update_check.check("0.1.0", config(env, insecure_hosts=set()))
    assert result["status"] == "error" and "non-HTTPS" in result["message"]


def test_offline_gives_a_plain_message(env):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        dead = sock.getsockname()[1]
    result = update_check.check("0.1.0", config(env, manifest_url=f"http://127.0.0.1:{dead}/latest.json"))
    assert result["status"] == "error" and "no connection" in result["message"]


def test_without_a_key_it_says_so(env):
    result = update_check.check("0.1.0", config(env, public_key=None))
    assert result["status"] == "error" and "no signing key" in result["message"]


def test_web_installer_is_checked_before_it_is_kept(env, tmp_path):
    manifest = publish(env)
    path = update_check.download_web_setup(manifest, tmp_path / "ok", config(env))
    assert path.read_bytes() == b"MZ fake web installer"
    env["server"].files["/PQ-SSE-Web-Setup.exe"] = b"MZ swapped installer!"
    with pytest.raises(update_check.UpdateError, match="does not match"):
        update_check.download_web_setup(manifest, tmp_path / "bad", config(env))
    assert not (tmp_path / "bad").exists()


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def new_session() -> Session:
    session = Session()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        session.settings["port"] = sock.getsockname()[1]
    return session


def test_bridge_never_goes_online_by_itself_and_checks_when_asked(env, qapp, monkeypatch, tmp_path):
    from app.spatial.bridge import AppBridge

    def no_network(*args, **kwargs):
        raise AssertionError("the app tried to go online without being asked")

    monkeypatch.setattr(urllib.request, "build_opener", no_network)
    bridge = AppBridge(new_session(), sync=True)
    try:
        assert bridge.updateState == {"status": "idle"} and bridge.updateMenu is True
        monkeypatch.undo()
        publish(env, "9.9.9")
        bridge.update_config = config(env)
        bridge.checkForUpdates()
        state = bridge.updateState
        assert state["status"] == "newer" and state["version"] == "9.9.9" and "manifest" not in state
        bridge.runWebInstaller()                                    # sync mode: downloads and checks, does not start it
        assert bridge.updateState["status"] == "web_ready" and Path(bridge.updateState["path"]).is_file()
        bridge.setUpdateMenu(False)
        assert bridge.updateMenu is False and bridge.session.settings["update_menu"] is False
    finally:
        bridge.shutdown()
