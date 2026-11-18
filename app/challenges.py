"""Challenges: short practice tasks with automatic checking. No score, hints available.

A challenge is complete when its check is true. Checks look at the narrator events seen
so far and at the data owner's own records, so they follow what really happened in the app.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from pqsse.narrator import Event

from .session import Session


@dataclass(frozen=True)
class Challenge:
    key: str
    title: str
    task: str
    hint: str
    check: Callable[[Session, Sequence[Event]], bool]


def _receiver(session: Session, name: str) -> dict | None:
    if session.owner is None:
        return None
    return next((r for r in session.owner.receivers.values() if r["name"].lower() == name), None)


def _carol_finance(session: Session, events: Sequence[Event]) -> bool:
    carol = _receiver(session, "receiver-b")
    return bool(carol) and not carol["revoked"] and carol["groups"] == ["Finance"]


def _found_invoice(session: Session, events: Sequence[Event]) -> bool:
    return any(e.kind == "verify" and e.data.get("keyword") == "invoice" and e.data.get("hits", 0) > 0 for e in events)


def _bob_revoked(session: Session, events: Sequence[Event]) -> bool:
    bob = _receiver(session, "receiver-a")
    return bool(bob) and bob["revoked"]


def _attack_caught(session: Session, events: Sequence[Event]) -> bool:
    return any(e.kind == "attack" and e.data.get("ok") for e in events)


def _compared(session: Session, events: Sequence[Event]) -> bool:
    return any(e.kind == "attack" and e.data.get("key") == "collusion" for e in events)


def _cloud_view(session: Session, events: Sequence[Event]) -> bool:
    return any(e.kind == "cloud_view" for e in events)


def _update_published(session: Session, events: Sequence[Event]) -> bool:
    kinds = [e.kind for e in events]
    return "update" in kinds and "publish" in kinds[kinds.index("update"):]


CHALLENGES: list[Challenge] = [
    Challenge("receiver-b", "Let Receiver B read only Finance",
              "Add Receiver B and have the data owner approve them for the Finance group and nothing else.",
              "Receiver tab: type carol and a passphrase, Unlock or create, Pair devices, Send join request. "
              "Owner tab: Refresh join requests, Approve selected, tick only Finance.", _carol_finance),
    Challenge("invoice", "Find a document containing 'invoice'",
              "As a receiver who belongs to Finance, search for the word invoice and get at least one verified result.",
              "Receiver tab: choose the group Finance, type invoice, press Search. If the receiver was just approved, "
              "press Fetch mailbox first.", _found_invoice),
    Challenge("revoke", "Revoke Receiver A so the receiver can no longer search",
              "Take Receiver A's access away. Afterwards a search by Receiver A must be refused.",
              "Owner tab: select bob under Approved receivers, choose a policy, press Revoke selected receiver, confirm.",
              _bob_revoked),
    Challenge("attack", "Make an attack get caught",
              "Run any attack in the Attack Lab and see which check stops it.",
              "Attack Lab tab: select a row, press Run selected attack.", _attack_caught),
    Challenge("compare", "Compare policy R and policy RE",
              "Find out what a revoked receiver can still read with the cloud's help under each policy.",
              "Attack Lab tab: run 'Collusion: R vs RE' and read the two numbers.", _compared),
    Challenge("cloudview", "Look at a document as the cloud sees it",
              "Display one stored document exactly the way the cloud holds it.",
              "Learn tab, page 'Who sees what': press 'Show a document as the cloud sees it'.", _cloud_view),
    Challenge("update", "Add a document and make it searchable",
              "As the data owner, add a document to a group and publish, so receivers can find it.",
              "Owner tab: select a group, Add document, then press Publish.", _update_published),
]


def completed(session: Session, events: Sequence[Event]) -> set[str]:
    """Keys of the challenges whose check is true right now."""
    done = set()
    for challenge in CHALLENGES:
        try:
            if challenge.check(session, events):
                done.add(challenge.key)
        except Exception:
            continue
    return done
