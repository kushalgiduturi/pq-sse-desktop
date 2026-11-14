"""Milestone 4: GPU engine, self-test, CPU fallback, calibration, benchmarks."""
from __future__ import annotations

import hashlib
import hmac
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from helpers import VOCAB, filled_world, random_update
from pqsse import bench
from pqsse.core import chain, index
from pqsse.gpu import CpuPRF, get_prf, status
from pqsse.gpu.batchprf import AutoPRF
from pqsse.gpu.keccak_host import hmac_states, host_sha3_256

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def gpu():
    info = status.gpu_status()
    if not info.usable:
        pytest.skip(f"no usable GPU: {info.reason}")
    return info.engine


def test_host_keccak_matches_hashlib():
    for length in (0, 1, 135, 136, 137, 500):
        msg = os.urandom(length)
        assert host_sha3_256(msg) == hashlib.sha3_256(msg).digest()
    inner, outer = hmac_states(os.urandom(32))
    assert inner.shape == (25,) and outer.dtype == np.uint64


def test_cpu_engine_passes_the_selftest():
    report = status.run_selftest(CpuPRF(), seed=1)
    assert report.passed and report.checked > 5000 and report.mismatches == 0


def test_selftest_catches_a_wrong_engine():
    """An engine with a single wrong bit must fail the self-test."""

    class Broken(CpuPRF):
        def hmac_fixed(self, key, mat):
            out = super().hmac_fixed(key, mat).copy()
            if len(out) > 100:
                out[100, 0] ^= 1
            return out

    report = status.run_selftest(Broken(), seed=2)
    assert not report.passed and report.mismatches >= 1
    assert any(line.startswith("FAIL") for line in report.lines)

    class Crashing(CpuPRF):
        def sha3_many(self, messages):
            raise RuntimeError("device lost")

    assert not status.run_selftest(Crashing(), seed=3).passed


@pytest.mark.gpu
def test_gpu_selftest_passes(gpu):
    info = status.gpu_status()
    assert info.selftest is not None and info.selftest.passed
    assert info.selftest.checked >= 1000 and info.device != "none" and info.total_mem > 0
    assert status.run_selftest(gpu).passed


@pytest.mark.gpu
def test_gpu_equals_cpu_on_random_batches(gpu):
    cpu = CpuPRF()
    rng = np.random.default_rng(5)
    for n, width in ((1, 1), (7, 20), (300, 21), (5000, 33), (20000, 69), (513, 136), (1000, 400)):
        key = os.urandom(32)
        mat = rng.integers(0, 256, size=(n, width), dtype=np.uint8)
        assert np.array_equal(gpu.hmac_fixed(key, mat), cpu.hmac_fixed(key, mat))
        assert np.array_equal(gpu.sha3_fixed(mat), cpu.sha3_fixed(mat))
    messages = [os.urandom(int(k)) for k in rng.integers(0, 900, size=3000)]
    key = os.urandom(32)
    assert gpu.hmac_many(key, messages) == [hmac.new(key, m, hashlib.sha3_256).digest() for m in messages]
    assert gpu.sha3_many(messages) == cpu.sha3_many(messages)
    assert gpu.hmac_many(key, [b""] * 5) == cpu.hmac_many(key, [b""] * 5)


@pytest.mark.gpu
def test_gpu_chunking_gives_the_same_result(gpu):
    from pqsse.gpu.cuda_kernel import GpuPRF

    small = GpuPRF(0, budget_bytes=4096)       # forces many launches
    key = os.urandom(32)
    mat = np.frombuffer(os.urandom(3000 * 25), dtype=np.uint8).reshape(3000, 25)
    assert np.array_equal(small.hmac_fixed(key, mat), CpuPRF().hmac_fixed(key, mat))
    messages = [os.urandom(n % 300) for n in range(2000)]
    assert small.hmac_many(key, messages) == CpuPRF().hmac_many(key, messages)


@pytest.mark.gpu
def test_index_derivation_and_chain_are_identical_on_gpu(gpu):
    key = os.urandom(32)
    words = ["a", "bb", "lattice", "kyber", "x" * 40, "sig"]
    items = [(words[i % len(words)], i // len(words)) for i in range(6000)]
    cpu_addrs, cpu_masks = index.derive(CpuPRF(), key, items)
    gpu_addrs, gpu_masks = index.derive(gpu, key, items)
    assert np.array_equal(cpu_addrs, gpu_addrs) and np.array_equal(cpu_masks, gpu_masks)
    slots = [i % 700 for i in range(6000)]
    vals = np.frombuffer(os.urandom(6000 * 5), dtype=np.uint8).reshape(6000, 5)
    heads_cpu = [os.urandom(32) for _ in range(700)]
    heads_gpu = list(heads_cpu)
    chain.update_heads(CpuPRF(), heads_cpu, slots, cpu_addrs, vals)
    chain.update_heads(AutoPRF(gpu, 256), heads_gpu, slots, cpu_addrs, vals)
    assert heads_cpu == heads_gpu


@pytest.mark.gpu
def test_scheme_is_correct_with_the_gpu_engine(gpu):
    """Owner and receivers on the GPU path produce results equal to the plaintext reference."""
    world, rng = filled_world(["alpha"], docs_per_group=40, seed=81, prf=AutoPRF(gpu, 1))
    bob = world.join("bob", ["alpha"])
    for _ in range(6):
        random_update(world, "alpha", rng)
    world.owner.publish("alpha")
    for word in VOCAB:
        result = bob.search("alpha", word)
        assert result.ids == world.owner.plaintext_search("alpha", word) and result.report.all_ok


def test_auto_engine_routes_by_batch_size():
    class Counting(CpuPRF):
        uses_gpu = True
        calls = 0

        def hmac_fixed(self, key, mat):
            Counting.calls += 1
            return super().hmac_fixed(key, mat)

    auto = AutoPRF(Counting(), 100)
    key = os.urandom(32)
    auto.hmac_fixed(key, np.zeros((99, 8), dtype=np.uint8))
    assert Counting.calls == 0 and auto.cpu_calls == 1
    auto.hmac_fixed(key, np.zeros((100, 8), dtype=np.uint8))
    assert Counting.calls == 1 and auto.gpu_calls == 1


def test_cpu_fallback_with_cuda_hidden(tmp_path):
    """With CUDA_VISIBLE_DEVICES=-1 everything still runs, on the CPU, and says so."""
    script = (
        "from pqsse.gpu import get_prf, status\n"
        "from pqsse.sandbox import World\n"
        "info = status.gpu_status()\n"
        "assert not info.usable and info.engine is None, info\n"
        "prf = get_prf('auto')\n"
        "assert not prf.uses_gpu and prf.name.startswith('CPU'), prf.name\n"
        "assert not get_prf('gpu').uses_gpu\n"
        "world = World(prf=prf)\n"
        "world.owner.create_group('g')\n"
        "doc = world.owner.add_document('g', 't', 'fallback works fine')\n"
        "world.owner.publish('g')\n"
        "bob = world.join('bob', ['g'])\n"
        "assert bob.search('g', 'fallback').ids == {doc}\n"
        "print('FALLBACK-OK', info.summary())\n"
    )
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "-1", "PYTHONPATH": str(ROOT), "PQSSE_DATA_DIR": str(tmp_path)}
    done = subprocess.run([sys.executable, "-c", script], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr
    assert "FALLBACK-OK" in done.stdout and "running on CPU" in done.stdout
    selftest = subprocess.run([sys.executable, "-m", "pqsse.gpu.selftest"], cwd=str(ROOT), env=env,
                              capture_output=True, text=True, timeout=300)
    assert selftest.returncode == 2
    assert "GPU path is OFF" in selftest.stdout and "runs fully on the CPU" in selftest.stdout


@pytest.mark.gpu
def test_calibration_stores_a_threshold(gpu, tmp_path):
    from pqsse.gpu.calibrate import calibrate

    result = calibrate(gpu)
    assert len(result.rows) >= 4 and all(row["gpu_ms"] > 0 for row in result.rows)
    assert status.load_threshold() == result.threshold
    auto = get_prf("auto")
    assert isinstance(auto, AutoPRF) and auto.threshold == result.threshold


def test_benchmark_runners_and_csv(tmp_path):
    rows = bench.run_build_benchmarks(sizes=(300, 1200))
    assert {r["engine"] for r in rows} >= {"CPU"} and all(r["total_s"] > 0 for r in rows)
    assert sum(1 for r in rows if r["engine"] == "CPU") == 2
    bench.write_csv(tmp_path / "build.csv", rows, bench.BUILD_COLUMNS)
    text = (tmp_path / "build.csv").read_text(encoding="utf-8").splitlines()
    assert text[0].split(",") == bench.BUILD_COLUMNS and len(text) == len(rows) + 1
    ops = bench.bench_operations(bench.FAST_PARAMS, repeats=1)
    names = {row["operation"].split(" ")[0] for row in ops}
    assert {"Join", "Update", "Publish", "TokenGen", "Search", "Verify", "Decrypt", "Revoke"} <= names
    bench.write_csv(tmp_path / "ops.csv", ops, bench.OPS_COLUMNS)
    assert "milliseconds" in (tmp_path / "ops.csv").read_text(encoding="utf-8")
    assert "occurrences" in bench.format_build_table(rows)
