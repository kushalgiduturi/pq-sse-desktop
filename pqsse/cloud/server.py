"""Local-only HTTP front end of the cloud server.

POST /api/<endpoint> with a wire encoded body. Replies: 200 with a wire encoded body,
403 with {reason, detail} when the cloud rejects the request. The socket is bound to
127.0.0.1 and non-loopback peers are refused. Operator endpoints (admin_*) need the
admin token that the launching process chose.
"""
from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..core import wire
from ..core.errors import Rejected
from .core import CloudCore

MAX_BODY = 512 * 1024 * 1024
LOOPBACK = ("127.0.0.1", "::1")


class CloudHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, core: CloudCore, host: str, port: int, admin_token: str | None) -> None:
        if host not in LOOPBACK:
            raise ValueError("the cloud API is local-only, bind to 127.0.0.1")
        super().__init__((host, port), _Handler)
        self.core = core
        self.admin_token = admin_token


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: CloudHTTPServer

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return  # the request log lives in the cloud database, nothing goes to stderr

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _reject(self, reason: str, detail: str = "") -> None:
        self._send(403, wire.enc({"reason": reason, "detail": detail}))

    def do_POST(self) -> None:  # noqa: N802
        if self.client_address[0] not in LOOPBACK:
            self._reject("not_local", "only loopback clients are served")
            return
        if not self.path.startswith("/api/"):
            self._send(404, b"")
            return
        endpoint = self.path[len("/api/"):]
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            self._reject("malformed", "bad content length")
            return
        body = self.rfile.read(length)
        if endpoint.startswith("admin_"):
            token = self.headers.get("X-Admin-Token", "")
            expected = self.server.admin_token
            if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
                self._reject("admin_only", "operator endpoint")
                return
        try:
            reply = self.server.core.handle(endpoint, body)
        except Rejected as exc:
            self._reject(exc.reason, exc.detail)
            return
        except Exception as exc:  # defensive: never leak a traceback to a client
            self._send(500, type(exc).__name__.encode())
            return
        self._send(200, reply)


def make_server(core: CloudCore, host: str = "127.0.0.1", port: int = 8765,
                admin_token: str | None = None) -> CloudHTTPServer:
    """Create (but do not start) the HTTP server for a CloudCore."""
    return CloudHTTPServer(core, host, port, admin_token)
