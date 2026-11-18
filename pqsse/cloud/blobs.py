"""Encrypted documents as files next to the server database (networked server only).

A document ciphertext is stored once, under the SHA-256 of its bytes, in ``<data>/blobs/ab/abcd...``.
The database row keeps a short reference instead of the bytes. Writes are atomic (temporary file,
fsync, rename), so a crash leaves either the old state or the complete new file, never half a file.
Every read checks the hash, and ``check`` lists missing, damaged and unreferenced files.
"""
from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path

PREFIX = b"\x00blob:"          # a stored reference: PREFIX + 64 hex characters


class BlobError(Exception):
    """A document file is missing or does not match its hash."""


def is_ref(stored: bytes) -> bool:
    return stored.startswith(PREFIX) and len(stored) == len(PREFIX) + 64


class BlobStore:
    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.total_bytes = sum(p.stat().st_size for p in self._files())

    def _path(self, digest: str) -> Path:
        return self.folder / digest[:2] / digest

    def _files(self):
        return (p for p in self.folder.glob("??/*") if p.is_file() and not p.name.endswith(".tmp"))

    def put(self, data: bytes) -> bytes:
        digest = hashlib.sha256(data).hexdigest()
        path = self._path(digest)
        with self._lock:
            if not path.exists():
                path.parent.mkdir(exist_ok=True)
                tmp = path.with_name(path.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
                try:
                    with open(tmp, "wb") as handle:
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(tmp, path)
                except OSError:
                    tmp.unlink(missing_ok=True)     # for example a full disk: leave no partial file behind
                    raise
                self.total_bytes += len(data)
        return PREFIX + digest.encode("ascii")

    def get(self, ref: bytes) -> bytes:
        digest = ref[len(PREFIX):].decode("ascii")
        try:
            data = self._path(digest).read_bytes()
        except OSError as exc:
            raise BlobError(f"document file {digest[:12]} is missing") from exc
        if hashlib.sha256(data).hexdigest() != digest:
            raise BlobError(f"document file {digest[:12]} is damaged")
        return data

    def delete(self, ref: bytes) -> None:
        digest = ref[len(PREFIX):].decode("ascii")
        path = self._path(digest)
        with self._lock:
            try:
                size = path.stat().st_size
                path.unlink()
                self.total_bytes -= size
            except OSError:
                pass

    def check(self, referenced: set[bytes]) -> list[str]:
        """Problems: referenced files that are missing or damaged, and files nothing refers to."""
        problems = []
        on_disk = {p.name: p for p in self._files()}
        wanted = {ref[len(PREFIX):].decode("ascii") for ref in referenced}
        for digest in sorted(wanted):
            path = on_disk.get(digest)
            if path is None:
                problems.append(f"missing document file {digest[:12]}")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                problems.append(f"damaged document file {digest[:12]}")
        for name in sorted(set(on_disk) - wanted):
            problems.append(f"unreferenced document file {name[:12]}")
        return problems
