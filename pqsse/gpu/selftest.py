"""GPU self-test:  python -m pqsse.gpu.selftest

Prints a report: device, memory, the byte for byte comparison of the CUDA engine with
hashlib and hmac, the calibration table (CPU vs GPU time per batch size) and the stored
threshold. Exit code 0 = GPU usable, 1 = self-test failed, 2 = no usable GPU (CPU only).
"""
from __future__ import annotations

import sys

from . import status
from .calibrate import NEVER, calibrate


def main() -> int:
    print("PQ-SSE Desktop GPU self-test")
    print("=" * 60)
    info = status.gpu_status(refresh=True)
    print(f"CuPy version : {info.cupy_version or 'not available'}")
    print(f"Device       : {info.device}")
    if info.available:
        print(f"Memory       : {info.total_mem / 2**30:.2f} GB total, {info.free_mem / 2**30:.2f} GB free")
        print(f"Runtime      : {info.driver}")
    if info.selftest is not None:
        print("-" * 60)
        print("Byte for byte comparison with hashlib / hmac:")
        for line in info.selftest.lines:
            print("  " + line)
        print(f"  total: {info.selftest.checked} digests checked, {info.selftest.mismatches} mismatches, "
              f"{info.selftest.seconds:.2f} s")
    print("-" * 60)
    if not info.usable or info.engine is None:
        print(f"RESULT: GPU path is OFF. Reason: {info.reason}")
        print("The application still runs fully on the CPU.")
        return 1 if info.available else 2
    print("Calibration (HMAC-SHA3-256, 21 byte messages, best of several runs):")
    print(f"  {'batch':>8} {'CPU ms':>10} {'GPU ms':>10} {'speedup':>9}")
    result = calibrate(info.engine)
    for row in result.rows:
        print(f"  {row['n']:>8} {row['cpu_ms']:>10.3f} {row['gpu_ms']:>10.3f} {row['speedup']:>8.2f}x")
    if result.threshold == NEVER:
        print("  The GPU was not faster at any tested size: auto mode will stay on the CPU.")
    else:
        print(f"  Stored threshold: use the GPU for batches of {result.threshold} messages or more.")
    print("-" * 60)
    print("Note: only the symmetric batch work (PRF, masks, hash chain levels) uses the GPU.")
    print("ML-KEM and ML-DSA always run on the CPU.")
    print("RESULT: PASS, the GPU path is enabled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
