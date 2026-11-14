"""Host side Keccak-f[1600], used only to precompute keyed HMAC states for the GPU.

HMAC-SHA3-256(K, m) = SHA3(K^opad || SHA3(K^ipad || m)). Both K^ipad and K^opad are
exactly one 136 byte rate block, so the sponge state after absorbing them can be
computed once per key here and handed to the CUDA kernel as its starting state.

This is the standard permutation from FIPS 202, nothing else. It is never used to
produce output directly: the GPU self-test checks the complete result byte for byte
against hashlib and hmac, which also covers this code.
"""
from __future__ import annotations

import numpy as np

from .batchprf import RATE, hmac_block_keys

_MASK = (1 << 64) - 1
ROUND_CONSTANTS = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)
# Rotation offsets r[x][y] of the rho step.
_ROT = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)


def _rol(value: int, shift: int) -> int:
    shift %= 64
    return ((value << shift) | (value >> (64 - shift))) & _MASK if shift else value


def keccak_f(state: list[int]) -> list[int]:
    """Keccak-f[1600], 24 rounds, on 25 lanes indexed x + 5*y."""
    a = list(state)
    for rc in ROUND_CONSTANTS:
        c = [a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        a = [a[i] ^ d[i % 5] for i in range(25)]
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rol(a[x + 5 * y], _ROT[x][y])
        a = [b[i] ^ ((~b[(i % 5 + 1) % 5 + 5 * (i // 5)]) & _MASK & b[(i % 5 + 2) % 5 + 5 * (i // 5)]) for i in range(25)]
        a[0] ^= rc
    return a


def absorb_block(state: list[int], block: bytes) -> list[int]:
    """XOR one 136 byte rate block into the state and permute."""
    if len(block) != RATE:
        raise ValueError("block must be exactly one rate block")
    lanes = list(state)
    for i in range(RATE // 8):
        lanes[i] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
    return keccak_f(lanes)


def host_sha3_256(msg: bytes) -> bytes:
    """SHA3-256 through this module (self-test only, to validate the permutation)."""
    state = [0] * 25
    offset = 0
    while len(msg) - offset >= RATE:
        state = absorb_block(state, msg[offset:offset + RATE])
        offset += RATE
    block = bytearray(msg[offset:].ljust(RATE, b"\x00"))
    block[len(msg) - offset] ^= 0x06
    block[RATE - 1] ^= 0x80
    state = absorb_block(state, bytes(block))
    return b"".join(lane.to_bytes(8, "little") for lane in state[:4])


def hmac_states(key: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Keyed inner and outer sponge states for HMAC-SHA3-256, as uint64[25] arrays."""
    ipad, opad = hmac_block_keys(key)
    inner = absorb_block([0] * 25, ipad)
    outer = absorb_block([0] * 25, opad)
    return np.array(inner, dtype=np.uint64), np.array(outer, dtype=np.uint64)
