"""Domain separated ML-DSA signing helpers.

Every signature in the system is over ``b"pqsse/v3/sig/" || label || 0x00 || H(payload)``.
The label names the message type (join, cap, cred, batch, state, doc, resp, rekey, ctl),
so a signature for one message type can never be replayed as another.
"""
from __future__ import annotations

from typing import Any

from .. import pqbackend
from ..pqbackend import Params
from . import wire
from .errors import VerifyError
from .prims import H

_PREFIX = b"pqsse/v3/sig/"


def _message(label: str, payload: bytes) -> bytes:
    return _PREFIX + label.encode("ascii") + b"\x00" + H(payload)


def sign_bytes(params: Params, sk: bytes, label: str, payload: bytes) -> bytes:
    """ML-DSA signature over a labelled hash of ``payload``."""
    return pqbackend.sig_sign(params.sig, sk, _message(label, payload))


def check_bytes(params: Params, vk: bytes, label: str, payload: bytes, sig: bytes) -> bool:
    """True when ``sig`` is a valid signature for (label, payload)."""
    return pqbackend.sig_verify(params.sig, vk, _message(label, payload), sig)


def verify_bytes(params: Params, vk: bytes, label: str, payload: bytes, sig: bytes, check: str) -> None:
    """Like check_bytes but raises VerifyError(check) on failure."""
    if not check_bytes(params, vk, label, payload, sig):
        raise VerifyError(check, f"invalid {label} signature")


def sign_obj(params: Params, sk: bytes, label: str, obj: Any) -> bytes:
    """Sign the canonical encoding of ``obj``."""
    return sign_bytes(params, sk, label, wire.enc(obj))


def check_obj(params: Params, vk: bytes, label: str, obj: Any, sig: bytes) -> bool:
    return check_bytes(params, vk, label, wire.enc(obj), sig)
