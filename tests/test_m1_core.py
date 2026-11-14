"""Milestone 1: PQ backend, wire format, seal/unseal, signing, key store, pairing."""
from __future__ import annotations

import hashlib
import hmac
import os
import random
from pathlib import Path

import numpy as np
import pytest

from pqsse import pqbackend
from pqsse.core import index, pairing, seal, signing, wire
from pqsse.core.chain import CHAIN_START, chain_fold, chain_step
from pqsse.core.errors import BadPassphrase, VerifyError, WireError
from pqsse.core.keystore import Vault
from pqsse.core.prims import F, H, aead_decrypt, aead_encrypt, group_subkeys, hkdf
from pqsse.gpu import CpuPRF
from pqsse.pqbackend import PARAM_SETS, Params

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("p", PARAM_SETS, ids=lambda p: p.kem)
def test_kem_round_trip(p):
    ek, dk = pqbackend.kem_keygen(p.kem)
    ct, shared = pqbackend.kem_encaps(p.kem, ek)
    assert len(shared) == 32
    assert pqbackend.kem_decaps(p.kem, dk, ct) == shared


@pytest.mark.parametrize("p", PARAM_SETS, ids=lambda p: p.sig)
def test_signature_round_trip(p):
    vk, sk = pqbackend.sig_keygen(p.sig)
    sig = pqbackend.sig_sign(p.sig, sk, b"message")
    assert pqbackend.sig_verify(p.sig, vk, b"message", sig)
    assert not pqbackend.sig_verify(p.sig, vk, b"other", sig)
    assert not pqbackend.sig_verify(p.sig, vk, b"message", sig[:-1] + bytes([sig[-1] ^ 1]))
    assert not pqbackend.sig_verify(p.sig, vk, b"message", b"garbage")


def test_backend_is_safe_to_use_from_several_threads():
    """Regression: dilithium-py is not thread-safe on its own, the backend serializes calls."""
    import sys
    import threading

    failures = []

    def work(i: int) -> None:
        vk, sk = pqbackend.sig_keygen("ML-DSA-44")
        ek, dk = pqbackend.kem_keygen("ML-KEM-512")
        for j in range(6):
            msg = b"message %d %d" % (i, j)
            if not pqbackend.sig_verify("ML-DSA-44", vk, msg, pqbackend.sig_sign("ML-DSA-44", sk, msg)):
                failures.append(("sig", i, j))
            ct, shared = pqbackend.kem_encaps("ML-KEM-512", ek)
            if pqbackend.kem_decaps("ML-KEM-512", dk, ct) != shared:
                failures.append(("kem", i, j))

    old = sys.getswitchinterval()
    sys.setswitchinterval(0.0005)
    try:
        threads = [threading.Thread(target=work, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old)
    assert failures == []


def test_backend_reports_a_name():
    assert pqbackend.backend_name()
    with pytest.raises(ValueError):
        Params("ML-KEM-999", "ML-DSA-65")


def test_wire_round_trip_and_canonical():
    obj = {"b": [1, 2, b"\x00\x01", "text", None, True, False], "a": {"z": 2**63, "y": b""}}
    blob = wire.enc(obj)
    assert wire.dec(blob) == obj
    assert wire.enc(wire.dec(blob)) == blob
    assert wire.enc({"a": 1, "b": 2}) == wire.enc({"b": 2, "a": 1})
    with pytest.raises(WireError):
        wire.dec(blob + b"\x00")
    with pytest.raises(WireError):
        wire.dec(blob[:-1])
    with pytest.raises(WireError):
        wire.enc({"x": -1})
    with pytest.raises(WireError):
        wire.enc({1: "x"})
    # two keys in the wrong order must be rejected by the decoder
    bad = bytes([7]) + wire.u32(2) + wire.u32(1) + b"b" + bytes([0]) + wire.u32(1) + b"a" + bytes([0])
    with pytest.raises(WireError):
        wire.dec(bad)


def test_wire_random_round_trip():
    rng = random.Random(7)

    def make(depth: int):
        kind = rng.randrange(7 if depth < 3 else 5)
        if kind == 0:
            return None
        if kind == 1:
            return rng.random() < 0.5
        if kind == 2:
            return rng.randrange(2**64)
        if kind == 3:
            return rng.randbytes(rng.randrange(40))
        if kind == 4:
            return "".join(rng.choice("abc xyz") for _ in range(rng.randrange(10)))
        if kind == 5:
            return [make(depth + 1) for _ in range(rng.randrange(4))]
        return {f"k{rng.randrange(50)}": make(depth + 1) for _ in range(rng.randrange(4))}

    for _ in range(300):
        value = make(0)
        assert wire.dec(wire.enc(value)) == value


def test_primitives_match_standard_library():
    key, msg = os.urandom(32), os.urandom(77)
    assert F(key, msg) == hmac.new(key, msg, hashlib.sha3_256).digest()
    assert H(b"ab", b"c") == hashlib.sha3_256(b"abc").digest()
    assert len(hkdf(key, b"info")) == 32
    assert hkdf(key, b"a") != hkdf(key, b"b")
    k1 = group_subkeys(key, "g", 1)
    assert len(set(k1)) == 3
    assert group_subkeys(key, "g", 2) != k1
    assert group_subkeys(key, "h", 1) != k1


def test_aead_detects_tampering():
    key = os.urandom(32)
    blob = aead_encrypt(key, b"secret", b"aad")
    assert aead_decrypt(key, blob, b"aad") == b"secret"
    assert aead_encrypt(key, b"secret", b"aad") != blob  # fresh nonce
    with pytest.raises(VerifyError):
        aead_decrypt(key, blob, b"other")
    with pytest.raises(VerifyError):
        aead_decrypt(key, blob[:-1] + bytes([blob[-1] ^ 1]), b"aad")
    with pytest.raises(VerifyError):
        aead_decrypt(os.urandom(32), blob, b"aad")


@pytest.mark.parametrize("p", PARAM_SETS, ids=lambda p: p.kem)
def test_seal_unseal(p):
    ek, dk = pqbackend.kem_keygen(p.kem)
    ek2, dk2 = pqbackend.kem_keygen(p.kem)
    box = seal.seal(p, ek, b"capability", b"ctx")
    assert seal.unseal(p, dk, box, b"ctx") == b"capability"
    with pytest.raises(VerifyError):
        seal.unseal(p, dk2, box, b"ctx")
    with pytest.raises(VerifyError):
        seal.unseal(p, dk, box, b"wrong")
    with pytest.raises(VerifyError):
        seal.unseal(p, dk, box[:-1] + bytes([box[-1] ^ 1]), b"ctx")
    with pytest.raises(VerifyError):
        seal.unseal(p, dk, b"not a box", b"ctx")


def test_seal_with_pre_shared_key(params):
    ek, dk = pqbackend.kem_keygen(params.kem)
    psk = os.urandom(32)
    box = seal.seal(params, ek, b"rekey", b"", psk=psk)
    assert seal.unseal(params, dk, box, b"", psk=psk) == b"rekey"
    with pytest.raises(VerifyError):
        seal.unseal(params, dk, box, b"")
    with pytest.raises(VerifyError):
        seal.unseal(params, dk, box, b"", psk=os.urandom(32))


def test_signing_is_domain_separated(params):
    vk, sk = pqbackend.sig_keygen(params.sig)
    sig = signing.sign_obj(params, sk, "batch", {"seq": 1})
    assert signing.check_obj(params, vk, "batch", {"seq": 1}, sig)
    assert not signing.check_obj(params, vk, "state", {"seq": 1}, sig)
    assert not signing.check_obj(params, vk, "batch", {"seq": 2}, sig)
    with pytest.raises(VerifyError) as err:
        signing.verify_bytes(params, vk, "batch", b"x", sig, check="update signature")
    assert err.value.check == "update signature"


def test_vault_encrypts_and_checks_passphrase(tmp_path):
    path = tmp_path / "role.sqlite"
    secret = os.urandom(32)
    vault = Vault(path, "correct horse", scrypt_n=2**10)
    vault.put("identity", {"sk": secret, "n": 5})
    vault.close()
    assert secret not in path.read_bytes()
    again = Vault(path, "correct horse")
    assert again.get("identity") == {"sk": secret, "n": 5}
    assert list(again.names()) == ["identity"]
    again.close()
    with pytest.raises(BadPassphrase):
        Vault(path, "wrong")


def test_pairing_file_round_trip(tmp_path, params):
    ek, _ = pqbackend.kem_keygen(params.kem)
    vk, _ = pqbackend.sig_keygen(params.sig)
    ident = pairing.PublicIdentity("cloud", "my cloud", params, vk, ek)
    target = tmp_path / "cloud.pqpub"
    pairing.export_pub(target, ident)
    loaded = pairing.import_pub(target, expect_role="cloud")
    assert loaded == ident and loaded.fingerprint() == ident.fingerprint()
    with pytest.raises(WireError):
        pairing.import_pub(target, expect_role="owner")
    target.write_text(target.read_text().replace(ident.fingerprint(), "0000"), encoding="utf-8")
    with pytest.raises(WireError):
        pairing.import_pub(target)


def test_index_derive_matches_definition():
    key = os.urandom(32)
    items = [("alpha", 0), ("alpha", 1), ("be", 0), ("gamma-delta", 7), ("", 3), ("be", 1)]
    addrs, masks = index.derive(CpuPRF(), key, items)
    for row, (w, i) in enumerate(items):
        assert addrs[row].tobytes() == F(key, wire.sstr(w) + wire.u32(i) + b"\x00")
        assert masks[row].tobytes() == F(key, wire.sstr(w) + wire.u32(i) + b"\x01")[:5]
    value = index.pack_value(index.OP_ADD, 123456)
    masked = index.xor5(value, masks[0].tobytes())
    assert index.unpack_value(index.xor5(masked, masks[0].tobytes())) == (index.OP_ADD, 123456)


def test_cpu_prf_matches_hmac():
    prf = CpuPRF()
    key = os.urandom(32)
    msgs = [os.urandom(n) for n in (0, 1, 135, 136, 137, 300)]
    assert prf.hmac_many(key, msgs) == [hmac.new(key, m, hashlib.sha3_256).digest() for m in msgs]
    assert prf.sha3_many(msgs) == [hashlib.sha3_256(m).digest() for m in msgs]
    mat = np.frombuffer(os.urandom(50 * 20), dtype=np.uint8).reshape(50, 20)
    out = prf.hmac_fixed(key, mat)
    assert out[7].tobytes() == hmac.new(key, mat[7].tobytes(), hashlib.sha3_256).digest()
    assert prf.sha3_fixed(mat)[9].tobytes() == hashlib.sha3_256(mat[9].tobytes()).digest()
    long_key = os.urandom(200)
    assert prf.hmac_many(long_key, [b"m"]) == [hmac.new(long_key, b"m", hashlib.sha3_256).digest()]


def test_hash_chain():
    a1, v1, a2, v2 = os.urandom(32), os.urandom(5), os.urandom(32), os.urandom(5)
    d1 = chain_step(CHAIN_START, a1, v1)
    assert d1 == hashlib.sha3_256(bytes(32) + a1 + v1).digest()
    assert chain_fold(CHAIN_START, [(a1, v1), (a2, v2)]) == chain_step(d1, a2, v2)
    assert chain_fold(CHAIN_START, [(a2, v2), (a1, v1)]) != chain_fold(CHAIN_START, [(a1, v1), (a2, v2)])


def test_no_em_dash_anywhere():
    """Hard rule 1: no em dash in any file of the project."""
    needle = chr(0x2014)
    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in {".git", "build", "dist", "__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".md", ".txt", ".toml", ".ps1", ".json", ".cfg", ".ini"}:
            continue
        if needle in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
