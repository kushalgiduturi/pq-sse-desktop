"""Post-quantum backend abstraction.

One interface for ML-KEM (FIPS 203) and ML-DSA (FIPS 204):
``kem_keygen / kem_encaps / kem_decaps`` and ``sig_keygen / sig_sign / sig_verify``.

Backends, in order of preference (decision M5-1 in REALLIFE_PLAN.md):

1. ``native``: OpenSSL's ML-KEM and ML-DSA through the ``cryptography`` package (already a dependency,
   pinned, OpenSSL bundled in its wheels). OpenSSL has no ML-KEM-512, so that set, and private keys
   stored in the older expanded form, go to the pure Python code.
2. ``oqs``: liboqs-python, only when chosen with ``PQSSE_PQ_BACKEND=oqs`` or when (1) is missing.
3. ``pure``: ``kyber-py`` and ``dilithium-py``: slow, not constant time, for teaching. The app, the server
   and the logs say so when it is in use (``is_fallback()``).

``PQSSE_PQ_BACKEND`` = ``native`` | ``oqs`` | ``pure`` forces one (tests, benchmarks).

Private keys: new keys are stored as their FIPS 203 / FIPS 204 seed (64 bytes for ML-KEM: d || z,
32 bytes for ML-DSA: xi). Public keys, ciphertexts and signatures are the standard encodings, the same
bytes whichever backend made them. Keys made before M5 are the expanded encodings and keep working.
No cryptography is implemented in this module.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

KEM_NAMES: tuple[str, ...] = ("ML-KEM-512", "ML-KEM-768", "ML-KEM-1024")
SIG_NAMES: tuple[str, ...] = ("ML-DSA-44", "ML-DSA-65", "ML-DSA-87")
KEM_SEED, SIG_SEED = 64, 32         # FIPS 203 (d || z) and FIPS 204 (xi) seed lengths


@dataclass(frozen=True)
class Params:
    """Selected parameter set. Default: ML-KEM-768 with ML-DSA-65."""

    kem: str = "ML-KEM-768"
    sig: str = "ML-DSA-65"

    def __post_init__(self) -> None:
        if self.kem not in KEM_NAMES:
            raise ValueError(f"unknown KEM {self.kem}")
        if self.sig not in SIG_NAMES:
            raise ValueError(f"unknown signature scheme {self.sig}")

    def label(self) -> str:
        return f"{self.kem} + {self.sig}"


PARAM_SETS: tuple[Params, ...] = (
    Params("ML-KEM-512", "ML-DSA-44"),
    Params("ML-KEM-768", "ML-DSA-65"),
    Params("ML-KEM-1024", "ML-DSA-87"),
)
DEFAULT_PARAMS = Params()
FAST_PARAMS = PARAM_SETS[0]


class Backend(Protocol):
    """Interface every PQ backend implements."""

    name: str

    def kem_keygen(self, alg: str) -> tuple[bytes, bytes]: ...
    def kem_encaps(self, alg: str, ek: bytes) -> tuple[bytes, bytes]: ...
    def kem_decaps(self, alg: str, dk: bytes, ct: bytes) -> bytes: ...
    def sig_keygen(self, alg: str) -> tuple[bytes, bytes]: ...
    def sig_sign(self, alg: str, sk: bytes, msg: bytes) -> bytes: ...
    def sig_verify(self, alg: str, vk: bytes, msg: bytes, sig: bytes) -> bool: ...


def is_seed(alg: str, key: bytes) -> bool:
    """True when a private key is stored as its seed, false for the older expanded encoding."""
    return len(key) == (KEM_SEED if alg.startswith("ML-KEM") else SIG_SEED)


class PurePythonBackend:
    """kyber-py (ML_KEM_*) and dilithium-py (ML_DSA_*).

    These pure Python libraries keep shared internal state (measured: concurrent ML-DSA
    signing from several threads yields invalid signatures), so every call is serialized
    with one lock. The GUI runs roles on worker threads, which makes this necessary.
    """

    name = "kyber-py + dilithium-py (pure Python)"

    def __init__(self) -> None:
        from dilithium_py.ml_dsa import ML_DSA_44, ML_DSA_65, ML_DSA_87
        from kyber_py.ml_kem import ML_KEM_512, ML_KEM_768, ML_KEM_1024

        self._kem = {"ML-KEM-512": ML_KEM_512, "ML-KEM-768": ML_KEM_768, "ML-KEM-1024": ML_KEM_1024}
        self._sig = {"ML-DSA-44": ML_DSA_44, "ML-DSA-65": ML_DSA_65, "ML-DSA-87": ML_DSA_87}
        self._lock = threading.RLock()
        self._expanded: dict[tuple[str, bytes], bytes] = {}

    def expand(self, alg: str, key: bytes) -> bytes:
        """The expanded private key for a seed (FIPS keygen from the seed), cached; expanded keys pass through."""
        if not is_seed(alg, key):
            return key
        with self._lock:
            hit = self._expanded.get((alg, key))
            if hit is None:
                lib = self._kem[alg] if alg.startswith("ML-KEM") else self._sig[alg]
                hit = bytes(lib.key_derive(key)[1])
                if len(self._expanded) > 64:
                    self._expanded.clear()
                self._expanded[(alg, key)] = hit
            return hit

    def kem_keygen(self, alg: str) -> tuple[bytes, bytes]:
        seed = os.urandom(KEM_SEED)
        with self._lock:
            ek, _ = self._kem[alg].key_derive(seed)
        return bytes(ek), seed

    def kem_encaps(self, alg: str, ek: bytes) -> tuple[bytes, bytes]:
        with self._lock:
            shared, ct = self._kem[alg].encaps(ek)
        return bytes(ct), bytes(shared)

    def kem_decaps(self, alg: str, dk: bytes, ct: bytes) -> bytes:
        dk = self.expand(alg, dk)
        with self._lock:
            return bytes(self._kem[alg].decaps(dk, ct))

    def sig_keygen(self, alg: str) -> tuple[bytes, bytes]:
        seed = os.urandom(SIG_SEED)
        with self._lock:
            vk, _ = self._sig[alg].key_derive(seed)
        return bytes(vk), seed

    def sig_sign(self, alg: str, sk: bytes, msg: bytes) -> bytes:
        sk = self.expand(alg, sk)
        with self._lock:
            return bytes(self._sig[alg].sign(sk, msg))

    def sig_verify(self, alg: str, vk: bytes, msg: bytes, sig: bytes) -> bool:
        with self._lock:
            try:
                return bool(self._sig[alg].verify(vk, msg, sig))
            except Exception:
                return False


class NativeBackend:
    """OpenSSL's ML-KEM and ML-DSA through the cryptography package; the pure Python code covers the rest."""

    def __init__(self) -> None:
        import cryptography
        from cryptography.hazmat.backends.openssl.backend import backend as ossl
        from cryptography.hazmat.primitives.asymmetric import mldsa, mlkem

        self._kem_priv = {f"ML-KEM-{n}": getattr(mlkem, f"MLKEM{n}PrivateKey") for n in (512, 768, 1024)
                          if hasattr(mlkem, f"MLKEM{n}PrivateKey")}
        self._kem_pub = {f"ML-KEM-{n}": getattr(mlkem, f"MLKEM{n}PublicKey") for n in (512, 768, 1024)
                         if hasattr(mlkem, f"MLKEM{n}PublicKey")}
        self._sig_priv = {f"ML-DSA-{n}": getattr(mldsa, f"MLDSA{n}PrivateKey") for n in (44, 65, 87)
                          if hasattr(mldsa, f"MLDSA{n}PrivateKey")}
        self._sig_pub = {f"ML-DSA-{n}": getattr(mldsa, f"MLDSA{n}PublicKey") for n in (44, 65, 87)
                         if hasattr(mldsa, f"MLDSA{n}PublicKey")}
        if not self._kem_priv or not self._sig_priv:
            raise ImportError("this cryptography build has no ML-KEM or ML-DSA")
        self.openssl = ossl.openssl_version_text()
        self.name = f"{self.openssl} via cryptography {cryptography.__version__} (native)"
        self.native = sorted(self._kem_priv) + sorted(self._sig_priv)
        self._pure: PurePythonBackend | None = None

    @property
    def pure(self) -> PurePythonBackend:
        if self._pure is None:
            self._pure = PurePythonBackend()
        return self._pure

    def kem_keygen(self, alg: str) -> tuple[bytes, bytes]:
        if alg not in self._kem_priv:
            return self.pure.kem_keygen(alg)
        seed = os.urandom(KEM_SEED)
        return self._kem_priv[alg].from_seed_bytes(seed).public_key().public_bytes_raw(), seed

    def kem_encaps(self, alg: str, ek: bytes) -> tuple[bytes, bytes]:
        if alg not in self._kem_pub:
            return self.pure.kem_encaps(alg, ek)
        shared, ct = self._kem_pub[alg].from_public_bytes(ek).encapsulate()
        return bytes(ct), bytes(shared)

    def kem_decaps(self, alg: str, dk: bytes, ct: bytes) -> bytes:
        if alg not in self._kem_priv or not is_seed(alg, dk):
            return self.pure.kem_decaps(alg, dk, ct)
        return bytes(self._kem_priv[alg].from_seed_bytes(dk).decapsulate(ct))

    def sig_keygen(self, alg: str) -> tuple[bytes, bytes]:
        if alg not in self._sig_priv:
            return self.pure.sig_keygen(alg)
        seed = os.urandom(SIG_SEED)
        return self._sig_priv[alg].from_seed_bytes(seed).public_key().public_bytes_raw(), seed

    def sig_sign(self, alg: str, sk: bytes, msg: bytes) -> bytes:
        if alg not in self._sig_priv or not is_seed(alg, sk):
            return self.pure.sig_sign(alg, sk, msg)
        return bytes(self._sig_priv[alg].from_seed_bytes(sk).sign(msg))

    def sig_verify(self, alg: str, vk: bytes, msg: bytes, sig: bytes) -> bool:
        if alg not in self._sig_pub:
            return self.pure.sig_verify(alg, vk, msg, sig)
        try:
            self._sig_pub[alg].from_public_bytes(vk).verify(sig, msg)
            return True
        except Exception:
            return False


class OqsBackend:
    """liboqs-python backend (expanded keys; a stored seed is expanded with the FIPS keygen first)."""

    name = "liboqs (oqs)"

    def __init__(self) -> None:
        import oqs  # type: ignore[import-not-found]

        self._oqs = oqs
        self._expander: PurePythonBackend | None = None

    def _expanded(self, alg: str, key: bytes) -> bytes:
        if not is_seed(alg, key):
            return key
        if self._expander is None:
            self._expander = PurePythonBackend()
        return self._expander.expand(alg, key)

    def kem_keygen(self, alg: str) -> tuple[bytes, bytes]:
        with self._oqs.KeyEncapsulation(alg) as kem:
            ek = kem.generate_keypair()
            return bytes(ek), bytes(kem.export_secret_key())

    def kem_encaps(self, alg: str, ek: bytes) -> tuple[bytes, bytes]:
        with self._oqs.KeyEncapsulation(alg) as kem:
            ct, shared = kem.encap_secret(ek)
            return bytes(ct), bytes(shared)

    def kem_decaps(self, alg: str, dk: bytes, ct: bytes) -> bytes:
        with self._oqs.KeyEncapsulation(alg, secret_key=self._expanded(alg, dk)) as kem:
            return bytes(kem.decap_secret(ct))

    def sig_keygen(self, alg: str) -> tuple[bytes, bytes]:
        with self._oqs.Signature(alg) as signer:
            vk = signer.generate_keypair()
            return bytes(vk), bytes(signer.export_secret_key())

    def sig_sign(self, alg: str, sk: bytes, msg: bytes) -> bytes:
        with self._oqs.Signature(alg, secret_key=self._expanded(alg, sk)) as signer:
            return bytes(signer.sign(msg))

    def sig_verify(self, alg: str, vk: bytes, msg: bytes, sig: bytes) -> bool:
        try:
            with self._oqs.Signature(alg) as verifier:
                return bool(verifier.verify(msg, sig, vk))
        except Exception:
            return False


def _round_trip_ok(backend: Backend) -> bool:
    """Check that a backend really works before it is selected (and that a wrong message fails)."""
    try:
        ek, dk = backend.kem_keygen("ML-KEM-768")
        ct, shared = backend.kem_encaps("ML-KEM-768", ek)
        if backend.kem_decaps("ML-KEM-768", dk, ct) != shared:
            return False
        vk, sk = backend.sig_keygen("ML-DSA-65")
        sig = backend.sig_sign("ML-DSA-65", sk, b"probe")
        return backend.sig_verify("ML-DSA-65", vk, b"probe", sig) and not backend.sig_verify("ML-DSA-65", vk, b"probf", sig)
    except Exception:
        return False


_FACTORIES = {"native": NativeBackend, "oqs": OqsBackend, "pure": PurePythonBackend}


@lru_cache(maxsize=1)
def get_backend() -> Backend:
    """The active backend: PQSSE_PQ_BACKEND if set, else native, then liboqs, then pure Python."""
    forced = os.environ.get("PQSSE_PQ_BACKEND", "").strip().lower()
    order = [forced] if forced in _FACTORIES else ["native", "oqs"]
    for key in order:
        try:
            candidate: Backend = _FACTORIES[key]()
            if _round_trip_ok(candidate):
                return candidate
        except Exception:
            pass
    return PurePythonBackend()


def is_fallback() -> bool:
    """True when every operation runs in the slow, not constant time, pure Python code."""
    return isinstance(get_backend(), PurePythonBackend)


def coverage() -> str:
    """One line on which parameter sets run natively, for About, Insights and the server's start line."""
    b = get_backend()
    if isinstance(b, NativeBackend):
        rest = [n for n in KEM_NAMES + SIG_NAMES if n not in b.native]
        extra = f"{', '.join(rest)} and " if rest else ""
        return (f"native: {', '.join(b.native)}; pure Python: {extra}private keys made before version 0.2 "
                "(stored in the expanded form)")
    if isinstance(b, OqsBackend):
        return "liboqs: every parameter set"
    return "pure Python for every operation: slow, not constant time, for teaching only"


def backend_name() -> str:
    return get_backend().name


def kem_keygen(alg: str) -> tuple[bytes, bytes]:
    """ML-KEM.KeyGen: returns (encapsulation key, decapsulation key as its 64-byte seed)."""
    return get_backend().kem_keygen(alg)


def kem_encaps(alg: str, ek: bytes) -> tuple[bytes, bytes]:
    """ML-KEM.Encaps: returns (ciphertext, shared secret)."""
    return get_backend().kem_encaps(alg, ek)


def kem_decaps(alg: str, dk: bytes, ct: bytes) -> bytes:
    """ML-KEM.Decaps: returns the shared secret. dk is a seed or an expanded key."""
    return get_backend().kem_decaps(alg, dk, ct)


def sig_keygen(alg: str) -> tuple[bytes, bytes]:
    """ML-DSA.KeyGen: returns (verification key, signing key as its 32-byte seed)."""
    return get_backend().sig_keygen(alg)


def sig_sign(alg: str, sk: bytes, msg: bytes) -> bytes:
    """ML-DSA.Sign (empty context). sk is a seed or an expanded key."""
    return get_backend().sig_sign(alg, sk, msg)


def sig_verify(alg: str, vk: bytes, msg: bytes, sig: bytes) -> bool:
    """ML-DSA.Verify. Never raises, returns False on any failure."""
    return get_backend().sig_verify(alg, vk, msg, sig)
