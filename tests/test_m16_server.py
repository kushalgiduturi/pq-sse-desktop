"""Milestone 2 of REALLIFE_PLAN.md: the networked server (pqsse.server).

Everything here runs the real server code in threads, over real TLS on 127.0.0.1, with a real
passphrase-protected store in a temporary folder. Fast parameter sets keep the pure-Python crypto quick.
"""
from __future__ import annotations

import json
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from pqsse.core import wire
from pqsse.core.errors import Rejected
from pqsse.core.keystore import MemoryVault
from pqsse.owner import Owner
from pqsse.pqbackend import Params
from pqsse.receiver import Receiver
from pqsse.server import config as cfg
from pqsse.server import store, tls
from pqsse.server.http import AdminServer, PublicServer, load_or_make_token
from pqsse.server.limits import RateLimiter
from pqsse.transport import CloudUnavailable, HttpsCloud

FAST = Params("ML-KEM-512", "ML-DSA-44")
PASS = "correct horse battery staple"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Running:
    """A server (public + admin) on free loopback ports, stopped by close()."""

    def __init__(self, tmp: Path, **overrides) -> None:
        pass_file = tmp / "pass.txt"
        pass_file.write_text(PASS, encoding="utf-8")
        self.config = cfg.Config(data_dir=tmp / "data", host="127.0.0.1", port=free_port(), admin_port=free_port(),
                                 passphrase_file=str(pass_file), kem=FAST.kem, sig=FAST.sig, **overrides)
        self.core = store.open_core(self.config, cfg.read_passphrase(self.config, prompt=False))
        cert, key = tmp / "data" / "server.crt", tmp / "data" / "server.key"
        tls.make_self_signed(cert, key, ["localhost", "127.0.0.1"])
        self.pin = tls.fingerprint(cert)
        self.public = PublicServer(self.core, self.config, tls.server_context(cert, key))
        self.admin = AdminServer(self.core, self.config, self.public)
        self.token = load_or_make_token(self.config)
        for server in (self.public, self.admin):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    def client(self, pin: str | None = None) -> HttpsCloud:
        return HttpsCloud("127.0.0.1", self.config.port, pin or self.pin, timeout=20)

    def admin_call(self, path: str, method: str = "GET", body: dict | None = None, token: str | None = None):
        data = None if body is None else json.dumps(body).encode()
        headers = {} if token == "" else {"X-Admin-Token": token or self.token}
        request = urllib.request.Request(f"http://127.0.0.1:{self.config.admin_port}/admin/{path}", data=data,
                                         method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as reply:
                return reply.status, json.loads(reply.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    def close(self) -> None:
        for server in (self.public, self.admin):
            server.shutdown()
            server.server_close()
        self.core.vault.close()


@pytest.fixture
def server(tmp_path):
    running = Running(tmp_path)
    yield running
    running.close()


def owner_and_receiver(running: Running) -> tuple[Owner, Receiver]:
    owner = Owner.create(MemoryVault(), FAST, cloud=running.client())
    owner.pair_cloud(running.core.public_identity())
    running.core.pair_owner(owner.public_identity())
    owner.create_group("Finance")
    owner.build_index("Finance", [])
    owner.add_document("Finance", "Invoice 1042", "invoice for server hardware", ["invoice", "hardware"])
    owner.add_document("Finance", "Budget", "budget for next year", ["budget"])
    owner.publish("Finance")
    bob = Receiver.create(MemoryVault(), FAST, "receiver-a", cloud=running.client())
    bob.pair(owner.public_identity(), running.core.public_identity())
    invite = owner.create_invite("127.0.0.1", running.config.port, running.pin, "receiver-a")   # the networked server requires one
    uid = bob.send_join(invite.id, invite.code)
    owner.approve_join(next(i for i in owner.pending_joins() if i["uid"] == uid), ["Finance"])
    bob.fetch_mail()
    return owner, bob


# ------------------------------------------------------------------ configuration
def test_config_from_toml_and_environment(tmp_path):
    path = tmp_path / "s.toml"
    path.write_text('data_dir = "d"\nport = 9000\npublic_names = ["pq.example", "10.0.0.5"]\n', encoding="utf-8")
    config = cfg.load(path, environ={"PQSSE_SERVER_PORT": "9443", "PQSSE_SERVER_ALLOW_REMOTE_ADMIN": "yes",
                                     "PQSSE_SERVER_PUBLIC_NAMES": "a.example, 192.0.2.1"})
    assert config.port == 9443 and config.allow_remote_admin is True
    assert config.public_names == ["a.example", "192.0.2.1"] and config.data_dir == (tmp_path / "d").resolve()
    path.write_text("colour = 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        cfg.load(path, environ={})


def test_passphrase_comes_from_a_file_never_from_arguments(tmp_path):
    secret = tmp_path / "p"
    secret.write_text("s3cret phrase\n", encoding="utf-8")
    assert cfg.read_passphrase(cfg.Config(passphrase_file=str(secret)), prompt=False) == "s3cret phrase"
    with pytest.raises(SystemExit):
        cfg.read_passphrase(cfg.Config(passphrase_file=str(tmp_path / "missing")), prompt=False)
    from pqsse.server.__main__ import main
    with pytest.raises(SystemExit):
        main(["run", "--passphrase", "x"])        # there is no such option


def test_self_signed_certificate_names_and_fingerprint(tmp_path):
    from cryptography import x509
    cert, key = tmp_path / "c.crt", tmp_path / "c.key"
    tls.make_self_signed(cert, key, ["pq.example", "192.0.2.7"])
    parsed = x509.load_pem_x509_certificate(cert.read_bytes())
    sans = parsed.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "pq.example" in sans.get_values_for_type(x509.DNSName)
    assert str(sans.get_values_for_type(x509.IPAddress)[0]) == "192.0.2.7"
    assert len(tls.fingerprint(cert)) == 64 and tls.fingerprint(cert) == tls.fingerprint(cert)


# ------------------------------------------------------------------ the protocol over TLS
def test_full_protocol_over_tls_with_a_pinned_certificate(server):
    owner, bob = owner_and_receiver(server)
    result = bob.search("Finance", "invoice")
    assert len(result.hits) == 1 and result.report.all_ok
    doc_id, epoch = result.hits[0]
    assert bob.open_document("Finance", doc_id, epoch).title == "Invoice 1042"
    owner.revoke(bob.uid, "RE")
    with pytest.raises(Rejected):
        bob.search("Finance", "invoice")
    assert abs(server.client().server_time() - time.time()) < 5


def test_wrong_pin_is_refused_before_any_request(server):
    before = server.core.db.execute("SELECT COUNT(*) FROM log").fetchone()[0]
    with pytest.raises(CloudUnavailable) as info:
        server.client(pin="00" * 32).call("info", None)
    assert "pinned" in str(info.value)
    assert server.core.db.execute("SELECT COUNT(*) FROM log").fetchone()[0] == before


def test_tls_versions_below_1_2_are_refused(server):
    # the server's own setting (the handshake below may also be refused by this PC's OpenSSL itself)
    cert, key = server.config.data_dir / "server.crt", server.config.data_dir / "server.key"
    assert tls.server_context(cert, key).minimum_version == ssl.TLSVersion.TLSv1_2
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        ctx.maximum_version = ssl.TLSVersion.TLSv1_1
    except ValueError:
        pytest.skip("this OpenSSL cannot even offer TLS 1.1")
    with socket.create_connection(("127.0.0.1", server.config.port), timeout=10) as raw:
        with pytest.raises(ssl.SSLError):
            ctx.wrap_socket(raw).do_handshake()
    ctx13 = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx13.check_hostname, ctx13.verify_mode = False, ssl.CERT_NONE
    with socket.create_connection(("127.0.0.1", server.config.port), timeout=10) as raw:
        with ctx13.wrap_socket(raw) as sock:
            assert sock.version() in ("TLSv1.3", "TLSv1.2")
            name, _, _ = sock.cipher()
            assert "GCM" in name or "CHACHA20" in name


def _raw_post(running: Running, path: str, body: bytes, headers: dict | None = None) -> int:
    from pqsse.server.tls import PinnedHTTPSConnection
    conn = PinnedHTTPSConnection("127.0.0.1", running.config.port, running.pin, timeout=20)
    try:
        conn.request("POST", path, body=body, headers=headers or {})
        return conn.getresponse().status
    finally:
        conn.close()


def test_unknown_paths_admin_endpoints_and_malformed_bodies(server):
    assert _raw_post(server, "/v1/admin_stats", wire.enc(None)) == 404       # operator calls are not on the public port
    assert _raw_post(server, "/v1/nothing", wire.enc(None)) == 404
    assert _raw_post(server, "/api/info", wire.enc(None)) == 404
    assert _raw_post(server, "/v1/search", b"\xff\x00garbage") == 403          # refused as malformed, no traceback


def test_body_limits(tmp_path):
    running = Running(tmp_path, max_small_body_bytes=1000)
    try:
        assert _raw_post(running, "/v1/join_post", b"x" * 2000) == 413
        assert _raw_post(running, "/v1/update", b"x" * 2000) == 403            # large endpoint: read, then refused as malformed
    finally:
        running.close()


def test_rate_limit_per_client_address(tmp_path):
    running = Running(tmp_path, requests_per_minute=5)
    try:
        codes = [_raw_post(running, "/v1/info", wire.enc(None)) for _ in range(8)]
        assert codes[:5] == [200] * 5 and 429 in codes[5:]
    finally:
        running.close()


def test_rate_limiter_refills():
    now = [0.0]
    limiter = RateLimiter(60, clock=lambda: now[0])
    assert all(limiter.allow("k")[0] for _ in range(60)) and not limiter.allow("k")[0]
    now[0] += 1.0
    assert limiter.allow("k")[0] and not limiter.allow("k")[0]


def test_connection_cap_and_slow_clients_are_cut(tmp_path):
    running = Running(tmp_path, max_connections=1, request_deadline=1.5)
    try:
        idle = socket.create_connection(("127.0.0.1", running.config.port), timeout=10)   # never says anything
        time.sleep(0.3)
        assert _raw_post(running, "/v1/info", wire.enc(None)) == 503
        time.sleep(1.6)                     # the deadline cuts the idle connection ...
        idle.settimeout(2)
        assert idle.recv(10) == b""
        idle.close()
        time.sleep(0.2)
        assert _raw_post(running, "/v1/info", wire.enc(None)) == 200   # ... and frees the slot
    finally:
        running.close()


# ------------------------------------------------------------------ operator interface
def test_admin_needs_the_token_and_shows_no_secrets(server):
    owner_and_receiver(server)
    assert server.admin_call("status", token="")[0] == 401
    assert server.admin_call("status", token="wrong")[0] == 401
    status, body = server.admin_call("status")
    assert status == 200 and body["paired"] is True and body["fingerprint"]
    status, storage = server.admin_call("storage")
    assert status == 200 and storage["docs"] == 2 and storage["storage_bytes"] > 0
    everything = json.dumps([body, storage, server.admin_call("log")[1], server.admin_call("connections")[1]])
    for plain in ("invoice", "hardware", "budget", "Invoice 1042", PASS):
        assert plain not in everything


def test_admin_rotate_token_delete_group_and_backup(server, tmp_path):
    owner_and_receiver(server)
    old = server.token
    assert server.admin_call("rotate-token", "POST", {})[0] == 200
    assert server.admin_call("status", token=old)[0] == 401
    server.token = load_or_make_token(server.config)
    status, body = server.admin_call("backup", "POST", {"to": str(tmp_path / "bk")})
    assert status == 200 and store.check(cfg.Config(data_dir=tmp_path / "bk")) == []
    status, body = server.admin_call("delete-group", "POST", {"g": "Finance"})
    assert status == 200 and body["deleted"]["docs"] == 2
    assert server.core.db.execute("SELECT COUNT(*) FROM docs").fetchone()[0] == 0
    assert not any(server.config.blob_dir.glob("??/*"))


def test_admin_interface_refuses_a_public_address(tmp_path):
    config = cfg.Config(data_dir=tmp_path, admin_host="0.0.0.0")
    with pytest.raises(ValueError):
        AdminServer(None, config, None)


# ------------------------------------------------------------------ store: limits, check, backup, restore
def test_storage_limits(tmp_path):
    running = Running(tmp_path, max_docs_per_group=2, max_doc_bytes=10_000)
    try:
        owner, _ = owner_and_receiver(running)
        with pytest.raises(Rejected) as info:
            owner.add_document("Finance", "third", "one too many", ["third"])
        assert info.value.reason == "group_full"
        owner.delete_document("Finance", owner.documents("Finance")[0]["id"])
        with pytest.raises(Rejected) as info:
            owner.add_document("Finance", "big", "x" * 20_000, ["big"])
        assert info.value.reason == "too_large"
    finally:
        running.close()


def test_documents_are_files_and_check_finds_damage(server):
    owner_and_receiver(server)
    files = list(server.config.blob_dir.glob("??/*"))
    assert len(files) == 2 and store.check(server.config) == []
    files[0].write_bytes(b"tampered")
    problems = store.check(server.config)
    assert any("damaged" in p for p in problems)


def test_backup_and_restore_round_trip(server, tmp_path):
    owner, bob = owner_and_receiver(server)
    store.backup(server.config, tmp_path / "bk")
    target = cfg.Config(data_dir=tmp_path / "restored", kem=FAST.kem, sig=FAST.sig)
    store.restore(tmp_path / "bk", target)
    assert store.check(target) == []
    restored = store.open_core(target, PASS)
    try:
        assert restored.public_identity().fingerprint() == server.core.public_identity().fingerprint()
        from pqsse.transport import InProcessCloud
        bob.cloud = InProcessCloud(restored)
        assert len(bob.search("Finance", "invoice").hits) == 1
    finally:
        restored.vault.close()
    with pytest.raises(store.StoreError):
        store.restore(tmp_path / "bk", target)          # never over an existing store


def test_damaged_database_refuses_to_start(tmp_path):
    running = Running(tmp_path)
    path = running.config.store_path
    running.close()
    data = bytearray(path.read_bytes())
    data[4096:4096 + 64] = b"\xff" * 64                 # damage a page in the middle
    path.write_bytes(bytes(data))
    assert store.check(running.config) != []


def test_server_runs_as_its_own_process():
    """scripts/server_smoke.py: start python -m pqsse.server as a separate process, pinned HTTPS, admin, check."""
    import subprocess
    import sys
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run([sys.executable, str(root / "scripts" / "server_smoke.py")], capture_output=True, text=True,
                            timeout=300, cwd=root)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-1000:]
    assert "SERVER SMOKE TEST: PASS" in result.stdout
