"""GPU detection, self-test and the stored batch-size threshold.

``gpu_status()`` is the only place that decides whether the GPU path may be used:
a CUDA device must exist, the kernel must compile, and the self-test must match
hashlib and hmac byte for byte. Otherwise the reason is recorded and the app runs on CPU.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import threading
import time
from dataclasses import dataclass, field

import numpy as np

from .. import paths
from .batchprf import BatchPRF, CpuPRF

DEFAULT_THRESHOLD = 4096
SELFTEST_MESSAGES = 1000
_EDGE_LENGTHS = (0, 1, 31, 32, 33, 135, 136, 137, 271, 272, 273, 408, 600)


@dataclass
class SelfTestReport:
    passed: bool
    checked: int = 0
    mismatches: int = 0
    seconds: float = 0.0
    lines: list[str] = field(default_factory=list)


@dataclass
class GpuStatus:
    available: bool = False          # a CUDA device and CuPy are present
    usable: bool = False             # available and the self-test passed
    device: str = "none"
    total_mem: int = 0
    free_mem: int = 0
    cupy_version: str = ""
    driver: str = ""
    reason: str = ""                 # why the GPU path is off, when it is
    engine: BatchPRF | None = None
    selftest: SelfTestReport | None = None

    def summary(self) -> str:
        if self.usable:
            return f"GPU: {self.device}, {self.total_mem / 2**30:.1f} GB (self-test passed)"
        return f"GPU: not used, running on CPU ({self.reason})"


def run_selftest(engine: BatchPRF, n: int = SELFTEST_MESSAGES, seed: int | None = None) -> SelfTestReport:
    """Compare an engine with hashlib and hmac, byte for byte.

    n random messages of varied lengths (including every block boundary), several keys
    (short, 32 bytes, exactly one block, longer than a block), variable and fixed paths.
    """
    rng = random.Random(seed if seed is not None else int.from_bytes(os.urandom(8), "big"))
    report = SelfTestReport(passed=True)
    start = time.perf_counter()

    def compare(label: str, got: list[bytes], want: list[bytes]) -> None:
        bad = sum(1 for g, w in zip(got, want) if g != w) + abs(len(got) - len(want))
        report.checked += len(want)
        report.mismatches += bad
        report.lines.append(f"{'ok  ' if bad == 0 else 'FAIL'} {label}: {len(want)} digests, {bad} mismatches")

    try:
        from .keccak_host import host_sha3_256

        probes = [rng.randbytes(length) for length in _EDGE_LENGTHS]
        compare("host Keccak-f vs hashlib.sha3_256", [host_sha3_256(m) for m in probes],
                [hashlib.sha3_256(m).digest() for m in probes])
        lengths = list(_EDGE_LENGTHS) + [rng.randrange(0, 700) for _ in range(n - len(_EDGE_LENGTHS))]
        messages = [rng.randbytes(length) for length in lengths]
        compare("SHA3-256, variable length vs hashlib", engine.sha3_many(messages),
                [hashlib.sha3_256(m).digest() for m in messages])
        for key_len in (32, 1, 136, 200):
            key = rng.randbytes(key_len)
            compare(f"HMAC-SHA3-256, variable length, {key_len} byte key vs hmac", engine.hmac_many(key, messages),
                    [hmac.new(key, m, hashlib.sha3_256).digest() for m in messages])
        key = rng.randbytes(32)
        for width in (1, 21, 69, 135, 136, 137, 300):
            rows = 257
            mat = np.frombuffer(rng.randbytes(rows * width), dtype=np.uint8).reshape(rows, width)
            got = engine.hmac_fixed(key, mat)
            compare(f"HMAC-SHA3-256, fixed width {width} vs hmac", [got[i].tobytes() for i in range(rows)],
                    [hmac.new(key, mat[i].tobytes(), hashlib.sha3_256).digest() for i in range(rows)])
            got = engine.sha3_fixed(mat)
            compare(f"SHA3-256, fixed width {width} vs hashlib", [got[i].tobytes() for i in range(rows)],
                    [hashlib.sha3_256(mat[i].tobytes()).digest() for i in range(rows)])
        compare("empty batch", engine.hmac_many(key, []), [])
    except Exception as exc:  # any engine failure counts as a failed self-test
        report.mismatches += 1
        report.lines.append(f"FAIL engine raised {type(exc).__name__}: {exc}")
    report.passed = report.mismatches == 0
    report.seconds = time.perf_counter() - start
    return report


_lock = threading.Lock()
_cached: GpuStatus | None = None


def _detect() -> GpuStatus:
    status = GpuStatus()
    if os.environ.get("PQSSE_FORCE_CPU") == "1":
        status.reason = "disabled by PQSSE_FORCE_CPU=1"
        return status
    if os.environ.get("CUDA_VISIBLE_DEVICES", "").strip() == "-1":
        status.reason = "CUDA hidden by CUDA_VISIBLE_DEVICES=-1"
        return status
    try:
        import cupy as cp
    except Exception as exc:
        status.reason = f"CuPy is not installed or failed to import ({type(exc).__name__})"
        return status
    status.cupy_version = cp.__version__
    try:
        count = cp.cuda.runtime.getDeviceCount()
    except Exception as exc:
        status.reason = f"no CUDA device ({type(exc).__name__})"
        return status
    if count < 1:
        status.reason = "no CUDA device found"
        return status
    try:
        from .cuda_kernel import GpuPRF

        engine = GpuPRF(0)
    except Exception as exc:
        status.reason = f"CUDA kernel could not be built ({type(exc).__name__}: {str(exc)[:120]})"
        return status
    status.available = True
    status.device = engine.device_name
    status.free_mem, status.total_mem = engine.mem_info()
    try:
        version = cp.cuda.runtime.runtimeGetVersion()
        status.driver = f"CUDA runtime {version // 1000}.{(version % 1000) // 10}"
    except Exception:
        status.driver = ""
    status.selftest = run_selftest(engine)
    if status.selftest.passed:
        status.usable = True
        status.engine = engine
    else:
        status.reason = (f"GPU self-test FAILED ({status.selftest.mismatches} mismatches against hashlib/hmac); "
                         "the GPU path is disabled")
    return status


def gpu_status(refresh: bool = False) -> GpuStatus:
    """Detect the GPU once (kernel build plus self-test) and cache the result."""
    global _cached
    with _lock:
        if _cached is None or refresh:
            _cached = _detect()
        return _cached


def _read_settings() -> dict:
    try:
        return json.loads(paths.settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_threshold() -> int:
    """Stored GPU batch threshold; calibrates on first use when a GPU is usable."""
    value = _read_settings().get("gpu_threshold")
    if isinstance(value, int) and value > 0:
        return value
    status = gpu_status()
    if status.usable and status.engine is not None:
        from .calibrate import calibrate

        return calibrate(status.engine).threshold
    return DEFAULT_THRESHOLD


def save_threshold(value: int, details: dict | None = None) -> None:
    settings = _read_settings()
    settings["gpu_threshold"] = int(value)
    if details is not None:
        settings["gpu_calibration"] = details
    paths.settings_file().write_text(json.dumps(settings, indent=2), encoding="utf-8")


def cpu_engine() -> BatchPRF:
    return CpuPRF()
