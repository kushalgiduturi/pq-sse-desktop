"""Benchmarks:  python -m pqsse.bench [--out bench_results] [--quick]

1. BuildIndex for 1k, 10k and 100k keyword occurrences, CPU engine vs GPU engine, with
   a per phase breakdown. Only the PRF and hash chain phases can use the GPU; document
   encryption, ML-DSA signing and the cloud store are CPU work and are reported as such.
2. Per event operations (Join, Update, Publish, TokenGen, Search, Verify, Decrypt,
   Revoke R, Revoke RE) for ML-KEM-512/768/1024 with ML-DSA-44/65/87.

All numbers are measured on the machine that runs this, nothing is assumed.
"""
from __future__ import annotations

import argparse
import csv
import random
import time
from pathlib import Path
from typing import Callable, Sequence

from . import pqbackend
from .gpu import status
from .gpu.batchprf import BatchPRF, CpuPRF
from .owner.owner import DocInput
from .pqbackend import FAST_PARAMS, PARAM_SETS, Params
from .sandbox import World

Progress = Callable[[str, float], None]
BUILD_SIZES = (1_000, 10_000, 100_000)
KEYWORDS_PER_DOC = 1000
PHASES = ("PRF addresses and masks", "hash chain", "documents (AES-GCM + ML-DSA)",
          "batch signature (ML-DSA)", "cloud store")
BUILD_COLUMNS = ["occurrences", "engine", "prf_s", "chain_s", "documents_s", "batch_sign_s", "cloud_store_s",
                 "total_s", "prf_speedup", "symmetric_speedup", "total_speedup"]
OPS_COLUMNS = ["operation", "kem", "sig", "backend", "milliseconds"]


def _noop(message: str, fraction: float) -> None:
    return None


def make_corpus(occurrences: int, seed: int = 1) -> list[DocInput]:
    """Synthetic corpus with exactly ``occurrences`` keyword occurrences.

    Documents carry up to 1000 distinct keywords from a vocabulary of varied word
    lengths, so each keyword occurs in several documents (real hash chains).
    """
    rng = random.Random(seed)
    per_doc = min(KEYWORDS_PER_DOC, occurrences)
    vocab_size = max(per_doc, occurrences // 8)
    stems = ["k", "kw", "term", "token", "keyword", "lattice"]
    vocab = [f"{stems[j % len(stems)]}{j}" for j in range(vocab_size)]
    docs = []
    remaining = occurrences
    number = 0
    while remaining > 0:
        take = min(per_doc, remaining)
        docs.append(DocInput(f"doc {number}", f"benchmark document {number}", rng.sample(vocab, take)))
        remaining -= take
        number += 1
    return docs


def bench_build_index(occurrences: int, prf: BatchPRF, params: Params = FAST_PARAMS) -> dict:
    """One BuildIndex run with the given engine. Returns the phase breakdown in seconds."""
    world = World(params=params, prf=prf)
    world.owner.create_group("bench")
    docs = make_corpus(occurrences)
    world.owner.timings = {}
    start = time.perf_counter()
    world.owner.build_index("bench", docs)
    total = time.perf_counter() - start
    t = world.owner.timings
    stored = world.cloud.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    assert stored == occurrences
    return {"occurrences": occurrences, "engine": "GPU" if prf.uses_gpu else "CPU",
            "prf_s": t.get(PHASES[0], 0.0), "chain_s": t.get(PHASES[1], 0.0), "documents_s": t.get(PHASES[2], 0.0),
            "batch_sign_s": t.get(PHASES[3], 0.0), "cloud_store_s": t.get(PHASES[4], 0.0), "total_s": total}


def run_build_benchmarks(sizes: Sequence[int] = BUILD_SIZES, progress: Progress = _noop,
                         params: Params = FAST_PARAMS) -> list[dict]:
    """BuildIndex CPU vs GPU for every size. GPU rows are omitted when no GPU is usable."""
    info = status.gpu_status()
    engines: list[BatchPRF] = [CpuPRF()]
    if info.usable and info.engine is not None:
        engines.append(info.engine)
        bench_build_index(256, info.engine, params)      # warm up: kernel load, memory pool
    rows: list[dict] = []
    steps = len(sizes) * len(engines)
    done = 0
    for n in sizes:
        cpu_row: dict | None = None
        for engine in engines:
            progress(f"BuildIndex {n:,} occurrences on {'GPU' if engine.uses_gpu else 'CPU'}", done / steps)
            row = bench_build_index(n, engine, params)
            if not engine.uses_gpu:
                cpu_row = row
                row.update(prf_speedup=1.0, symmetric_speedup=1.0, total_speedup=1.0)
            elif cpu_row is not None:
                sym_cpu = cpu_row["prf_s"] + cpu_row["chain_s"]
                sym_gpu = row["prf_s"] + row["chain_s"]
                row.update(prf_speedup=cpu_row["prf_s"] / row["prf_s"] if row["prf_s"] else 0.0,
                           symmetric_speedup=sym_cpu / sym_gpu if sym_gpu else 0.0,
                           total_speedup=cpu_row["total_s"] / row["total_s"] if row["total_s"] else 0.0)
            rows.append(row)
            done += 1
    progress("BuildIndex benchmarks done", 1.0)
    return rows


def bench_operations(params: Params, repeats: int = 3, progress: Progress = _noop,
                     base: float = 0.0, span: float = 1.0) -> list[dict]:
    """Time the per event operations for one parameter set (mean of ``repeats`` runs)."""
    rng = random.Random(7)
    vocab = [f"word{j}" for j in range(60)]
    results: dict[str, list[float]] = {}

    def record(name: str, seconds: float) -> None:
        results.setdefault(name, []).append(seconds * 1000.0)

    def note(text: str, part: float) -> None:
        progress(f"{params.label()}: {text}", base + span * part)

    note("Setup and BuildIndex", 0.0)
    start = time.perf_counter()
    world = World(params=params)
    record("Setup", time.perf_counter() - start)
    owner = world.owner
    owner.create_group("g")
    owner.build_index("g", [DocInput(f"d{i}", "text " * 20, rng.sample(vocab, 20)) for i in range(30)])
    owner.publish("g")

    note("Join", 0.1)
    members = []
    for i in range(repeats + 3):
        start = time.perf_counter()
        members.append(world.join(f"user{i}", ["g"]))
        record("Join", time.perf_counter() - start)
    reader = members[0]

    note("Update and Publish", 0.3)
    for i in range(repeats):
        start = time.perf_counter()
        owner.add_document("g", f"new{i}", "text " * 20, rng.sample(vocab, 20))
        record("Update (add, 20 keywords)", time.perf_counter() - start)
        start = time.perf_counter()
        owner.publish("g")
        record("Publish", time.perf_counter() - start)

    note("TokenGen, Search, Verify, Decrypt", 0.5)
    hits: list[tuple[int, int]] = []
    for i in range(repeats):
        reader.timings = {}
        result = reader.search("g", vocab[i])
        hits = result.hits or hits
        for name in ("TokenGen", "Search", "Verify"):
            record(name, reader.timings.get(name, 0.0))
    reader.timings = None
    for i in range(repeats):
        if hits:
            start = time.perf_counter()
            reader.open_document("g", *hits[i % len(hits)])
            record("Decrypt", time.perf_counter() - start)

    note("Revoke R", 0.7)
    start = time.perf_counter()
    owner.revoke(members[-1].uid, "R")
    record("Revoke R (30 docs, remaining users rekeyed)", time.perf_counter() - start)
    note("Revoke RE", 0.8)
    start = time.perf_counter()
    owner.revoke(members[-2].uid, "RE")
    record("Revoke RE (30 docs re-encrypted)", time.perf_counter() - start)
    reader.search("g", vocab[0])      # sanity: remaining user still works

    backend = pqbackend.backend_name()
    return [{"operation": name, "kem": params.kem, "sig": params.sig, "backend": backend,
             "milliseconds": sum(values) / len(values)} for name, values in results.items()]


def run_operation_benchmarks(param_sets: Sequence[Params] = PARAM_SETS, repeats: int = 3,
                             progress: Progress = _noop) -> list[dict]:
    rows: list[dict] = []
    for i, params in enumerate(param_sets):
        rows += bench_operations(params, repeats, progress, base=i / len(param_sets), span=1 / len(param_sets))
    progress("Operation benchmarks done", 1.0)
    return rows


def write_csv(path: str | Path, rows: Sequence[dict], columns: Sequence[str]) -> None:
    """Write benchmark rows to a CSV file."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (f"{v:.6f}" if isinstance(v, float) else v) for k, v in row.items()})


def format_build_table(rows: Sequence[dict]) -> str:
    lines = [f"{'occurrences':>12} {'engine':>6} {'PRF s':>9} {'chain s':>9} {'docs s':>9} {'sign s':>8} "
             f"{'store s':>8} {'total s':>9} {'PRF x':>8} {'sym x':>8} {'total x':>8}"]
    for r in rows:
        lines.append(f"{r['occurrences']:>12,} {r['engine']:>6} {r['prf_s']:>9.4f} {r['chain_s']:>9.4f} "
                     f"{r['documents_s']:>9.4f} {r['batch_sign_s']:>8.4f} {r['cloud_store_s']:>8.4f} "
                     f"{r['total_s']:>9.4f} {r.get('prf_speedup', 0):>7.2f}x {r.get('symmetric_speedup', 0):>7.2f}x "
                     f"{r.get('total_speedup', 0):>7.2f}x")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pqsse.bench")
    parser.add_argument("--out", type=Path, default=Path("bench_results"))
    parser.add_argument("--quick", action="store_true", help="skip the 100k run and use one repeat")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    def show(message: str, fraction: float) -> None:
        print(f"[{fraction * 100:5.1f}%] {message}", flush=True)

    info = status.gpu_status()
    print(info.summary())
    print("PQ backend:", pqbackend.backend_name())
    sizes = BUILD_SIZES[:2] if args.quick else BUILD_SIZES
    build_rows = run_build_benchmarks(sizes, show)
    print(format_build_table(build_rows))
    write_csv(args.out / "buildindex.csv", build_rows, BUILD_COLUMNS)
    op_rows = run_operation_benchmarks(repeats=1 if args.quick else 3, progress=show)
    print(f"{'operation':<46} {'parameters':<26} {'ms':>10}")
    for row in op_rows:
        print(f"{row['operation']:<46} {row['kem'] + ' + ' + row['sig']:<26} {row['milliseconds']:>10.2f}")
    write_csv(args.out / "operations.csv", op_rows, OPS_COLUMNS)
    print(f"CSV files written to {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
