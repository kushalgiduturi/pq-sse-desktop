"""The server's store on disk: open (WAL, quick integrity check), check, online backup, restore.

Layout of the data folder:
    cloud.sqlite        keys (encrypted with the passphrase), index, states, credentials, mailbox, log
    blobs/              encrypted documents, one file per ciphertext, named by its SHA-256
    server.crt/.key     TLS certificate and key (self-signed unless the operator supplies one)
    admin.token         token for the operator interface
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import time
from pathlib import Path

from ..cloud.blobs import BlobStore, is_ref
from ..cloud.core import CloudCore
from ..core import fileperm
from ..core.keystore import Vault
from ..pqbackend import Params
from .config import Config

BACKUP_MANIFEST = "pqsse-backup.json"


class StoreError(Exception):
    """The store cannot be used: damaged, incomplete or not a PQ-SSE server store."""


def open_core(config: Config, passphrase: str) -> CloudCore:
    """Open (or create) the store for serving: WAL journal, quick check, blobs and limits wired in."""
    if not config.data_dir.exists():
        config.data_dir.mkdir(parents=True)
        fileperm.restrict(config.data_dir)        # new files inside inherit "this account only"
    vault = Vault(config.store_path, passphrase)
    db = vault.db
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        result = db.execute("PRAGMA quick_check").fetchone()[0]
    except sqlite3.DatabaseError as exc:
        vault.close()
        raise StoreError(f"the store is damaged: {exc}") from exc
    if result != "ok":
        vault.close()
        raise StoreError(f"the store failed its integrity check: {result}")
    return CloudCore(vault, Params(config.kem, config.sig), "cloud", blobs=BlobStore(config.blob_dir), require_invite=True,
                     limits=config.limits())


def check(config: Config) -> list[str]:
    """Verify the store without starting the server or needing the passphrase. Empty list: all good."""
    problems: list[str] = []
    if not config.store_path.is_file():
        return [f"no store at {config.store_path}"]
    db = sqlite3.connect(f"file:{config.store_path}?mode=ro", uri=True)
    try:
        try:
            result = db.execute("PRAGMA integrity_check").fetchall()
        except sqlite3.DatabaseError as exc:
            return [f"database is damaged: {exc}"]
        if [r[0] for r in result] != ["ok"]:
            problems += [f"database: {r[0]}" for r in result]
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = {"vault", "groups", "entries", "docs", "states", "creds"} - tables
        if missing:
            problems.append(f"not a complete PQ-SSE server store, missing tables: {sorted(missing)}")
            return problems
        referenced = {row[0] for row in db.execute("SELECT blob FROM docs") if is_ref(row[0])}
    finally:
        db.close()
    if config.blob_dir.exists() or referenced:
        problems += BlobStore(config.blob_dir).check(referenced)
    return problems


def backup(config: Config, dest: Path) -> Path:
    """A consistent copy while the server may be running: SQLite's online backup, then the document files.

    The database is copied first; files are content-addressed and never change, so every file the copied
    database refers to already exists. Files added after the database copy are harmless extras."""
    if not config.store_path.is_file():
        raise StoreError(f"no store at {config.store_path}")
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise StoreError(f"{dest} is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{config.store_path}?mode=ro", uri=True)
    out = sqlite3.connect(dest / "cloud.sqlite")
    try:
        src.backup(out)
        referenced = {row[0] for row in out.execute("SELECT blob FROM docs") if is_ref(row[0])}
    finally:
        out.close()
        src.close()
    for ref in referenced:
        digest = ref.decode("latin-1")[-64:]
        source = config.blob_dir / digest[:2] / digest
        target = dest / "blobs" / digest[:2] / digest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (dest / BACKUP_MANIFEST).write_text(json.dumps({"format": 1, "created": time.time(), "documents": len(referenced)}),
                                        encoding="utf-8")
    problems = check(Config(data_dir=dest))
    if problems:
        raise StoreError("the backup does not check out: " + "; ".join(problems))
    return dest


def restore(source: Path, config: Config) -> None:
    """Copy a backup into an empty data folder (the TLS certificate and admin token are made anew)."""
    source = Path(source)
    if not (source / BACKUP_MANIFEST).is_file():
        raise StoreError(f"{source} is not a PQ-SSE server backup")
    problems = check(Config(data_dir=source))
    if problems:
        raise StoreError("the backup is damaged: " + "; ".join(problems))
    if config.store_path.exists():
        raise StoreError(f"{config.store_path} already exists; restore only into an empty data folder")
    config.data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "cloud.sqlite", config.store_path)
    if (source / "blobs").is_dir():
        shutil.copytree(source / "blobs", config.blob_dir, dirs_exist_ok=True)
