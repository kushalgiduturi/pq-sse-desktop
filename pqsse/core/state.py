"""Published state ST_{g,e} (algorithm Publish) and its checks (algorithm Verify).

Plaintext: u32 record count, then records (H(w)[:8] || u32 c_w || d_w) sorted by tag,
zero padded to N_max records. Encrypted with AES-256-GCM under K_st with the header as
associated data. Header: (g, e, ver, exp, final, base). The owner signs
header || H(ciphertext) under the label "state".
"""
from __future__ import annotations

from dataclasses import dataclass

from ..pqbackend import Params
from . import signing, wire
from .errors import VerifyError, WireError
from .index import TAG_LEN
from .prims import H, aead_decrypt, aead_encrypt
from .wire import u32

RECORD_LEN = TAG_LEN + 4 + 32
DEFAULT_NMAX = 1024


@dataclass(frozen=True)
class StateHeader:
    g: str
    e: int
    ver: int
    exp: int      # expiry, unix milliseconds
    final: bool
    base: int     # oldest live epoch of the group

    def encode(self) -> bytes:
        return wire.enc({"g": self.g, "e": self.e, "ver": self.ver, "exp": self.exp,
                         "final": self.final, "base": self.base})

    @staticmethod
    def decode(raw: bytes) -> "StateHeader":
        try:
            d = wire.dec(raw)
            return StateHeader(d["g"], d["e"], d["ver"], d["exp"], bool(d["final"]), d["base"])
        except (WireError, KeyError, TypeError) as exc:
            raise VerifyError("state signature", "malformed state header") from exc


def fit_nmax(count: int, nmax: int) -> int:
    """Smallest power-of-two multiple of nmax that holds ``count`` records."""
    while nmax < count:
        nmax *= 2
    return nmax


def encode_records(records: dict[bytes, tuple[int, bytes]], nmax: int) -> bytes:
    """Serialize and pad the record table."""
    if len(records) > nmax:
        raise ValueError("more records than N_max")
    body = bytearray(u32(len(records)))
    for tag in sorted(records):
        count, head = records[tag]
        body += tag + u32(count) + head
    body += bytes(RECORD_LEN * (nmax - len(records)))
    return bytes(body)


def decode_records(plain: bytes) -> dict[bytes, tuple[int, bytes]]:
    count = int.from_bytes(plain[:4], "big")
    if 4 + count * RECORD_LEN > len(plain):
        raise VerifyError("state signature", "state body is inconsistent")
    out: dict[bytes, tuple[int, bytes]] = {}
    for i in range(count):
        rec = plain[4 + i * RECORD_LEN:4 + (i + 1) * RECORD_LEN]
        out[rec[:TAG_LEN]] = (int.from_bytes(rec[TAG_LEN:TAG_LEN + 4], "big"), rec[TAG_LEN + 4:])
    return out


def make_state(params: Params, owner_sk: bytes, k_st: bytes, header: StateHeader,
               records: dict[bytes, tuple[int, bytes]], nmax: int) -> dict:
    """Algorithm 5 Publish: build the signed, encrypted, padded state message."""
    hdr = header.encode()
    ct = aead_encrypt(k_st, encode_records(records, nmax), hdr)
    sig = signing.sign_bytes(params, owner_sk, "state", hdr + H(ct))
    return {"hdr": hdr, "ct": ct, "sig": sig}


def check_state_signature(params: Params, owner_vk: bytes, msg: dict) -> StateHeader:
    """Verify the owner's signature on a state message and return its header."""
    try:
        hdr, ct, sig = msg["hdr"], msg["ct"], msg["sig"]
    except (KeyError, TypeError) as exc:
        raise VerifyError("state signature", "malformed state message") from exc
    signing.verify_bytes(params, owner_vk, "state", hdr + H(ct), sig, check="state signature")
    return StateHeader.decode(hdr)


def open_state(k_st: bytes, msg: dict) -> dict[bytes, tuple[int, bytes]]:
    """Decrypt a state whose signature has already been checked."""
    return decode_records(aead_decrypt(k_st, msg["ct"], msg["hdr"], what="state signature"))
