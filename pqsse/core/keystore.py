"""Encrypted at rest key-value store (one SQLite file per role).

The master key is derived from the user's passphrase with scrypt. Every record is
``AES-256-GCM(master, enc(value), aad = record name)``. Secret keys are only ever
written through this class and are never logged.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterator

from . import wire
from .errors import BadPassphrase, VerifyError
from .prims import aead_decrypt, aead_encrypt

SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_CHECK_NAME = "__vault_check__"


def derive_master_key(passphrase: str, salt: bytes, n: int = SCRYPT_N) -> bytes:
    """scrypt(passphrase, salt) -> 32 byte master key."""
    return hashlib.scrypt(
        passphrase.encode("utf-8"), salt=salt, n=n, r=_SCRYPT_R, p=_SCRYPT_P,
        maxmem=256 * 1024 * 1024, dklen=32,
    )


class Vault:
    """Passphrase protected record store backed by SQLite."""

    def __init__(self, path: str | Path, passphrase: str, scrypt_n: int = SCRYPT_N) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS vault_meta (k TEXT PRIMARY KEY, v BLOB)")
        self._db.execute("CREATE TABLE IF NOT EXISTS vault (name TEXT PRIMARY KEY, blob BLOB)")
        row = self._db.execute("SELECT v FROM vault_meta WHERE k='salt'").fetchone()
        if row is None:
            salt = os.urandom(16)
            self._db.execute("INSERT INTO vault_meta VALUES ('salt', ?)", (salt,))
            self._db.execute("INSERT INTO vault_meta VALUES ('n', ?)", (str(scrypt_n).encode(),))
            self._master = derive_master_key(passphrase, salt, scrypt_n)
            self.put(_CHECK_NAME, "ok")
        else:
            n_row = self._db.execute("SELECT v FROM vault_meta WHERE k='n'").fetchone()
            self._master = derive_master_key(passphrase, row[0], int(n_row[0]))
            try:
                self.get(_CHECK_NAME)
            except VerifyError as exc:
                self._db.close()
                raise BadPassphrase("wrong passphrase for " + self.path.name) from exc
        self._db.commit()

    @property
    def db(self) -> sqlite3.Connection:
        """The underlying connection, for roles that keep extra plain tables."""
        return self._db

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def encrypt(self, name: str, value: Any) -> bytes:
        """Encrypt a value under the master key, bound to ``name``."""
        return aead_encrypt(self._master, wire.enc(value), name.encode("utf-8"))

    def decrypt(self, name: str, blob: bytes) -> Any:
        return wire.dec(aead_decrypt(self._master, blob, name.encode("utf-8"), what="vault"))

    def put(self, name: str, value: Any) -> None:
        blob = self.encrypt(name, value)
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO vault VALUES (?, ?)", (name, blob))
            self._db.commit()

    def get(self, name: str, default: Any = None) -> Any:
        with self._lock:
            row = self._db.execute("SELECT blob FROM vault WHERE name=?", (name,)).fetchone()
        if row is None:
            return default
        return self.decrypt(name, row[0])

    def delete(self, name: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM vault WHERE name=?", (name,))
            self._db.commit()

    def names(self, prefix: str = "") -> Iterator[str]:
        with self._lock:
            rows = self._db.execute("SELECT name FROM vault WHERE name LIKE ? ORDER BY name", (prefix + "%",)).fetchall()
        for (name,) in rows:
            if name != _CHECK_NAME:
                yield name

    def close(self) -> None:
        with self._lock:
            self._db.close()


class MemoryVault:
    """In-memory stand-in with the same interface, used by tests and benchmarks."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}
        self._key = os.urandom(32)
        self._lock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def encrypt(self, name: str, value: Any) -> bytes:
        """Test stand-in: random key AES-GCM so stored blobs are still ciphertext."""
        return aead_encrypt(self._key, wire.enc(value), name.encode("utf-8"))

    def decrypt(self, name: str, blob: bytes) -> Any:
        return wire.dec(aead_decrypt(self._key, blob, name.encode("utf-8"), what="vault"))

    def put(self, name: str, value: Any) -> None:
        self._data[name] = wire.enc(value)

    def get(self, name: str, default: Any = None) -> Any:
        blob = self._data.get(name)
        return default if blob is None else wire.dec(blob)

    def delete(self, name: str) -> None:
        self._data.pop(name, None)

    def names(self, prefix: str = "") -> Iterator[str]:
        return iter(sorted(k for k in self._data if k.startswith(prefix)))

    def close(self) -> None:
        self._data.clear()
