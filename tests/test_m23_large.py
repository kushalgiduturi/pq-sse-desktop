"""Design note 005: large collections. A: updates split into batches. B: states fetched only when they changed."""
from __future__ import annotations

import pytest

from pqsse.core import wire
from pqsse.core.errors import VerifyError
from pqsse.owner import DocInput, Owner
from pqsse.owner import owner as owner_module
from pqsse.sandbox import World


class Counting:
    """Counts calls and reply bytes per endpoint; can rewrite a reply."""

    def __init__(self, inner, rewrite=None) -> None:
        self.inner, self.rewrite = inner, rewrite
        self.calls: dict[str, int] = {}
        self.bytes: dict[str, int] = {}

    def call(self, endpoint, obj):
        reply = self.inner.call(endpoint, obj)
        if self.rewrite is not None:
            reply = self.rewrite(endpoint, obj, reply)
        self.calls[endpoint] = self.calls.get(endpoint, 0) + 1
        self.bytes[endpoint] = self.bytes.get(endpoint, 0) + len(wire.enc(reply))
        return reply


def docs(n: int, word: str = "contract") -> list[DocInput]:
    return [DocInput(f"doc {i}", f"text {i}", [word, f"only{i}"]) for i in range(n)]


# ------------------------------------------------------------------ A: batches
def test_a_large_build_is_split_and_invisible_until_published(monkeypatch):
    monkeypatch.setattr(owner_module, "BATCH_DOCS", 3)
    world = World()
    world.owner.create_group("g")
    world.owner.publish("g")
    bob = world.join("receiver-a", ["g"])
    ids = world.owner.build_index("g", docs(10))
    assert len(ids) == 10 and world.owner.groups["g"]["seq"] == 4                   # 3 + 3 + 3 + 1
    assert world.cloud.db.execute("SELECT seq FROM groups WHERE g='g'").fetchone()[0] == 4
    assert bob.search("g", "contract").hits == []                                    # not published yet
    world.owner.publish("g")
    assert len(bob.search("g", "contract").hits) == 10


def test_batches_also_split_by_size(monkeypatch):
    monkeypatch.setattr(owner_module, "BATCH_BYTES", 35_000)        # each estimate: 10 KB text + 5 KB overhead
    chunks = owner_module._chunks([DocInput("t", "x" * 10_000, ["w"]) for _ in range(5)])
    assert [len(c) for c in chunks] == [2, 2, 1]
    assert [len(c) for c in owner_module._chunks([DocInput("t", "x" * 100_000, ["w"])])] == [1]   # never empty


def test_a_split_re_rebuild_interrupted_half_way_finishes_without_losing_a_document(monkeypatch):
    monkeypatch.setattr(owner_module, "BATCH_DOCS", 3)
    world = World()
    world.owner.create_group("g")
    world.owner.build_index("g", docs(8))
    world.owner.publish("g")
    leaving = world.join("receiver-a", ["g"])
    staying = world.join("receiver-b", ["g"])

    class DiesOnSecondRebuildBatch:
        def __init__(self) -> None:
            self.updates = 0

        def call(self, endpoint, obj):
            if endpoint == "update":
                self.updates += 1
                if self.updates == 2:
                    raise RuntimeError("the owner's computer lost power")
            return world.api.call(endpoint, obj)

    world.owner.cloud = DiesOnSecondRebuildBatch()
    with pytest.raises(RuntimeError):
        world.owner.revoke(leaving.uid, "RE")
    rest = world.owner.groups["g"]["rebuild_rest"]
    assert len(rest) == 5 and len(world.owner.groups["g"]["docs"]) == 3              # 3 rebuilt, 5 remembered
    owner = Owner(world.owner.vault, cloud=world.api, clock=world.clock)              # the app starts again
    assert owner.has_pending
    owner.resume_pending()
    assert not owner.has_pending and len(owner.groups["g"]["docs"]) == 8
    staying.fetch_mail()
    result = staying.search("g", "contract")
    assert result.report.all_ok and len(result.hits) == 8


# ------------------------------------------------------------------ B: unchanged states are not sent again
def big_world(n: int = 400) -> tuple[World, object, Counting]:
    world = World()
    world.owner.create_group("g")
    world.owner.build_index("g", docs(n))
    world.owner.publish("g")
    bob = world.join("receiver-a", ["g"])
    counting = Counting(world.api)
    bob.cloud = counting
    return world, bob, counting


def test_a_second_search_does_not_download_the_state_again():
    world, bob, counting = big_world()
    bob.search("g", "only1")
    first = counting.bytes["states_get"]
    bob.search("g", "only2")
    second = counting.bytes["states_get"] - first
    assert first > 20_000 and second < 200, (first, second)
    world.owner.add_document("g", "new", "new", ["only2"])
    world.owner.publish("g")
    result = bob.search("g", "only2")                                                 # changed: fetched again
    assert counting.bytes["states_get"] - first - second > 20_000 and len(result.hits) == 2


def test_an_expired_cached_state_is_refused_like_an_old_one():
    world, bob, counting = big_world(5)
    bob.search("g", "contract")
    world.clock.advance(world.owner.state_ttl + 60)
    with pytest.raises(VerifyError) as info:
        bob.search("g", "contract")
    assert info.value.check == "freshness"


def test_a_server_that_falsely_says_unchanged_is_the_same_as_one_that_serves_the_old_state():
    world, bob, counting = big_world(5)
    bob.search("g", "contract")
    world.owner.add_document("g", "newer", "newer", ["contract"])
    world.owner.publish("g")

    def lie(endpoint, obj, reply):
        if endpoint == "states_get":
            return {**reply, "states": [{"e": 1, "same": True}]}
        return reply

    bob.cloud = Counting(world.api, rewrite=lie)
    result = bob.search("g", "contract")                  # the old state: within its window, so accepted ...
    assert len(result.hits) == 5 and result.report.all_ok  # ... and it hides the new document, nothing more
    bob._state_cache.clear()
    with pytest.raises(VerifyError):
        bob.search("g", "contract")                       # "unchanged" for a state never received: refused


def test_clients_that_do_not_send_have_get_full_states():
    world, bob, counting = big_world(5)
    reply = world.cloud.read_states("g", 1, 1)
    assert "hdr" in reply["states"][0]
    assert world.cloud.read_states("g", 1, 1, {1: 999})["states"][0].get("same") is None
