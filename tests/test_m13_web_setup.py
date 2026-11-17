"""The web installer against a local fake release server.

Each test runs a TEST BUILD of PQ-SSE-Web-Setup.exe (allows http://127.0.0.1 and the /TESTGPU=
and /LOGFILE= parameters) silently against a small HTTP server on 127.0.0.1 that serves a signed
latest.json and a fake package (a tiny Inno installer that records its command line). A run
passes only when the right thing happened and, in every failure case, nothing was run.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_web_setup  # noqa: E402
import make_manifest  # noqa: E402

ISCC = build_web_setup.find_iscc()
ISSIGTOOL = make_manifest.find_issigtool()
pytestmark = pytest.mark.skipif(not (ISCC and ISSIGTOOL and sys.platform == "win32"), reason="needs Windows and Inno Setup 6.7")
PACKAGE = "PQ-SSE-Desktop-Setup-9.9.9.exe"
GPU_PACKAGE = "PQ-SSE-Desktop-Setup-9.9.9-GPU.exe"


class Server:
    """Serves files from a folder; `rules` change the behavior of single paths."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.rules: dict[str, tuple] = {}
        self.requests: list[str] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, body_wanted: bool):
                path = self.path.split("?")[0]
                server.requests.append(f"{self.command} {path}")
                rule = server.rules.get(path)
                if rule and rule[0] == "redirect":
                    self.send_response(302)
                    self.send_header("Location", rule[1])
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                data = server.files.get(path)
                if data is None:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if not body_wanted:
                    return
                if rule and rule[0] == "truncate":
                    self.wfile.write(data[: len(data) // 2])
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                self.wfile.write(data)

            def do_HEAD(self):
                self.answer(False)

            def do_GET(self):
                self.answer(True)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self.httpd.shutdown()


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    work = tmp_path_factory.mktemp("websetup")
    key = work / "throwaway.key"
    subprocess.run([ISSIGTOOL, f"--key-file={key}", "generate-private-key"], check=True, capture_output=True)
    pub = work / "pub.txt"
    subprocess.run([ISSIGTOOL, f"--key-file={key}", "export-public-key", str(pub)], check=True, capture_output=True)
    fixtures = work / "fixtures"
    shutil.copytree(ROOT / "tests" / "fixtures", fixtures)
    subprocess.run([ISCC, "/Q", f"/O{work}", str(fixtures / "fake-package.iss")], check=True, capture_output=True)
    package = (work / "fake-package.exe").read_bytes()
    server = Server()
    stub = build_web_setup.build(work / "stub", pub, version="9.9.9", test_manifest=server.base + "/latest.json",
                                 test_hosts=["127.0.0.1"])
    with socket.socket() as sock:              # a port with nothing listening: "offline"
        sock.bind(("127.0.0.1", 0))
        dead = sock.getsockname()[1]
    offline = build_web_setup.build(work / "offline", pub, version="9.9.9", test_manifest=f"http://127.0.0.1:{dead}/latest.json",
                                    test_hosts=["127.0.0.1"])
    yield {"work": work, "key": key, "pub": pub, "package": package, "server": server, "stub": stub, "offline": offline}
    server.stop()


def sign(env, name: str, data: bytes) -> bytes:
    folder = env["work"] / "sign"
    folder.mkdir(exist_ok=True)
    (folder / name).write_bytes(data)
    subprocess.run([ISSIGTOOL, f"--key-file={env['key']}", "--allow-overwrite", "--quiet", "sign", str(folder / name)], check=True)
    return (folder / (name + ".issig")).read_bytes()


def publish(env, *, gpu: bool = False, manifest_hash: str | None = None, sign_manifest: bool = True, package: bytes | None = None,
            package_url: str | None = None) -> None:
    server = env["server"]
    server.files.clear()
    server.rules.clear()
    data = env["package"]
    files = {PACKAGE: data}
    if gpu:
        files[GPU_PACKAGE] = data + b"\0" * 16
    channels = {}
    for key, name in (("standard", PACKAGE), ("gpu", GPU_PACKAGE)):
        if name not in files:
            channels[key] = {"available": False}
            continue
        server.files["/files/" + name] = files[name] if package is None else package
        server.files["/files/" + name + ".issig"] = sign(env, name, files[name])
        channels[key] = {"available": True, "file": name, "url": package_url or f"{server.base}/files/{name}",
                         "size": len(files[name]), "sha256": hashlib.sha256(files[name]).hexdigest()}
    channels["gpu"]["min_driver"] = "528.33"
    if manifest_hash:
        channels["standard"]["sha256"] = manifest_hash
    manifest = json.dumps({"schema": 1, "version": "9.9.9", "released": "2026-11-20", "min_os": "10.0.17763",
                           "channels": channels}, indent=2).encode()
    server.files["/latest.json"] = manifest
    if sign_manifest:
        server.files["/latest.json.issig"] = sign(env, "latest.json", manifest)


def run(env, tmp_path, *extra: str, stub: Path | None = None) -> tuple[int, str, Path]:
    target = tmp_path / "Install Dir With Spaces"
    log = tmp_path / "web-setup.log"
    args = [str(stub or env["stub"]), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={target}", f"/LOGFILE={log}", *extra]
    result = subprocess.run(args, timeout=180)
    return result.returncode, log.read_text(encoding="utf-8", errors="replace") if log.exists() else "", target


def test_success_installs_silently_to_a_path_with_spaces(env, tmp_path):
    publish(env)
    code, log, target = run(env, tmp_path, "/TESTGPU=none")
    assert code == 0, log
    marker = (target / "marker.txt").read_text()
    assert "/VERYSILENT" in marker and "/CURRENTUSER" in marker and "Install Dir With Spaces" in marker
    assert "SHA-256 matches the manifest" in log and "Chosen: Standard build" in log


def test_wrong_hash_in_the_signed_manifest_is_refused_and_nothing_runs(env, tmp_path):
    publish(env, manifest_hash="0" * 64)
    code, log, target = run(env, tmp_path, "/TESTGPU=none")
    assert code != 0 and not (target / "marker.txt").exists()
    assert "does not match the SHA-256" in log


def test_swapped_package_fails_its_signature_and_nothing_runs(env, tmp_path):
    publish(env, package=env["package"][:-10] + b"x" * 10)
    code, log, target = run(env, tmp_path, "/TESTGPU=none")
    assert code != 0 and not (target / "marker.txt").exists()
    assert "signature check" in log


def test_unsigned_manifest_is_refused(env, tmp_path):
    publish(env, sign_manifest=False)
    code, log, target = run(env, tmp_path, "/TESTGPU=none")
    assert code != 0 and not (target / "marker.txt").exists()
    assert "signature file for latest.json could not be reached" in log


def test_truncated_download_fails_cleanly(env, tmp_path):
    publish(env)
    env["server"].rules["/files/" + PACKAGE] = ("truncate",)
    code, log, target = run(env, tmp_path, "/TESTGPU=none")
    assert code != 0 and not (target / "marker.txt").exists()
    assert "failed or did not pass the signature check" in log


def test_redirect_to_a_host_outside_the_list_is_refused_before_it_is_fetched(env, tmp_path):
    publish(env, package_url=None)
    server = env["server"]
    server.rules["/files/" + PACKAGE] = ("redirect", f"http://evil.example:{server.port}/files/{PACKAGE}")
    code, log, target = run(env, tmp_path, "/TESTGPU=none")
    assert code != 0 and not (target / "marker.txt").exists()
    assert "is not on the list of official PQ-SSE hosts" in log and "evil.example" in log


def test_redirect_within_the_allowed_hosts_is_followed(env, tmp_path):
    publish(env)
    server = env["server"]
    server.files["/mirror/" + PACKAGE] = server.files["/files/" + PACKAGE]
    server.rules["/files/" + PACKAGE] = ("redirect", f"{server.base}/mirror/{PACKAGE}")
    code, log, target = run(env, tmp_path, "/TESTGPU=none")
    assert code == 0, log
    assert (target / "marker.txt").exists() and "Redirect 302" in log


def test_offline_shows_the_friendly_message(env, tmp_path):
    code, log, target = run(env, tmp_path, "/TESTGPU=none", stub=env["offline"])
    assert code != 0 and not (target / "marker.txt").exists()
    assert "No connection to the PQ-SSE download server" in log


@pytest.mark.parametrize("driver, chosen", [("none", "Standard"), ("31.0.15.2833", "GPU"), ("31.0.15.1000", "Standard")])
def test_gpu_detection_picks_gpu_only_with_a_new_enough_driver(env, tmp_path, driver, chosen):
    publish(env, gpu=True)
    code, log, target = run(env, tmp_path, f"/TESTGPU={driver}")
    assert code == 0, log
    assert f"Chosen: {chosen} build" in log
    if driver == "31.0.15.1000":
        assert "older than 528.33" in log


def test_gpu_build_not_in_the_manifest_means_standard(env, tmp_path):
    publish(env, gpu=False)
    code, log, target = run(env, tmp_path, "/TESTGPU=31.0.15.6109")
    assert code == 0, log
    assert "Chosen: Standard build" in log and "GPU build not available" in log
