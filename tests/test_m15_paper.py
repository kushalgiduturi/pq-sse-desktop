"""Milestone 1 of REALLIFE_PLAN.md: properties the paper states, tested against the code.

docs/PAPER_CONFORMANCE.md maps every paper item to code and tests. Tests marked xfail record a
known deviation from the paper that is waiting for a decision (P-numbers in that file); they are
strict, so they fail loudly the day the deviation is fixed and the mark must come off.
"""
from __future__ import annotations

import random
from typing import Any

import pytest

from pqsse.core import index, wire
from pqsse.owner import DocInput
from pqsse.sandbox import World
from pqsse.transport import InProcessCloud


class Tap:
    """The view of the cloud server and of a network observer: every message in and out, as bytes."""

    def __init__(self, core: Any) -> None:
        self.core = core
        self.log: list[tuple[str, bytes, bytes]] = []

    def call(self, endpoint: str, obj: Any) -> Any:
        body = wire.enc(obj)
        reply = self.core.handle(endpoint, body)
        self.log.append((endpoint, body, reply))
        return wire.dec(reply)

    def sent(self, endpoint: str) -> list[bytes]:
        return [body for ep, body, _ in self.log if ep == endpoint]

    def replies(self, endpoint: str) -> list[bytes]:
        return [reply for ep, _, reply in self.log if ep == endpoint]


def tapped_world(**kwargs) -> tuple[World, Tap]:
    world = World(**kwargs)
    tap = Tap(world.cloud)
    world.api = tap
    world.owner.cloud = tap
    return world, tap


def doc(title: str, words: list[str]) -> DocInput:
    return DocInput(title, " ".join(words), words)


# ------------------------------------------------------------------ leakage profile (Section II-F)
def test_update_leakage_is_group_entry_count_and_document_handles_only():
    """L_Upd: per batch the server learns the group, the number of entries and which documents were added
    or deleted (here as handles, not ids); entries reveal neither keyword nor operation."""
    world, tap = tapped_world()
    world.owner.create_group("g")
    world.owner.build_index("g", [doc("a", ["alpha", "beta"]), doc("b", ["alpha", "gamma"])])
    batch = wire.dec(wire.dec(tap.sent("update")[-1])["msg"])
    assert set(batch) == {"g", "e", "seq", "addrs", "vals", "docs", "del", "reset"}
    assert len(batch["addrs"]) // index.ADDR_LEN == 4                    # 2 + 2 keyword occurrences
    raw = tap.sent("update")[-1]
    for secret in (b"alpha", b"beta", b"gamma"):
        assert secret not in raw                                         # no keyword in the batch
    handles = [h for h, _, _ in batch["docs"]]
    assert all(len(h) == 16 for h in handles) and len(set(handles)) == 2


def test_search_leakage_is_search_pattern_and_update_history_of_the_keyword():
    """L_Srch(g, w) = (g, sp_g(w), Updates_g(w)): the addresses a search asks for are exactly the entries
    ever written for w in the live segments, and a repeated search asks for the same addresses."""
    world, tap = tapped_world()
    world.owner.create_group("g")
    world.owner.build_index("g", [doc("a", ["alpha", "beta"]), doc("b", ["beta"])])
    world.owner.add_document("g", "c", "alpha", ["alpha"])
    world.owner.publish("g")
    bob = world.join("receiver-a", ["g"], api=tap)
    stored = {row[0] for row in world.cloud.db.execute("SELECT addr FROM entries WHERE g='g'")}
    world.cloud.trace_tokens = []
    bob.search("g", "alpha")
    first = list(world.cloud.trace_tokens)
    world.cloud.trace_tokens = []
    bob.search("g", "alpha")
    assert first == world.cloud.trace_tokens                             # search pattern: same addresses again
    assert len(first) == 2 and set(first) <= stored                      # Updates_g(alpha): the two alpha entries
    world.cloud.trace_tokens = []
    bob.search("g", "beta")
    assert len(world.cloud.trace_tokens) == 2 and not set(world.cloud.trace_tokens) & set(first)


def test_type_ii_backward_privacy_add_and_delete_entries_look_alike():
    """Definition 7 needs the stored value to hide the operation: (op || id) XOR mask. Over many entries the
    first byte (the masked op) of additions and deletions must not reveal which is which."""
    world, _ = tapped_world()
    world.owner.create_group("g")
    rng = random.Random(5)
    ids = world.owner.build_index("g", [doc(f"d{i}", [f"w{rng.randrange(40)}" for _ in range(6)]) for i in range(60)])
    for doc_id in ids[:30]:
        world.owner.delete_document("g", doc_id)
    first_bytes = [row[0][0] for row in world.cloud.db.execute("SELECT val FROM entries WHERE g='g'")]
    assert len(first_bytes) > 300
    # unmasked, every first byte would be 1 (add) or 2 (delete)
    assert sum(b in (index.OP_ADD, index.OP_DEL) for b in first_bytes) < len(first_bytes) * 0.05
    assert len(set(first_bytes)) > 100


def test_receivers_search_results_survive_add_delete_add_across_epochs():
    """Correctness (Theorem 1) across segments: an id added, deleted and added again, with a revocation
    (policy R) in between, is decoded by processing segments in increasing epoch order."""
    world, _ = tapped_world()
    world.owner.create_group("g")
    [doc_id] = world.owner.build_index("g", [doc("a", ["alpha"])])
    world.owner.publish("g")
    bob, carol = world.join("receiver-a", ["g"]), world.join("receiver-b", ["g"])
    world.owner.delete_document("g", doc_id)
    world.owner.revoke(carol.uid, "R")
    world.owner.add_document("g", "a2", "alpha", ["alpha"])
    world.owner.publish("g")
    bob.fetch_mail()
    result = bob.search("g", "alpha")
    assert {i for i, _ in result.hits} == world.owner.plaintext_search("g", "alpha") and len(result.hits) == 1


# ------------------------------------------------------------------ decided deviations (design note 001, P-03)
def test_search_response_hides_the_searched_addresses_from_the_network():
    """P-01, fixed: the response is encrypted under the receiver's credential (paper Algorithm 7, step 5)."""
    world, tap = tapped_world()
    world.owner.create_group("g")
    world.owner.build_index("g", [doc("a", ["alpha"])])
    world.owner.publish("g")
    bob = world.join("receiver-a", ["g"], api=tap)
    world.cloud.trace_tokens = []
    bob.search("g", "alpha")
    [address] = world.cloud.trace_tokens
    assert address not in tap.replies("search")[-1]


def test_control_messages_are_confidential_on_the_network():
    """P-02, fixed: control messages are sealed to the cloud's ML-KEM key (paper Section II-A, Ctl)."""
    world, tap = tapped_world()
    world.owner.create_group("quarterly-reports")
    assert b"quarterly-reports" not in tap.sent("ctl")[-1]
    bob = world.join("receiver-a", ["quarterly-reports"])
    world.owner.revoke(bob.uid, "R")
    assert all(bob.uid.encode() not in body for body in tap.sent("ctl"))


def test_revoked_credential_is_erased_at_the_server():
    """P-06, fixed: Revoke deletes a_u at the server and keeps only a revoked marker."""
    world, _ = tapped_world()
    world.owner.create_group("g")
    world.owner.publish("g")
    bob = world.join("receiver-a", ["g"])
    world.owner.revoke(bob.uid, "R")
    enc_a, revoked = world.cloud.db.execute("SELECT enc_a, revoked FROM creds WHERE uid=?", (bob.uid,)).fetchone()
    assert revoked == 1 and enc_a == b""
    from pqsse.core.errors import Rejected
    with pytest.raises(Rejected) as info:
        bob.search("g", "alpha")
    assert info.value.reason == "revoked"


def test_state_size_is_fixed_up_to_the_capacity_and_doubles_beyond_it():
    """P-03, accepted: the padded state hides the keyword count up to N_max (4096 records by default); a group
    that outgrows it gets a doubled capacity, so the server learns the power-of-two range. Stated in the docs."""
    from pqsse.core.state import DEFAULT_NMAX, RECORD_LEN
    world, tap = tapped_world()
    world.owner.create_group("g")
    empty = len(wire.dec(tap.sent("state_put")[-1])["ct"])
    world.owner.build_index("g", [doc(f"d{i}", [f"word{i}x{j}" for j in range(30)]) for i in range(50)])
    world.owner.publish("g")
    assert len(wire.dec(tap.sent("state_put")[-1])["ct"]) == empty            # 1500 keywords: same size
    world.owner.build_index("g", [doc(f"e{i}", [f"more{i}x{j}" for j in range(30)]) for i in range(100)])
    world.owner.publish("g")
    assert len(wire.dec(tap.sent("state_put")[-1])["ct"]) == empty + DEFAULT_NMAX * RECORD_LEN   # 4500: doubled
