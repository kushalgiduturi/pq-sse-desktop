"""Several independent data owners on one server (design note 004 A).

Each data owner beyond the first gets a store of its own: its own database (and document files), with the
server's identity keys copied in, so clients see one server key. Nothing else is shared, so groups,
receivers, invites, join requests, mail and sequence numbers of one owner cannot touch another's.

Requests name their owner in a top-level ``owner`` field: the owner id, the first 8 bytes of
``H(owner verification key)`` in hex. Requests without it, or naming the first owner, go to the first
owner's store, which is the store a one-owner server always had (no migration). ``owner_pub`` may ask
for an owner by key fingerprint instead (``{"fp": ...}``), which is what an invite carries.
"""
from __future__ import annotations

from typing import Any, Callable

from ..core import wire
from ..core.errors import Rejected, WireError
from ..core.pairing import PublicIdentity
from ..core.prims import H
from .core import CloudCore


def owner_id(vk: bytes) -> str:
    """The id a request uses to name its data owner."""
    return H(vk)[:8].hex()


class OwnerRouter:
    """Routes each request to its owner's store. Anything else is the first owner's store (``default``)."""

    def __init__(self, default: CloudCore, open_store: Callable[[str], CloudCore], existing: list[str] = (),
                 exists: Callable[[str], bool] | None = None) -> None:
        self.default = default
        self._open_store = open_store
        self._exists = exists or (lambda oid: False)     # a store paired by another process (the CLI) since start
        self.extra: dict[str, CloudCore] = {}
        for oid in existing:
            self.extra[oid] = open_store(oid)

    # ------------------------------------------------------------------ owners
    def default_id(self) -> str | None:
        ident = self.default.owner_identity()
        return None if ident is None else owner_id(ident.vk)

    def add_owner(self, ident: PublicIdentity) -> str:
        """Pair one more data owner (the first one pairs into the default store). Returns its owner id."""
        oid = owner_id(ident.vk)
        if self.default.owner_identity() is None or oid == self.default_id():
            self.default.pair_owner(ident)
            return oid
        if oid not in self.extra:
            core = self._open_store(oid)
            core.pair_owner(ident)
            self.extra[oid] = core
        return oid

    def owners(self) -> list[dict]:
        out = []
        for oid, core in ([(self.default_id(), self.default)] if self.default_id() else []) + sorted(self.extra.items()):
            ident = core.owner_identity()
            out.append({"owner": oid, "fingerprint": ident.fingerprint() if ident else "",
                        "groups": core.db.execute("SELECT COUNT(*) FROM groups").fetchone()[0],
                        "storage_bytes": core.storage_bytes(), "first": core is self.default})
        return out

    def core_for(self, oid: str | None) -> CloudCore:
        if oid is None or oid == self.default_id():
            return self.default
        core = self.extra.get(str(oid))
        if core is None and len(str(oid)) == 16 and all(c in "0123456789abcdef" for c in str(oid)) and self._exists(str(oid)):
            core = self.extra[str(oid)] = self._open_store(str(oid))
        if core is None:
            raise Rejected("unknown_owner", "no data owner with this id on this server")
        return core

    def close(self) -> None:
        for core in [self.default, *self.extra.values()]:
            core.vault.close()

    # ------------------------------------------------------------------ requests
    def handle(self, endpoint: str, body: bytes) -> bytes:
        try:
            obj = wire.dec(body)
        except (WireError, ValueError):
            return self.default.handle(endpoint, body)     # the default store refuses it as malformed
        if endpoint == "owner_pub" and isinstance(obj, dict) and obj.get("fp"):
            for core in [self.default, *self.extra.values()]:
                ident = core.owner_identity()
                if ident is not None and ident.fingerprint().replace(" ", "") == str(obj["fp"]).replace(" ", ""):
                    return core.handle(endpoint, body)
            raise Rejected("unknown_owner", "no data owner with this fingerprint on this server")
        oid = obj.get("owner") if isinstance(obj, dict) else None
        return self.core_for(oid).handle(endpoint, body)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.default, name)                  # operator views and tools of the first store
