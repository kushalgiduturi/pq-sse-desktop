"""BatchPRF: one interface for batched HMAC-SHA3-256 and SHA3-256.

Implementations:
  CpuPRF   hashlib based, always available, the reference.
  GpuPRF   CUDA kernel through CuPy (see cuda_kernel.py), only after a passed self-test.
  AutoPRF  uses the GPU above a calibrated batch-size threshold, the CPU below it.

The CPU path contains no hand written hashing: it uses ``hashlib.sha3_256`` objects that
were pre-fed with the HMAC ipad and opad blocks and are copied per message.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Sequence

import numpy as np

RATE = 136  # SHA3-256 rate in bytes, also the HMAC block size
DIGEST = 32


def hmac_block_keys(key: bytes) -> tuple[bytes, bytes]:
    """Return (K xor ipad, K xor opad) as full 136 byte blocks (RFC 2104 with SHA3-256)."""
    if len(key) > RATE:
        key = hashlib.sha3_256(key).digest()
    padded = key.ljust(RATE, b"\x00")
    return bytes(b ^ 0x36 for b in padded), bytes(b ^ 0x5C for b in padded)


def _as_matrix(mat: np.ndarray) -> np.ndarray:
    arr = np.ascontiguousarray(mat, dtype=np.uint8)
    if arr.ndim != 2:
        raise ValueError("expected a 2-D uint8 matrix, one message per row")
    return arr


class BatchPRF(ABC):
    """Batched F = HMAC-SHA3-256 and H = SHA3-256."""

    name: str = "abstract"
    uses_gpu: bool = False

    @abstractmethod
    def hmac_many(self, key: bytes, messages: Sequence[bytes]) -> list[bytes]:
        """HMAC-SHA3-256 of every message under one key (variable lengths)."""

    @abstractmethod
    def hmac_fixed(self, key: bytes, mat: np.ndarray) -> np.ndarray:
        """Fixed length fast path: rows of ``mat`` are messages, returns an (n, 32) matrix."""

    @abstractmethod
    def sha3_many(self, messages: Sequence[bytes]) -> list[bytes]:
        """SHA3-256 of every message."""

    @abstractmethod
    def sha3_fixed(self, mat: np.ndarray) -> np.ndarray:
        """SHA3-256 of every row, returns an (n, 32) matrix."""

    def describe(self) -> str:
        return self.name


class CpuPRF(BatchPRF):
    """Reference implementation on top of hashlib."""

    name = "CPU (hashlib)"
    uses_gpu = False

    def hmac_many(self, key: bytes, messages: Sequence[bytes]) -> list[bytes]:
        ipad, opad = hmac_block_keys(key)
        inner0, outer0 = hashlib.sha3_256(ipad), hashlib.sha3_256(opad)
        out: list[bytes] = []
        for msg in messages:
            inner = inner0.copy()
            inner.update(msg)
            outer = outer0.copy()
            outer.update(inner.digest())
            out.append(outer.digest())
        return out

    def hmac_fixed(self, key: bytes, mat: np.ndarray) -> np.ndarray:
        arr = _as_matrix(mat)
        n, width = arr.shape
        ipad, opad = hmac_block_keys(key)
        inner0, outer0 = hashlib.sha3_256(ipad), hashlib.sha3_256(opad)
        raw = arr.tobytes()
        out = bytearray(n * DIGEST)
        for j in range(n):
            inner = inner0.copy()
            inner.update(raw[j * width:(j + 1) * width])
            outer = outer0.copy()
            outer.update(inner.digest())
            out[j * DIGEST:(j + 1) * DIGEST] = outer.digest()
        return np.frombuffer(bytes(out), dtype=np.uint8).reshape(n, DIGEST)

    def sha3_many(self, messages: Sequence[bytes]) -> list[bytes]:
        return [hashlib.sha3_256(msg).digest() for msg in messages]

    def sha3_fixed(self, mat: np.ndarray) -> np.ndarray:
        arr = _as_matrix(mat)
        n, width = arr.shape
        raw = arr.tobytes()
        out = bytearray(n * DIGEST)
        for j in range(n):
            out[j * DIGEST:(j + 1) * DIGEST] = hashlib.sha3_256(raw[j * width:(j + 1) * width]).digest()
        return np.frombuffer(bytes(out), dtype=np.uint8).reshape(n, DIGEST)


class AutoPRF(BatchPRF):
    """GPU above ``threshold`` messages per call, CPU below."""

    uses_gpu = True

    def __init__(self, gpu: BatchPRF, threshold: int) -> None:
        self.cpu = CpuPRF()
        self.gpu = gpu
        self.threshold = max(1, int(threshold))
        self.name = f"Auto (GPU from {self.threshold} messages, else CPU)"
        self.gpu_calls = 0
        self.cpu_calls = 0

    def _pick(self, n: int) -> BatchPRF:
        if n >= self.threshold:
            self.gpu_calls += 1
            return self.gpu
        self.cpu_calls += 1
        return self.cpu

    def hmac_many(self, key: bytes, messages: Sequence[bytes]) -> list[bytes]:
        return self._pick(len(messages)).hmac_many(key, messages)

    def hmac_fixed(self, key: bytes, mat: np.ndarray) -> np.ndarray:
        return self._pick(len(mat)).hmac_fixed(key, mat)

    def sha3_many(self, messages: Sequence[bytes]) -> list[bytes]:
        return self._pick(len(messages)).sha3_many(messages)

    def sha3_fixed(self, mat: np.ndarray) -> np.ndarray:
        return self._pick(len(mat)).sha3_fixed(mat)

    def describe(self) -> str:
        return f"{self.name} on {self.gpu.describe()}"


def get_prf(mode: str = "auto") -> BatchPRF:
    """Return the engine for ``mode``: "cpu", "gpu" or "auto".

    "gpu" and "auto" fall back to the CPU when no CUDA device is usable or the GPU
    self-test fails. The fallback is silent here, ``pqsse.gpu.status`` reports the reason.
    """
    if mode == "cpu":
        return CpuPRF()
    from . import status

    info = status.gpu_status()
    if not info.usable or info.engine is None:
        return CpuPRF()
    if mode == "gpu":
        return info.engine
    return AutoPRF(info.engine, status.load_threshold())
