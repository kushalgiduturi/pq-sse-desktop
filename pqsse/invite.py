"""Invites: how a receiver on another computer learns where the server is and whose keys to trust.

Design note 002 (approved 2026-11-18). An invite carries the server address, the SHA-256 of the server's TLS
certificate (the client pins it), the fingerprints of the server's and the data owner's post-quantum public
keys, a random invite id, a one-time code and an expiry. It travels as a small file (``*.pqinvite``, JSON) or
as a link ``pqsse://host:port/join?...``. The code may travel with it or, safer, by a second channel.

The code never leaves the receiver's computer. From it the receiver derives two keys:
    k_server = HKDF-SHA3-256(code, "pqsse/v3/invite/server")    registered at the server by the owner
    k_owner  = HKDF-SHA3-256(code, "pqsse/v3/invite/owner")     kept by the owner
and sends two proofs over the hash of its signed join request: HMAC-SHA3-256(k_server, "join" || H(req)) for
the server, which stores a request only for a registered, unexpired, unused invite, and the same with
k_owner for the owner, which checks it again. The server holds k_server only, so it cannot forge the
owner's proof.

Fingerprints are also shown as six words from the 256-word list below (48 bits), for comparing by voice.
"""
from __future__ import annotations

import hmac
import json
import os
import time
import urllib.parse
from dataclasses import asdict, dataclass

from .core.prims import F, H, hkdf

VERSION = 1
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"     # no 0, 1, I, O: easy to read aloud
DEFAULT_DAYS = 7.0


class InviteError(ValueError):
    """An invite that cannot be used: malformed, wrong version, expired."""


@dataclass
class Invite:
    v: int
    host: str
    port: int
    tls: str               # SHA-256 of the server certificate, 64 hex
    server_fp: str         # fingerprint of the server's public keys
    owner_fp: str          # fingerprint of the data owner's public key
    id: str                # 32 hex
    expires: float         # unix seconds
    name: str = ""         # the person the owner meant it for (shown, not enforced)
    code: str = ""         # empty when the code travels separately

    def to_file(self, include_code: bool = False) -> str:
        data = asdict(self)
        if not include_code:
            data["code"] = ""
        return json.dumps(data, indent=2)

    def to_link(self, include_code: bool = False) -> str:
        query = {"v": self.v, "tls": self.tls, "s": self.server_fp.replace(" ", ""), "o": self.owner_fp.replace(" ", ""),
                 "id": self.id, "exp": int(self.expires), "n": self.name}
        if include_code and self.code:
            query["c"] = self.code
        return f"pqsse://{self.host}:{self.port}/join?" + urllib.parse.urlencode(query)

    @property
    def expired(self) -> bool:
        return time.time() > self.expires


def new_code(length: int = 12) -> str:
    """A one-time code like 7KQM-X3PA-9TRD: 60 bits, grouped for reading."""
    raw = "".join(CODE_ALPHABET[b % len(CODE_ALPHABET)] for b in os.urandom(length))
    return "-".join(raw[i:i + 4] for i in range(0, length, 4))


def normalise_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def keys_from_code(code: str) -> tuple[bytes, bytes]:
    """(k_server, k_owner) from the one-time code."""
    raw = normalise_code(code).encode("ascii")
    if len(raw) < 8:
        raise InviteError("the invite code is too short")
    return hkdf(raw, b"pqsse/v3/invite/server"), hkdf(raw, b"pqsse/v3/invite/owner")


def proof(key: bytes, request: bytes) -> bytes:
    return F(key, b"join" + H(request))


def check_proof(key: bytes, request: bytes, given: bytes) -> bool:
    return hmac.compare_digest(proof(key, request), given)


def new_invite(host: str, port: int, tls: str, server_fp: str, owner_fp: str, name: str = "",
               days: float = DEFAULT_DAYS) -> Invite:
    return Invite(VERSION, host, int(port), tls.replace(" ", "").lower(), server_fp, owner_fp,
                  os.urandom(16).hex(), time.time() + days * 86400.0, name, new_code())


def parse(text: str) -> Invite:
    """An invite from the contents of a .pqinvite file or from a pqsse:// link."""
    text = text.strip()
    try:
        if text.startswith("pqsse://"):
            url = urllib.parse.urlsplit(text)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
            invite = Invite(int(q["v"]), url.hostname or "", int(url.port or 8443), q["tls"], q["s"], q["o"], q["id"],
                            float(q["exp"]), q.get("n", ""), q.get("c", ""))
        else:
            data = json.loads(text)
            invite = Invite(**{k: data[k] for k in Invite.__dataclass_fields__ if k in data})
    except (KeyError, ValueError, TypeError) as exc:
        raise InviteError("this is not a PQ-SSE invite") from exc
    if invite.v != VERSION:
        raise InviteError(f"invite version {invite.v} is not supported by this app")
    if len(invite.tls) != 64 or len(invite.id) != 32 or not invite.host:
        raise InviteError("the invite is incomplete")
    return invite


# 256 short, distinct, common English words (one per byte). Written for this project.
WORDS = """
able acid aged also arch area army atom aunt away axis baby back bake ball band bank barn base bath beam bean
bear beef bell belt bend best bike bird bite blue boat body bold bolt bone book boot born boss bowl bulb bush
busy cafe cage cake calm camp card care cart case cash cast cave cell chef chin chip city clay clip club coal
coat code coin cold cook cool copy cord corn cost crab crew crop cube curl cute dark data date dawn deck deep
deer desk dial diet dirt dish dock doll door dose dove down drum duck dusk dust duty each east easy echo edge
egg else epic even exit face fact fair farm fast fern file film fine fire firm fish flag flat flow foam fold
folk food foot fork form fort four frog fuel full gate gear gift girl glad glow glue goal goat gold golf good
gown grab gray grid grin grip gulf hair half hall hand harp hawk heat herb hero hill hint hive hold home hood
hook horn host hour huge hunt idea inch iron isle item jade jazz joke jump jury keen kept kick kind king kite
knee knot lace lake lamp land lane last lava lawn leaf lean left lens lily lime line link lion list loaf lock
loft long loop lord loud love luck lung made mail main malt many maps mark mask mast meal melt menu mild milk
mill mind mint mist mode moon moss moth move much mule nail navy neat neck nest news nice nine node noon nose
note oak oath oval oven owl pack page
""".split()[:256]
assert len(WORDS) == 256 and len(set(WORDS)) == 256


def words(fingerprint: str, count: int = 6) -> str:
    """Six words for a fingerprint (hex, any spacing): the first six bytes, one word each."""
    raw = bytes.fromhex("".join(ch for ch in fingerprint if ch in "0123456789abcdefABCDEF")[: 2 * count])
    return " ".join(WORDS[b] for b in raw)
