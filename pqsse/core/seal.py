"""Seal and unseal: hybrid public key encryption built from standard parts.

seal(ek, m):   (ct_kem, ss) = ML-KEM.Encaps(ek)
               k = HKDF-SHA3-256(ikm = ss, salt = psk, info = label || H(ct_kem))
               c = AES-256-GCM(k, m, aad)

The optional pre-shared key ``psk`` is mixed in as the HKDF salt. A box sealed with a
psk only opens for a party that holds both the decapsulation key and the psk, which is
how rekey messages are authenticated with the receiver's ``m_v`` (algorithm Revoke).
"""
from __future__ import annotations

from .. import pqbackend
from ..pqbackend import Params
from . import wire
from .errors import VerifyError, WireError
from .prims import H, aead_decrypt, aead_encrypt, hkdf

_INFO = b"pqsse/v3/seal"


def _box_key(shared: bytes, kem_ct: bytes, psk: bytes | None) -> bytes:
    return hkdf(shared, _INFO + H(kem_ct), salt=psk)


def seal(params: Params, ek: bytes, plaintext: bytes, aad: bytes = b"", psk: bytes | None = None) -> bytes:
    """Seal ``plaintext`` to the ML-KEM encapsulation key ``ek``."""
    kem_ct, shared = pqbackend.kem_encaps(params.kem, ek)
    key = _box_key(shared, kem_ct, psk)
    return wire.enc({"k": kem_ct, "c": aead_encrypt(key, plaintext, aad)})


def unseal(params: Params, dk: bytes, box: bytes, aad: bytes = b"", psk: bytes | None = None) -> bytes:
    """Open a sealed box. Raises VerifyError on any failure."""
    try:
        parts = wire.dec(box)
        kem_ct, body = parts["k"], parts["c"]
    except (WireError, KeyError, TypeError) as exc:
        raise VerifyError("unseal", "malformed box") from exc
    try:
        shared = pqbackend.kem_decaps(params.kem, dk, kem_ct)
    except Exception as exc:
        raise VerifyError("unseal", "decapsulation failed") from exc
    return aead_decrypt(_box_key(shared, kem_ct, psk), body, aad, what="unseal")
