"""Milestone 2: update authenticity, state checks, join, scope and forward privacy."""
from __future__ import annotations

import os

import pytest

from helpers import VOCAB, filled_world, random_doc
from pqsse import pqbackend
from pqsse.attacks import HoldBack, Recorder, TamperCloud
from pqsse.core import seal, signing, wire
from pqsse.core.errors import AccessDenied, Rejected, VerifyError
from pqsse.core.index import doc_aad, doc_handle, token_aad, token_key
from pqsse.core.prims import aead_decrypt, aead_encrypt, group_subkeys
from pqsse.core.state import StateHeader, make_state
from pqsse.transport import InProcessCloud


# ---------------------------------------------------------------- update authenticity
def test_forged_modified_replayed_and_out_of_order_updates_are_rejected():
    world, rng = filled_world(["alpha"], docs_per_group=3, seed=21)
    recorder = Recorder(world.api)
    world.owner.cloud = recorder
    world.owner.add_document("alpha", "genuine", "genuine update text")
    genuine, _ = recorder.last("update")
    entries_before = world.cloud.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]

    # replayed: the same signed batch again
    with pytest.raises(Rejected) as err:
        world.api.call("update", genuine)
    assert err.value.reason == "bad_sequence"

    # modified: one byte changed, signature kept
    raw = bytearray(genuine["msg"])
    raw[len(raw) // 2] ^= 1
    with pytest.raises(Rejected) as err:
        world.api.call("update", {"msg": bytes(raw), "sig": genuine["sig"]})
    assert err.value.reason == "bad_signature"

    # forged: a well formed next batch signed by somebody else's ML-DSA key
    batch = wire.dec(genuine["msg"])
    batch["seq"] += 1
    batch["addrs"], batch["vals"], batch["docs"], batch["del"] = os.urandom(32), os.urandom(5), [], []
    forged = wire.enc(batch)
    _, attacker_sk = pqbackend.sig_keygen(world.params.sig)
    with pytest.raises(Rejected) as err:
        world.api.call("update", {"msg": forged, "sig": signing.sign_bytes(world.params, attacker_sk, "batch", forged)})
    assert err.value.reason == "bad_signature"

    # a signature of the right key over another message type does not work either
    with pytest.raises(Rejected):
        world.api.call("update", {"msg": genuine["msg"], "sig": genuine["sig"][::-1]})

    # out of order: batch n+2 arrives before n+1
    hold = HoldBack(world.api, "update")
    world.owner.cloud = hold
    world.owner.add_document("alpha", "held", "first held batch")       # n+1, kept back
    hold.active = False
    rec2 = Recorder(world.api)
    world.owner.cloud = rec2

    class Capture:
        def __init__(self):
            self.msg = None

        def call(self, endpoint, obj):
            if endpoint == "update":
                self.msg = obj
            return world.api.call(endpoint, obj)

    capture = Capture()
    world.owner.cloud = capture
    with pytest.raises(Rejected) as err:
        world.owner.add_document("alpha", "early", "second batch arrives early")   # n+2
    assert err.value.reason == "bad_sequence"
    assert world.cloud.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == entries_before
    # delivered in order, both are accepted
    assert world.api.call("update", hold.held[0])["ok"]
    assert world.api.call("update", capture.msg)["ok"]


def test_update_for_wrong_epoch_or_unknown_group_is_rejected():
    world, _ = filled_world(["alpha"], docs_per_group=1, seed=22)
    recorder = Recorder(world.api)
    world.owner.cloud = recorder
    world.owner.add_document("alpha", "x", "some words here")
    genuine, _ = recorder.last("update")
    batch = wire.dec(genuine["msg"])
    for change in ({"e": 5}, {"g": "nope"}):
        bad = wire.enc({**batch, "seq": batch["seq"] + 1, **change})
        sig = signing.sign_bytes(world.params, world.owner._sk, "batch", bad)
        with pytest.raises(Rejected):
            world.api.call("update", {"msg": bad, "sig": sig})


# ---------------------------------------------------------------- states
def _bob_behind_tamper(seed: int):
    world, rng = filled_world(["alpha"], docs_per_group=4, seed=seed)
    tamper = TamperCloud(world.cloud, seed=seed)
    recorder = Recorder(InProcessCloud(world.cloud))
    tamper.inner = recorder
    bob = world.join("receiver-a", ["alpha"], api=tamper)
    return world, rng, tamper, recorder, bob


def test_receiver_forged_state_is_rejected():
    """A group member knows K_st but cannot make a state the others accept."""
    world, rng, tamper, recorder, bob = _bob_behind_tamper(31)
    mallory = world.join("mallory", ["alpha"])
    bob.search("alpha", "token")
    _, genuine = recorder.last("states_get")
    hdr = StateHeader.decode(genuine["states"][-1]["hdr"])
    key = mallory._me["cap"]["groups"]["alpha"]["keys"]["1"]
    k_st = group_subkeys(key, "alpha", 1)[2]
    fake_header = StateHeader("alpha", 1, hdr.ver + 1, hdr.exp, False, 1)
    forged = make_state(world.params, mallory._sk, k_st, fake_header, {}, 1024)
    tamper.mode, tamper.states_override = "states", {"cur": 1, "base": 1, "states": [forged]}
    with pytest.raises(VerifyError) as err:
        bob.search("alpha", "token")
    assert err.value.check == "state signature"
    # an owner signed state with its ciphertext replaced is rejected too
    mixed = dict(genuine["states"][-1], ct=forged["ct"])
    tamper.states_override = {"cur": 1, "base": 1, "states": [mixed]}
    with pytest.raises(VerifyError) as err:
        bob.search("alpha", "token")
    assert err.value.check == "state signature"


def test_state_rollback_is_rejected():
    world, rng, tamper, recorder, bob = _bob_behind_tamper(32)
    bob.search("alpha", "token")
    _, old_states = recorder.last("states_get")
    doc_id = world.owner.add_document("alpha", "new", "freshly added unicorn")
    world.owner.publish("alpha")
    assert bob.search("alpha", "unicorn").ids == {doc_id}
    tamper.mode, tamper.states_override = "states", old_states
    with pytest.raises(VerifyError) as err:
        bob.search("alpha", "unicorn")
    assert err.value.check == "no rollback"
    tamper.mode = None
    assert bob.search("alpha", "unicorn").ids == {doc_id}


def test_expired_state_is_rejected():
    world, rng, tamper, recorder, bob = _bob_behind_tamper(33)
    result = bob.search("alpha", "token")
    assert result.report.fresh_until > world.clock()
    world.clock.advance(world.owner.state_ttl + 5)
    with pytest.raises(VerifyError) as err:
        bob.search("alpha", "token")
    assert err.value.check == "freshness"
    world.owner.publish("alpha")          # the owner refreshes the state
    assert bob.search("alpha", "token").report.all_ok


def test_hiding_a_new_epoch_is_detected():
    """After a revocation the cloud cannot keep serving the closed epoch as current."""
    world, rng, tamper, recorder, bob = _bob_behind_tamper(34)
    carol = world.join("receiver-b", ["alpha"])
    bob.search("alpha", "token")
    world.owner.revoke(carol.uid, "R")
    final_only = world.cloud.read_states("alpha", 1, 1)
    tamper.mode, tamper.states_override = "states", final_only
    with pytest.raises(VerifyError) as err:
        bob.search("alpha", "token")
    assert err.value.check == "freshness"       # newest presented state is final
    tamper.mode = None
    assert bob.search("alpha", "token").report.all_ok
    tamper.mode = "states"
    with pytest.raises(VerifyError) as err:
        bob.search("alpha", "token")
    assert err.value.check in ("no rollback", "freshness")
    # a missing middle segment is detected as well
    world.owner.revoke(world.join("dave", ["alpha"]).uid, "R")
    tamper.mode = None
    bob.search("alpha", "token")
    full = world.cloud.read_states("alpha", 3, 1)
    tamper.mode, tamper.states_override = "states", {**full, "states": [full["states"][0], full["states"][2]]}
    with pytest.raises(VerifyError) as err:
        bob.search("alpha", "token")
    assert err.value.check == "segments complete"


# ---------------------------------------------------------------- join
def test_join_with_wrong_proof_of_ownership_is_rejected():
    world, _ = filled_world(["alpha"], docs_per_group=1, seed=41)
    eve = world.new_receiver("eve")
    victim = world.new_receiver("victim")
    good = eve.join_request()
    assert world.owner.check_join(good).name == "eve"

    # eve claims the victim's keys but can only sign with her own
    stolen = wire.dec(good["req"])
    stolen["ek"], stolen["vk"] = victim.ek, victim.vk
    req = wire.enc(stolen)
    with pytest.raises(VerifyError) as err:
        world.owner.check_join({"req": req, "sig": signing.sign_bytes(world.params, eve._sk, "join", req)})
    assert err.value.check == "join proof"
    # a modified request keeps no valid proof
    changed = wire.dec(good["req"])
    changed["name"] = "admin"
    with pytest.raises(VerifyError):
        world.owner.check_join({"req": wire.enc(changed), "sig": good["sig"]})
    with pytest.raises(VerifyError):
        world.owner.approve_join({"req": good["req"], "sig": os.urandom(len(good["sig"]))}, ["alpha"])
    # a stale request and a reused nonce are rejected
    world.owner.approve_join(good, ["alpha"])
    with pytest.raises(VerifyError):
        world.owner.approve_join(good, ["alpha"])
    late = victim.join_request()
    world.clock.advance(3600)
    with pytest.raises(VerifyError):
        world.owner.check_join(late)


def test_unapproved_key_is_rejected():
    world, _ = filled_world(["alpha"], docs_per_group=2, seed=42)
    bob = world.join("receiver-a", ["alpha"])
    eve = world.new_receiver("eve")
    eve.send_join()                      # requested, never approved
    assert eve.fetch_mail() == [] and not eve.joined
    with pytest.raises(AccessDenied):
        eve.search("alpha", "token")
    # eve writes herself a capability: not owner signed, so her own client refuses it
    cap = wire.enc({"uid": eve.uid, "a": os.urandom(32), "m": os.urandom(32),
                    "groups": {"alpha": {"base": 1, "keys": {"1": os.urandom(32)}}}})
    box = seal.seal(world.params, eve.ek, cap, b"cap" + eve.uid.encode())
    with pytest.raises(VerifyError):
        eve.accept_capability(box, signing.sign_obj(world.params, eve._sk, "cap", [eve.uid, box]))
    # she patches her client anyway: the cloud has no credential for her key
    eve._me["cap"] = wire.dec(cap)
    with pytest.raises(Rejected) as err:
        eve.search("alpha", "token")
    assert err.value.reason == "unknown_user"
    # she tries bob's uid with a guessed credential
    ct = aead_encrypt(token_key(os.urandom(32)), wire.enc({"g": "alpha", "ts": int(world.clock() * 1000)}),
                      token_aad(bob.uid, "states_get"))
    with pytest.raises(Rejected) as err:
        world.api.call("states_get", {"uid": bob.uid, "ct": ct})
    assert err.value.reason == "bad_token"
    # a control message that is not signed by the owner is refused
    msg = wire.enc({"seq": 99, "op": "cred", "uid": eve.uid})
    with pytest.raises(Rejected):
        world.api.call("ctl", {"msg": msg, "sig": signing.sign_bytes(world.params, eve._sk, "ctl", msg)})


def test_a_capability_only_opens_for_its_receiver():
    world, _ = filled_world(["alpha"], docs_per_group=1, seed=43)
    bob = world.join("receiver-a", ["alpha"])
    eve = world.new_receiver("eve")
    mail = world.api.call("mail_get", {"uid": bob.uid})
    assert mail and mail[0]["kind"] == "cap"
    with pytest.raises(VerifyError):
        eve.accept_capability(mail[0]["body"], mail[0]["sig"])
    with pytest.raises(VerifyError):
        seal.unseal(world.params, eve._dk, mail[0]["body"], b"cap" + bob.uid.encode())


# ---------------------------------------------------------------- scope
def test_scope_confinement():
    world, _ = filled_world(["alpha", "beta"], docs_per_group=5, seed=51)
    alice = world.join("alice", ["alpha"])
    bob = world.join("receiver-a", ["beta"])
    with pytest.raises(AccessDenied):
        alice.search("beta", "token")
    with pytest.raises(AccessDenied):
        alice.open_document("beta", 1, 1)

    def raw(endpoint: str, req: dict):
        cap = alice._me["cap"]
        ct = aead_encrypt(token_key(cap["a"]), wire.enc({**req, "ts": int(world.clock() * 1000)}),
                          token_aad(alice.uid, endpoint))
        return world.api.call(endpoint, {"uid": alice.uid, "ct": ct})

    beta_doc = world.owner.documents("beta")[0]["id"]
    bob_key = group_subkeys(bob._me["cap"]["groups"]["beta"]["keys"]["1"], "beta", 1)[1]
    handle = doc_handle(bob_key, beta_doc)
    for endpoint, req in (("states_get", {"g": "beta"}),
                          ("search", {"g": "beta", "cur": 1, "segs": [[1, os.urandom(32)]]}),
                          ("doc_get", {"g": "beta", "e": 1, "handle": handle})):
        with pytest.raises(Rejected) as err:
            raw(endpoint, req)
        assert err.value.reason == "scope"
    # a token for one endpoint cannot be replayed on another
    cap = alice._me["cap"]
    ct = aead_encrypt(token_key(cap["a"]), wire.enc({"g": "alpha", "ts": int(world.clock() * 1000)}),
                      token_aad(alice.uid, "states_get"))
    with pytest.raises(Rejected) as err:
        world.api.call("search", {"uid": alice.uid, "ct": ct})
    assert err.value.reason == "bad_token"
    # even with the ciphertext in hand (colluding cloud), alice has no key for beta
    blob = world.cloud.db.execute("SELECT blob FROM docs WHERE g='beta' AND handle=?", (handle,)).fetchone()[0]
    alice_key = group_subkeys(cap["groups"]["alpha"]["keys"]["1"], "alpha", 1)[1]
    for key in (alice_key, group_subkeys(cap["groups"]["alpha"]["keys"]["1"], "beta", 1)[1]):
        with pytest.raises(VerifyError):
            aead_decrypt(key, blob, doc_aad("beta", 1, beta_doc))
    assert bob.open_document("beta", beta_doc, 1).title


def test_stale_token_timestamp_is_rejected():
    world, _ = filled_world(["alpha"], docs_per_group=1, seed=52)
    alice = world.join("alice", ["alpha"])
    recorder = Recorder(world.api)
    alice.cloud = recorder
    alice.search("alpha", "token")
    token, _ = recorder.last("search")
    assert world.api.call("search", token)["sig"]
    world.clock.advance(900)
    with pytest.raises(Rejected) as err:
        world.api.call("search", token)
    assert err.value.reason == "stale_token"


# ---------------------------------------------------------------- forward privacy
def test_forward_privacy_new_updates_share_no_address_with_old_tokens():
    world, rng = filled_world(["alpha"], docs_per_group=10, seed=61)
    recorder = Recorder(world.api)
    bob = world.join("receiver-a", ["alpha"], api=recorder)
    world.cloud.trace_tokens = []
    old_counts = {}
    for word in VOCAB:
        old_counts[word] = bob.search("alpha", word).entries
    seen_in_tokens = set(world.cloud.trace_tokens)
    assert seen_in_tokens
    old_tokens = [obj for name, obj, _ in recorder.calls if name == "search"]
    before = {row[0] for row in world.cloud.db.execute("SELECT addr FROM entries")}
    assert seen_in_tokens <= before

    for _ in range(8):
        doc = random_doc(rng)
        world.owner.add_document("alpha", doc.title, doc.text)
    world.owner.delete_document("alpha", world.owner.documents("alpha")[0]["id"])
    world.owner.publish("alpha")
    after = {row[0] for row in world.cloud.db.execute("SELECT addr FROM entries")}
    new_addresses = after - before
    assert len(new_addresses) > 10
    assert new_addresses.isdisjoint(seen_in_tokens)

    # replaying every old token returns exactly the old entries, never a new one
    for token in old_tokens:
        body = wire.dec(world.api.call("search", token)["body"])
        for _, addrs, _ in body["segs"]:
            returned = {addrs[i:i + 32] for i in range(0, len(addrs), 32)}
            assert returned <= before and returned.isdisjoint(new_addresses)
    # the receiver, with the new state, does find the new entries
    assert sum(bob.search("alpha", w).entries for w in VOCAB) > sum(old_counts.values())
