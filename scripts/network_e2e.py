"""Network end-to-end test: the cloud server, the data owner and a receiver as separate processes.

    python scripts/network_e2e.py               (loopback, about two minutes)
    python scripts/network_e2e.py --exe dist/pqsse-server/pqsse-server.exe

The server runs as `python -m pqsse.server run` (or the built exe) with its own data folder. The data
owner and the receiver each have their own folder and vault, and every step runs as a fresh process
(scripts/net_party.py), so nothing is shared in memory. Only what people would really pass on goes from
one to the other: the operator's fingerprints, the owner's public key file, the invite file, the
one-time code and the receiver's fingerprint words.

Steps: start, pair the owner (operator CLI), publish, invite, join, compare words, approve, search and
open over HTTPS, add a document and find it, stop and restart the server and search again, revoke
(policy RE) and see the refusal, then the store check. Exits 1 on failure.
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARTY = [sys.executable, str(ROOT / "scripts" / "net_party.py")]
KEM, SIG = "ML-KEM-512", "ML-DSA-44"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, command: list[str], config: Path, env: dict) -> None:
        self.command, self.config, self.env = command, config, env
        self.proc: subprocess.Popen | None = None
        self.ready = ""

    def start(self) -> str:
        self.proc = subprocess.Popen(self.command + ["run", "--config", str(self.config)], cwd=ROOT, env=self.env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        deadline = time.time() + 120
        while time.time() < deadline and self.proc.poll() is None:
            line = self.proc.stdout.readline()
            if "PQSSE-SERVER READY" in line:
                self.ready = line.strip()
                return self.ready
        raise RuntimeError("the server did not print its READY line")

    def cli(self, *args: str) -> str:
        out = subprocess.run(self.command + list(args) + ["--config", str(self.config)], cwd=ROOT, env=self.env,
                             capture_output=True, text=True, timeout=300)
        return out.stdout + out.stderr

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


def party(step: str, folder: Path, args: dict, env: dict) -> dict:
    out = subprocess.run(PARTY + [step, str(folder), json.dumps(args)], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=600)
    if out.returncode != 0:
        raise RuntimeError(f"{step} failed:\n{(out.stdout + out.stderr)[-2000:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default=None)
    args = parser.parse_args()
    command = [args.exe] if args.exe else [sys.executable, "-m", "pqsse.server"]
    failures = 0

    def check(ok: bool, text: str) -> None:
        nonlocal failures
        print(("  PASS  " if ok else "  FAIL  ") + text, flush=True)
        failures += 0 if ok else 1

    env = dict(os.environ, PYTHONPATH=str(ROOT))
    with tempfile.TemporaryDirectory(prefix="pqsse-net-e2e-") as tmp:
        tmp = Path(tmp)
        server_dir, owner_dir, rec_dir = tmp / "server", tmp / "owner", tmp / "receiver"
        server_dir.mkdir()
        (server_dir / "pass.txt").write_text("network test server passphrase", encoding="utf-8")
        port, admin_port = free_port(), free_port()
        config = server_dir / "server.toml"
        config.write_text(f'data_dir = "{(server_dir / "data").as_posix()}"\nhost = "127.0.0.1"\nport = {port}\n'
                          f'admin_port = {admin_port}\npassphrase_file = "{(server_dir / "pass.txt").as_posix()}"\n'
                          f'kem = "{KEM}"\nsig = "{SIG}"\n', encoding="utf-8")
        server = Server(command, config, env)
        try:
            ready = server.start()
            prints = server.cli("fingerprint")
            pin = re.search(r"TLS certificate SHA-256:\s*([0-9a-fA-F ]+)", prints).group(1).replace(" ", "").lower()
            server_fp = re.search(r"Server key fingerprint:\s*(.+)", prints).group(1).strip()
            check(f"tls={pin}" in ready, "server process started; the operator's fingerprint matches its READY line")
            net = {"host": "127.0.0.1", "port": port, "pin": pin}

            init = party("owner-init", owner_dir, {**net, "server_fp": server_fp, "kem": KEM, "sig": SIG}, env)
            paired = server.cli("pair-owner", str(owner_dir / "owner.pqpub"))
            check(init["owner_fp"] in paired, "owner process made its keys; the operator paired the owner's public key file")

            made = party("owner-publish", owner_dir, net, env)
            check(Path(made["invite_file"]).is_file() and made["code"] not in Path(made["invite_file"]).read_text(),
                  "owner published a group and made an invite file without the code in it")

            joined = party("receiver-join", rec_dir, {"invite_file": made["invite_file"], "code": made["code"]}, env)
            check(len(joined["words"].split()) == 6, "receiver process checked both keys against the invite and sent its join")

            approved = party("owner-approve", owner_dir, {**net, "uid": joined["uid"], "words": joined["words"]}, env)
            check(approved["approved"] == joined["uid"] and approved["invite"] == "receiver-a",
                  "owner checked the invite proof and the fingerprint words, then approved")

            found = party("receiver-search", rec_dir, {**net, "word": "confidential"}, env)
            check(found.get("titles") == ["Contract A"] and found["checks_ok"],
                  f"receiver searched and opened the document over HTTPS, all {found.get('checks')} checks passed")

            party("owner-add", owner_dir, {**net, "title": "Contract B", "text": "a second confidential contract",
                                           "keywords": ["contract", "confidential"]}, env)
            found = party("receiver-search", rec_dir, {**net, "word": "confidential"}, env)
            check(found.get("titles") == ["Contract A", "Contract B"] and found["checks_ok"],
                  "after an update by the owner process, the receiver finds both documents")

            server.stop()
            server.start()
            found = party("receiver-search", rec_dir, {**net, "word": "contract"}, env)
            check(found.get("titles") == ["Contract A", "Contract B"] and found["checks_ok"],
                  "server process stopped and started again: the same results, all checks passed")

            party("owner-revoke", owner_dir, {**net, "uid": joined["uid"]}, env)
            found = party("receiver-search", rec_dir, {**net, "word": "confidential"}, env)
            check(found.get("refused") == "revoked", "after revocation (policy RE) the receiver is refused")

            server.stop()
            check("Store check: OK" in server.cli("check"), "store check on the stopped server's data")
            leaked = [p for p in (server_dir / "data").rglob("*") if p.is_file()
                      and any(w in p.read_bytes() for w in (b"penalty clause", b"Contract A", b"quarterly report"))]
            check(not leaked, "no document text or title in any file of the server's data folder")
        except Exception as exc:  # report and fail, keep the cleanup
            print(f"  FAIL  {exc}", flush=True)
            failures += 1
        finally:
            server.stop()
    print("NETWORK END-TO-END: " + ("PASS" if failures == 0 else f"FAIL ({failures})"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
