"""Smoke test of the server program as a separate process (source or the built console exe).

    python scripts/server_smoke.py                              # python -m pqsse.server
    python scripts/server_smoke.py --exe path/to/pqsse-server.exe

In a temporary folder: write a configuration and a passphrase file, start the server, wait for its
READY line, then check the pinned HTTPS clock endpoint, the admin status (with and without the token),
"check" on the store, and a clean stop. Exits 1 on any failure.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default=None)
    args = parser.parse_args()
    command = [args.exe] if args.exe else [sys.executable, "-m", "pqsse.server"]
    from pqsse.server.tls import PinnedHTTPSConnection
    failures = 0

    def check(ok: bool, text: str) -> None:
        nonlocal failures
        print(("  PASS  " if ok else "  FAIL  ") + text)
        failures += 0 if ok else 1

    with tempfile.TemporaryDirectory(prefix="pqsse-server-smoke-") as tmp:
        tmp = Path(tmp)
        (tmp / "pass.txt").write_text("smoke test passphrase", encoding="utf-8")
        port, admin_port = free_port(), free_port()
        (tmp / "server.toml").write_text(
            f'data_dir = "data"\nhost = "127.0.0.1"\nport = {port}\nadmin_port = {admin_port}\n'
            f'passphrase_file = "{(tmp / "pass.txt").as_posix()}"\nkem = "ML-KEM-512"\nsig = "ML-DSA-44"\n', encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        proc = subprocess.Popen(command + ["run", "--config", str(tmp / "server.toml")], cwd=ROOT, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        ready, deadline = None, time.time() + 120
        while time.time() < deadline and proc.poll() is None:
            line = proc.stdout.readline()
            print("    " + line.rstrip())
            if line.startswith("PQSSE-SERVER READY"):
                ready = line
                break
        check(ready is not None, "the server started and printed its READY line")
        if ready is None:
            proc.kill()
            return 1
        pin = re.search(r"tls=([0-9a-f]{64})", ready).group(1)
        conn = PinnedHTTPSConnection("127.0.0.1", port, pin, timeout=20)
        conn.request("GET", "/v1/time")
        server_time = json.loads(conn.getresponse().read())["time"]
        conn.close()
        check(abs(server_time - time.time()) < 5, "HTTPS with the pinned certificate works; server clock agrees")
        token = (tmp / "data" / "admin.token").read_text(encoding="ascii").strip()
        url = f"http://127.0.0.1:{admin_port}/admin/status"
        try:
            urllib.request.urlopen(urllib.request.Request(url), timeout=10)
            check(False, "admin status without the token is refused")
        except urllib.error.HTTPError as exc:
            check(exc.code == 401, "admin status without the token is refused")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"X-Admin-Token": token}), timeout=10) as reply:
            status = json.loads(reply.read())
        check(status.get("kem") == "ML-KEM-512" and status.get("fingerprint"), "admin status with the token")
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        check(proc.returncode is not None, f"the server was stopped (on Windows terminate() kills it: exit code {proc.returncode}); the store must survive that")
        result = subprocess.run(command + ["check", "--config", str(tmp / "server.toml")], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=60)
        check(result.returncode == 0 and "OK" in result.stdout, "store check after the run: OK")
        for name in ("server.crt", "server.key", "admin.token", "cloud.sqlite", "cloud.pqpub"):
            check((tmp / "data" / name).is_file(), f"data folder holds {name}")
    print("SERVER SMOKE TEST: " + ("PASS" if failures == 0 else f"FAIL ({failures})"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
