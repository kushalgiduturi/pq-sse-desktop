"""Check Inno Setup signature files (.issig, format issig-v2) in Python.

The web installer checks downloads with Inno Setup's own signature support; the in-app update
check and the tests use this module to check the same files the same way. Nothing new is
invented: the signature is ECDSA over P-256 (the `cryptography` package does the math), and the
signed data is the one Inno Setup's ISSigFunc.pas builds:

    SHA-256( u32 len(name) || name || u32 len(tag) || tag || i64 size || 32-byte SHA-256 of the file )

with little-endian integers and UTF-8 strings. key-id is SHA-256(public_x || public_y).
"""
from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


class SignatureError(Exception):
    """The signature file is malformed, from an unknown key, or does not match."""


@dataclass(frozen=True)
class PublicKey:
    key_id: str
    x: str
    y: str


def _fields(text: str) -> dict[str, str]:
    if len(text) > 2500:
        raise SignatureError("the signature file is too long")
    out: dict[str, str] = {}
    for line in text.replace("\r\n", "\n").split("\n"):
        if not line:
            continue
        name, _, value = line.partition(" ")
        if not value or name in out:
            raise SignatureError(f"malformed line in the signature file: {line[:40]!r}")
        out[name] = value
    return out


def parse_public_key(text: str) -> PublicKey:
    f = _fields(text)
    if f.get("format") != "issig-public-key":
        raise SignatureError("not an Inno Setup public key")
    for name in ("key-id", "public-x", "public-y"):
        if not _HEX64.match(f.get(name, "")):
            raise SignatureError(f"bad {name} in the public key")
    key = PublicKey(f["key-id"].lower(), f["public-x"].lower(), f["public-y"].lower())
    if hashlib.sha256(bytes.fromhex(key.x + key.y)).hexdigest() != key.key_id:
        raise SignatureError("the public key does not match its key-id")
    return key


def _quoted(value: str) -> str:
    if len(value) < 2 or value[0] != '"' or value[-1] != '"' or '"' in value[1:-1]:
        raise SignatureError("bad quoted value in the signature file")
    return value[1:-1]


def verify(signature_text: str, data: bytes, keys: list[PublicKey], expected_name: str | None = None) -> str:
    """Check `data` against an issig-v2 signature from one of `keys`. Returns the key-id used.

    Raises SignatureError when the signature is malformed, made with an unknown key, does not
    verify, or when the size, the SHA-256 or (if given) the file name does not match."""
    f = _fields(signature_text)
    if f.get("format") != "issig-v2":
        raise SignatureError("unsupported signature format (issig-v2 expected)")
    for name in ("file-name", "file-size", "file-hash", "file-tag", "key-id", "sig-r", "sig-s"):
        if name not in f:
            raise SignatureError(f"the signature file has no {name}")
    name, tag = _quoted(f["file-name"]), _quoted(f["file-tag"])
    if not re.fullmatch(r"0|[1-9][0-9]{0,15}", f["file-size"]):
        raise SignatureError("bad file-size in the signature file")
    for field in ("file-hash", "key-id", "sig-r", "sig-s"):
        if not _HEX64.match(f[field]):
            raise SignatureError(f"bad {field} in the signature file")
    key = next((k for k in keys if k.key_id == f["key-id"].lower()), None)
    if key is None:
        raise SignatureError("the file was signed with a key this program does not trust")
    size, file_hash = int(f["file-size"]), bytes.fromhex(f["file-hash"])
    name_bytes, tag_bytes = name.encode("utf-8"), tag.encode("utf-8")
    preimage = (struct.pack("<I", len(name_bytes)) + name_bytes + struct.pack("<I", len(tag_bytes)) + tag_bytes
                + struct.pack("<q", size) + file_hash)
    digest = hashlib.sha256(preimage).digest()
    public = ec.EllipticCurvePublicNumbers(int(key.x, 16), int(key.y, 16), ec.SECP256R1()).public_key()
    signature = utils.encode_dss_signature(int(f["sig-r"], 16), int(f["sig-s"], 16))
    try:
        public.verify(signature, digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())))
    except InvalidSignature:
        raise SignatureError("the signature does not verify") from None
    if len(data) != size:
        raise SignatureError(f"size mismatch: {len(data)} bytes, the signature says {size}")
    if hashlib.sha256(data).digest() != file_hash:
        raise SignatureError("SHA-256 mismatch: the file is not the one that was signed")
    if expected_name is not None and name != expected_name:
        raise SignatureError(f"the signature is for {name!r}, not {expected_name!r}")
    return key.key_id
