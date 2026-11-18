"""Milestone 2: a malicious cloud that tampers with results is always detected."""
from __future__ import annotations

import random

import pytest

from helpers import filled_world
from pqsse.attacks import SEARCH_MODES, Recorder, TamperCloud
from pqsse.core.errors import VerifyError
from pqsse.transport import InProcessCloud

SMALL_VOCAB = ["lattice", "kyber", "token", "cloud", "epoch", "chain", "state", "nonce"]
TRIALS = 100


@pytest.fixture(scope="module")
def setup():
    world, rng = filled_world(["alpha"], docs_per_group=24, seed=11, vocab=SMALL_VOCAB)
    for doc in world.owner.documents("alpha")[:4]:
        world.owner.delete_document("alpha", doc["id"])
    world.owner.publish("alpha")
    tamper = TamperCloud(world.cloud, seed=3)
    bob = world.join("receiver-a", ["alpha"], api=tamper)
    return world, tamper, bob


@pytest.mark.parametrize("mode", SEARCH_MODES)
def test_search_tampering_is_detected(setup, mode):
    """drop, modify, reorder, truncate, substitute: 100 trials each, re-signed by the cloud."""
    world, tamper, bob = setup
    rng = random.Random(sum(mode.encode()))
    tamper.resign = True
    detected = 0
    attempts = 0
    while detected < TRIALS:
        attempts += 1
        assert attempts < TRIALS * 5
        word = rng.choice(SMALL_VOCAB)
        tamper.mode = mode
        try:
            bob.search("alpha", word)
        except VerifyError as exc:
            assert tamper.applied
            assert exc.check in ("completeness", "hash chain"), exc
            assert not exc.report.all_ok
            detected += 1
        else:
            assert not tamper.applied, f"undetected {mode}: {tamper.note}"
    tamper.mode = None
    for word in SMALL_VOCAB:
        assert bob.search("alpha", word).ids == world.owner.plaintext_search("alpha", word)


def test_unsigned_and_badly_signed_responses_are_rejected(setup):
    _, tamper, bob = setup
    for mode in ("unsigned", "badsig"):
        tamper.mode = mode
        with pytest.raises(VerifyError) as err:
            bob.search("alpha", "kyber")
        assert err.value.check == "response signature"
    tamper.mode, tamper.resign = "modify", False   # tampered but the old signature kept
    with pytest.raises(VerifyError) as err:
        bob.search("alpha", "kyber")
    assert err.value.check == "response signature"
    tamper.mode, tamper.resign = None, True


def test_response_for_another_token_is_rejected(setup):
    """The cloud signature binds the response to this token: a replayed response fails."""
    world, tamper, bob = setup
    tamper.mode = None
    recorder = Recorder(InProcessCloud(world.cloud))
    bob.cloud = recorder
    bob.search("alpha", "kyber")
    _, old_reply = recorder.last("search")

    class Replay:
        def call(self, endpoint, obj):
            reply = recorder.inner.call(endpoint, obj)
            return old_reply if endpoint == "search" else reply

    bob.cloud = Replay()
    with pytest.raises(VerifyError) as err:
        bob.search("alpha", "kyber")
    assert err.value.check == "response signature"
    bob.cloud = tamper


def test_modified_documents_are_rejected(setup):
    world, tamper, bob = setup
    tamper.mode = None
    hits = bob.search("alpha", "kyber").hits
    rng = random.Random(4)
    for _ in range(TRIALS):
        doc_id, epoch = rng.choice(hits)
        tamper.mode = "doc_modify"
        with pytest.raises(VerifyError) as err:
            bob.open_document("alpha", doc_id, epoch)
        assert err.value.check == "document signature"
    tamper.mode = None
    assert bob.open_document("alpha", *hits[0]).text


def test_swapped_documents_are_rejected(setup):
    """Substitute a document: the cloud answers with a different genuine, owner signed document."""
    world, tamper, bob = setup
    tamper.mode = None
    docs = [(d["id"], d["epoch"]) for d in world.owner.documents("alpha")]
    recorder = Recorder(InProcessCloud(world.cloud))
    tamper.inner = recorder
    replies = {}
    for doc_id, epoch in docs:
        bob.open_document("alpha", doc_id, epoch)
        replies[doc_id] = recorder.last("doc_get")[1]
    rng = random.Random(5)
    for _ in range(TRIALS):
        (want, epoch), (other, _) = rng.sample(docs, 2)
        tamper.mode, tamper.doc_override = "doc_swap", replies[other]
        with pytest.raises(VerifyError) as err:
            bob.open_document("alpha", want, epoch)
        assert err.value.check == "document signature"
    tamper.mode, tamper.doc_override = None, None
    tamper.inner = InProcessCloud(world.cloud)
