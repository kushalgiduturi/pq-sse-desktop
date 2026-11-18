"""Milestone 3 of REALLIFE_PLAN.md, the parts that need no protocol change: safe retransmission, the
retrying HTTPS client, the clock-skew check, and the client modes (Local demo, Data owner, Receiver)."""
from __future__ import annotations

import time

import pytest
from test_m16_server import FAST, Running

from pqsse.core import wire
from pqsse.core.errors import PQSSEError, Rejected
from pqsse.core.keystore import MemoryVault
from pqsse.owner import Owner
from pqsse.sandbox import World
from pqsse.transport import (CloudUnavailable, HttpsCloud, PinRefused, ServerBusy, clock_skew)


# ------------------------------------------------------------------ safe retransmission at the server
class Capture:
    """Remembers the last body sent to an endpoint, so a test can send exactly the same bytes again."""

    def __init__(self, core) -> None:
        self.core, self.last = core, {}

    def call(self, endpoint, obj):
        body = wire.enc(obj)
        self.last[endpoint] = body
        return wire.dec(self.core.handle(endpoint, body))


def test_the_exact_last_batch_control_and_state_are_refused_as_duplicate_and_applied_once():
    world = World()
    cap = Capture(world.cloud)
    world.owner.cloud = cap
    world.owner.create_group("g")                                     # ctl + state_put
    world.owner.add_document("g", "a", "alpha beta", ["alpha", "beta"])
    entries = world.cloud.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    for endpoint in ("ctl", "state_put", "update"):
        with pytest.raises(Rejected) as info:
            world.cloud.handle(endpoint, cap.last[endpoint])
        assert info.value.reason == "duplicate"
    assert world.cloud.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == entries   # applied once only
    # the owner's own resend of the same bytes counts as accepted
    assert world.owner._send("update", wire.dec(cap.last["update"])) == {"ok": True, "repeat": True}


def test_a_different_message_with_the_same_number_is_still_refused():
    world = World()
    cap = Capture(world.cloud)
    world.owner.cloud = cap
    world.owner.create_group("g")
    world.owner.add_document("g", "a", "alpha", ["alpha"])
    first = cap.last["update"]
    world.owner.groups["g"]["seq"] -= 1                               # pretend the owner lost track and reuses seq 1
    with pytest.raises(Rejected) as info:
        world.owner.add_document("g", "b", "beta", ["beta"])
    assert info.value.reason == "bad_sequence" and cap.last["update"] != first


# ------------------------------------------------------------------ the retrying HTTPS client
class Scripted(HttpsCloud):
    """HttpsCloud whose single attempts follow a script of outcomes."""

    def __init__(self, outcomes) -> None:
        self.slept: list[float] = []
        super().__init__("127.0.0.1", 1, "0" * 64, attempts=4, backoff=0.1, sleep=self.slept.append)
        self.outcomes, self.calls = list(outcomes), 0

    def _once(self, endpoint, body):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def test_client_retries_connection_failures_with_backoff():
    api = Scripted([CloudUnavailable("down"), CloudUnavailable("down"), {"ok": 1}])
    assert api.call("info", None) == {"ok": 1} and api.calls == 3 and api.online is True
    assert len(api.slept) == 2 and api.slept[0] < api.slept[1] * 2          # growing waits with jitter
    api = Scripted([CloudUnavailable("down")] * 4)
    with pytest.raises(CloudUnavailable):
        api.call("info", None)
    assert api.calls == 4 and api.online is False


def test_client_honours_retry_after_and_never_retries_refusals_or_a_wrong_pin():
    api = Scripted([ServerBusy("busy", 3.0), {"ok": 1}])
    assert api.call("info", None) == {"ok": 1} and api.slept == [3.0]
    for outcome in (Rejected("revoked", "x"), PinRefused("wrong certificate")):
        api = Scripted([outcome, {"ok": 1}])
        with pytest.raises(type(outcome)):
            api.call("info", None)
        assert api.calls == 1


def test_lost_reply_is_recovered_against_the_real_server(tmp_path):
    """The server applies an update but its reply is lost; the client sends the same bytes again and the owner commits."""
    running = Running(tmp_path)
    try:
        class LosesFirstUpdateReply(HttpsCloud):
            lost = False

            def _once(self, endpoint, body):
                reply = super()._once(endpoint, body)
                if endpoint == "update" and not LosesFirstUpdateReply.lost:
                    LosesFirstUpdateReply.lost = True
                    raise CloudUnavailable("connection reset after the server answered")
                return reply

        api = LosesFirstUpdateReply("127.0.0.1", running.config.port, running.pin, backoff=0.01)
        owner = Owner.create(MemoryVault(), FAST, cloud=api)
        owner.pair_cloud(running.core.public_identity())
        running.core.pair_owner(owner.public_identity())
        owner.create_group("g")
        owner.add_document("g", "a", "alpha", ["alpha"])
        assert LosesFirstUpdateReply.lost and owner.groups["g"]["seq"] == 1
        owner.add_document("g", "b", "beta", ["beta"])                # owner and server still agree
        assert running.core.db.execute("SELECT seq FROM groups WHERE g='g'").fetchone()[0] == 2
    finally:
        running.close()


def test_clock_skew_levels():
    class Clock:
        def __init__(self, offset):
            self.offset = offset

        def server_time(self):
            return time.time() + self.offset
    assert clock_skew(Clock(1.0))[1] == "ok"
    assert clock_skew(Clock(-200.0))[1] == "warn"
    skew, level, message = clock_skew(Clock(600.0))
    assert level == "refuse" and "Set the clock automatically" in message and skew > 590


# ------------------------------------------------------------------ client modes
@pytest.fixture
def server(tmp_path):
    (tmp_path / "srv").mkdir()
    running = Running(tmp_path / "srv")
    yield running
    running.close()


def test_modes_keep_their_own_data_and_the_lesson_stays_local(tmp_path):
    from app.session import LESSON_PROFILE, NETWORK_PROFILE, Session
    from pqsse import paths
    session = Session()
    assert session.use == "demo" and not session.networked and paths.data_dir() == paths.base_dir()
    session.set_use("owner")
    assert session.networked and session.remote and paths.data_dir() == paths.base_dir() / NETWORK_PROFILE
    with pytest.raises(PQSSEError):
        session.start_cloud("pass")                                   # the server runs elsewhere
    with pytest.raises(PQSSEError):
        session.api()                                                 # not connected yet
    session.set_profile(LESSON_PROFILE)
    assert not session.remote                                         # the lesson keeps its own local cloud
    session.set_profile(session.own_profile)
    assert session.remote
    session.set_use("demo")
    assert paths.data_dir() == paths.base_dir() and Session().use == "demo"


def test_owner_mode_connects_with_the_pin_and_checks_the_server_key(server, monkeypatch):
    from app.session import Session
    session = Session()
    session.set_use("owner")
    fp = server.core.public_identity().fingerprint()
    with pytest.raises(PQSSEError) as info:
        session.connect_server("127.0.0.1", server.config.port, server.pin, "AAAA BBBB CCCC DDDD EEEE")
    assert "does not match" in str(info.value)
    with pytest.raises(CloudUnavailable):
        session.connect_server("127.0.0.1", server.config.port, "11" * 32, fp)      # wrong certificate
    info = session.connect_server("127.0.0.1", server.config.port, server.pin, fp)
    assert info["fingerprint"] == fp and info["level"] == "ok" and session.cloud_running()
    session.settings["kem"], session.settings["sig"] = FAST.kem, FAST.sig
    session.open_owner("owner passphrase")
    session.owner_pair_cloud()
    server.core.pair_owner(session.owner.public_identity())          # the operator's pair-owner step
    session.owner.create_group("Finance")
    assert server.core.db.execute("SELECT COUNT(*) FROM groups").fetchone()[0] == 1
    monkeypatch.setattr(HttpsCloud, "server_time", lambda self: time.time() + 900)
    with pytest.raises(PQSSEError) as info:
        session.connect_server("127.0.0.1", server.config.port, server.pin, fp)
    assert "clock" in str(info.value)
    session.close()


def test_bridge_mode_of_use_and_connect(server):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.session import Session
    from app.spatial.bridge import AppBridge
    bridge = AppBridge(Session(), sync=True)
    assert bridge.use == "demo" and not bridge.remote
    bridge.setUse("receiver")
    assert bridge.use == "receiver" and bridge.remote and bridge.server["connected"] is False
    bridge.connectServer("127.0.0.1", server.config.port, server.pin, server.core.public_identity().fingerprint())
    assert bridge.server["connected"] is True and bridge.server["level"] == "ok"
    bridge.setUse("demo")
    assert not bridge.remote
    bridge.session.close()
