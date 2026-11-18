"""Design note 006 B: the data owner's write-ahead journal.

A "crash" here: the server applies the message, the answer is lost, and the owner object is thrown away.
A "restart" builds a new Owner from the same vault, as the app does when it is opened again.
"""
from __future__ import annotations

import pytest

from pqsse.core.errors import Rejected
from pqsse.owner import Owner
from pqsse.owner.owner import JOURNAL
from pqsse.sandbox import World
from pqsse.transport import CloudUnavailable


class Crash(Exception):
    """The owner app dies here."""


class CrashAfter:
    """Delivers the next call to ``endpoint`` to the server, then dies before the answer arrives."""

    def __init__(self, inner, endpoint: str, deliver: bool = True) -> None:
        self.inner, self.endpoint, self.deliver, self.armed = inner, endpoint, deliver, True

    def call(self, endpoint, obj):
        if self.armed and endpoint == self.endpoint:
            self.armed = False
            if self.deliver:
                self.inner.call(endpoint, obj)
            raise Crash(endpoint)
        return self.inner.call(endpoint, obj)


def restart(world: World) -> Owner:
    owner = Owner(world.owner.vault, cloud=world.api, clock=world.clock)
    world.owner = owner
    return owner


def seq_at_server(world: World, g: str) -> int:
    return world.cloud.db.execute("SELECT seq FROM groups WHERE g=?", (g,)).fetchone()[0]


@pytest.mark.parametrize("deliver", [True, False], ids=["applied-then-crash", "crash-before-the-server"])
def test_an_update_survives_a_crash(deliver):
    world = World()
    world.owner.create_group("g")
    world.owner.publish("g")
    bob = world.join("receiver-a", ["g"])
    world.owner.cloud = CrashAfter(world.api, "update", deliver)
    with pytest.raises(Crash):
        world.owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    owner = restart(world)
    assert owner.has_pending and any(True for _ in owner.vault.names(JOURNAL))
    owner.add_document("g", "Contract B", "another penalty clause", ["contract"])   # settles first, then sends
    owner.publish("g")
    assert seq_at_server(world, "g") == owner.groups["g"]["seq"] == 2
    titles = {bob.open_document("g", d, e).title for d, e in bob.search("g", "contract").hits}
    assert titles == {"Contract A", "Contract B"}                  # the message sent before the crash counts once
    assert not owner.has_pending


def test_an_approval_survives_a_crash_and_the_receiver_is_known_afterwards():
    world = World()
    world.owner.create_group("g")
    world.owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    world.owner.publish("g")
    bob = world.new_receiver("receiver-a")
    uid = bob.send_join()
    item = next(i for i in world.owner.pending_joins() if i["uid"] == uid)
    world.owner.cloud = CrashAfter(world.api, "ctl")
    with pytest.raises(Crash):
        world.owner.approve_join(item, ["g"])
    owner = restart(world)
    assert uid not in owner.receivers                              # not committed yet ...
    assert owner.resume_pending() == ["ctl: last message committed"]
    assert uid in owner.receivers                                  # ... now it is, exactly as the server has it
    bob.fetch_mail()
    assert len(bob.search("g", "contract").hits) == 1
    owner.revoke(uid, "R")                                         # and later steps work on the committed state
    with pytest.raises(Rejected):
        bob.search("g", "contract")


def test_a_publish_survives_a_crash():
    world = World()
    world.owner.create_group("g")
    world.owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    world.owner.cloud = CrashAfter(world.api, "state_put")
    with pytest.raises(Crash):
        world.owner.publish("g")
    owner = restart(world)
    version = owner.publish("g")                                   # settles the first, then publishes the next
    stored = world.cloud.db.execute("SELECT ver FROM states WHERE g='g'").fetchone()[0]
    assert version == stored == 3                                  # 1 at creation, 2 settled, 3 now
    assert len(world.join("receiver-a", ["g"]).search("g", "contract").hits) == 1


def test_a_refused_message_leaves_nothing_behind():
    world = World()
    world.owner.create_group("g")
    world.cloud.db.execute("UPDATE groups SET seq = 5 WHERE g='g'")     # the server disagrees: a refusal follows
    world.cloud.db.commit()
    with pytest.raises(Rejected):
        world.owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    assert not world.owner.has_pending and world.owner.groups["g"]["seq"] == 0 and world.owner.groups["g"]["docs"] == {}


def test_no_answer_keeps_the_message_for_later_and_a_revocation_is_not_blocked():
    world = World()
    world.owner.create_group("g")
    world.owner.publish("g")
    bob = world.join("receiver-a", ["g"])

    class Down:
        def call(self, endpoint, obj):
            if endpoint == "update":
                raise CloudUnavailable("the server does not answer")
            return world.api.call(endpoint, obj)

    world.owner.cloud = Down()
    with pytest.raises(CloudUnavailable):
        world.owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    with pytest.raises(CloudUnavailable):
        world.owner.revoke(bob.uid, "R")                           # the deauth goes through; the rotation waits
    with pytest.raises(Rejected) as info:
        bob.search("g", "contract")
    assert info.value.reason == "revoked"
    world.owner.cloud = world.api
    done = world.owner.resume_pending()
    assert "group:g: last message committed" in done and "g: rotation finished" in done
    assert world.owner.groups["g"]["epoch"] == 2 and not world.owner.has_pending
