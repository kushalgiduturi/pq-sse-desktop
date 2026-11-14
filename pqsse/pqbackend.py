"""Post-quantum backend abstraction.

One interface for ML-KEM (FIPS 203) and ML-DSA (FIPS 204):
``kem_keygen / kem_encaps / kem_decaps`` and ``sig_keygen / sig_sign / sig_verify``.

Backend choice: ``liboqs-python`` (``oqs``) when it imports and passes a round trip,
otherwise the pure Python ``kyber-py`` and ``dilithium-py`` packages.
No cryptography is implemented in this module.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

KEM_NAMES: tuple[str, ...] = ("ML-KEM-512", "ML-KEM-768", "ML-KEM-1024")
SIG_NAMES: tuple[str, ...] = ("ML-DSA-44", "ML-DSA-65", "ML-DSA-87")


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
        self._lock = threading.Lock()

    def kem_keygen(self, alg: str) -> tuple[bytes, bytes]:
        with self._lock:
            ek, dk = self._kem[alg].keygen()
        return bytes(ek), bytes(dk)

    def kem_encaps(self, alg: str, ek: bytes) -> tuple[bytes, bytes]:
        with self._lock:
            shared, ct = self._kem[alg].encaps(ek)
        return bytes(ct), bytes(shared)

    def kem_decaps(self, alg: str, dk: bytes, ct: bytes) -> bytes:
        with self._lock:
            return bytes(self._kem[alg].decaps(dk, ct))

    def sig_keygen(self, alg: str) -> tuple[bytes, bytes]:
        with self._lock:
            vk, sk = self._sig[alg].keygen()
        return bytes(vk), bytes(sk)

    def sig_sign(self, alg: str, sk: bytes, msg: bytes) -> bytes:
        with self._lock:
            return bytes(self._sig[alg].sign(sk, msg))

    def sig_verify(self, alg: str, vk: bytes, msg: bytes, sig: bytes) -> bool:
        with self._lock:
            try:
                return bool(self._sig[alg].verify(vk, msg, sig))
            except Exception:
                return False


class OqsBackend:
    """liboqs-python backend."""

    name = "liboqs (oqs)"

    def __init__(self) -> None:
        import oqs  # type: ignore[import-not-found]

        self._oqs = oqs

    def kem_keygen(self, alg: str) -> tuple[bytes, bytes]:
        with self._oqs.KeyEncapsulation(alg) as kem:
            ek = kem.generate_keypair()
            return bytes(ek), bytes(kem.export_secret_key())

    def kem_encaps(self, alg: str, ek: bytes) -> tuple[bytes, bytes]:
        with self._oqs.KeyEncapsulation(alg) as kem:
            ct, shared = kem.encap_secret(ek)
            return bytes(ct), bytes(shared)

    def kem_decaps(self, alg: str, dk: bytes, ct: bytes) -> bytes:
        with self._oqs.KeyEncapsulation(alg, secret_key=dk) as kem:
            return bytes(kem.decap_secret(ct))

    def sig_keygen(self, alg: str) -> tuple[bytes, bytes]:
        with self._oqs.Signature(alg) as signer:
            vk = signer.generate_keypair()
            return bytes(vk), bytes(signer.export_secret_key())

    def sig_sign(self, alg: str, sk: bytes, msg: bytes) -> bytes:
        with self._oqs.Signature(alg, secret_key=sk) as signer:
            return bytes(signer.sign(msg))

    def sig_verify(self, alg: str, vk: bytes, msg: bytes, sig: bytes) -> bool:
        try:
            with self._oqs.Signature(alg) as verifier:
                return bool(verifier.verify(msg, sig, vk))
        except Exception:
            return False


def _round_trip_ok(backend: Backend) -> bool:
    """Check that a backend really works before it is selected."""
    try:
        ek, dk = backend.kem_keygen("ML-KEM-512")
        ct, shared = backend.kem_encaps("ML-KEM-512", ek)
        if backend.kem_decaps("ML-KEM-512", dk, ct) != shared:
            return False
        vk, sk = backend.sig_keygen("ML-DSA-44")
        sig = backend.sig_sign("ML-DSA-44", sk, b"probe")
        return backend.sig_verify("ML-DSA-44", vk, b"probe", sig)
    except Exception:
        return False


@lru_cache(maxsize=1)
def get_backend() -> Backend:
    """Return the active backend: oqs if importable and working, else pure Python."""
    try:
        candidate: Backend = OqsBackend()
        if _round_trip_ok(candidate):
            return candidate
    except Exception:
        pass
    return PurePythonBackend()


def backend_name() -> str:
    return get_backend().name


def kem_keygen(alg: str) -> tuple[bytes, bytes]:
    """ML-KEM.KeyGen: returns (encapsulation key, decapsulation key)."""
    return get_backend().kem_keygen(alg)


def kem_encaps(alg: str, ek: bytes) -> tuple[bytes, bytes]:
    """ML-KEM.Encaps: returns (ciphertext, shared secret)."""
    return get_backend().kem_encaps(alg, ek)


def kem_decaps(alg: str, dk: bytes, ct: bytes) -> bytes:
    """ML-KEM.Decaps: returns the shared secret."""
    return get_backend().kem_decaps(alg, dk, ct)


def sig_keygen(alg: str) -> tuple[bytes, bytes]:
    """ML-DSA.KeyGen: returns (verification key, signing key)."""
    return get_backend().sig_keygen(alg)


def sig_sign(alg: str, sk: bytes, msg: bytes) -> bytes:
    """ML-DSA.Sign."""
    return get_backend().sig_sign(alg, sk, msg)


def sig_verify(alg: str, vk: bytes, msg: bytes, sig: bytes) -> bool:
    """ML-DSA.Verify. Never raises, returns False on any failure."""
    return get_backend().sig_verify(alg, vk, msg, sig)
