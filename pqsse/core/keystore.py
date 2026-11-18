"""Encrypted at rest key-value store (one SQLite file per role).

The master key is derived from the user's passphrase with scrypt. Every record is
``AES-256-GCM(master, enc(value), aad = record name)``. Secret keys are only ever
written through this class and are never logged.

Key lifecycle (milestone 5): ``change_passphrase`` re-encrypts every record under a new key in one
transaction; ``export_backup`` writes one file, encrypted under a separate backup passphrase, that
``import_backup`` turns back into a vault; a new vault file is made readable by this account only
(``fileperm``); ``close`` overwrites the master key in memory. That last step is best effort: Python
may hold other copies of key bytes, which it frees but does not overwrite.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterator

from . import fileperm, wire
from .errors import BadPassphrase, PQSSEError, VerifyError
from .prims import aead_decrypt, aead_encrypt

SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_CHECK_NAME = "__vault_check__"
BACKUP_MAGIC = b"PQSSE-KEY-BACKUP-1\n"
BACKUP_SCRYPT_N = 2**17          # a backup leaves this computer: a higher cost for guessing its passphrase


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
        new_file = not self.path.exists()
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS vault_meta (k TEXT PRIMARY KEY, v BLOB)")
        self._db.execute("CREATE TABLE IF NOT EXISTS vault (name TEXT PRIMARY KEY, blob BLOB)")
        row = self._db.execute("SELECT v FROM vault_meta WHERE k='salt'").fetchone()
        if row is None:
            salt = os.urandom(16)
            self._db.execute("INSERT INTO vault_meta VALUES ('salt', ?)", (salt,))
            self._db.execute("INSERT INTO vault_meta VALUES ('n', ?)", (str(scrypt_n).encode(),))
            self._master = bytearray(derive_master_key(passphrase, salt, scrypt_n))
            self.put(_CHECK_NAME, "ok")
        else:
            n_row = self._db.execute("SELECT v FROM vault_meta WHERE k='n'").fetchone()
            self._master = bytearray(derive_master_key(passphrase, row[0], int(n_row[0])))
            try:
                self.get(_CHECK_NAME)
            except VerifyError as exc:
                self._db.close()
                self._wipe()
                raise BadPassphrase("wrong passphrase for " + self.path.name) from exc
        self._db.commit()
        if new_file:
            fileperm.restrict(self.path)

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
            self._wipe()

    def _wipe(self) -> None:
        for i in range(len(self._master)):
            self._master[i] = 0

    # ------------------------------------------------------------------ key lifecycle
    def _kdf_params(self) -> tuple[bytes, int]:
        salt = self._db.execute("SELECT v FROM vault_meta WHERE k='salt'").fetchone()[0]
        n = int(self._db.execute("SELECT v FROM vault_meta WHERE k='n'").fetchone()[0])
        return salt, n

    def check_passphrase(self, passphrase: str) -> bool:
        salt, n = self._kdf_params()
        return hmac.compare_digest(derive_master_key(passphrase, salt, n), bytes(self._master))

    def change_passphrase(self, old: str, new: str, scrypt_n: int | None = None) -> None:
        """Re-encrypt every record under a key from the new passphrase and a new salt, all or nothing."""
        if not self.check_passphrase(old):
            raise BadPassphrase("the current passphrase is wrong")
        if not new:
            raise PQSSEError("the new passphrase is empty")
        with self._lock:
            _, n = self._kdf_params()
            n = scrypt_n or n
            salt = os.urandom(16)
            master = bytearray(derive_master_key(new, salt, n))
            rows = self._db.execute("SELECT name, blob FROM vault").fetchall()
            try:
                for name, blob in rows:
                    fresh = aead_encrypt(bytes(master), wire.enc(self.decrypt(name, blob)), name.encode("utf-8"))
                    self._db.execute("UPDATE vault SET blob=? WHERE name=?", (fresh, name))
                self._db.execute("UPDATE vault_meta SET v=? WHERE k='salt'", (salt,))
                self._db.execute("UPDATE vault_meta SET v=? WHERE k='n'", (str(n).encode(),))
                self._db.commit()
            except BaseException:
                self._db.rollback()
                for i in range(len(master)):
                    master[i] = 0
                raise
            self._wipe()
            self._master = master

    def export_backup(self, dest: str | Path, backup_passphrase: str, scrypt_n: int = BACKUP_SCRYPT_N) -> Path:
        """Write every record to one file encrypted under the backup passphrase (scrypt, AES-256-GCM)."""
        records = {name: self.get(name) for name in self.names() if not name.startswith("journal:")}
        return seal_file(dest, BACKUP_MAGIC, records, backup_passphrase, scrypt_n)


def seal_file(dest: str | Path, magic: bytes, value: Any, passphrase: str, scrypt_n: int = BACKUP_SCRYPT_N) -> Path:
    """Write ``value`` to a new file, encrypted under a passphrase (scrypt, AES-256-GCM, the magic as aad).
    Used by key backups and group exports. Never overwrites a file; the file is made private to this account."""
    if len(passphrase) < 12:
        raise PQSSEError("use a passphrase of at least 12 characters")
    dest = Path(dest)
    if dest.exists():
        raise PQSSEError(f"{dest.name} already exists; choose a new file name")
    salt = os.urandom(16)
    key = bytearray(derive_master_key(passphrase, salt, scrypt_n))
    try:
        sealed = aead_encrypt(bytes(key), wire.enc(value), magic)
    finally:
        for i in range(len(key)):
            key[i] = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(magic + wire.enc({"salt": salt, "n": scrypt_n, "data": sealed}))
    fileperm.restrict(dest)
    return dest


def open_file(source: str | Path, magic: bytes, passphrase: str, what: str) -> Any:
    """Read a file written by ``seal_file``. Raises BadPassphrase for a wrong passphrase or a damaged file."""
    source = Path(source)
    raw = source.read_bytes()
    if not raw.startswith(magic):
        raise PQSSEError(f"{source.name} is not a PQ-SSE {what}")
    try:
        meta = wire.dec(raw[len(magic):])
        key = derive_master_key(passphrase, meta["salt"], int(meta["n"]))
        return wire.dec(aead_decrypt(key, meta["data"], magic, what=what))
    except VerifyError as exc:
        raise BadPassphrase(f"wrong passphrase, or the {what} file is damaged") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise PQSSEError(f"{source.name} is not a readable PQ-SSE {what}") from exc


def import_backup(source: str | Path, backup_passphrase: str, dest: str | Path, new_passphrase: str,
                  scrypt_n: int = SCRYPT_N) -> Vault:
    """Make a new vault at ``dest`` from a backup file. Never overwrites an existing vault."""
    source, dest = Path(source), Path(dest)
    if dest.exists():
        raise PQSSEError(f"{dest.name} already exists; a backup is never imported over existing keys")
    records = open_file(source, BACKUP_MAGIC, backup_passphrase, "key backup")
    vault = Vault(dest, new_passphrase, scrypt_n)
    for name, value in records.items():
        vault.put(name, value)
    return vault


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
