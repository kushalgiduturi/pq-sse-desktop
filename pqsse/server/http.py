"""The networked cloud server: a public HTTPS API and a separate operator (admin) interface.

Public API  POST /v1/<endpoint>  body = canonical wire encoding (docs/wire-format.md)
            GET  /v1/time        {"time": unix seconds}, for the clients' clock-skew check
  replies   200 wire body; 403 wire {reason, detail} when the protocol refuses; 400 malformed;
            404 unknown path; 413 too large; 429 too many requests (Retry-After); 503 busy; 500 generic.
  Error replies never contain stack traces, keys or file paths.

Admin       GET  /admin/status | /admin/storage | /admin/connections | /admin/log
            POST /admin/rotate-token | /admin/backup {"to"} | /admin/delete-group {"g"} | /admin/pair-owner {pqpub}
  Bound to 127.0.0.1 by default; every request needs the admin token (header X-Admin-Token); clients that
  are not local are refused unless allow_remote_admin is set. JSON in and out.

Defences against slow or abusive clients: a cap on open connections, a total deadline per connection
(the socket is shut when it passes, which also ends a slow TLS handshake), body limits per endpoint, and
rate limits per client address and per receiver credential.
"""
from __future__ import annotations

import hmac
import json
import secrets
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .. import pqbackend
from ..cloud.core import CloudCore
from ..core import wire
from ..core.errors import Rejected, WireError
from ..core.pairing import PublicIdentity
from ..version import get_version
from . import store
from .config import Config
from .limits import RateLimiter

API_PREFIX = "/v1/"
LARGE_ENDPOINTS = {"update", "state_put"}
PUBLIC_ENDPOINTS = {"pub", "info", "owner_pub", "join_post", "join_list", "mail_get", "ctl", "update", "state_put",
                    "states_get", "search", "doc_get"}
LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}


class _Connections:
    """Open connections, for the operator's view and the connection cap."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self._lock = threading.Lock()
        self._open: dict[int, dict] = {}

    def enter(self, peer: str) -> int | None:
        with self._lock:
            if len(self._open) >= self.cap:
                return None
            key = id(threading.current_thread()) ^ int(time.time() * 1e6)
            self._open[key] = {"peer": peer, "since": time.time(), "endpoint": ""}
            return key

    def note(self, key: int, endpoint: str) -> None:
        with self._lock:
            if key in self._open:
                self._open[key]["endpoint"] = endpoint

    def leave(self, key: int) -> None:
        with self._lock:
            self._open.pop(key, None)

    def snapshot(self) -> list[dict]:
        with self._lock:
            now = time.time()
            return [{"peer": c["peer"], "seconds": round(now - c["since"], 1), "endpoint": c["endpoint"]}
                    for c in self._open.values()]


class PublicServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    request_queue_size = 128

    def __init__(self, core: CloudCore, config: Config, context: ssl.SSLContext | None) -> None:
        self.core, self.config, self.context = core, config, context
        self.connections = _Connections(config.max_connections)
        self.by_address = RateLimiter(config.requests_per_minute)
        self.by_receiver = RateLimiter(config.requests_per_minute)
        self.started = time.time()
        family = socket.AF_INET6 if ":" in config.host else socket.AF_INET
        self.address_family = family
        super().__init__((config.host, config.port), _PublicHandler)

    def get_request(self):
        sock, addr = super().get_request()
        if self.context is not None:   # the handshake happens in the handler thread, under the deadline
            sock = self.context.wrap_socket(sock, server_side=True, do_handshake_on_connect=False)
        return sock, addr


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "pqsse-server"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return   # requests are logged by the core in its database, without contents

    def _send(self, status: int, body: bytes, ctype: str = "application/octet-stream", extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _read_body(self, limit: int) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._send(411 if "Content-Length" not in self.headers else 400, b"")
            return None
        if length < 0:
            self._send(400, b"")
            return None
        if length > limit:
            self._send(413, b"")
            return None
        return self.rfile.read(length)


class _PublicHandler(_Handler):
    server: PublicServer

    def setup(self) -> None:
        self._key = self.server.connections.enter(self.client_address[0])
        deadline = self.server.config.request_deadline
        self._timer = threading.Timer(deadline, self._cut)
        self._timer.daemon = True
        self._timer.start()
        self.request.settimeout(min(deadline, 30.0))
        self._handshake_ok = True
        if isinstance(self.request, ssl.SSLSocket):   # under the deadline, also for a connection over the cap
            try:
                self.request.do_handshake()
            except (OSError, ssl.SSLError):
                self._handshake_ok = False
        super().setup()

    def _cut(self) -> None:
        try:
            self.request.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def handle(self) -> None:
        if not self._handshake_ok:
            return
        try:
            super().handle()
        except (OSError, ssl.SSLError):
            pass   # client went away, timed out or failed the handshake

    def finish(self) -> None:
        self._timer.cancel()
        if self._key is not None:
            self.server.connections.leave(self._key)
        try:
            super().finish()
        except OSError:
            pass

    def _busy(self) -> bool:
        """Over the connection cap: read the request, answer 503, close."""
        if self._key is not None:
            return False
        self._read_body(self.server.config.max_small_body_bytes) if self.command == "POST" else None
        self._send(503, b"", extra={"Retry-After": "5"})
        return True

    def do_GET(self) -> None:  # noqa: N802
        if self._busy():
            return
        if self.path == API_PREFIX + "time":
            self._send(200, json.dumps({"time": time.time()}).encode(), "application/json")
        else:
            self._send(404, b"")

    def do_POST(self) -> None:  # noqa: N802
        if self._busy():
            return
        if not self.path.startswith(API_PREFIX):
            self._send(404, b"")
            return
        endpoint = self.path[len(API_PREFIX):]
        if endpoint not in PUBLIC_ENDPOINTS:
            self._send(404, b"")
            return
        self.server.connections.note(self._key, endpoint)
        ok, wait = self.server.by_address.allow(self.client_address[0])
        if not ok:
            self._send(429, b"", extra={"Retry-After": str(max(1, int(wait + 0.999)))})
            return
        limit = self.server.config.max_body_bytes if endpoint in LARGE_ENDPOINTS else self.server.config.max_small_body_bytes
        body = self._read_body(limit)
        if body is None:
            return
        uid = _receiver_of(body)
        if uid:
            ok, wait = self.server.by_receiver.allow(uid)
            if not ok:
                self._send(429, b"", extra={"Retry-After": str(max(1, int(wait + 0.999)))})
                return
        try:
            reply = self.server.core.handle(endpoint, body)
        except Rejected as exc:
            self._send(403, wire.enc({"reason": exc.reason, "detail": exc.detail}))
            return
        except Exception:  # never leak internals to a client
            self._send(500, b"")
            return
        self._send(200, reply)


def _receiver_of(body: bytes) -> str:
    """The receiver id a request claims (for its rate limit); empty for owner and public requests."""
    try:
        obj = wire.dec(body)
    except (WireError, ValueError):
        return ""
    if isinstance(obj, dict) and isinstance(obj.get("uid"), str):
        return obj["uid"][:64]
    return ""


# ------------------------------------------------------------------ admin interface
class AdminServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, core: CloudCore, config: Config, public: PublicServer | None) -> None:
        if config.admin_host not in LOOPBACK and not config.allow_remote_admin:
            raise ValueError("the admin interface binds to 127.0.0.1 unless allow_remote_admin is true")
        self.core, self.config, self.public = core, config, public
        self.started = time.time()
        super().__init__((config.admin_host, config.admin_port), _AdminHandler)


def load_or_make_token(config: Config, rotate: bool = False) -> str:
    path = config.admin_token_path
    if rotate or not path.is_file():
        token = secrets.token_urlsafe(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        from .tls import _write_private
        _write_private(tmp, token.encode("ascii"))
        tmp.replace(path)
        return token
    return path.read_text(encoding="ascii").strip()


class _AdminHandler(_Handler):
    server: AdminServer

    def _authorised(self) -> bool:
        if self.client_address[0] not in LOOPBACK and not self.server.config.allow_remote_admin:
            self._send(403, b'{"error": "admin requests are accepted from this computer only"}', "application/json")
            return False
        given = self.headers.get("X-Admin-Token", "")
        expected = load_or_make_token(self.server.config)
        if not given or not hmac.compare_digest(given.encode(), expected.encode()):
            self._send(401, b'{"error": "admin token missing or wrong"}', "application/json")
            return False
        return True

    def _json(self, status: int, obj: Any) -> None:
        self._send(status, json.dumps(obj, indent=1).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorised():
            return
        core, public = self.server.core, self.server.public
        if self.path == "/admin/status":
            info = core.handle("info", wire.enc(None))
            self._json(200, {"version": get_version(), "backend": pqbackend.backend_name(), **wire.dec(info),
                             "uptime_s": round(time.time() - self.server.started),
                             "connections": len(public.connections.snapshot()) if public else 0,
                             "fingerprint": core.public_identity().fingerprint()})
        elif self.path == "/admin/storage":
            stats = wire.dec(core.handle("admin_stats", wire.enc(None)))
            self._json(200, {"storage_bytes": core.storage_bytes(), "limit_bytes": self.server.config.max_storage_bytes,
                             **stats})
        elif self.path == "/admin/connections":
            self._json(200, public.connections.snapshot() if public else [])
        elif self.path.startswith("/admin/log"):
            self._json(200, wire.dec(core.handle("admin_log", wire.enc({"since": 0}))))
        else:
            self._json(404, {"error": "unknown admin path"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorised():
            return
        raw = self._read_body(1024 * 1024)
        if raw is None:
            return
        try:
            args = json.loads(raw or b"{}")
        except ValueError:
            self._json(400, {"error": "body is not JSON"})
            return
        try:
            if self.path == "/admin/rotate-token":
                load_or_make_token(self.server.config, rotate=True)
                self._json(200, {"ok": True, "token_file": str(self.server.config.admin_token_path)})
            elif self.path == "/admin/backup":
                dest = Path(args.get("to") or self.server.config.data_dir / "backups" / time.strftime("%Y%m%d-%H%M%S"))
                self._json(200, {"ok": True, "backup": str(store.backup(self.server.config, dest))})
            elif self.path == "/admin/delete-group":
                self._json(200, {"ok": True, "deleted": self.server.core.delete_group(str(args["g"]))})
            elif self.path == "/admin/pair-owner":
                ident = PublicIdentity.from_wire(wire.dec(bytes.fromhex(args["pqpub_hex"])))
                self.server.core.pair_owner(ident, replace=bool(args.get("replace")))
                self._json(200, {"ok": True, "owner_fingerprint": ident.fingerprint()})
            else:
                self._json(404, {"error": "unknown admin path"})
        except (Rejected, store.StoreError, KeyError, ValueError, WireError) as exc:
            self._json(400, {"error": getattr(exc, "detail", None) or str(exc) or type(exc).__name__})
