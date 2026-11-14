"""CUDA engine: batched Keccak-f[1600] / SHA3-256 / HMAC-SHA3-256 through CuPy RawKernel.

One GPU thread per message. 64-bit lanes, 24 rounds, rate 136 bytes, SHA3 domain byte
0x06 and final bit 0x80. For HMAC the keyed inner and outer states are precomputed once
per key on the host (keccak_host.hmac_states), so a short message costs two permutations.

This module imports CuPy at import time. Import it only through ``pqsse.gpu.status``,
which handles a missing CuPy or a missing CUDA device.
"""
from __future__ import annotations

from typing import Sequence

import cupy as cp
import numpy as np

from .batchprf import DIGEST, BatchPRF, _as_matrix
from .keccak_host import hmac_states

_SOURCE = r"""
typedef unsigned long long u64;

__device__ __forceinline__ u64 rotl64(u64 x, int n) { return (x << n) | (x >> (64 - n)); }

__device__ void keccak_f1600(u64 st[25]) {
    const u64 RC[24] = {
        0x0000000000000001ULL, 0x0000000000008082ULL, 0x800000000000808AULL, 0x8000000080008000ULL,
        0x000000000000808BULL, 0x0000000080000001ULL, 0x8000000080008081ULL, 0x8000000000008009ULL,
        0x000000000000008AULL, 0x0000000000000088ULL, 0x0000000080008009ULL, 0x000000008000000AULL,
        0x000000008000808BULL, 0x800000000000008BULL, 0x8000000000008089ULL, 0x8000000000008003ULL,
        0x8000000000008002ULL, 0x8000000000000080ULL, 0x000000000000800AULL, 0x800000008000000AULL,
        0x8000000080008081ULL, 0x8000000000008080ULL, 0x0000000080000001ULL, 0x8000000080008008ULL};
    const int ROTC[24] = {1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14, 27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44};
    const int PILN[24] = {10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4, 15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1};
    u64 t, bc[5];
    for (int r = 0; r < 24; r++) {
        for (int i = 0; i < 5; i++) bc[i] = st[i] ^ st[i + 5] ^ st[i + 10] ^ st[i + 15] ^ st[i + 20];   /* theta */
        for (int i = 0; i < 5; i++) {
            t = bc[(i + 4) % 5] ^ rotl64(bc[(i + 1) % 5], 1);
            for (int j = 0; j < 25; j += 5) st[j + i] ^= t;
        }
        t = st[1];                                                                                    /* rho, pi */
        for (int i = 0; i < 24; i++) {
            int j = PILN[i];
            bc[0] = st[j];
            st[j] = rotl64(t, ROTC[i]);
            t = bc[0];
        }
        for (int j = 0; j < 25; j += 5) {                                                             /* chi */
            for (int i = 0; i < 5; i++) bc[i] = st[j + i];
            for (int i = 0; i < 5; i++) st[j + i] ^= (~bc[(i + 1) % 5]) & bc[(i + 2) % 5];
        }
        st[0] ^= RC[r];                                                                               /* iota */
    }
}

/* Absorb a whole message with SHA3 padding. The state must be at a block boundary. */
__device__ void sha3_absorb(u64 st[25], const unsigned char* msg, long long len) {
    long long off = 0;
    while (len - off >= 136) {
        for (int i = 0; i < 17; i++) {
            u64 w = 0;
            for (int b = 0; b < 8; b++) w |= ((u64)msg[off + 8 * i + b]) << (8 * b);
            st[i] ^= w;
        }
        keccak_f1600(st);
        off += 136;
    }
    int rem = (int)(len - off);
    for (int i = 0; i < 17; i++) {
        u64 w = 0;
        for (int b = 0; b < 8; b++) {
            int p = 8 * i + b;
            unsigned char c = (p < rem) ? msg[off + p] : 0;
            if (p == rem) c ^= 0x06;      /* SHA3 domain separation */
            if (p == 135) c ^= 0x80;      /* final bit of pad10*1 */
            w |= ((u64)c) << (8 * b);
        }
        st[i] ^= w;
    }
    keccak_f1600(st);
}

/* mode 0: HMAC-SHA3-256 from the keyed inner/outer states.  mode 1: plain SHA3-256. */
extern "C" __global__ void pqsse_keccak_batch(
        const unsigned char* data, const long long* offsets, const int* lengths,
        long long stride, int fixed, const u64* inner, const u64* outer, int mode,
        unsigned char* out, long long n) {
    long long idx = (long long)blockIdx.x * (long long)blockDim.x + (long long)threadIdx.x;
    if (idx >= n) return;
    const unsigned char* msg = fixed ? (data + idx * stride) : (data + offsets[idx]);
    long long len = fixed ? stride : (long long)lengths[idx];
    u64 st[25];
    if (mode == 0) { for (int i = 0; i < 25; i++) st[i] = inner[i]; }
    else           { for (int i = 0; i < 25; i++) st[i] = 0; }
    sha3_absorb(st, msg, len);
    if (mode == 0) {
        u64 o[25];
        for (int i = 0; i < 25; i++) o[i] = outer[i];
        o[0] ^= st[0]; o[1] ^= st[1]; o[2] ^= st[2]; o[3] ^= st[3];   /* 32 byte inner digest */
        o[4] ^= 0x06ULL;                                              /* padding byte at offset 32 */
        o[16] ^= 0x8000000000000000ULL;                               /* final bit at offset 135 */
        keccak_f1600(o);
        for (int i = 0; i < 4; i++) st[i] = o[i];
    }
    unsigned char* dst = out + idx * 32;
    for (int i = 0; i < 4; i++)
        for (int b = 0; b < 8; b++) dst[8 * i + b] = (unsigned char)(st[i] >> (8 * b));
}
"""

_BLOCK = 256


class GpuPRF(BatchPRF):
    """BatchPRF on one CUDA device."""

    uses_gpu = True

    def __init__(self, device: int = 0, budget_bytes: int | None = None) -> None:
        self.device_id = device
        self.device = cp.cuda.Device(device)
        with self.device:
            self._kernel = cp.RawKernel(_SOURCE, "pqsse_keccak_batch")
            self._kernel.compile()
            props = cp.cuda.runtime.getDeviceProperties(device)
            free, total = self.device.mem_info
        raw_name = props["name"]
        self.device_name = raw_name.decode() if isinstance(raw_name, bytes) else str(raw_name)
        self.total_mem = int(total)
        self.name = f"GPU ({self.device_name})"
        # Chunk size: at most a quarter of the free memory, capped at 512 MB per launch.
        self.budget = int(budget_bytes or max(16 << 20, min(free // 4, 512 << 20)))
        self._zero_state = np.zeros(25, dtype=np.uint64)
        self._state_cache: dict[bytes, tuple[np.ndarray, np.ndarray]] = {}

    def describe(self) -> str:
        return f"{self.device_name}, {self.total_mem / 2**30:.1f} GB"

    def mem_info(self) -> tuple[int, int]:
        with self.device:
            free, total = self.device.mem_info
        return int(free), int(total)

    def _states(self, key: bytes | None) -> tuple[np.ndarray, np.ndarray]:
        if key is None:
            return self._zero_state, self._zero_state
        cached = self._state_cache.get(key)
        if cached is None:
            if len(self._state_cache) > 64:
                self._state_cache.clear()
            cached = self._state_cache[key] = hmac_states(key)
        return cached

    def _launch(self, data: np.ndarray, offsets: np.ndarray, lengths: np.ndarray, stride: int,
                fixed: bool, key: bytes | None, n: int) -> np.ndarray:
        inner, outer = self._states(key)
        with self.device:
            d_data = cp.asarray(data if data.size else np.zeros(1, dtype=np.uint8))
            d_off = cp.asarray(offsets)
            d_len = cp.asarray(lengths)
            d_inner, d_outer = cp.asarray(inner), cp.asarray(outer)
            d_out = cp.empty(n * DIGEST, dtype=cp.uint8)
            grid = ((n + _BLOCK - 1) // _BLOCK,)
            self._kernel(grid, (_BLOCK,), (d_data, d_off, d_len, np.int64(stride), np.int32(1 if fixed else 0),
                                           d_inner, d_outer, np.int32(0 if key is not None else 1), d_out, np.int64(n)))
            return cp.asnumpy(d_out).reshape(n, DIGEST)

    def _fixed(self, key: bytes | None, mat: np.ndarray) -> np.ndarray:
        arr = _as_matrix(mat)
        n, width = arr.shape
        if n == 0:
            return np.zeros((0, DIGEST), dtype=np.uint8)
        if width == 0:
            return self._variable(key, [b""] * n)
        rows = max(1, self.budget // (width + DIGEST))
        dummy_off, dummy_len = np.zeros(1, dtype=np.int64), np.zeros(1, dtype=np.int32)
        parts = [self._launch(arr[s:s + rows].reshape(-1), dummy_off, dummy_len, width, True, key, min(rows, n - s))
                 for s in range(0, n, rows)]
        return parts[0] if len(parts) == 1 else np.concatenate(parts, axis=0)

    def _variable(self, key: bytes | None, messages: Sequence[bytes]) -> np.ndarray:
        n = len(messages)
        if n == 0:
            return np.zeros((0, DIGEST), dtype=np.uint8)
        lengths = np.fromiter((len(m) for m in messages), dtype=np.int32, count=n)
        parts = []
        start = 0
        while start < n:
            end, size = start, 0
            while end < n and (end == start or size + int(lengths[end]) + DIGEST <= self.budget):
                size += int(lengths[end]) + DIGEST
                end += 1
            chunk_len = lengths[start:end]
            offsets = np.zeros(end - start, dtype=np.int64)
            np.cumsum(chunk_len[:-1], out=offsets[1:])
            data = np.frombuffer(b"".join(messages[start:end]), dtype=np.uint8)
            parts.append(self._launch(data, offsets, chunk_len, 0, False, key, end - start))
            start = end
        return parts[0] if len(parts) == 1 else np.concatenate(parts, axis=0)

    # ------------------------------------------------------------------ BatchPRF interface
    def hmac_many(self, key: bytes, messages: Sequence[bytes]) -> list[bytes]:
        out = self._variable(key, messages).tobytes()
        return [out[i * DIGEST:(i + 1) * DIGEST] for i in range(len(messages))]

    def hmac_fixed(self, key: bytes, mat: np.ndarray) -> np.ndarray:
        return self._fixed(key, mat)

    def sha3_many(self, messages: Sequence[bytes]) -> list[bytes]:
        out = self._variable(None, messages).tobytes()
        return [out[i * DIGEST:(i + 1) * DIGEST] for i in range(len(messages))]

    def sha3_fixed(self, mat: np.ndarray) -> np.ndarray:
        return self._fixed(None, mat)
