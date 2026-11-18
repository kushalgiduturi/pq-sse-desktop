"""End-to-end test: the cloud server in Docker, the data owner and a receiver on this computer.

    python scripts/docker_e2e.py            (Docker must be running)

Starts docker/docker-compose.yml with a throwaway passphrase secret, reads the TLS and server key
fingerprints from inside the container, pairs a new data owner, and runs Join, BuildIndex, Publish,
Search with all checks, Decrypt and Revoke (policy RE) from the host over HTTPS with the certificate
pinned. Then it shows the admin status and removes the container and its data volume. Exits 1 on failure.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
COMPOSE = ["docker", "compose", "-p", "pqsse-e2e", "-f", str(ROOT / "docker" / "docker-compose.yml")]
SECRET = ROOT / "docker" / "secrets" / "pqsse_passphrase"


def run(args: list[str], stdin: bytes | None = None, check: bool = True) -> str:
    result = subprocess.run(args, input=stdin, capture_output=True, timeout=600)
    out = result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace")
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(args[3:])} failed:\n{out[-2000:]}")
    return out


def main() -> int:
    from pqsse.core.errors import Rejected
    from pqsse.core.keystore import MemoryVault
    from pqsse.core.pairing import PublicIdentity, export_pub
    from pqsse.owner import Owner
    from pqsse.pqbackend import Params
    from pqsse.receiver import Receiver
    from pqsse.transport import HttpsCloud

    failures = 0

    def check(ok: bool, text: str) -> None:
        nonlocal failures
        print(("  PASS  " if ok else "  FAIL  ") + text, flush=True)
        failures += 0 if ok else 1

    SECRET.parent.mkdir(parents=True, exist_ok=True)
    made_secret = not SECRET.exists()
    if made_secret:
        SECRET.write_text(secrets.token_urlsafe(24), encoding="utf-8")   # throwaway, deleted at the end
    try:
        run(COMPOSE + ["up", "-d", "--build"])
        ready, deadline = "", time.time() + 180
        while time.time() < deadline:
            ready = next((l for l in run(COMPOSE + ["logs", "server"]).splitlines() if "PQSSE-SERVER READY" in l), "")
            if ready:
                break
            time.sleep(2)
        check(bool(ready), "the server container started and printed its READY line")
        if not ready:
            print(run(COMPOSE + ["logs", "server"], check=False)[-3000:])
            return 1
        prints = run(COMPOSE + ["exec", "-T", "server", "python", "-m", "pqsse.server", "fingerprint"])
        pin = re.search(r"TLS certificate SHA-256:\s*([0-9a-f ]+)", prints).group(1).replace(" ", "")
        key_fp = re.search(r"Server key fingerprint:\s*(.+)", prints).group(1).strip()
        check(len(pin) == 64 and pin in ready, "the TLS fingerprint from inside the container matches the READY line")

        api = HttpsCloud("127.0.0.1", 8443, pin, timeout=120)
        server_ident = PublicIdentity.from_wire(api.call("pub", None))
        check(server_ident.fingerprint() == key_fp, "the server key fetched over HTTPS matches the operator's fingerprint")
        params = Params(server_ident.params.kem, server_ident.params.sig)
        check(abs(api.server_time() - time.time()) < 10, "the container's clock agrees with this computer's")

        owner = Owner.create(MemoryVault(), params, cloud=api)
        owner.pair_cloud(server_ident)
        with tempfile.TemporaryDirectory() as tmp:
            export_pub(Path(tmp) / "owner.pqpub", owner.public_identity())
            out = run(COMPOSE + ["exec", "-T", "server", "python", "-m", "pqsse.server", "pair-owner", "/dev/stdin"],
                      stdin=(Path(tmp) / "owner.pqpub").read_bytes())
        check("Data owner paired" in out, "the operator paired the data owner (owner key given on stdin)")

        owner.create_group("Finance")
        owner.build_index("Finance", [])
        owner.add_document("Finance", "Invoice 1042, server hardware", "invoice for the server hardware", ["invoice", "hardware"])
        owner.add_document("Finance", "Budget 2026", "budget for next year", ["budget"])
        owner.publish("Finance")
        bob = Receiver.create(MemoryVault(), params, "receiver-a", cloud=api)
        owner_from_server = PublicIdentity.from_wire(api.call("owner_pub", None))
        invite = owner.create_invite("127.0.0.1", 8443, pin, "receiver-a")
        check(owner_from_server.fingerprint() == invite.owner_fp, "the owner key the server hands out matches the invite")
        bob.pair(owner_from_server, server_ident)
        uid = bob.send_join(invite.id, invite.code)
        owner.approve_join(next(i for i in owner.pending_joins() if i["uid"] == uid), ["Finance"])
        bob.fetch_mail()
        result = bob.search("Finance", "invoice")
        check(len(result.hits) == 1 and result.report.all_ok, f"search over HTTPS to the container: 1 hit, all {len(result.report.checks)} checks passed")
        doc_id, epoch = result.hits[0]
        check(bob.open_document("Finance", doc_id, epoch).title.startswith("Invoice 1042"), "the document decrypts on this computer")
        owner.revoke(bob.uid, "RE")
        try:
            bob.search("Finance", "invoice")
            check(False, "a revoked receiver is refused")
        except Rejected as exc:
            check(exc.reason == "revoked", "a revoked receiver is refused (policy RE)")

        status = json.loads(run(COMPOSE + ["exec", "-T", "server", "python", "-m", "pqsse.server", "admin", "status"]))
        storage = json.loads(run(COMPOSE + ["exec", "-T", "server", "python", "-m", "pqsse.server", "admin", "storage"]))
        check(status.get("paired") is True and storage.get("docs") == 2, "admin status and storage from inside the container")
        dump = json.dumps([status, storage])
        check(not any(w in dump for w in ("invoice", "hardware", "budget")), "the operator's view holds no document words")
        check_out = run(COMPOSE + ["exec", "-T", "server", "python", "-m", "pqsse.server", "check"], check=False)
        check("Store check: OK" in check_out, "store check inside the container")
        user = run(COMPOSE + ["exec", "-T", "server", "id", "-u"]).strip()
        check(user == "10001", f"the server runs as a non-root user (uid {user})")
    finally:
        run(COMPOSE + ["down", "-v"], check=False)          # removes the container and the test data volume
        if made_secret:
            SECRET.unlink(missing_ok=True)
    print("DOCKER END-TO-END: " + ("PASS" if failures == 0 else f"FAIL ({failures})"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
