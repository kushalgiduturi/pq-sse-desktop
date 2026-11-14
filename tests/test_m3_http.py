"""Milestone 3: the cloud as a separate local HTTP process, encrypted key storage,
and the scan of every database for plaintext."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from pqsse.core.errors import BadPassphrase, Rejected
from pqsse.core.keystore import Vault
from pqsse.core.pairing import export_pub, import_pub
from pqsse.owner import DocInput, Owner
from pqsse.pqbackend import FAST_PARAMS
from pqsse.receiver import Receiver
from pqsse.transport import CloudUnavailable, HttpCloud

ROOT = Path(__file__).resolve().parent.parent
SECRET_WORDS = ["xylophonic", "quetzalcoatl", "zymurgy", "brouhaha", "kerfuffle"]
DOCS = [
    ("Budget Zeppelin", "xylophonic quetzalcoatl ledger for the third quarter"),
    ("Recipe Marzipan", "zymurgy notes and a brouhaha about yeast"),
    ("Minutes Platypus", "kerfuffle over the xylophonic schedule"),
]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CloudProcess:
    """python -m pqsse.cloud as a child process."""

    def __init__(self, tmp: Path, passphrase: str = "cloud-pass", owner_pub: Path | None = None) -> None:
        self.port = free_port()
        self.db = tmp / "cloud.sqlite"
        self.pub = tmp / "cloud.pqpub"
        self.token = "admin-" + os.urandom(8).hex()
        env = {**os.environ, "PQSSE_CLOUD_PASSPHRASE": passphrase, "PQSSE_CLOUD_ADMIN_TOKEN": self.token,
               "PYTHONPATH": str(ROOT)}
        cmd = [sys.executable, "-m", "pqsse.cloud", "--port", str(self.port), "--db", str(self.db),
               "--pub", str(self.pub), "--kem", FAST_PARAMS.kem, "--sig", FAST_PARAMS.sig]
        if owner_pub is not None:
            cmd += ["--owner-pub", str(owner_pub)]
        self.proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.first_line = self.proc.stdout.readline().strip()
        self.api = HttpCloud(port=self.port, admin_token=self.token)

    def wait_ready(self) -> None:
        assert self.first_line.startswith("PQSSE-CLOUD READY"), self.first_line
        deadline = time.time() + 20
        while time.time() < deadline:
            if self.api.alive():
                return
            time.sleep(0.05)
        raise AssertionError("cloud process did not come up")

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.proc.stdout.close()


def all_bytes(path: Path) -> bytes:
    """A database file plus any SQLite side files."""
    data = b""
    for candidate in path.parent.glob(path.name + "*"):
        data += candidate.read_bytes()
    return data


def test_full_scenario_over_http_with_encrypted_stores(tmp_path):
    owner_vault = Vault(tmp_path / "owner.sqlite", "owner-pass")
    owner = Owner.create(owner_vault, FAST_PARAMS, "owner")
    owner_pub = tmp_path / "owner.pqpub"
    export_pub(owner_pub, owner.public_identity())

    cloud = CloudProcess(tmp_path, owner_pub=owner_pub)
    try:
        cloud.wait_ready()
        cloud_ident = import_pub(cloud.pub, expect_role="cloud")
        assert cloud_ident.fingerprint() in cloud.first_line
        owner.cloud = cloud.api
        owner.pair_cloud(cloud_ident)
        owner.create_group("alpha")
        owner.create_group("beta")
        ids = owner.build_index("alpha", [DocInput(t, x) for t, x in DOCS])
        owner.add_document("beta", "Other", "unrelated beta content")
        owner.publish("alpha")
        owner.publish("beta")

        receivers = {}
        for name, groups in (("alice", ["alpha"]), ("bob", ["alpha", "beta"])):
            vault = Vault(tmp_path / f"{name}.sqlite", name + "-pass")
            rec = Receiver.create(vault, FAST_PARAMS, name, cloud=cloud.api)
            rec.pair(import_pub(owner_pub, "owner"), cloud_ident)
            uid = rec.send_join()
            item = next(i for i in owner.pending_joins() if i["uid"] == uid)
            owner.approve_join(item, groups)
            assert rec.fetch_mail()
            receivers[name] = rec
        alice, bob = receivers["alice"], receivers["bob"]

        result = alice.search("alpha", "xylophonic")
        assert result.ids == {ids[0], ids[2]} and result.report.all_ok
        assert alice.open_document("alpha", ids[1], 1).text == DOCS[1][1]
        with pytest.raises(Rejected) as err:
            HttpCloud(port=cloud.port).call("admin_stats", None)        # no admin token
        assert err.value.reason == "admin_only"
        with pytest.raises(Rejected) as err:
            cloud.api.call("update", {"msg": b"junk", "sig": b"junk"})
        assert err.value.reason in ("bad_signature", "malformed")

        owner.revoke(alice.uid, "R")
        with pytest.raises(Rejected) as err:
            alice.search("alpha", "xylophonic")
        assert err.value.reason == "revoked"
        new_id = owner.add_document("alpha", "Later", "zymurgy revisited after revocation")
        owner.delete_document("alpha", ids[0])
        owner.publish("alpha")
        assert bob.search("alpha", "zymurgy").ids == {ids[1], new_id}
        assert bob.search("alpha", "xylophonic").ids == {ids[2]}
        assert bob.search("beta", "unrelated").report.all_ok

        stats = cloud.api.call("admin_stats", None)
        assert stats["entries"] > 0 and stats["revoked"] == 1 and stats["rejected"] >= 2
        log = cloud.api.call("admin_log", {"since": 0})
        assert any(row[2] == "search" and row[5] == 0 and row[6] == "revoked" for row in log)
        peek = cloud.api.call("admin_peek", None)
        assert peek["entries"] and peek["docs"] and peek["states"]

        # restart: the cloud keeps its identity and data, and a wrong passphrase is refused
        cloud.stop()
        bad = CloudProcess(tmp_path, passphrase="not-the-passphrase")
        assert "wrong passphrase" in bad.first_line
        bad.stop()
        again = CloudProcess(tmp_path)
        again.wait_ready()
        assert import_pub(again.pub, "cloud") == cloud_ident
        bob.cloud = again.api
        owner.cloud = again.api
        assert bob.search("alpha", "zymurgy").ids == {ids[1], new_id}
        again.stop()
        cloud = None

        # ---- scan the cloud database: no plaintext keywords, documents or keys
        blob = all_bytes(tmp_path / "cloud.sqlite")
        assert len(blob) > 10_000
        for word in SECRET_WORDS + [t for t, _ in DOCS] + ["Zeppelin", "Marzipan", "Platypus", "revisited"]:
            assert word.encode() not in blob, word
            assert word.lower().encode() not in blob, word
        group_state = owner._group("alpha")
        secrets = list(group_state["keys"].values()) + list(owner._group("beta")["keys"].values())
        secrets += [owner._sk, bob._dk, bob._sk, alice._dk]
        secrets += [r["a"] for r in owner.receivers.values()] + [r["m"] for r in owner.receivers.values()]
        cloud_vault = Vault(tmp_path / "cloud.sqlite", "cloud-pass")
        ident = cloud_vault.get("identity")
        secrets += [ident["dk"], ident["sk"]]
        cloud_vault.close()
        for secret in secrets:
            assert secret not in blob
            assert secret[:16] not in blob

        # ---- owner and receiver stores are encrypted at rest as well
        owner_vault.close()
        bob.vault.close()
        alice.vault.close()
        owner_blob = all_bytes(tmp_path / "owner.sqlite")
        bob_blob = all_bytes(tmp_path / "bob.sqlite")
        for word in SECRET_WORDS:
            assert word.encode() not in owner_blob and word.encode() not in bob_blob
        for secret in secrets:
            assert secret[:16] not in owner_blob and secret[:16] not in bob_blob
        with pytest.raises(BadPassphrase):
            Vault(tmp_path / "owner.sqlite", "guess")
        reopened = Owner(Vault(tmp_path / "owner.sqlite", "owner-pass"))
        assert reopened.overview("alpha")["epoch"] == 2
        reopened.vault.close()
    finally:
        if cloud is not None:
            cloud.stop()


def test_cloud_unreachable_is_reported_cleanly():
    with pytest.raises(CloudUnavailable):
        HttpCloud(port=free_port(), timeout=2).call("info", None)
    assert not HttpCloud(port=free_port(), timeout=2).alive()


def test_server_refuses_non_loopback_bind():
    from pqsse.cloud.core import CloudCore
    from pqsse.cloud.server import make_server
    from pqsse.core.keystore import MemoryVault

    with pytest.raises(ValueError):
        make_server(CloudCore(MemoryVault(), FAST_PARAMS), "0.0.0.0", free_port())
