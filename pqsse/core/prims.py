"""Symmetric primitives. Thin wrappers only, nothing is implemented here.

H    = SHA3-256                       (hashlib)
F    = HMAC-SHA3-256                  (hmac + hashlib)
HKDF = HKDF with SHA3-256             (cryptography)
AEAD = AES-256-GCM, 96-bit nonce      (cryptography)
"""
from __future__ import annotations

import hashlib
import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .errors import VerifyError
from .wire import sstr, u32

KEY_LEN = 32
NONCE_LEN = 12
DIGEST_LEN = 32


def H(*parts: bytes) -> bytes:
    """SHA3-256 over the concatenation of ``parts``."""
    digest = hashlib.sha3_256()
    for part in parts:
        digest.update(part)
    return digest.digest()


def F(key: bytes, msg: bytes) -> bytes:
    """PRF F = HMAC-SHA3-256."""
    return hmac.new(key, msg, hashlib.sha3_256).digest()


def hkdf(key: bytes, info: bytes, length: int = KEY_LEN, salt: bytes | None = None) -> bytes:
    """HKDF-SHA3-256."""
    return HKDF(algorithm=hashes.SHA3_256(), length=length, salt=salt, info=info).derive(key)


def random_key() -> bytes:
    return os.urandom(KEY_LEN)


def aead_encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM with a fresh random 96-bit nonce. Returns nonce || ciphertext || tag."""
    nonce = os.urandom(NONCE_LEN)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def aead_decrypt(key: bytes, blob: bytes, aad: bytes = b"", what: str = "aead") -> bytes:
    """Inverse of aead_encrypt. Raises VerifyError when authentication fails."""
    if len(blob) < NONCE_LEN + 16:
        raise VerifyError(what, "ciphertext too short")
    try:
        return AESGCM(key).decrypt(blob[:NONCE_LEN], blob[NONCE_LEN:], aad)
    except InvalidTag as exc:
        raise VerifyError(what, "authentication failed") from exc


def group_subkeys(group_key: bytes, group: str, epoch: int) -> tuple[bytes, bytes, bytes]:
    """BuildIndex key derivation: K_idx, K_doc, K_st from K_g^e with labels idx, doc, st."""
    context = sstr(group) + u32(epoch)
    return (
        hkdf(group_key, b"pqsse/v3/idx" + context),
        hkdf(group_key, b"pqsse/v3/doc" + context),
        hkdf(group_key, b"pqsse/v3/st" + context),
    )


def ct_equal(a: bytes, b: bytes) -> bool:
    """Constant time comparison."""
    return hmac.compare_digest(a, b)
