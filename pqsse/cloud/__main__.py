"""Run the cloud server as its own process:  python -m pqsse.cloud

The passphrase that protects the cloud's secret keys comes from the environment
variable PQSSE_CLOUD_PASSPHRASE (set by the desktop app for its child process) or from
a console prompt. It is never taken from the command line and never printed.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from .. import paths, pqbackend
from ..core.errors import BadPassphrase, PQSSEError
from ..core.keystore import Vault
from ..core.pairing import export_pub, import_pub
from ..pqbackend import KEM_NAMES, SIG_NAMES, Params
from .core import CloudCore
from .server import make_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pqsse.cloud", description="PQ-SSE cloud server (local only)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=None, help="cloud database file")
    parser.add_argument("--kem", choices=KEM_NAMES, default="ML-KEM-768", help="used only when the database is new")
    parser.add_argument("--sig", choices=SIG_NAMES, default="ML-DSA-65", help="used only when the database is new")
    parser.add_argument("--name", default="cloud")
    parser.add_argument("--pub", type=Path, default=None, help="where to write cloud.pqpub")
    parser.add_argument("--owner-pub", type=Path, default=None, help="owner.pqpub to pair with at start")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = args.db or paths.cloud_db()
    passphrase = os.environ.get("PQSSE_CLOUD_PASSPHRASE")
    if passphrase is None:
        passphrase = getpass.getpass("Cloud passphrase: ")
    if not passphrase:
        print("PQSSE-CLOUD ERROR empty passphrase", flush=True)
        return 2
    try:
        vault = Vault(db_path, passphrase)
    except BadPassphrase:
        print("PQSSE-CLOUD ERROR wrong passphrase", flush=True)
        return 3
    core = CloudCore(vault, Params(args.kem, args.sig), args.name)
    pub_path = args.pub or (paths.pub_dir() / "cloud.pqpub")
    pub_path.parent.mkdir(parents=True, exist_ok=True)
    export_pub(pub_path, core.public_identity())
    if args.owner_pub is not None:
        try:
            core.pair_owner(import_pub(args.owner_pub, expect_role="owner"))
        except PQSSEError as exc:
            print(f"PQSSE-CLOUD ERROR pairing failed: {exc}", flush=True)
            return 4
    try:
        server = make_server(core, "127.0.0.1", args.port, os.environ.get("PQSSE_CLOUD_ADMIN_TOKEN"))
    except OSError as exc:
        print(f"PQSSE-CLOUD ERROR cannot bind port {args.port}: {exc}", flush=True)
        return 5
    print(f"PQSSE-CLOUD READY port={args.port} params={core.params.kem}/{core.params.sig} "
          f"backend={pqbackend.backend_name()} fingerprint={core.public_identity().fingerprint()}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        vault.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
