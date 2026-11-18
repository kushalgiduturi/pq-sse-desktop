"""Plain role names, the demo receivers, and the optional teaching names.

Everything the app shows uses plain role names: Data owner, Receiver, Cloud server. The guided
lesson can switch on "Teaching names" (off by default): then a fixed list of plain phrases is shown
with the names of the lesson's cast instead (Alice, Bob, Carol, the Cloud). The words are swapped only
for display; ids, stored data and the protocol never change.
"""
from __future__ import annotations

import re
import threading

OWNER = "alice"          # internal role key of the data owner (kept: stored settings and events use it)
CLOUD = "cloud"
RECEIVER_A, RECEIVER_B = "receiver-a", "receiver-b"   # user ids of the two demo receivers

NAMES = {OWNER: "Data owner", CLOUD: "Cloud server", RECEIVER_A: "Receiver A", RECEIVER_B: "Receiver B"}
TEACHING_NAMES = {OWNER: "Alice", CLOUD: "Cloud", RECEIVER_A: "Bob", RECEIVER_B: "Carol"}

# plain phrase -> teaching phrase; longer phrases first so "the data owner's" wins over "the data owner"
_PHRASES = [
    ("The data owner's", "Alice's"), ("the data owner's", "Alice's"),
    ("The data owner", "Alice"), ("the data owner", "Alice"), ("Data owner", "Alice"),
    ("Receiver A's", "Bob's"), ("Receiver A", "Bob"), ("Receiver B's", "Carol's"), ("Receiver B", "Carol"),
]
_PATTERN = re.compile("|".join(re.escape(plain) for plain, _ in _PHRASES))
_LOOKUP = dict(_PHRASES)
_state = {"teaching": False}
_lock = threading.Lock()


def set_teaching(on: bool) -> None:
    with _lock:
        _state["teaching"] = bool(on)


def teaching() -> bool:
    return _state["teaching"]


def display(uid: str) -> str:
    """The name to show for a role key or user id: plain by default, the cast name in teaching mode."""
    if not uid:
        return ""
    table = TEACHING_NAMES if teaching() else NAMES
    if uid in table:
        return table[uid]
    return uid[:1].upper() + uid[1:]


def teach(text: str) -> str:
    """Show a text with the teaching names when that option is on; otherwise unchanged."""
    if not teaching() or not text:
        return text
    return _PATTERN.sub(lambda m: _LOOKUP[m.group(0)], text)


def teach_all(obj):
    """teach() applied to every string inside dicts and lists (dict keys are left alone)."""
    if not teaching():
        return obj
    if isinstance(obj, str):
        return teach(obj)
    if isinstance(obj, dict):
        return {k: teach_all(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(teach_all(v) for v in obj)
    return obj
