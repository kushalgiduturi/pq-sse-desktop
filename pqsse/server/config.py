"""Configuration of the networked cloud server: one TOML file, then PQSSE_SERVER_* environment variables.

    data_dir         where the store, the blobs, the certificate and the admin token live
    host, port       the public HTTPS API (all interfaces by default)
    admin_host, admin_port   the operator interface (127.0.0.1 by default; never on the public port)
    public_names     names and addresses put into the self-signed certificate and into invites
    tls_cert, tls_key        a certificate the operator supplies (empty: a self-signed one is made)
    passphrase_file  file that holds the passphrase protecting the server's secret keys
    limits           body sizes, documents per group, total storage, requests per minute, connections

The passphrase is never read from the command line or from a plain environment variable. It comes from
``passphrase_file``, from the Docker secret /run/secrets/pqsse_passphrase, or from a prompt.
"""
from __future__ import annotations

import getpass
import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

ENV_PREFIX = "PQSSE_SERVER_"
DOCKER_SECRET = Path("/run/secrets/pqsse_passphrase")
MiB = 1024 * 1024


@dataclass
class Config:
    data_dir: Path = Path("pqsse-server-data")
    host: str = "0.0.0.0"
    port: int = 8443
    admin_host: str = "127.0.0.1"
    admin_port: int = 8444
    public_names: list[str] = field(default_factory=lambda: ["localhost", "127.0.0.1"])
    tls_cert: str = ""
    tls_key: str = ""
    passphrase_file: str = ""
    kem: str = "ML-KEM-768"
    sig: str = "ML-DSA-65"
    max_body_bytes: int = 64 * MiB          # update batches and states
    max_small_body_bytes: int = 4 * MiB     # every other request
    max_doc_bytes: int = 16 * MiB
    max_docs_per_group: int = 100_000
    max_storage_bytes: int = 10 * 1024 * MiB
    requests_per_minute: int = 600          # per receiver credential and per client address
    max_connections: int = 64
    request_deadline: float = 60.0          # seconds a connection may take in total (slow clients are cut)
    allow_remote_admin: bool = False        # the admin port refuses non-local clients unless this is true

    @property
    def store_path(self) -> Path:
        return self.data_dir / "cloud.sqlite"

    @property
    def blob_dir(self) -> Path:
        return self.data_dir / "blobs"

    @property
    def admin_token_path(self) -> Path:
        return self.data_dir / "admin.token"

    def limits(self) -> dict:
        return {"max_doc_bytes": self.max_doc_bytes, "max_docs_per_group": self.max_docs_per_group,
                "max_storage_bytes": self.max_storage_bytes}


def _coerce(kind: type, raw: str):
    if kind is bool:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if kind is int:
        return int(raw)
    if kind is float:
        return float(raw)
    if kind is Path:
        return Path(raw)
    if kind == list[str]:
        return [part.strip() for part in raw.split(",") if part.strip()]
    return raw


def load(path: Path | None = None, environ: dict | None = None) -> Config:
    """Defaults, then the TOML file (if any), then PQSSE_SERVER_<NAME> environment variables."""
    environ = os.environ if environ is None else environ
    config = Config()
    def kind_of(name: str):
        value = getattr(config, name)
        if isinstance(value, Path):       # WindowsPath or PosixPath
            return Path
        return list[str] if isinstance(value, list) else type(value)
    kinds = {f.name: kind_of(f.name) for f in fields(Config)}
    path = path or (Path(environ[ENV_PREFIX + "CONFIG"]) if environ.get(ENV_PREFIX + "CONFIG") else None)
    if path is not None:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
        for key, value in data.items():
            if key not in kinds:
                raise ValueError(f"unknown setting {key!r} in {path}")
            setattr(config, key, Path(value) if kinds[key] is Path else value)
        if not config.data_dir.is_absolute():
            config.data_dir = (path.parent / config.data_dir).resolve()
    for key, kind in kinds.items():
        raw = environ.get(ENV_PREFIX + key.upper())
        if raw is not None:
            setattr(config, key, _coerce(kind, raw))
    return config


def read_passphrase(config: Config, prompt: bool = True) -> str:
    """From passphrase_file, then the Docker secret, then (on a console) a prompt. Never from argv."""
    for candidate in (config.passphrase_file, os.environ.get(ENV_PREFIX + "PASSPHRASE_FILE", ""), str(DOCKER_SECRET)):
        if candidate and Path(candidate).is_file():
            text = Path(candidate).read_text(encoding="utf-8").rstrip("\r\n")
            if text:
                return text
    if prompt:
        return getpass.getpass("Cloud server passphrase: ")
    raise SystemExit("No passphrase: set passphrase_file in the configuration or provide the pqsse_passphrase secret.")


TEMPLATE = """# PQ-SSE cloud server configuration. Every setting can also be set as PQSSE_SERVER_<NAME>.
data_dir = "data"
port = 8443
admin_port = 8444
# names and addresses clients use to reach this server; they go into the certificate and the invites
public_names = ["localhost", "127.0.0.1"]
# a file holding the passphrase that protects the server's keys (keep it readable by this account only)
passphrase_file = ""
# tls_cert = "/path/to/fullchain.pem"   # optional: your own certificate (clients still pin it)
# tls_key = "/path/to/privkey.pem"
requests_per_minute = 600
max_connections = 64
"""
