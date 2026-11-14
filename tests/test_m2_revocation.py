"""Milestone 2: Revoke with policy R (rotate) and policy RE (rotate and re-encrypt)."""
from __future__ import annotations

import pytest

from helpers import VOCAB, filled_world, random_doc, random_update
from pqsse.attacks import Recorder
from pqsse.core import index
from pqsse.core.errors import AccessDenied, PQSSEError, Rejected, VerifyError
from pqsse.core.index import doc_aad
from pqsse.core.prims import aead_decrypt, group_subkeys
from pqsse.gpu import CpuPRF


def _setup(seed: int):
    world, rng = filled_world(["alpha", "beta"], docs_per_group=8, seed=seed)
    recorder = Recorder(world.api)
    alice = world.join("alice", ["alpha"], api=recorder)
    bob = world.join("bob", ["alpha", "beta"])
    carol = world.join("carol", ["alpha"])
    hits = alice.search("alpha", "token").hits or alice.search("alpha", "cloud").hits
    alice.open_document("alpha", *hits[0])
    return world, rng, recorder, alice, bob, carol


def _check_all(world, receiver, group):
    for word in VOCAB:
        result = receiver.search(group, word)
        assert result.ids == world.owner.plaintext_search(group, word), word
        assert result.report.all_ok
    return True


def _can_decrypt_anything(world, group: str, keys: dict[str, bytes], max_id: int) -> int:
    """Colluding cloud: try every stored document with every key the user holds."""
    opened = 0
    rows = world.cloud.db.execute("SELECT e, blob FROM docs WHERE g=?", (group,)).fetchall()
    for epoch, blob in rows:
        for held_epoch, key in keys.items():
            for use_epoch in {epoch, int(held_epoch)}:
                k_doc = group_subkeys(key, group, use_epoch)[1]
                for doc_id in range(1, max_id + 1):
                    try:
                        aead_decrypt(k_doc, blob, doc_aad(group, epoch, doc_id))
                        opened += 1
                    except VerifyError:
                        pass
    return opened


def test_revoke_policy_r():
    world, rng, recorder, alice, bob, carol = _setup(71)
    old_token, _ = recorder.last("search")
    old_fetch, _ = recorder.last("doc_get")
    old_keys = dict(alice._me["cap"]["groups"]["alpha"]["keys"])
    entries_e1 = world.cloud.db.execute("SELECT COUNT(*) FROM entries WHERE g='alpha' AND e=1").fetchone()[0]

    assert world.owner.revoke(alice.uid, "R") == ["alpha"]

    # old token and fetch are rejected, and so is every new request
    for endpoint, msg in (("search", old_token), ("doc_get", old_fetch)):
        with pytest.raises(Rejected) as err:
            world.api.call(endpoint, msg)
        assert err.value.reason == "revoked"
    with pytest.raises(Rejected) as err:
        alice.search("alpha", "token")
    assert err.value.reason == "revoked"
    with pytest.raises(Rejected):
        alice.open_document("alpha", 1, 1)
    assert alice.fetch_mail() == []
    assert set(alice._me["cap"]["groups"]["alpha"]["keys"]) == {"1"}     # no key for epoch 2
    with pytest.raises(PQSSEError):
        world.owner.revoke(alice.uid, "R")

    # old segments stay, the group is at epoch 2, beta is untouched
    overview = world.owner.overview("alpha")
    assert (overview["epoch"], overview["base"]) == (2, 1)
    assert world.owner.overview("beta")["epoch"] == 1
    assert world.cloud.db.execute("SELECT COUNT(*) FROM entries WHERE g='alpha' AND e=1").fetchone()[0] == entries_e1

    # remaining users are still correct across segments, including new adds and deletes
    for _ in range(10):
        random_update(world, "alpha", rng)
    world.owner.publish("alpha")
    for receiver in (bob, carol):
        assert _check_all(world, receiver, "alpha")
    assert _check_all(world, bob, "beta")
    assert set(bob._me["cap"]["groups"]["alpha"]["keys"]) == {"1", "2"}
    epochs_hit = set()
    for word in VOCAB:
        for doc_id, epoch in bob.search("alpha", word).hits:
            epochs_hit.add(epoch)
            assert bob.open_document("alpha", doc_id, epoch).title
    assert epochs_hit == {1, 2}

    # the revoked user cannot derive addresses for new entries
    new_entries = {row[0] for row in world.cloud.db.execute("SELECT addr FROM entries WHERE g='alpha' AND e=2")}
    assert len(new_entries) > 10
    words = sorted({w for d in world.owner._group("alpha")["docs"].values() for w in d["kws"]} | set(VOCAB))
    items = [(w, i) for w in words for i in range(40)]
    guesses = set()
    for epoch in (1, 2):
        k_idx = group_subkeys(old_keys["1"], "alpha", epoch)[0]
        addrs, _ = index.derive(CpuPRF(), k_idx, items)
        guesses |= {addrs[i].tobytes() for i in range(len(items))}
    assert guesses.isdisjoint(new_entries)

    # documented limit of policy R: with a colluding cloud, pre-revocation data stays readable
    max_id = world.owner._group("alpha")["next_id"]
    assert _can_decrypt_anything(world, "alpha", old_keys, max_id) > 0
    # but nothing written after the revocation is
    new_only = world.cloud.db.execute("SELECT COUNT(*) FROM docs WHERE g='alpha' AND e=2").fetchone()[0]
    assert new_only > 0
    rows = world.cloud.db.execute("SELECT blob FROM docs WHERE g='alpha' AND e=2").fetchall()
    for (blob,) in rows:
        for doc_id in range(1, max_id + 1):
            for use_epoch in (1, 2):
                with pytest.raises(VerifyError):
                    aead_decrypt(group_subkeys(old_keys["1"], "alpha", use_epoch)[1], blob, doc_aad("alpha", 2, doc_id))


def test_revoke_policy_re():
    world, rng, recorder, alice, bob, carol = _setup(72)
    old_token, _ = recorder.last("search")
    old_fetch, _ = recorder.last("doc_get")
    old_keys = dict(alice._me["cap"]["groups"]["alpha"]["keys"])
    live_before = {d["id"]: d["text"] for d in world.owner.documents("alpha")}

    world.owner.revoke(alice.uid, "RE")

    for endpoint, msg in (("search", old_token), ("doc_get", old_fetch)):
        with pytest.raises(Rejected) as err:
            world.api.call(endpoint, msg)
        assert err.value.reason == "revoked"

    # old segments and documents are dropped at the cloud
    db = world.cloud.db
    assert db.execute("SELECT COUNT(*) FROM entries WHERE g='alpha' AND e<2").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM docs WHERE g='alpha' AND e<2").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM states WHERE g='alpha' AND e<2").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM docs WHERE g='alpha' AND e=2").fetchone()[0] == len(live_before)
    assert db.execute("SELECT cur, base FROM groups WHERE g='alpha'").fetchone() == (2, 2)
    overview = world.owner.overview("alpha")
    assert (overview["epoch"], overview["base"]) == (2, 2)

    # the revoked user cannot decrypt any stored document, even with the whole cloud database
    max_id = world.owner._group("alpha")["next_id"]
    assert _can_decrypt_anything(world, "alpha", old_keys, max_id) == 0

    # remaining users are correct, on the re-encrypted data and after further updates
    assert _check_all(world, bob, "alpha")
    assert set(bob._me["cap"]["groups"]["alpha"]["keys"]) == {"2"}
    for word in VOCAB[:6]:
        for doc_id, epoch in carol.search("alpha", word).hits:
            assert epoch == 2
            assert carol.open_document("alpha", doc_id, epoch).text == live_before[doc_id]
    for _ in range(8):
        random_update(world, "alpha", rng)
    world.owner.publish("alpha")
    assert _check_all(world, bob, "alpha") and _check_all(world, carol, "alpha")
    assert _check_all(world, bob, "beta")
    with pytest.raises(Rejected) as err:
        world.api.call("search", old_token)
    assert err.value.reason == "revoked"


def test_r_then_re_then_new_member():
    """Mixed history: R, more data, RE, then a new receiver joins and sees everything live."""
    world, rng, recorder, alice, bob, carol = _setup(73)
    world.owner.revoke(alice.uid, "R")
    for _ in range(5):
        random_update(world, "alpha", rng)
    world.owner.publish("alpha")
    assert _check_all(world, bob, "alpha")
    world.owner.revoke(carol.uid, "RE")
    assert world.owner.overview("alpha")["base"] == 3
    assert _check_all(world, bob, "alpha")
    dave = world.join("dave", ["alpha"])
    assert set(dave._me["cap"]["groups"]["alpha"]["keys"]) == {"3"}
    doc = random_doc(rng)
    world.owner.add_document("alpha", doc.title, doc.text)
    world.owner.publish("alpha")
    assert _check_all(world, dave, "alpha") and _check_all(world, bob, "alpha")
    for gone in (alice, carol):
        with pytest.raises(Rejected):
            gone.search("alpha", "token")


def test_rekey_box_is_bound_to_the_pre_shared_key():
    """A rekey box needs both the ML-KEM key and m_v, and must be owner signed."""
    world, rng, recorder, alice, bob, carol = _setup(74)
    world.owner.revoke(alice.uid, "R")
    mail = [m for m in world.api.call("mail_get", {"uid": bob.uid}) if m["kind"] == "rekey"]
    assert len(mail) == 1
    good_m = bob._me["cap"]["m"]
    bob._me["cap"]["m"] = bytes(32)
    with pytest.raises(VerifyError):
        bob._accept_rekey(mail[0]["body"], mail[0]["sig"])
    bob._me["cap"]["m"] = good_m
    with pytest.raises(VerifyError):
        carol._accept_rekey(mail[0]["body"], mail[0]["sig"])     # box for another receiver
    with pytest.raises(VerifyError):
        bob._accept_rekey(mail[0]["body"], mail[0]["sig"][::-1])
    assert "epoch 2" in bob._accept_rekey(mail[0]["body"], mail[0]["sig"])
    assert _check_all(world, bob, "alpha")
    with pytest.raises(AccessDenied):
        alice.open_document("alpha", 1, 2)
