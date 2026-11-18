"""Primitive benchmarks:  python -m pqsse.bench_primitives [--out bench_results] [--quick]

Times ML-KEM (keygen, encapsulate, decapsulate) and ML-DSA (keygen, sign, verify) for every parameter
set on every backend that works on this machine (pure Python, native OpenSSL, liboqs if installed),
next to classical baselines from the same OpenSSL: X25519, ECDH P-256, Ed25519, ECDSA P-256 and
RSA-2048 (OAEP and PSS). The message is 64 bytes, the size the protocol signs (a label and a hash).

Each figure is the median of several runs after one warm-up run, in microseconds, measured on the
computer that runs this. Nothing is assumed or copied from elsewhere.
"""
from __future__ import annotations

import argparse
import csv
import os
import platform
import statistics
import time
from pathlib import Path
from typing import Callable

from . import pqbackend
from .pqbackend import KEM_NAMES, SIG_NAMES

COLUMNS = ["family", "algorithm", "operation", "backend", "median_us", "runs"]
MESSAGE = os.urandom(64)


def _median_us(fn: Callable[[], object], runs: int) -> float:
    fn()                                            # warm-up
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times) * 1e6


def _backends() -> dict[str, object]:
    found: dict[str, object] = {"pure": pqbackend.PurePythonBackend()}
    for key, factory in (("native", pqbackend.NativeBackend), ("oqs", pqbackend.OqsBackend)):
        try:
            backend = factory()
            if pqbackend._round_trip_ok(backend):
                found[key] = backend
        except Exception:
            pass
    return found


def post_quantum(runs_fast: int, runs_slow: int) -> list[dict]:
    rows = []
    for key, b in _backends().items():
        runs = runs_slow if key == "pure" else runs_fast
        native_set = set(getattr(b, "native", KEM_NAMES + SIG_NAMES)) if key != "pure" else set(KEM_NAMES + SIG_NAMES)
        for alg in KEM_NAMES:
            if alg not in native_set:
                continue                             # would only measure the pure Python fallback again
            ek, dk = b.kem_keygen(alg)
            ct, _ = b.kem_encaps(alg, ek)
            for op, fn in (("keygen", lambda: b.kem_keygen(alg)), ("encapsulate", lambda: b.kem_encaps(alg, ek)),
                           ("decapsulate", lambda: b.kem_decaps(alg, dk, ct))):
                rows.append({"family": "KEM", "algorithm": alg, "operation": op, "backend": key,
                             "median_us": round(_median_us(fn, runs), 1), "runs": runs})
        for alg in SIG_NAMES:
            if alg not in native_set:
                continue
            vk, sk = b.sig_keygen(alg)
            sig = b.sig_sign(alg, sk, MESSAGE)
            for op, fn in (("keygen", lambda: b.sig_keygen(alg)), ("sign", lambda: b.sig_sign(alg, sk, MESSAGE)),
                           ("verify", lambda: b.sig_verify(alg, vk, MESSAGE, sig))):
                rows.append({"family": "SIG", "algorithm": alg, "operation": op, "backend": key,
                             "median_us": round(_median_us(fn, runs), 1), "runs": runs})
    return rows


def classical(runs: int) -> list[dict]:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa, x25519

    rows = []

    def add(family: str, alg: str, op: str, fn: Callable[[], object], n: int = runs) -> None:
        rows.append({"family": family, "algorithm": alg, "operation": op, "backend": "classical",
                     "median_us": round(_median_us(fn, n), 1), "runs": n})

    xa, xb = x25519.X25519PrivateKey.generate(), x25519.X25519PrivateKey.generate().public_key()
    add("KEM", "X25519", "keygen", x25519.X25519PrivateKey.generate)
    add("KEM", "X25519", "exchange", lambda: xa.exchange(xb))
    pa, pb = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1()).public_key()
    add("KEM", "ECDH P-256", "keygen", lambda: ec.generate_private_key(ec.SECP256R1()))
    add("KEM", "ECDH P-256", "exchange", lambda: pa.exchange(ec.ECDH(), pb))
    rk = rsa.generate_private_key(65537, 2048)
    oaep = padding.OAEP(padding.MGF1(hashes.SHA256()), hashes.SHA256(), None)
    ct = rk.public_key().encrypt(MESSAGE[:32], oaep)
    add("KEM", "RSA-2048 OAEP", "keygen", lambda: rsa.generate_private_key(65537, 2048), max(3, runs // 20))
    add("KEM", "RSA-2048 OAEP", "encrypt", lambda: rk.public_key().encrypt(MESSAGE[:32], oaep))
    add("KEM", "RSA-2048 OAEP", "decrypt", lambda: rk.decrypt(ct, oaep))
    ed = ed25519.Ed25519PrivateKey.generate()
    ed_sig = ed.sign(MESSAGE)
    add("SIG", "Ed25519", "keygen", ed25519.Ed25519PrivateKey.generate)
    add("SIG", "Ed25519", "sign", lambda: ed.sign(MESSAGE))
    add("SIG", "Ed25519", "verify", lambda: ed.public_key().verify(ed_sig, MESSAGE))
    ecdsa = ec.ECDSA(hashes.SHA256())
    es = pa.sign(MESSAGE, ecdsa)
    add("SIG", "ECDSA P-256", "sign", lambda: pa.sign(MESSAGE, ecdsa))
    add("SIG", "ECDSA P-256", "verify", lambda: pa.public_key().verify(es, MESSAGE, ecdsa))
    pss = padding.PSS(padding.MGF1(hashes.SHA256()), padding.PSS.MAX_LENGTH)
    rs = rk.sign(MESSAGE, pss, hashes.SHA256())
    add("SIG", "RSA-2048 PSS", "sign", lambda: rk.sign(MESSAGE, pss, hashes.SHA256()))
    add("SIG", "RSA-2048 PSS", "verify", lambda: rk.public_key().verify(rs, MESSAGE, pss, hashes.SHA256()))
    return rows


def speedups(rows: list[dict]) -> list[dict]:
    """Pure Python time divided by native time, per algorithm and operation."""
    pure = {(r["algorithm"], r["operation"]): r["median_us"] for r in rows if r["backend"] == "pure"}
    out = []
    for r in rows:
        if r["backend"] in ("native", "oqs") and (r["algorithm"], r["operation"]) in pure and r["median_us"] > 0:
            out.append({"algorithm": r["algorithm"], "operation": r["operation"], "backend": r["backend"],
                        "pure_us": pure[(r["algorithm"], r["operation"])], "fast_us": r["median_us"],
                        "speedup": round(pure[(r["algorithm"], r["operation"])] / r["median_us"], 1)})
    return out


def markdown(rows: list[dict], ups: list[dict]) -> str:
    import cryptography
    lines = ["# Primitive timings", "",
             f"Measured with `python -m pqsse.bench_primitives` on {platform.processor() or platform.machine()}, "
             f"{platform.system()} {platform.release()}, Python {platform.python_version()}, cryptography "
             f"{cryptography.__version__}. Median of the runs shown, after one warm-up, in microseconds; "
             "64-byte message. Native decapsulate and sign include deriving the private key from its stored seed on "
             "every call (the app keeps no expanded private keys in memory between calls). Numbers from one "
             "computer: they show the ratio between backends, not a promise.", "",
             "| Family | Algorithm | Operation | Backend | Median (us) | Runs |", "| --- | --- | --- | --- | ---: | ---: |"]
    lines += [f"| {r['family']} | {r['algorithm']} | {r['operation']} | {r['backend']} | {r['median_us']:,.1f} | {r['runs']} |"
              for r in rows]
    if ups:
        lines += ["", "## Native against pure Python", "", "| Algorithm | Operation | Pure (us) | Native (us) | Faster by |",
                  "| --- | --- | ---: | ---: | ---: |"]
        lines += [f"| {u['algorithm']} | {u['operation']} | {u['pure_us']:,.1f} | {u['fast_us']:,.1f} | {u['speedup']:,.1f}x |"
                  for u in ups]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pqsse.bench_primitives")
    parser.add_argument("--out", type=Path, default=Path("bench_results"))
    parser.add_argument("--quick", action="store_true", help="fewer runs")
    args = parser.parse_args(argv)
    fast, slow = (50, 3) if args.quick else (500, 15)
    rows = post_quantum(fast, slow) + classical(fast)
    ups = speedups(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "primitives.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    (args.out / "primitives.md").write_text(markdown(rows, ups), encoding="utf-8")
    print(markdown(rows, ups))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
