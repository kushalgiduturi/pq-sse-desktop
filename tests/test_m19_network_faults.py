"""Milestone 4 of REALLIFE_PLAN.md: faults and abuse against the real server over TLS on loopback.

Faults: dropped and delayed connections, a lost reply for every kind of write, a server restart, a full
disk in the middle of a batch (also during a policy RE revocation), a receiver that crashes after sending
its join, clock skew, a replayed join, searches running while the owner updates, a large document and
a large result. Abuse: random and malformed bodies on every endpoint, non-TLS bytes, a flood of
connections, after which a real client is still served.
"""
from __future__ import annotations

import os
import random
import socket
import ssl
import threading
import time

import pytest
from test_m16_server import FAST, Running, _raw_post

from pqsse.core import wire
from pqsse.core.errors import Rejected, VerifyError
from pqsse.core.keystore import MemoryVault, Vault
from pqsse.owner import DocInput, Owner
from pqsse.receiver import Receiver
from pqsse.receiver import receiver as receiver_module
from pqsse.server import store
from pqsse.server.http import PUBLIC_ENDPOINTS
from pqsse.transport import CloudUnavailable, HttpsCloud


# ------------------------------------------------------------------ helpers
class Proxy:
    """A TCP relay in front of the server that can drop or delay connections (TLS passes through unchanged)."""

    def __init__(self, target_port: int) -> None:
        self.target = target_port
        self.drop_next = 0
        self.delay = 0.0
        self.connections = 0
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(32)
        self.port = self.sock.getsockname()[1]
        self.closed = False
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while not self.closed:
            try:
                client, _ = self.sock.accept()
            except OSError:
                return
            self.connections += 1
            if self.drop_next > 0:
                self.drop_next -= 1
                client.close()
                continue
            threading.Thread(target=self._relay, args=(client,), daemon=True).start()

    def _relay(self, client: socket.socket) -> None:
        time.sleep(self.delay)
        try:
            upstream = socket.create_connection(("127.0.0.1", self.target), timeout=30)
        except OSError:
            client.close()
            return

        def pump(src: socket.socket, dst: socket.socket) -> None:
            try:
                while data := src.recv(65536):
                    dst.sendall(data)
            except OSError:
                pass
            finally:
                for s in (src, dst):
                    try:
                        s.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

        threading.Thread(target=pump, args=(upstream, client), daemon=True).start()
        pump(client, upstream)

    def close(self) -> None:
        self.closed = True
        self.sock.close()


class LosesFirstReply(HttpsCloud):
    """The server answers, but the first reply for each listed endpoint never reaches the client."""

    def __init__(self, *args, endpoints=(), **kwargs) -> None:
        super().__init__(*args, backoff=0.01, **kwargs)
        self.pending = set(endpoints)
        self.lost: list[str] = []

    def _once(self, endpoint, body):
        reply = super()._once(endpoint, body)
        if endpoint in self.pending:
            self.pending.discard(endpoint)
            self.lost.append(endpoint)
            raise CloudUnavailable("connection reset after the server answered")
        return reply


def setup_owner(running: Running, cloud=None) -> Owner:
    owner = Owner.create(MemoryVault(), FAST, cloud=cloud or running.client())
    owner.pair_cloud(running.core.public_identity())
    running.core.pair_owner(owner.public_identity())
    return owner


def join(running: Running, owner: Owner, name: str, groups=("g",), vault=None, cloud=None) -> Receiver:
    rec = Receiver.create(vault or MemoryVault(), FAST, name, cloud=cloud or running.client())
    rec.pair(owner.public_identity(), running.core.public_identity())
    inv = owner.create_invite("127.0.0.1", running.config.port, running.pin, name)
    uid = rec.send_join(inv.id, inv.code)
    owner.approve_join(next(i for i in owner.pending_joins() if i["uid"] == uid), list(groups))
    rec.fetch_mail()
    return rec


@pytest.fixture
def server(tmp_path):
    running = Running(tmp_path)
    yield running
    running.close()


# ------------------------------------------------------------------ faults
def test_dropped_and_delayed_connections_are_retried(server):
    proxy = Proxy(server.config.port)
    try:
        api = HttpsCloud("127.0.0.1", proxy.port, server.pin, timeout=10, backoff=0.01)
        owner = setup_owner(server, api)
        proxy.drop_next = 2                                   # the next two connections die before TLS
        owner.create_group("g")
        owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
        proxy.delay = 0.4                                     # every connection is slow to start
        owner.publish("g")
        rec = join(server, owner, "receiver-a", cloud=api)
        assert len(rec.search("g", "contract").hits) == 1
        assert proxy.connections >= 2 and api.online is True
        impatient = HttpsCloud("127.0.0.1", proxy.port, server.pin, timeout=0.2, attempts=2, backoff=0.01)
        with pytest.raises(CloudUnavailable):
            impatient.call("info", None)                      # too slow for its timeout: a clear "unreachable"
        assert impatient.online is False
    finally:
        proxy.close()


def test_a_lost_reply_on_every_kind_of_write_leaves_owner_server_and_receiver_in_step(server):
    writes = ("ctl", "update", "state_put", "join_post")
    api = LosesFirstReply("127.0.0.1", server.config.port, server.pin, endpoints=writes)
    owner = setup_owner(server, api)
    owner.create_group("g")
    owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    owner.publish("g")
    rec = join(server, owner, "receiver-a", cloud=api)
    assert sorted(api.lost) == sorted(writes)                 # each kind of write lost its first reply ...
    result = rec.search("g", "contract")                      # ... and everything still agrees
    assert len(result.hits) == 1 and result.report.all_ok
    owner.add_document("g", "Contract B", "another penalty clause", ["contract"])
    owner.publish("g")
    assert len(rec.search("g", "contract").hits) == 2
    assert server.core.db.execute("SELECT seq FROM groups WHERE g='g'").fetchone()[0] == owner.groups["g"]["seq"]


def test_server_restart_keeps_the_data_the_pin_and_the_receivers(tmp_path):
    first = Running(tmp_path)
    owner = setup_owner(first)
    owner.create_group("g")
    owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    owner.publish("g")
    rec = join(first, owner, "receiver-a")
    pin = first.pin
    first.close()
    second = Running(tmp_path)
    try:
        assert second.pin == pin
        owner.cloud = rec.cloud = second.client()
        assert len(rec.search("g", "contract").hits) == 1
        owner.add_document("g", "Contract B", "another penalty clause", ["contract"])
        owner.publish("g")
        assert len(rec.search("g", "contract").hits) == 2
        assert store.check(second.config) == []
    finally:
        second.close()


def test_a_full_disk_in_the_middle_of_a_batch_changes_nothing(server, monkeypatch):
    api = HttpsCloud("127.0.0.1", server.config.port, server.pin, backoff=0.01, attempts=2)
    owner = setup_owner(server, api)
    owner.create_group("g")
    owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    owner.publish("g")
    leaving = join(server, owner, "receiver-a", cloud=api)
    staying = join(server, owner, "receiver-b", cloud=api)
    seq_before = server.core.db.execute("SELECT seq FROM groups WHERE g='g'").fetchone()[0]
    files_before = sorted(p.name for p in server.config.blob_dir.rglob("*") if p.is_file())

    real_put = server.core.blobs.put
    def disk_full(data):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(server.core.blobs, "put", disk_full)
    with pytest.raises(CloudUnavailable):
        owner.add_document("g", "Contract B", "another penalty clause", ["contract"])
    assert server.core.db.execute("SELECT seq FROM groups WHERE g='g'").fetchone()[0] == seq_before
    assert len(staying.search("g", "contract").hits) == 1    # the last good state is still served

    with pytest.raises(CloudUnavailable):
        owner.revoke(leaving.uid, "RE")                       # access is withdrawn; the rotation waits for the batch
    with pytest.raises(Rejected) as info:
        leaving.search("g", "contract")
    assert info.value.reason == "revoked"
    assert owner._meta["rotations"] == {"g": "RE"} and owner.has_pending
    assert owner.groups["g"]["epoch"] == 1                    # nothing rotated yet
    assert sorted(p.name for p in server.config.blob_dir.rglob("*") if p.is_file()) == files_before
    assert store.check(server.config) == []                   # no file lost, no half-written file left

    monkeypatch.setattr(server.core.blobs, "put", real_put)   # space again: the next change settles everything first
    owner.add_document("g", "Contract C", "a third penalty clause", ["contract"])
    owner.publish("g")
    assert not owner.has_pending and owner.groups["g"]["epoch"] == 2
    assert server.core.db.execute("SELECT seq FROM groups WHERE g='g'").fetchone()[0] == owner.groups["g"]["seq"]
    staying.fetch_mail()
    result = staying.search("g", "contract")
    assert result.report.all_ok
    # Contract B was sent before the revocation and is delivered by the journal; Contract C comes after the rotation
    assert {staying.open_document("g", d, e).title for d, e in result.hits} == {"Contract A", "Contract B", "Contract C"}
    assert {d["title"]: d["epoch"] for d in owner.documents("g")}["Contract C"] == 2
    assert store.check(server.config) == []


def test_resume_pending_finishes_an_interrupted_rebuild(server, monkeypatch):
    owner = setup_owner(server)
    owner.create_group("g")
    owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    owner.publish("g")
    leaving = join(server, owner, "receiver-a")
    real_apply = Owner._apply
    def lost_network(self, g, adds, dels, reset=False, **kwargs):
        if reset:
            raise CloudUnavailable("the network went away")
        return real_apply(self, g, adds, dels, reset, **kwargs)
    monkeypatch.setattr(Owner, "_apply", lost_network)
    with pytest.raises(CloudUnavailable):
        owner.revoke(leaving.uid, "RE")
    monkeypatch.setattr(Owner, "_apply", real_apply)
    assert owner.resume_pending() == ["g: rebuild finished"] and owner.resume_pending() == []
    staying = join(server, owner, "receiver-b")
    assert len(staying.search("g", "contract").hits) == 1


def test_a_receiver_that_crashes_after_sending_its_join_continues_from_its_vault(server, tmp_path):
    owner = setup_owner(server)
    owner.create_group("g")
    owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    owner.publish("g")
    path = tmp_path / "receiver.db"
    vault = Vault(path, "receiver passphrase", scrypt_n=2 ** 12)
    rec = Receiver.create(vault, FAST, "receiver-a", cloud=server.client())
    rec.pair(owner.public_identity(), server.core.public_identity())
    inv = owner.create_invite("127.0.0.1", server.config.port, server.pin, "receiver-a")
    uid = rec.send_join(inv.id, inv.code)
    vault.close()                                             # the process dies here
    del rec
    owner.approve_join(next(i for i in owner.pending_joins() if i["uid"] == uid), ["g"])
    again = Receiver(Vault(path, "receiver passphrase", scrypt_n=2 ** 12), cloud=server.client())
    assert again.uid == uid
    again.fetch_mail()
    assert len(again.search("g", "contract").hits) == 1
    again.vault.close()


def test_clock_skew_beyond_the_window_is_refused_both_ways(server):
    owner = setup_owner(server)
    owner.create_group("g")
    owner.publish("g")
    rec = join(server, owner, "receiver-a")
    rec.clock = lambda: time.time() + 600
    with pytest.raises(Rejected) as info:
        rec.mail_items()
    assert info.value.reason == "stale_token"
    owner.clock = lambda: time.time() - 600
    with pytest.raises(Rejected) as info:
        owner.pending_joins()
    assert info.value.reason == "stale_token"


def test_a_replayed_join_is_a_duplicate_and_a_used_invite_stays_used(server):
    owner = setup_owner(server)
    owner.create_group("g")
    inv = owner.create_invite("127.0.0.1", server.config.port, server.pin, "receiver-a")
    rec = Receiver.create(MemoryVault(), FAST, "receiver-a", cloud=server.client())
    rec.pair(owner.public_identity(), server.core.public_identity())
    request = rec.join_request(inv.id, inv.code)
    api = server.client()
    api.call("join_post", request)
    with pytest.raises(Rejected) as info:
        api.call("join_post", request)                        # the same bytes again: stored once
    assert info.value.reason == "duplicate"
    assert len(owner.pending_joins()) == 1
    with pytest.raises(Rejected) as info:
        api.call("join_post", rec.join_request(inv.id, inv.code))   # a new request on the used invite
    assert info.value.reason == "invite_used"


def test_searches_while_the_owner_updates_never_return_a_wrong_result(server):
    owner = setup_owner(server)
    owner.create_group("g")
    owner.add_document("g", "doc 0", "seed", ["shared"])
    owner.publish("g")
    readers = [join(server, owner, f"receiver-{c}") for c in "ab"]
    stop, outcomes, errors = threading.Event(), [], []

    def search_loop(rec: Receiver) -> None:
        while not stop.is_set():
            try:
                result = rec.search("g", "shared")
                titles = {rec.open_document("g", d, e).title for d, e in result.hits}
                outcomes.append((result.report.all_ok, titles))
            except (VerifyError, Rejected) as exc:          # a state in between: refused, never wrong
                outcomes.append((False, type(exc).__name__))
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))

    threads = [threading.Thread(target=search_loop, args=(r,)) for r in readers]
    for t in threads:
        t.start()
    for n in range(1, 7):
        owner.add_document("g", f"doc {n}", "more", ["shared"])
        owner.publish("g")
    time.sleep(0.5)
    stop.set()
    for t in threads:
        t.join(60)
    assert not errors, errors
    every = {f"doc {n}" for n in range(7)}
    for ok, titles in outcomes:
        if ok:
            assert titles <= every and "doc 0" in titles      # verified results are real documents only
    assert any(ok for ok, _ in outcomes)
    final = readers[0].search("g", "shared")
    assert final.report.all_ok and len(final.hits) == 7


def test_a_large_document_and_a_large_result(server, monkeypatch):
    monkeypatch.setattr(receiver_module, "DOWNLOAD_PART", 1 << 20)
    owner = setup_owner(server)
    owner.create_group("g")
    big = "lorem ipsum " * 700_000 + "needle"                 # about 8 MiB
    docs = [DocInput("big", big, ["needle"])] + [DocInput(f"item {i}", f"item {i}", ["common"]) for i in range(150)]
    owner.build_index("g", docs)
    owner.publish("g")
    rec = join(server, owner, "receiver-a")
    [(doc_id, epoch)] = rec.search("g", "needle").hits
    calls = []
    real_call = rec.cloud.call
    rec.cloud.call = lambda endpoint, obj: (calls.append(endpoint), real_call(endpoint, obj))[1]
    assert rec.open_document("g", doc_id, epoch).text.endswith("needle")
    assert calls.count("doc_get") >= 8                        # fetched in 1 MiB parts
    result = rec.search("g", "common")
    assert len(result.hits) == 150 and result.report.all_ok


# ------------------------------------------------------------------ abuse
def test_random_and_malformed_bodies_never_crash_the_server(server):
    owner = setup_owner(server)
    owner.create_group("g")
    owner.publish("g")
    rng = random.Random(7)
    samples = [b"", b"\x00", b"\xff" * 64, wire.enc(None), wire.enc([]), wire.enc({"uid": "x" * 5000}),
               wire.enc({"msg": b"", "sig": b""}), wire.enc({"req": b"\x01\x02", "sig": b"", "proof_s": b""})]
    samples += [os.urandom(rng.randint(1, 400)) for _ in range(12)]
    statuses: dict[int, int] = {}
    for endpoint in sorted(PUBLIC_ENDPOINTS):
        for body in samples:
            code = _raw_post(server, f"/v1/{endpoint}", body)
            statuses[code] = statuses.get(code, 0) + 1
            assert code in (200, 403, 429), (endpoint, body[:20], code)
            if code == 429:
                time.sleep(1.1)
    assert statuses.get(403, 0) > 0
    rec = join(server, owner, "receiver-a")                   # and real work goes on
    assert rec.search("g", "anything").report.all_ok


def test_non_tls_bytes_and_a_connection_flood_leave_the_server_serving(tmp_path):
    running = Running(tmp_path, max_connections=8, request_deadline=1.0)
    try:
        for junk in (b"GET / HTTP/1.1\r\nHost: x\r\n\r\n", os.urandom(300), b"\x16\x03\x01\x00\x05hello"):
            with socket.create_connection(("127.0.0.1", running.config.port), timeout=5) as s:
                s.sendall(junk)
                s.settimeout(5)
                try:
                    s.recv(100)
                except (OSError, socket.timeout):
                    pass
        flood = []
        for _ in range(40):                                   # far more than the cap, all idle
            try:
                flood.append(socket.create_connection(("127.0.0.1", running.config.port), timeout=5))
            except OSError:
                break
        time.sleep(1.5)                                       # the deadline cuts every idle one
        for s in flood:
            s.close()
        time.sleep(0.3)
        context = ssl.create_default_context()
        context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
        assert running.client().call("info", None) is not None
    finally:
        running.close()
