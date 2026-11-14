"""First-run calibration of the batch size above which the GPU is faster than the CPU.

Times the fixed length HMAC path (the BuildIndex workload: about 20 byte PRF inputs) on
both engines for growing batch sizes and stores the smallest size where the GPU wins.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import numpy as np

from .batchprf import BatchPRF, CpuPRF

SIZES = (64, 256, 1024, 4096, 16384, 65536)
WIDTH = 21
NEVER = 1 << 30


@dataclass
class Calibration:
    threshold: int
    rows: list[dict] = field(default_factory=list)   # {"n", "cpu_ms", "gpu_ms", "speedup"}


def _time(engine: BatchPRF, key: bytes, mat: np.ndarray, repeats: int) -> float:
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        engine.hmac_fixed(key, mat)
        best = min(best, time.perf_counter() - start)
    return best


def calibrate(gpu: BatchPRF, store: bool = True) -> Calibration:
    """Measure and (by default) store the threshold. Returns the measurements."""
    cpu = CpuPRF()
    key = os.urandom(32)
    warm = np.frombuffer(os.urandom(256 * WIDTH), dtype=np.uint8).reshape(256, WIDTH)
    gpu.hmac_fixed(key, warm)
    result = Calibration(threshold=NEVER)
    for n in SIZES:
        mat = np.frombuffer(os.urandom(n * WIDTH), dtype=np.uint8).reshape(n, WIDTH)
        cpu_s = _time(cpu, key, mat, 3 if n <= 4096 else 1)
        gpu_s = _time(gpu, key, mat, 5)
        result.rows.append({"n": n, "cpu_ms": round(cpu_s * 1000, 3), "gpu_ms": round(gpu_s * 1000, 3),
                            "speedup": round(cpu_s / gpu_s, 2) if gpu_s > 0 else 0.0})
        if result.threshold == NEVER and gpu_s < cpu_s * 0.9:
            result.threshold = n
    if store:
        from . import status

        status.save_threshold(result.threshold, {"rows": result.rows})
    return result
