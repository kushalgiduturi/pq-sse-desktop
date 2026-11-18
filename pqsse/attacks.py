"""A malicious cloud, for the tamper tests and the Attack Lab.

``TamperCloud`` wraps an honest CloudCore and changes what it returns. It has the
cloud's own signing key, so it re-signs tampered search responses: the receiver must
detect the tampering from the owner signed state and the hash chain, not from a broken
cloud signature. ``Recorder`` captures messages for replay attacks.
"""
from __future__ import annotations

import random
from typing import Any

from .cloud.core import CloudCore
from .core import wire
from .core.index import ADDR_LEN, VAL_LEN
from .transport import CloudAPI, InProcessCloud

SEARCH_MODES = ("drop", "modify", "reorder", "truncate", "substitute")


def _split(addrs: bytes, vals: bytes) -> list[tuple[bytes, bytes]]:
    n = len(addrs) // ADDR_LEN
    return [(addrs[i * ADDR_LEN:(i + 1) * ADDR_LEN], vals[i * VAL_LEN:(i + 1) * VAL_LEN]) for i in range(n)]


def _join(pairs: list[tuple[bytes, bytes]]) -> tuple[bytes, bytes]:
    return b"".join(a for a, _ in pairs), b"".join(v for _, v in pairs)


def _flip(data: bytes, rng: random.Random) -> bytes:
    pos = rng.randrange(len(data))
    return data[:pos] + bytes([data[pos] ^ (1 << rng.randrange(8))]) + data[pos + 1:]


class Recorder:
    """Pass-through transport that records every request and reply."""

    def __init__(self, inner: CloudAPI) -> None:
        self.inner = inner
        self.calls: list[tuple[str, Any, Any]] = []

    def call(self, endpoint: str, obj: Any) -> Any:
        reply = self.inner.call(endpoint, obj)
        self.calls.append((endpoint, obj, reply))
        return reply

    def last(self, endpoint: str) -> tuple[Any, Any]:
        for name, obj, reply in reversed(self.calls):
            if name == endpoint:
                return obj, reply
        raise LookupError(endpoint)


class HoldBack:
    """Transport that swallows chosen requests (pretends success) and keeps them."""

    def __init__(self, inner: CloudAPI, endpoint: str) -> None:
        self.inner = inner
        self.endpoint = endpoint
        self.held: list[Any] = []
        self.active = True

    def call(self, endpoint: str, obj: Any) -> Any:
        if self.active and endpoint == self.endpoint:
            self.held.append(obj)
            return {"ok": True}
        return self.inner.call(endpoint, obj)


class TamperCloud:
    """Malicious cloud front end. Set ``mode`` to choose the attack."""

    def __init__(self, core: CloudCore, seed: int | None = None) -> None:
        self.core = core
        self.inner = InProcessCloud(core)
        self.rng = random.Random(seed)
        self.mode: str | None = None
        self.resign = True
        self.applied = False
        self.note = ""
        self.states_override: dict | None = None      # served instead of the real states reply
        self.doc_override: dict | None = None         # served instead of the real document

    def call(self, endpoint: str, obj: Any) -> Any:
        self.applied = False
        if endpoint == "search" and self.mode in SEARCH_MODES + ("unsigned", "badsig"):
            return self._search(obj)
        if endpoint == "doc_get" and self.mode in ("doc_modify", "doc_swap"):
            reply = self.inner.call(endpoint, obj)
            self.applied = True
            if self.mode == "doc_modify":
                if "part" in reply:                       # documents fetched in parts (design note 002 D)
                    return {**reply, "part": _flip(reply["part"], self.rng)}
                return {"blob": _flip(reply["blob"], self.rng), "sig": reply["sig"]}
            return dict(self.doc_override or reply)
        if endpoint == "states_get" and self.mode == "states" and self.states_override is not None:
            self.inner.call(endpoint, obj)  # still authenticate the caller
            self.applied = True
            return self.states_override
        return self.inner.call(endpoint, obj)

    # ------------------------------------------------------------------ search tampering
    def _search(self, obj: Any) -> Any:
        reply = self.inner.call("search", obj)
        if self.mode == "unsigned":
            self.applied = True
            return {"ct": reply["ct"], "sig": b""}
        if self.mode == "badsig":
            self.applied = True
            return {"ct": reply["ct"], "sig": _flip(reply["sig"], self.rng)}
        # the cloud holds a_u, so a cheating cloud can open and rewrite its own response
        body = wire.dec(self.core.open_response(obj["uid"], reply["ct"]))
        segs = [[e, _split(a, v)] for e, a, v in body["segs"]]
        changed = getattr(self, "_m_" + str(self.mode))(body["g"], segs)
        if not changed:
            return reply
        self.applied = True
        body["segs"] = [[e, *_join(pairs)] for e, pairs in segs]
        new_body = wire.enc(body)
        resealed = self.core.sign_response(obj["uid"], obj["ct"], new_body)
        if self.resign:
            return resealed
        return {"ct": resealed["ct"], "sig": reply["sig"]}

    def _pick(self, segs: list, minimum: int) -> list | None:
        choices = [pairs for _, pairs in segs if len(pairs) >= minimum]
        return self.rng.choice(choices) if choices else None

    def _m_drop(self, g: str, segs: list) -> bool:
        pairs = self._pick(segs, 1)
        if pairs is None:
            return False
        k = self.rng.randrange(len(pairs))
        del pairs[k]
        self.note = f"dropped entry {k}"
        return True

    def _m_modify(self, g: str, segs: list) -> bool:
        pairs = self._pick(segs, 1)
        if pairs is None:
            return False
        k = self.rng.randrange(len(pairs))
        addr, val = pairs[k]
        pairs[k] = (addr, _flip(val, self.rng))
        self.note = f"flipped one bit in value {k}"
        return True

    def _m_reorder(self, g: str, segs: list) -> bool:
        pairs = self._pick(segs, 2)
        if pairs is None:
            return False
        i, j = self.rng.sample(range(len(pairs)), 2)
        if self.rng.random() < 0.5:
            pairs[i], pairs[j] = pairs[j], pairs[i]
            self.note = f"swapped entries {i} and {j}"
        else:
            if pairs[i][1] == pairs[j][1]:
                return False
            pairs[i], pairs[j] = (pairs[i][0], pairs[j][1]), (pairs[j][0], pairs[i][1])
            self.note = f"swapped the values of entries {i} and {j}"
        return True

    def _m_truncate(self, g: str, segs: list) -> bool:
        pairs = self._pick(segs, 1)
        if pairs is None:
            return False
        keep = self.rng.randrange(len(pairs))
        del pairs[keep:]
        self.note = f"truncated to {keep} entries"
        return True

    def _m_substitute(self, g: str, segs: list) -> bool:
        """Replace an entry by another genuine entry stored for a different address."""
        pairs = self._pick(segs, 1)
        if pairs is None:
            return False
        k = self.rng.randrange(len(pairs))
        addr, val = pairs[k]
        rows = self.core.db.execute(
            "SELECT addr, val FROM entries WHERE g=? AND addr<>? AND val<>? ORDER BY RANDOM() LIMIT 1", (g, addr, val)).fetchall()
        if not rows:
            return False
        other_addr, other_val = rows[0]
        if self.rng.random() < 0.5:
            pairs[k] = (addr, other_val)
            self.note = f"entry {k}: value replaced by the value of another entry"
        else:
            pairs[k] = (other_addr, other_val)
            self.note = f"entry {k}: replaced by another stored entry"
        return True
