"""Real run of the web installer on this PC, against a local server, with the real Standard build.

    python scripts/test_web_setup_real.py [--dist <one-folder Standard build>]

Steps: compile a twin of the Standard installer (name "PQ-SSE Desktop Test", its own AppId, so a
real PQ-SSE Desktop install on this PC is never touched), sign it and a manifest with a throwaway
key, serve them on 127.0.0.1, compile a TEST BUILD of the web installer with that key, run it
silently into a folder with spaces (real GPU detection, no simulation), run --smoke-test of the
installed program, uninstall it, and check that the install folder is gone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_web_setup  # noqa: E402
import make_manifest  # noqa: E402

DEFAULT_DIST = Path(os.environ.get("LOCALAPPDATA", "")) / "PQ-SSE-Desktop-build" / "standard" / "dist" / "PQ-SSE-Desktop"


def step(text: str) -> None:
    print(f"\n== {text}", flush=True)


def check(ok: bool, text: str) -> None:
    print(("  PASS  " if ok else "  FAIL  ") + text, flush=True)
    if not ok:
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST)
    args = parser.parse_args()
    iscc, tool = build_web_setup.find_iscc(), make_manifest.find_issigtool()
    check(bool(iscc and tool), "Inno Setup 6.7 (ISCC and ISSigTool) found")
    check((args.dist / "PQ-SSE-Desktop.exe").is_file(), f"Standard build found: {args.dist}")
    version = make_manifest.read_version()
    work = Path(tempfile.mkdtemp(prefix="pqsse-web-real-"))
    files = work / "files"
    files.mkdir()

    step("Twin Standard installer and throwaway signing key")
    name = f"PQ-SSE-Desktop-Setup-{version}.exe"
    subprocess.run([iscc, "/Q", f"/DAppVersion={version}", "/DVariant=Standard", f"/DSourceDir={args.dist}", f"/DOutputDir={files}",
                    f"/DOutputBase={name[:-4]}", "/DTestInstall=1", str(ROOT / "installer" / "pqsse.iss")], check=True)
    key, pub = work / "throwaway.key", work / "pub.txt"
    subprocess.run([tool, f"--key-file={key}", "generate-private-key"], check=True, capture_output=True)
    subprocess.run([tool, f"--key-file={key}", "export-public-key", str(pub)], check=True, capture_output=True)
    data = (files / name).read_bytes()
    check(len(data) > 10_000_000, f"twin installer built: {len(data) / 2**20:.1f} MB")

    step("Local release server")
    handler = partial(SimpleHTTPRequestHandler, directory=str(files))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    manifest = {"schema": 1, "version": version, "released": time.strftime("%Y-%m-%d"), "min_os": "10.0.17763",
                "channels": {"standard": {"available": True, "file": name, "url": f"{base}/{name}", "size": len(data),
                                          "sha256": hashlib.sha256(data).hexdigest()},
                             "gpu": {"available": False, "min_driver": "528.33"}}}
    (files / "latest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    subprocess.run([tool, f"--key-file={key}", "--quiet", "sign", str(files / "latest.json"), str(files / name)], check=True)
    print(f"  serving {files} at {base}")

    step("Web installer (test build) and silent install into a folder with spaces")
    stub = build_web_setup.build(work / "stub", pub, version=version, test_manifest=f"{base}/latest.json", test_hosts=["127.0.0.1"])
    size = stub.stat().st_size
    check(size < 5 * 2**20, f"web installer is {size / 2**20:.1f} MB (limit about 5 MB)")
    target = work / "Install Test Dir" / "PQ-SSE Desktop Test"
    log = work / "web-setup.log"
    started = time.time()
    result = subprocess.run([str(stub), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={target}", f"/LOGFILE={log}"], timeout=900)
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    print("  " + "\n  ".join(line for line in text.splitlines() if "Video controller" in line or "GPU" in line or "Chosen" in line))
    check(result.returncode == 0, f"web installer exit code 0 (was {result.returncode}), {time.time() - started:.0f} s")
    print(f"  log: {log}")
    check("SHA-256 matches the manifest" in text, "download checked against the signed manifest")
    exe = target / "PQ-SSE-Desktop.exe"
    check(exe.is_file(), f"installed program exists: {exe}")

    step("Smoke test of the installed program")
    data_dir = work / "data"
    smoke = subprocess.run([str(exe), "--smoke-test"], env={**os.environ, "PQSSE_DATA_DIR": str(data_dir)}, capture_output=True,
                           text=True, timeout=600)
    print("  " + "\n  ".join(smoke.stdout.strip().splitlines()[-3:]))
    check(smoke.returncode == 0, "smoke test from the installed location passes")

    step("Uninstall")
    uninstallers = sorted(target.glob("unins*.exe"))
    check(bool(uninstallers), "uninstaller exists")
    subprocess.run([str(uninstallers[-1]), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=300)
    for _ in range(60):
        if not exe.exists():
            break
        time.sleep(1)
    check(not exe.exists(), "the program was removed")
    httpd.shutdown()
    print("\nWEB INSTALLER REAL RUN: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
