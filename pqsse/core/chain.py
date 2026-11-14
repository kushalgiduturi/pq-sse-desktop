"""Per keyword hash chain used by BuildIndex, Update, Publish and Verify.

d_i = H(d_{i-1} || a_i || v_i), with d_{-1} = 32 zero bytes.
"""
from __future__ import annotations

import hashlib
from typing import Iterable

CHAIN_START = bytes(32)


def chain_step(prev: bytes, addr: bytes, value: bytes) -> bytes:
    """One link: H(prev || addr || value)."""
    return hashlib.sha3_256(prev + addr + value).digest()


def chain_fold(start: bytes, entries: Iterable[tuple[bytes, bytes]]) -> bytes:
    """Fold a sequence of (address, value) pairs into the chain head."""
    head = start
    for addr, value in entries:
        head = hashlib.sha3_256(head + addr + value).digest()
    return head
