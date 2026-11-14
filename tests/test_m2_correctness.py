"""Milestone 2: correctness of the ten algorithms against a plaintext reference index."""
from __future__ import annotations

import pytest

from helpers import VOCAB, filled_world, random_update
from pqsse.core.errors import AccessDenied
from pqsse.core.keystore import MemoryVault
from pqsse.owner import Owner
from pqsse.pqbackend import PARAM_SETS
from pqsse.receiver import CHECKS, Receiver
from pqsse.sandbox import World


def test_random_workload_matches_plaintext_reference():
    """Multiple groups, adds, deletes and edits, several receivers, at least 300 queries."""
    groups = ["alpha", "beta", "gamma"]
    world, rng = filled_world(groups, docs_per_group=6, seed=2024)
    members = {"alice": ["alpha", "beta"], "bob": ["beta", "gamma"], "carol": groups}
    receivers = {name: world.join(name, gs) for name, gs in members.items()}
    queries = 0
    for _ in range(12):
        for g in groups:
            for _ in range(3):
                random_update(world, g, rng)
            world.owner.publish(g)
        for name, gs in members.items():
            for g in gs:
                for word in rng.sample(VOCAB, 3) + ["absentword"]:
                    result = receivers[name].search(g, word)
                    assert result.ids == world.owner.plaintext_search(g, word), (name, g, word)
                    assert result.report.all_ok
                    assert [c[0] for c in result.report.checks] == list(CHECKS)
                    queries += 1
    assert queries >= 300


def test_search_then_decrypt_returns_the_documents():
    world, rng = filled_world(["alpha"], docs_per_group=8, seed=5)
    bob = world.join("bob", ["alpha"])
    by_id = {d["id"]: d for d in world.owner.documents("alpha")}
    opened = 0
    for word in VOCAB:
        result = bob.search("alpha", word)
        for doc_id, epoch in result.hits:
            doc = bob.open_document("alpha", doc_id, epoch)
            assert (doc.title, doc.text) == (by_id[doc_id]["title"], by_id[doc_id]["text"])
            assert word in doc.text
            opened += 1
    assert opened > 10


def test_unpublished_updates_are_not_visible_until_publish():
    world, _ = filled_world(["alpha"], docs_per_group=2, seed=6)
    bob = world.join("bob", ["alpha"])
    doc_id = world.owner.add_document("alpha", "late", "zebra crossing")
    assert bob.search("alpha", "zebra").ids == set()
    world.owner.publish("alpha")
    assert bob.search("alpha", "zebra").ids == {doc_id}
    world.owner.delete_document("alpha", doc_id)
    world.owner.publish("alpha")
    assert bob.search("alpha", "zebra").ids == set()


def test_keyword_search_is_case_insensitive_and_edit_changes_id():
    world, _ = filled_world(["alpha"], docs_per_group=1, seed=7)
    bob = world.join("bob", ["alpha"])
    first = world.owner.add_document("alpha", "Report", "Falcon and Sphincs")
    world.owner.publish("alpha")
    assert bob.search("alpha", "FALCON").ids == {first}
    second = world.owner.edit_document("alpha", first, "Report", "Sphincs only")
    world.owner.publish("alpha")
    assert second != first
    assert bob.search("alpha", "falcon").ids == set()
    assert bob.search("alpha", "sphincs").ids == {second}


@pytest.mark.parametrize("p", PARAM_SETS, ids=lambda p: p.label())
def test_every_parameter_set_end_to_end(p):
    world = World(params=p)
    world.owner.create_group("g")
    doc_id = world.owner.add_document("g", "t", "hello post quantum world")
    world.owner.publish("g")
    bob = world.join("bob", ["g"])
    result = bob.search("g", "quantum")
    assert result.ids == {doc_id} and result.report.all_ok
    assert bob.open_document("g", doc_id, 1).text == "hello post quantum world"


def test_owner_and_receiver_state_survive_reload():
    """All role state lives in the vault: a fresh object over the same vault continues."""
    world, _ = filled_world(["alpha"], docs_per_group=3, seed=8)
    bob = world.join("bob", ["alpha"])
    owner2 = Owner(world.owner.vault, cloud=world.api, clock=world.clock)
    doc_id = owner2.add_document("alpha", "after reload", "persistence check")
    owner2.publish("alpha")
    bob2 = Receiver(bob.vault, cloud=world.api, clock=world.clock)
    assert bob2.uid == bob.uid
    assert bob2.search("alpha", "persistence").ids == {doc_id}


def test_receiver_without_capability_cannot_search():
    world, _ = filled_world(["alpha"], docs_per_group=2, seed=9)
    stranger = world.new_receiver("stranger")
    with pytest.raises(AccessDenied):
        stranger.search("alpha", "token")
    assert not MemoryVault().get("receiver")
