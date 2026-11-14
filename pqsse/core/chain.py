"""Per keyword hash chain used by BuildIndex, Update, Publish and Verify.

d_i = H(d_{i-1} || a_i || v_i), with d_{-1} = 32 zero bytes.
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Iterable, Sequence

import numpy as np

if TYPE_CHECKING:
    from ..gpu.batchprf import BatchPRF

CHAIN_START = bytes(32)


def chain_step(prev: bytes, addr: bytes, value: bytes) -> bytes:
    """One link: H(prev || addr || value)."""
    return hashlib.sha3_256(prev + addr + value).digest()


def update_heads(prf: "BatchPRF", heads: list[bytes], slots: Sequence[int],
                 addrs: np.ndarray, vals: np.ndarray) -> None:
    """Advance many chains at once (BuildIndex, Update).

    Item j extends chain ``slots[j]`` with (addrs[j], vals[j]); items of one chain are
    applied in order. A chain is sequential, so the only parallelism is across chains:
    "level" t holds the t-th new link of every chain and is one fixed width SHA3 batch.
    Levels that are large enough go through the batch engine (GPU), the rest runs on
    the CPU. The result is identical either way.
    """
    n = len(slots)
    if n == 0:
        return
    raw_a, raw_v = addrs.tobytes(), vals.tobytes()
    threshold = getattr(prf, "threshold", 1) if prf.uses_gpu else n + 1
    done = np.zeros(n, dtype=bool)
    if n >= threshold:
        seen: dict[int, int] = {}
        level = np.empty(n, dtype=np.int64)
        for j, slot in enumerate(slots):
            level[j] = seen.get(slot, 0)
            seen[slot] = level[j] + 1
        slot_arr = np.asarray(slots, dtype=np.int64)
        head_mat = np.frombuffer(b"".join(heads), dtype=np.uint8).reshape(len(heads), 32).copy()
        current = 0
        while True:
            idx = np.nonzero(level == current)[0]
            if len(idx) < threshold:
                break
            mat = np.concatenate([head_mat[slot_arr[idx]], addrs[idx], vals[idx]], axis=1)
            head_mat[slot_arr[idx]] = prf.sha3_fixed(mat)
            done[idx] = True
            current += 1
        for slot in set(slots):
            heads[slot] = head_mat[slot].tobytes()
    for j in range(n):
        if not done[j]:
            slot = slots[j]
            heads[slot] = hashlib.sha3_256(heads[slot] + raw_a[j * 32:(j + 1) * 32] + raw_v[j * 5:(j + 1) * 5]).digest()


def chain_fold(start: bytes, entries: Iterable[tuple[bytes, bytes]]) -> bytes:
    """Fold a sequence of (address, value) pairs into the chain head."""
    head = start
    for addr, value in entries:
        head = hashlib.sha3_256(head + addr + value).digest()
    return head
