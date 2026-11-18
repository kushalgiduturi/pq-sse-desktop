"""Narrator: a typed event bus plus the plain-language story for every event.

Owner and receiver code call ``emit(kind, who, **facts)`` in one line at the points where
something worth explaining happens. Subscribers (the Narrator panel, the data-flow diagram,
the challenge checker) receive ``Event`` objects and turn them into text with ``render``.

Safety rule: facts may only be numbers, booleans, short strings and lists of strings.
``emit`` refuses bytes, so key material cannot enter an event by accident. With no
subscriber, ``emit`` does almost nothing, so the protocol code pays no real cost.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable

from . import roles

ALGORITHMS = {1: "Setup", 2: "Join", 3: "BuildIndex", 4: "Update", 5: "Publish",
              6: "TokenGen", 7: "Search", 8: "Verify", 9: "Decrypt", 10: "Revoke"}
TAGS = {"alice": "Data owner", "receiver": "", "cloud": "Cloud server", "security": "Security"}


@dataclass(frozen=True)
class Event:
    kind: str
    who: str
    data: dict = field(default_factory=dict)
    ts: float = 0.0
    scope: str = ""     # "" = the real system; "practice" = a throwaway copy (Attack Lab, comparisons)


@dataclass(frozen=True)
class Packet:
    """One thing travelling in the data-flow diagram."""

    src: str            # "alice", "receiver" or "cloud"
    dst: str
    icon: str           # BOX (locked data), STAMP (signature), SLIP (search token), KEY, NOTE
    label: str
    contents: str
    readers: str        # who can read it


@dataclass(frozen=True)
class Story:
    tag: str            # alice, receiver, cloud, security
    line: str           # one plain sentence
    more: str           # "Tell me more"
    technical: str      # the real name of the step
    hood: str = ""      # "Under the hood": field names and sizes
    algorithm: int = 0  # 1..10 when the event is one of the ten algorithms
    packet: Packet | None = None


@dataclass(frozen=True)
class Rendered:
    kind: str
    tag: str
    tag_label: str
    line: str
    more: str
    technical: str
    hood: str
    packet: Packet | None
    ts: float


STORIES: dict[str, Story] = {
    "setup.owner": Story(
        "alice", "The data owner created their signing key pair. The private half never leaves their computer.",
        "The data owner now has a private key for stamping (signing) and a public key that lets everyone check their "
        "stamps. The keys use a post-quantum method, so the stamps should stay trustworthy even against "
        "future quantum computers.",
        "Setup, Algorithm 1 (owner part)", "Signature scheme {sig}. Public key: {vk_bytes} bytes.", 1),
    "setup.receiver": Story(
        "receiver", "{who} created two key pairs: one for receiving sealed secrets, one for signing.",
        "The first pair lets the data owner send {who} secrets that only {who} can open. The second pair lets {who} "
        "prove that a request really comes from this key.",
        "Setup, Algorithm 1 (receiver part)", "Key exchange {kem}, signatures {sig}.", 1),
    "cloud.started": Story(
        "cloud", "The cloud server started. It is a separate program that only stores and looks up locked data.",
        "The cloud has its own keys for receiving sealed messages and for stamping its answers. It never "
        "receives a group key, so it cannot unlock documents or the index.",
        "Setup, Algorithm 1 (cloud part)", "Listening on 127.0.0.1 port {port}, this computer only.", 1),
    "pair": Story(
        "security", "{who} imported the public key of {other}. They can now recognise each other's stamps.",
        "Public keys are not secret, but they must be the right ones. Pairing is the step where they are "
        "exchanged over a path you trust, like handing over a card in person.",
        "Setup, Algorithm 1 (pair devices)", "A .pqpub file holds public keys only."),
    "group": Story(
        "alice", "The data owner created the group {g} with its own fresh secret key.",
        "A group is a folder with one lock. The data owner made a random key for it. Only people the owner gives this key "
        "to can search or read the group. The cloud is told that the group exists, not the key.",
        "Group setup", "Group key: 32 random bytes, epoch 1.",
        packet=Packet("alice", "cloud", "NOTE", "new group", "The group name and the data owner's stamp.", "Anyone (no secret inside)")),
    "join.request": Story(
        "receiver", "{who} asked to join. The request carries {who}'s public keys and a stamp proving they are {who}'s.",
        "The stamp is made over a fresh random number, so nobody can copy an old request or claim a key "
        "that is not theirs. The data owner still decides whether to approve.",
        "Join, Algorithm 2 (request)", "Request size: {bytes} bytes. Signed with {who}'s ML-DSA key.", 2,
        Packet("receiver", "cloud", "STAMP", "join request", "Public keys, a fresh random number and a stamp.",
               "Anyone (public keys only)")),
    "join.approved": Story(
        "alice", "The data owner approved {who} for: {groups}. The owner sealed an access pass that only {who} can open.",
        "The pass holds the keys for exactly the chosen groups and a secret pass for talking to the cloud. "
        "It is sealed with a post-quantum method and stamped by the data owner. The cloud passes it on but cannot open it. "
        "The cloud is told which groups {who} may ask about.",
        "Join, Algorithm 2 (approval)", "Sealed capability: {cap_bytes} bytes (ML-KEM ciphertext plus AES-GCM).", 2,
        Packet("alice", "cloud", "KEY", "sealed access pass", "Group keys and a cloud pass for one receiver.",
               "Only that receiver")),
    "join.capability": Story(
        "receiver", "{who} opened the access pass from the data owner. {who} can now search: {groups}.",
        "{who} first checked the data owner's stamp on the pass, then opened it with a private key. A pass made by "
        "anyone else would have been refused.",
        "Join, Algorithm 2 (receiver accepts the capability)", "",  2,
        Packet("cloud", "receiver", "KEY", "sealed access pass", "Group keys and a cloud pass.", "Only this receiver")),
    "build_index": Story(
        "alice", "The data owner locked {docs} document(s) for {g} and built {entries} locked index entries. "
        "Everything went to the cloud in one stamped batch.",
        "Each document went into its own locked box. For every word, the data owner stored one index entry at an "
        "address that looks random. The cloud can store and fetch entries but cannot tell which word an "
        "entry belongs to. This step can take a moment because every document gets its own stamp.",
        "BuildIndex, Algorithm 3", "{entries} entries of 32 + 5 bytes, batch {bytes} bytes, addresses computed on: {engine}.", 3,
        Packet("alice", "cloud", "BOX", "locked documents + index", "Locked documents, masked index entries, the data owner's stamp.",
               "Nobody at the cloud. Group members can unlock the documents.")),
    "update": Story(
        "alice", "The data owner changed {g}: {adds} document(s) added, {deletes} deleted, {entries} new index entries.",
        "Updates are numbered and stamped. The cloud accepts only the next number with a valid stamp, so "
        "nobody can replay, reorder or forge an update. A delete is just one more masked entry, so the cloud "
        "cannot tell which older entry it cancels.",
        "Update, Algorithm 4", "Batch {bytes} bytes for epoch {e}.", 4,
        Packet("alice", "cloud", "BOX", "stamped update", "New locked documents and masked index entries.",
               "Nobody at the cloud")),
    "reencrypt": Story(
        "alice", "The data owner re-locked all {docs} document(s) of {g} with the new key. The cloud dropped the old copies.",
        "This is the extra work of policy RE. After it, the old key opens nothing that the cloud still stores.",
        "Revoke, Algorithm 10 (policy RE, reset batch)", "{entries} index entries rebuilt for epoch {e}.",
        packet=Packet("alice", "cloud", "BOX", "re-locked group", "Every document and index entry under the new key.",
                      "Nobody at the cloud")),
    "publish": Story(
        "alice", "The data owner published a stamped summary of the {g} index (version {ver}).",
        "The summary says, for every word, how many entries exist and what their running fingerprint is. "
        "It is encrypted for group members and stamped by the data owner. Receivers use it to check that the cloud's "
        "answers are complete and unchanged. It also has an expiry time, so old summaries cannot be reused forever.",
        "Publish, Algorithm 5", "{records} word records, padded to hide the exact count, {bytes} bytes. Final: {final}.", 5,
        Packet("alice", "cloud", "STAMP", "stamped summary", "Encrypted list of counts and fingerprints, the data owner's stamp.",
               "Group members only")),
    "tokengen": Story(
        "receiver", "{who} wrote a sealed search slip for '{keyword}' in {g}.",
        "The slip does not contain the word. It lists {addresses} secret addresses that only a holder of the "
        "group key can compute. The slip is encrypted, so only the cloud can read even those addresses.",
        "TokenGen, Algorithm 6", "{addresses} addresses over {segments} segment(s), encrypted token {bytes} bytes.", 6,
        Packet("receiver", "cloud", "SLIP", "sealed search slip", "A list of secret addresses. Not the search word.",
               "Only the cloud (and it sees addresses, not the word)")),
    "search": Story(
        "cloud", "The cloud looked up the slip and returned {entries} scrambled entries with its own stamp.",
        "The cloud checked that {who} is allowed to ask about {g}. It never saw the word, only addresses. "
        "It stamped its answer so that it cannot later deny what it sent.",
        "Search, Algorithm 7", "Reply {bytes} bytes, cloud ML-DSA signature {sig_bytes} bytes.", 7,
        Packet("cloud", "receiver", "BOX", "stamped answer", "Masked index entries and the cloud's stamp.",
               "Only group members can unmask them")),
    "verify": Story(
        "security", "{who} checked the cloud's answer: all {checks} checks passed. {hits} document(s) match.",
        "{who} did not trust the cloud. The app checked the data owner's stamp on the summary, that nothing is "
        "missing or out of date, the cloud's stamp, that every expected entry is present, and the running "
        "fingerprint. Only then were the results shown.",
        "Verify, Algorithm 8", "{entries} entries verified against the signed state.", 8),
    "verify.failed": Story(
        "security", "{who}'s app refused the cloud's answer. The '{check}' check failed.",
        "Something in the answer did not match what the data owner stamped. The app shows no result at all rather "
        "than a wrong one. Detail: {detail}",
        "Verify, Algorithm 8 (failed)", ""),
    "decrypt": Story(
        "receiver", "{who} fetched document {doc_id}, checked the data owner's stamp on it, and unlocked it.",
        "The stamp proves this is exactly the box the data owner stored under that name, not a swapped one. Then "
        "{who} unlocked it with the {g} key.",
        "Decrypt, Algorithm 9", "Ciphertext {bytes} bytes, key of epoch {e}.", 9,
        Packet("cloud", "receiver", "BOX", "locked document", "One locked document and the data owner's stamp.",
               "Only members of the group")),
    "decrypt.denied": Story(
        "security", "{who} could not open a document in {g}: {who} does not hold that group's key.",
        "Access is decided by keys, not by promises. Without the group key the locked box is just random "
        "bytes, even if someone hands it over.",
        "Decrypt, Algorithm 9 (denied)", ""),
    "search.denied": Story(
        "security", "{who} could not search {g}: {who} holds no key for that group.",
        "The data owner never gave {who} the key for {g}. Without it the app cannot even compute where to look, "
        "and the cloud would refuse the request as outside {who}'s permission.",
        "TokenGen, Algorithm 6 (denied: scope)", ""),
    "revoke": Story(
        "alice", "The data owner revoked {who} using policy {policy}. The locks of {groups} were changed.",
        "The cloud now refuses {who}'s pass. Each affected group got a new key, and the receivers who are "
        "still allowed received it in a sealed message. With policy R, data from before the change is "
        "still locked with the old key. With policy RE, everything was re-locked.",
        "Revoke, Algorithm 10", "", 10,
        Packet("alice", "cloud", "KEY", "new keys for the others", "Sealed new group keys, one per remaining receiver.",
               "Only each remaining receiver")),
    "rekey": Story(
        "receiver", "{who} received the new key for {g} (epoch {e}).",
        "The new key arrived sealed for {who} alone and stamped by the data owner. A revoked receiver gets no such message.",
        "Revoke, Algorithm 10 (rekey box)", "",
        packet=Packet("cloud", "receiver", "KEY", "sealed new key", "The new group key.", "Only this receiver")),
    "blocked": Story(
        "security", "Blocked: {what}",
        "The app stopped this action. The message under the tab explains why it matters and what to do next.",
        "Refusal or failed check", ""),
    "attack": Story(
        "security", "Attack Lab: '{title}' was tried. Result: {result}",
        "The attack ran on a separate practice copy, not on your data. Stopped by: {caught_by}.",
        "Attack Lab scenario", ""),
    "cloud_view": Story(
        "cloud", "You looked at a document the way the cloud sees it: {bytes} bytes that look random.",
        "This is the real stored data. Without the group key there is no way to turn it back into text.",
        "Ciphertext at rest", ""),
    "wait": Story("alice", "{message}", "Some steps take a moment. The window stays usable while they run.", "Progress note", ""),
}

_lock = threading.Lock()
_subscribers: list[Callable[[Event], None]] = []
_local = threading.local()


@contextmanager
def scope(name: str):
    """Label every event emitted by this thread inside the block (read-only hook for the UI).

    The Attack Lab and the policy comparison run on throwaway copies of the system. They
    use the same code, so they emit the same events. The label lets a listener tell them
    apart from events of the real system. It changes nothing about what is emitted.
    """
    previous = getattr(_local, "scope", "")
    _local.scope = name
    try:
        yield
    finally:
        _local.scope = previous


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "?"


def _check(value: object) -> None:
    if isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str) and len(value) <= 300:
        return
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) and len(v) <= 100 for v in value):
        return
    raise TypeError("narrator facts must be numbers, short strings or lists of strings (never bytes)")


def subscribe(fn: Callable[[Event], None]) -> Callable[[], None]:
    """Register a subscriber. Returns a function that removes it again."""
    with _lock:
        _subscribers.append(fn)

    def unsubscribe() -> None:
        with _lock:
            if fn in _subscribers:
                _subscribers.remove(fn)

    return unsubscribe


def emit(kind: str, who: str = "", **facts: object) -> None:
    """Announce that something happened. Unknown kinds and unsafe facts are programming errors."""
    if kind not in STORIES:
        raise KeyError(f"unknown narrator event {kind}")
    with _lock:
        targets = list(_subscribers)
    if not targets:
        return
    for value in facts.values():
        _check(value)
    event = Event(kind, display_name(who), dict(facts), time.time(), getattr(_local, "scope", ""))
    for fn in targets:
        try:
            fn(event)
        except Exception:
            pass  # a broken listener must never break the protocol


def display_name(name: str) -> str:
    return roles.display(name)


def render(event: Event) -> Rendered:
    """Turn an event into the text shown by the Narrator."""
    story = STORIES[event.kind]
    facts = _Safe({k: (", ".join(v) if isinstance(v, (list, tuple)) else v) for k, v in event.data.items()})
    facts["who"] = event.who or "Someone"
    tag_label = roles.teach(TAGS[story.tag]) or facts["who"]
    technical = story.technical
    t = roles.teach
    return Rendered(event.kind, story.tag, tag_label, t(story.line.format_map(facts)), t(story.more.format_map(facts)),
                    technical, t(story.hood.format_map(facts)), story.packet, event.ts)


def algorithm_of(kind: str) -> int:
    return STORIES[kind].algorithm
