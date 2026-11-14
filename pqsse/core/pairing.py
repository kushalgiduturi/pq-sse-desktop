"""Pair devices: export and import of public keys as small ``.pqpub`` files.

This models the authentic public key assumption of Setup. A ``.pqpub`` file holds
public keys only. The fingerprint is shown in the UI so the user can compare it.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

from ..pqbackend import Params
from .errors import WireError
from .prims import H
from .wire import sstr

ROLES = ("owner", "cloud", "receiver")


@dataclass(frozen=True)
class PublicIdentity:
    """Public keys of one party. ``ek`` is empty for the owner (it has no KEM key)."""

    role: str
    name: str
    params: Params
    vk: bytes
    ek: bytes = b""

    def fingerprint(self) -> str:
        """Short hex fingerprint over role, parameter set and public keys."""
        digest = H(sstr(self.role), sstr(self.params.kem), sstr(self.params.sig), self.ek, self.vk)
        text = digest[:10].hex().upper()
        return " ".join(text[i:i + 4] for i in range(0, len(text), 4))

    def to_json(self) -> str:
        return json.dumps({
            "format": "pqpub-1",
            "role": self.role,
            "name": self.name,
            "kem": self.params.kem,
            "sig": self.params.sig,
            "vk": base64.b64encode(self.vk).decode("ascii"),
            "ek": base64.b64encode(self.ek).decode("ascii"),
            "fingerprint": self.fingerprint(),
        }, indent=2)

    @staticmethod
    def from_json(text: str) -> "PublicIdentity":
        try:
            raw = json.loads(text)
            if raw["format"] != "pqpub-1" or raw["role"] not in ROLES:
                raise WireError("not a pqpub file")
            ident = PublicIdentity(
                role=raw["role"], name=str(raw["name"]), params=Params(raw["kem"], raw["sig"]),
                vk=base64.b64decode(raw["vk"]), ek=base64.b64decode(raw["ek"]),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise WireError("malformed pqpub file") from exc
        if raw.get("fingerprint") != ident.fingerprint():
            raise WireError("pqpub fingerprint mismatch")
        return ident

    def to_wire(self) -> dict:
        return {"role": self.role, "name": self.name, "kem": self.params.kem,
                "sig": self.params.sig, "vk": self.vk, "ek": self.ek}

    @staticmethod
    def from_wire(raw: dict) -> "PublicIdentity":
        return PublicIdentity(raw["role"], raw["name"], Params(raw["kem"], raw["sig"]), raw["vk"], raw["ek"])


def export_pub(path: str | Path, ident: PublicIdentity) -> None:
    Path(path).write_text(ident.to_json(), encoding="utf-8")


def import_pub(path: str | Path, expect_role: str | None = None) -> PublicIdentity:
    ident = PublicIdentity.from_json(Path(path).read_text(encoding="utf-8"))
    if expect_role is not None and ident.role != expect_role:
        raise WireError(f"expected a {expect_role} key file, got {ident.role}")
    return ident
