"""Attack Lab scenarios: one-click demos that tamper with data and show the detection.

Every scenario builds its own throwaway three-party world in memory (it never touches
the user's real data), runs an honest baseline, performs the attack with a malicious
cloud, and reports which check caught it. ``passed`` means the system behaved as the
paper claims (the attack was detected or rejected, or, for the collusion demo, the
documented difference between policy R and RE was observed).
"""
from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from typing import Callable

from . import pqbackend
from .attacks import Recorder, TamperCloud
from .core import signing, wire
from .core.errors import PQSSEError, Rejected, VerifyError
from .core.index import doc_aad
from .core.prims import aead_decrypt, group_subkeys
from .owner.owner import DocInput
from .pqbackend import FAST_PARAMS
from .sandbox import World
from .transport import InProcessCloud

LAB_VOCAB = ["invoice", "contract", "patient", "salary", "merger", "audit", "roadmap", "password"]
GROUP = "lab"


@dataclass
class Outcome:
    key: str
    title: str
    passed: bool = False
    verdict: str = ""
    lines: list[str] = field(default_factory=list)

    def say(self, text: str) -> None:
        self.lines.append(text)

    def text(self) -> str:
        head = f"{self.title}\n{'=' * len(self.title)}\n"
        return head + "\n".join(self.lines) + f"\n\nVERDICT: {self.verdict}\n"


@dataclass
class Lab:
    world: World
    tamper: TamperCloud
    recorder: Recorder
    bob: object
    keyword: str


def _lab(seed: int = 1, docs: int = 12) -> Lab:
    """World with one group, a published index and receiver bob behind a malicious cloud."""
    rng = random.Random(seed)
    world = World(params=FAST_PARAMS)
    world.owner.create_group(GROUP)
    batch = [DocInput(f"file {i}", " ".join(rng.sample(LAB_VOCAB, 4))) for i in range(docs)]
    world.owner.build_index(GROUP, batch)
    world.owner.publish(GROUP)
    tamper = TamperCloud(world.cloud, seed=seed)
    recorder = Recorder(InProcessCloud(world.cloud))
    tamper.inner = recorder
    bob = world.join("bob", [GROUP], api=tamper)
    return Lab(world, tamper, recorder, bob, LAB_VOCAB[0])


def _search_attack(key: str, title: str, mode: str, story: str) -> Outcome:
    out = Outcome(key, title)
    lab = _lab()
    honest = lab.bob.search(GROUP, lab.keyword)
    out.say(f"Honest cloud: search for '{lab.keyword}' returns {len(honest.hits)} documents, "
            f"{honest.entries} index entries, all 8 checks pass.")
    out.say(f"Attack: {story}")
    out.say("The malicious cloud re-signs the changed response with its own ML-DSA key.")
    lab.tamper.mode = mode
    try:
        lab.bob.search(GROUP, lab.keyword)
    except VerifyError as exc:
        out.say(f"What the cloud did: {lab.tamper.note}.")
        out.say(f"Receiver Verify failed at check '{exc.check}': {exc.detail}.")
        out.passed, out.verdict = True, f"DETECTED by the '{exc.check}' check. No result was shown to the user."
    else:
        out.verdict = "NOT DETECTED (this would be a bug)"
    return out


def drop_result() -> Outcome:
    return _search_attack("drop", "Drop a result", "drop", "the cloud removes one matching entry from the response.")


def modify_result() -> Outcome:
    return _search_attack("modify", "Modify a result", "modify", "the cloud flips one bit in a returned value.")


def reorder_results() -> Outcome:
    return _search_attack("reorder", "Reorder results", "reorder", "the cloud swaps two entries of the response.")


def truncate_results() -> Outcome:
    return _search_attack("truncate", "Truncate results", "truncate", "the cloud cuts off the tail of the response.")


def substitute_document() -> Outcome:
    out = Outcome("substitute", "Substitute a document")
    lab = _lab()
    hits = lab.bob.search(GROUP, lab.keyword).hits
    (want, epoch), (other, other_epoch) = hits[0], hits[1]
    genuine = lab.bob.open_document(GROUP, want, epoch)
    lab.bob.open_document(GROUP, other, other_epoch)
    other_reply = lab.recorder.last("doc_get")[1]
    out.say(f"Honest cloud: document {want} decrypts to '{genuine.title}'.")
    out.say(f"Attack: when document {want} is requested, the cloud answers with document {other}, "
            "a genuine ciphertext with a genuine owner signature.")
    lab.tamper.mode, lab.tamper.doc_override = "doc_swap", other_reply
    try:
        lab.bob.open_document(GROUP, want, epoch)
    except VerifyError as exc:
        out.say(f"Receiver Decrypt refused: {exc}.")
        out.say("The owner's signature covers group, epoch and the document handle, so a swap cannot verify.")
        out.passed, out.verdict = True, "DETECTED by the owner's document signature."
    else:
        out.verdict = "NOT DETECTED (this would be a bug)"
    return out


def replay_update() -> Outcome:
    out = Outcome("replay", "Replay an update")
    lab = _lab()
    recorder = Recorder(lab.world.api)
    lab.world.owner.cloud = recorder
    lab.world.owner.add_document(GROUP, "fresh", "audit invoice appendix")
    batch, _ = recorder.last("update")
    seq = wire.dec(batch["msg"])["seq"]
    out.say(f"The owner sends update batch number {seq}; the cloud accepts it.")
    out.say("Attack: an attacker on the network sends the very same signed batch again.")
    try:
        lab.world.api.call("update", batch)
    except Rejected as exc:
        out.say(f"Cloud answer: rejected, reason '{exc.reason}' ({exc.detail}).")
        out.passed, out.verdict = True, "REJECTED: batches are sequence numbered, a replay is out of sequence."
    else:
        out.verdict = "ACCEPTED (this would be a bug)"
    return out


def forge_update() -> Outcome:
    out = Outcome("forge", "Forge an update")
    lab = _lab()
    recorder = Recorder(lab.world.api)
    lab.world.owner.cloud = recorder
    lab.world.owner.add_document(GROUP, "fresh", "audit invoice appendix")
    batch = wire.dec(recorder.last("update")[0]["msg"])
    batch.update(seq=batch["seq"] + 1, addrs=os.urandom(32), vals=os.urandom(5), docs=[], **{"del": []})
    forged = wire.enc(batch)
    _, attacker_sk = pqbackend.sig_keygen(lab.world.params.sig)
    out.say("Attack: the attacker builds a well formed next batch with a fake index entry and signs it "
            "with their own ML-DSA key.")
    try:
        lab.world.api.call("update", {"msg": forged, "sig": signing.sign_bytes(lab.world.params, attacker_sk, "batch", forged)})
    except Rejected as exc:
        out.say(f"Cloud answer: rejected, reason '{exc.reason}' ({exc.detail}).")
        out.passed, out.verdict = True, "REJECTED: only batches signed by the owner's ML-DSA key are accepted."
    else:
        out.verdict = "ACCEPTED (this would be a bug)"
    return out


def rollback_state() -> Outcome:
    out = Outcome("rollback", "Roll back a state")
    lab = _lab()
    lab.bob.search(GROUP, lab.keyword)
    old_states = lab.recorder.last("states_get")[1]
    new_id = lab.world.owner.add_document(GROUP, "addendum", f"{lab.keyword} addendum")
    version = lab.world.owner.publish(GROUP)
    seen = lab.bob.search(GROUP, lab.keyword)
    out.say(f"The owner adds document {new_id} and publishes state version {version}; bob sees it "
            f"({len(seen.hits)} documents).")
    out.say(f"Attack: the cloud serves the older, genuinely signed state (version {version - 1}) "
            "together with the matching old index entries, hiding the new document.")
    lab.tamper.mode, lab.tamper.states_override = "states", old_states
    try:
        lab.bob.search(GROUP, lab.keyword)
    except VerifyError as exc:
        out.say(f"Receiver Verify failed at check '{exc.check}': {exc.detail}.")
        out.passed, out.verdict = True, "DETECTED: the receiver remembers the highest version it has seen."
    else:
        out.verdict = "NOT DETECTED (this would be a bug)"
    return out


def expired_state() -> Outcome:
    out = Outcome("expired", "Use an expired state")
    lab = _lab()
    first = lab.bob.search(GROUP, lab.keyword)
    out.say(f"The published state is valid for {lab.world.owner.state_ttl / 60:.0f} minutes. "
            f"Honest search passes ({len(first.hits)} documents).")
    out.say("Attack: the cloud keeps serving that state after its expiry time (the clock moves past t_exp), "
            "so later updates would stay hidden.")
    lab.world.clock.advance(lab.world.owner.state_ttl + 60)
    try:
        lab.bob.search(GROUP, lab.keyword)
    except VerifyError as exc:
        out.say(f"Receiver Verify failed at check '{exc.check}': {exc.detail}.")
        lab.world.owner.publish(GROUP)
        again = lab.bob.search(GROUP, lab.keyword)
        out.say(f"After the owner republishes, search works again ({len(again.hits)} documents).")
        out.passed, out.verdict = True, "DETECTED: a state older than the freshness window is refused."
    else:
        out.verdict = "NOT DETECTED (this would be a bug)"
    return out


def revoked_retry() -> Outcome:
    out = Outcome("revoked", "Revoked user retries search")
    lab = _lab()
    carol = lab.world.join("carol", [GROUP])
    recorder = Recorder(lab.world.api)
    carol.cloud = recorder
    before = carol.search(GROUP, lab.keyword)
    old_token = recorder.last("search")[0]
    out.say(f"carol is a member: her search returns {len(before.hits)} documents.")
    lab.world.owner.revoke(carol.uid, "R")
    out.say("The owner revokes carol (policy R). She retries with a new token, then replays her old token.")
    reasons = []
    for label, action in (("new search", lambda: carol.search(GROUP, lab.keyword)),
                          ("replayed old token", lambda: lab.world.api.call("search", old_token))):
        try:
            action()
            reasons.append(None)
        except Rejected as exc:
            reasons.append(exc.reason)
            out.say(f"  {label}: rejected by the cloud, reason '{exc.reason}'.")
    still = lab.bob.search(GROUP, lab.keyword)
    out.say(f"bob, who was not revoked, still gets {len(still.hits)} documents in the new epoch.")
    if all(reasons):
        out.passed, out.verdict = True, "REJECTED: the cloud deauthorized the credential, old tokens are dead."
    else:
        out.verdict = "ACCEPTED (this would be a bug)"
    return out


def _collude(world: World, keys: dict, max_id: int) -> tuple[int, int]:
    """Revoked user plus cloud: try every stored document with every key the user holds."""
    rows = world.cloud.db.execute("SELECT e, blob FROM docs WHERE g=?", (GROUP,)).fetchall()
    opened = 0
    for epoch, blob in rows:
        ok = False
        for held, key in keys.items():
            for use_epoch in {epoch, int(held)}:
                k_doc = group_subkeys(key, GROUP, use_epoch)[1]
                for doc_id in range(1, max_id + 1):
                    try:
                        aead_decrypt(k_doc, blob, doc_aad(GROUP, epoch, doc_id))
                        ok = True
                    except VerifyError:
                        pass
        opened += int(ok)
    return opened, len(rows)


def collusion_demo() -> Outcome:
    out = Outcome("collusion", "Collusion: policy R vs policy RE")
    out.say("Setting: a revoked user keeps their old group key and colludes with the cloud, which hands over "
            "its whole database. How many stored documents can they decrypt?")
    results = {}
    for policy in ("R", "RE"):
        lab = _lab(seed=3)
        mallory = lab.world.join("mallory", [GROUP])
        keys = dict(mallory._me["cap"]["groups"][GROUP]["keys"])
        lab.world.owner.revoke(mallory.uid, policy)
        lab.world.owner.add_document(GROUP, "after revocation", "merger secret written later")
        lab.world.owner.publish(GROUP)
        opened, total = _collude(lab.world, keys, lab.world.owner._group(GROUP)["next_id"])
        results[policy] = (opened, total)
        kept = lab.world.cloud.db.execute("SELECT COUNT(DISTINCT e) FROM entries WHERE g=?", (GROUP,)).fetchone()[0]
        out.say(f"Policy {policy}: the cloud stores {total} documents in {kept} segment(s); "
                f"revoked user plus cloud decrypt {opened} of them.")
    out.say("Under R the old segment stays under the old key, so pre-revocation documents remain readable "
            "to this coalition (the documented model limit). Documents added after the revocation are safe.")
    out.say("Under RE everything was re-encrypted under the new epoch key and the old segments were dropped.")
    r_ok = 0 < results["R"][0] < results["R"][1]
    re_ok = results["RE"][0] == 0
    out.passed = r_ok and re_ok
    out.verdict = ("AS DOCUMENTED: R leaves old data exposed to a revoked user who colludes with the cloud, RE does not."
                   if out.passed else "UNEXPECTED RESULT (this would be a bug)")
    return out


SCENARIOS: list[tuple[str, str, str, Callable[[], Outcome]]] = [
    ("drop", "Drop a result", "The cloud omits one matching entry.", drop_result),
    ("modify", "Modify a result", "The cloud changes one returned value.", modify_result),
    ("reorder", "Reorder results", "The cloud swaps entries.", reorder_results),
    ("truncate", "Truncate results", "The cloud cuts the response short.", truncate_results),
    ("substitute", "Substitute a document", "The cloud returns a different genuine document.", substitute_document),
    ("replay", "Replay an update", "An old signed update batch is sent again.", replay_update),
    ("forge", "Forge an update", "A batch signed by the wrong key.", forge_update),
    ("rollback", "Roll back a state", "The cloud serves an older signed state.", rollback_state),
    ("expired", "Use an expired state", "The cloud serves a state past its expiry.", expired_state),
    ("revoked", "Revoked user retries search", "A revoked receiver tries again.", revoked_retry),
    ("collusion", "Collusion: R vs RE", "Revoked user colludes with the cloud.", collusion_demo),
]


def run_scenario(key: str) -> Outcome:
    """Run one scenario by key. Unexpected errors become a failed outcome, not a crash."""
    for name, title, _, fn in SCENARIOS:
        if name == key:
            try:
                return fn()
            except PQSSEError as exc:
                return Outcome(key, title, False, f"ERROR: {type(exc).__name__}: {exc}")
    raise KeyError(key)
