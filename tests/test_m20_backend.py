"""Milestone 5 of REALLIFE_PLAN.md: the native post-quantum backend (OpenSSL through cryptography).

The native backend must produce and accept exactly the same bytes as the pure Python one: the same public
key from the same seed, signatures and ciphertexts that the other side accepts, and private keys stored
by earlier versions (expanded form) must keep working.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from pqsse import pqbackend
from pqsse.pqbackend import KEM_NAMES, SIG_NAMES, NativeBackend, PurePythonBackend
from pqsse.sandbox import World

try:
    NATIVE = NativeBackend()
except ImportError:                       # pragma: no cover - an old cryptography without ML-KEM / ML-DSA
    NATIVE = None
PURE = PurePythonBackend()
needs_native = pytest.mark.skipif(NATIVE is None, reason="this cryptography build has no ML-KEM / ML-DSA")


@needs_native
def test_the_native_backend_is_the_default_here():
    assert pqbackend.get_backend().name == NATIVE.name and not pqbackend.is_fallback()
    assert "native: " in pqbackend.coverage()
    assert {"ML-KEM-768", "ML-KEM-1024", "ML-DSA-44", "ML-DSA-65", "ML-DSA-87"} <= set(NATIVE.native)


@needs_native
@pytest.mark.parametrize("alg", SIG_NAMES)
def test_signatures_cross_both_ways_and_seeds_give_the_same_key(alg):
    vk_n, seed = NATIVE.sig_keygen(alg)
    assert len(seed) == pqbackend.SIG_SEED
    vk_p, _ = PURE._sig[alg].key_derive(seed)
    assert bytes(vk_p) == vk_n                                    # FIPS 204 keygen agrees across implementations
    msg = b"pqsse/v3/sig/test\x00" + os.urandom(32)
    assert PURE.sig_verify(alg, vk_n, msg, NATIVE.sig_sign(alg, seed, msg))
    assert NATIVE.sig_verify(alg, vk_n, msg, PURE.sig_sign(alg, seed, msg))
    assert not NATIVE.sig_verify(alg, vk_n, msg + b"x", NATIVE.sig_sign(alg, seed, msg))
    assert not NATIVE.sig_verify(alg, vk_n, msg, b"\x00" * 10)    # malformed: False, never an exception


@needs_native
@pytest.mark.parametrize("alg", KEM_NAMES)
def test_kem_crosses_both_ways(alg):
    ek, seed = NATIVE.kem_keygen(alg)
    assert len(seed) == pqbackend.KEM_SEED
    assert bytes(PURE._kem[alg].key_derive(seed)[0]) == ek
    ct, shared = NATIVE.kem_encaps(alg, ek)
    assert PURE.kem_decaps(alg, seed, ct) == shared
    ct, shared = PURE.kem_encaps(alg, ek)
    assert NATIVE.kem_decaps(alg, seed, ct) == shared


@needs_native
@pytest.mark.parametrize("kem,sig", [("ML-KEM-768", "ML-DSA-65"), ("ML-KEM-512", "ML-DSA-44")])
def test_private_keys_from_earlier_versions_still_work(kem, sig):
    """Before M5 the vaults held the expanded keys that kyber-py and dilithium-py's keygen() return."""
    ek, dk = (bytes(x) for x in PURE._kem[kem].keygen())
    vk, sk = (bytes(x) for x in PURE._sig[sig].keygen())
    assert not pqbackend.is_seed(kem, dk) and not pqbackend.is_seed(sig, sk)
    ct, shared = NATIVE.kem_encaps(kem, ek)
    assert NATIVE.kem_decaps(kem, dk, ct) == shared
    assert NATIVE.sig_verify(sig, vk, b"m", NATIVE.sig_sign(sig, sk, b"m"))


@needs_native
def test_the_whole_protocol_on_the_native_backend_with_the_default_parameters():
    world = World(pqbackend.DEFAULT_PARAMS)
    world.owner.create_group("g")
    world.owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    world.owner.publish("g")
    rec = world.join("receiver-a", ["g"])
    result = rec.search("g", "contract")
    assert len(result.hits) == 1 and result.report.all_ok


@pytest.mark.parametrize("choice,expect", [("pure", "kyber-py"), ("native", "OpenSSL")])
def test_the_backend_can_be_forced_for_tests_and_benchmarks(choice, expect):
    if choice == "native" and NATIVE is None:
        pytest.skip("no native backend")
    code = "from pqsse import pqbackend; print(pqbackend.backend_name()); print(pqbackend.is_fallback())"
    env = dict(os.environ, PQSSE_PQ_BACKEND=choice)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True).stdout
    assert out.startswith(expect) and out.split()[-1] == str(choice == "pure")
