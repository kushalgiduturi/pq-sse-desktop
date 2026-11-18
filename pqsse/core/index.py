"""Index entry layout shared by owner (BuildIndex, Update) and receiver (TokenGen, Verify).

For keyword w and occurrence index i:
    address  a_i = F(K_idx, sstr(w) || u32(i) || 0x00)
    mask     p_i = F(K_idx, sstr(w) || u32(i) || 0x01)[0:5]
    value    v_i = (op || id) XOR p_i          with op one byte, id a u32

``derive`` evaluates F for a whole batch through a BatchPRF. Messages are grouped by
keyword byte length so every group is a fixed width NumPy matrix (the fast path).
"""
from __future__ import annotations

import hashlib
from typing import Sequence

import numpy as np

from ..gpu.batchprf import BatchPRF
from .prims import F, hkdf
from .wire import sstr, u32

ADDR_LEN = 32
VAL_LEN = 5
OP_ADD = 1
OP_DEL = 2
TAG_LEN = 8


def prf_message(keyword: str, i: int, selector: int) -> bytes:
    """The PRF input sstr(w) || u32(i) || selector."""
    return sstr(keyword) + u32(i) + bytes([selector])


def keyword_tag(keyword: str) -> bytes:
    """H(w)[:8] as stored in the published state."""
    return hashlib.sha3_256(sstr(keyword)).digest()[:TAG_LEN]


def pack_value(op: int, doc_id: int) -> bytes:
    return bytes([op]) + u32(doc_id)


def unpack_value(raw: bytes) -> tuple[int, int]:
    return raw[0], int.from_bytes(raw[1:5], "big")


def xor5(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def derive(prf: BatchPRF, k_idx: bytes, items: Sequence[tuple[str, int]]) -> tuple[np.ndarray, np.ndarray]:
    """Batch derivation of addresses and masks.

    ``items`` is a sequence of (keyword, occurrence index). Returns
    (addresses as an (n, 32) uint8 matrix, masks as an (n, 5) uint8 matrix).
    """
    n = len(items)
    addrs = np.zeros((n, ADDR_LEN), dtype=np.uint8)
    masks = np.zeros((n, VAL_LEN), dtype=np.uint8)
    if n == 0:
        return addrs, masks
    groups: dict[int, list[int]] = {}
    encoded: list[bytes] = []
    for pos, (keyword, _) in enumerate(items):
        raw = keyword.encode("utf-8")
        encoded.append(raw)
        groups.setdefault(len(raw), []).append(pos)
    for length, positions in groups.items():
        m = len(positions)
        width = 4 + length + 4 + 1
        mat = np.zeros((2 * m, width), dtype=np.uint8)
        mat[:, 0:4] = np.frombuffer(u32(length), dtype=np.uint8)
        if length:
            joined = b"".join(encoded[p] for p in positions)
            kw = np.frombuffer(joined, dtype=np.uint8).reshape(m, length)
            mat[:m, 4:4 + length] = kw
            mat[m:, 4:4 + length] = kw
        counters = np.array([items[p][1] for p in positions], dtype=">u4").view(np.uint8).reshape(m, 4)
        mat[:m, 4 + length:8 + length] = counters
        mat[m:, 4 + length:8 + length] = counters
        mat[m:, width - 1] = 1
        out = prf.hmac_fixed(k_idx, mat)
        index = np.array(positions, dtype=np.int64)
        addrs[index] = out[:m]
        masks[index] = out[m:, :VAL_LEN]
    return addrs, masks


def doc_handle(k_doc: bytes, doc_id: int) -> bytes:
    """Storage handle of a document at the cloud (hides the plain id)."""
    return F(k_doc, b"handle" + u32(doc_id))[:16]


def doc_aad(group: str, epoch: int, doc_id: int) -> bytes:
    """Associated data g || e || id of a document ciphertext."""
    return sstr(group) + u32(epoch) + u32(doc_id)


def token_key(a_u: bytes) -> bytes:
    """Key that protects receiver requests (tokens), derived from the credential a_u."""
    return hkdf(a_u, b"pqsse/v3/token")


def token_aad(uid: str, endpoint: str) -> bytes:
    return uid.encode("ascii") + b"/" + endpoint.encode("ascii")


# AAD label of the encrypted search response (design note 001, paper Algorithm 7 step 5)
RESPONSE_LABEL = "search-response"
