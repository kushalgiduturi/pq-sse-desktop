"""pqsse-server: the PQ-SSE cloud server as its own program (Windows console, Linux, Docker).

    python -m pqsse.server init     [--config pqsse-server.toml]   make the data folder, keys, certificate, admin token
    python -m pqsse.server run      [--config ...]                 serve the HTTPS API and the admin interface
    python -m pqsse.server check    [--config ...]                 verify the store without starting (no passphrase needed)
    python -m pqsse.server backup   DEST [--config ...]            consistent copy, also while the server runs
    python -m pqsse.server restore  SOURCE [--config ...]          into an empty data folder
    python -m pqsse.server fingerprint [--config ...]              TLS certificate and server key fingerprints
    python -m pqsse.server pair-owner OWNER.pqpub [--replace]      install the data owner's public key
    python -m pqsse.server admin status|storage|connections|log|rotate-token|backup [DEST]|delete-group G

The passphrase that protects the server's keys comes from passphrase_file, the Docker secret
/run/secrets/pqsse_passphrase, or a prompt; never from the command line.
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import urllib.request
from pathlib import Path

from .. import pqbackend
from ..core.errors import BadPassphrase, PQSSEError
from ..core.pairing import export_pub, import_pub
from ..version import get_version
from . import config as cfg
from . import store, tls
from .http import AdminServer, PublicServer, load_or_make_token


def _config(args) -> cfg.Config:
    path = Path(args.config) if args.config else None
    if path is not None and not path.is_file():
        raise SystemExit(f"No configuration file at {path}. Run: python -m pqsse.server init --config {path}")
    return cfg.load(path)


def _certificate(config: cfg.Config) -> tuple[Path, Path]:
    if config.tls_cert and config.tls_key:
        return Path(config.tls_cert), Path(config.tls_key)
    cert, key = config.data_dir / "server.crt", config.data_dir / "server.key"
    if not cert.is_file() or not key.is_file():
        tls.make_self_signed(cert, key, config.public_names)
    return cert, key


def _open(config: cfg.Config):
    try:
        core = store.open_core(config, cfg.read_passphrase(config))
    except BadPassphrase:
        raise SystemExit("Wrong passphrase for the server store.") from None
    except store.StoreError as exc:
        raise SystemExit(f"The store cannot be used: {exc}. Run: python -m pqsse.server check") from None
    export_pub(config.data_dir / "cloud.pqpub", core.public_identity())
    return core


def cmd_init(args) -> int:
    path = Path(args.config or "pqsse-server.toml")
    if not path.exists():
        path.write_text(cfg.TEMPLATE, encoding="utf-8")
        print(f"Wrote {path}. Edit public_names and passphrase_file, then run init again.")
        return 0
    config = cfg.load(path)
    core = _open(config)
    cert, _ = _certificate(config)
    load_or_make_token(config)
    print(f"Data folder:         {config.data_dir}")
    print(f"Server public key:   {config.data_dir / 'cloud.pqpub'}  fingerprint {core.public_identity().fingerprint()}")
    print(f"TLS certificate:     {cert}  SHA-256 {tls.pretty(tls.fingerprint(cert))}")
    print(f"Admin token file:    {config.admin_token_path}")
    core.vault.close()
    return 0


def cmd_run(args) -> int:
    config = _config(args)
    core = _open(config)
    cert, key = _certificate(config)
    load_or_make_token(config)
    try:
        public = PublicServer(core, config, tls.server_context(cert, key))
        admin = AdminServer(core, config, public)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot start: {exc}") from None
    threads = [threading.Thread(target=s.serve_forever, daemon=True, name=n) for s, n in ((public, "api"), (admin, "admin"))]
    for t in threads:
        t.start()
    if pqbackend.is_fallback():
        print("WARNING: post-quantum code is the pure-Python fallback: slow, not constant time, for teaching only.", flush=True)
    else:
        print(f"Post-quantum code: {pqbackend.backend_name()}. {pqbackend.coverage()}.", flush=True)
    print(f"PQSSE-SERVER READY version={get_version()} api=https://{config.host}:{config.port}/v1/ "
          f"admin=http://{config.admin_host}:{config.admin_port}/admin/ tls={tls.fingerprint(cert)} "
          f"key={core.public_identity().fingerprint()}", flush=True)
    stop = threading.Event()
    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stop.set())
    try:
        while not stop.wait(0.5):
            pass
    finally:
        public.shutdown()
        admin.shutdown()
        public.server_close()
        admin.server_close()
        core.vault.close()
    return 0


def cmd_check(args) -> int:
    problems = store.check(_config(args))
    for line in problems:
        print("PROBLEM: " + line)
    print("Store check: " + ("OK" if not problems else f"{len(problems)} problem(s)"))
    return 1 if problems else 0


def cmd_backup(args) -> int:
    print("Backup written to", store.backup(_config(args), Path(args.dest)))
    return 0


def cmd_restore(args) -> int:
    store.restore(Path(args.source), _config(args))
    print("Restored. Start the server with: python -m pqsse.server run")
    return 0


def cmd_fingerprint(args) -> int:
    config = _config(args)
    cert, _ = _certificate(config)
    print("TLS certificate SHA-256:", tls.pretty(tls.fingerprint(cert)))
    pub = config.data_dir / "cloud.pqpub"
    if pub.is_file():
        print("Server key fingerprint: ", import_pub(pub, expect_role="cloud").fingerprint())
    return 0


def cmd_pair_owner(args) -> int:
    config = _config(args)
    ident = import_pub(Path(args.file), expect_role="owner")
    core = _open(config)
    try:
        core.pair_owner(ident, replace=args.replace)
    except PQSSEError as exc:
        raise SystemExit(f"Pairing refused: {exc}") from None
    finally:
        core.vault.close()
    print("Data owner paired. Owner key fingerprint:", ident.fingerprint())
    return 0


def cmd_admin(args) -> int:
    config = _config(args)
    token = load_or_make_token(config)
    base = f"http://127.0.0.1:{config.admin_port}/admin/"
    routes = {"status": ("GET", "status", None), "storage": ("GET", "storage", None),
              "connections": ("GET", "connections", None), "log": ("GET", "log", None),
              "rotate-token": ("POST", "rotate-token", {}),
              "backup": ("POST", "backup", {"to": args.arg} if args.arg else {}),
              "delete-group": ("POST", "delete-group", {"g": args.arg})}
    method, path, body = routes[args.action]
    if args.action == "delete-group" and not args.arg:
        raise SystemExit("Name the group: python -m pqsse.server admin delete-group GROUP")
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + path, data=data, method=method, headers={"X-Admin-Token": token})
    try:
        with urllib.request.urlopen(request, timeout=60) as reply:
            print(reply.read().decode())
    except urllib.error.HTTPError as exc:
        print(exc.read().decode() or exc.reason)
        return 1
    except OSError as exc:
        raise SystemExit(f"The admin interface is not reachable on 127.0.0.1:{config.admin_port}: {exc}") from None
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pqsse-server", description="PQ-SSE cloud server")
    parser.add_argument("--version", action="version", version=get_version())
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in (("init", cmd_init), ("run", cmd_run), ("check", cmd_check), ("fingerprint", cmd_fingerprint)):
        p = sub.add_parser(name)
        p.add_argument("--config")
        p.set_defaults(fn=fn)
    p = sub.add_parser("backup"); p.add_argument("dest"); p.add_argument("--config"); p.set_defaults(fn=cmd_backup)  # noqa: E702
    p = sub.add_parser("restore"); p.add_argument("source"); p.add_argument("--config"); p.set_defaults(fn=cmd_restore)  # noqa: E702
    p = sub.add_parser("pair-owner"); p.add_argument("file"); p.add_argument("--replace", action="store_true")  # noqa: E702
    p.add_argument("--config"); p.set_defaults(fn=cmd_pair_owner)  # noqa: E702
    p = sub.add_parser("admin")
    p.add_argument("action", choices=["status", "storage", "connections", "log", "rotate-token", "backup", "delete-group"])
    p.add_argument("arg", nargs="?")
    p.add_argument("--config")
    p.set_defaults(fn=cmd_admin)
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except store.StoreError as exc:
        print(f"FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
