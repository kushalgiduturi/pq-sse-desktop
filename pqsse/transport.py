"""Transports between a client role (owner, receiver) and the cloud.

Both transports carry the same wire encoded bodies to ``CloudCore.handle``:
  InProcessCloud  direct call, used by tests, benchmarks and the Attack Lab sandbox.
  HttpCloud       HTTP POST to the local cloud process on 127.0.0.1.
"""
from __future__ import annotations

import http.client
from typing import Any, Protocol

from .core import wire
from .core.errors import PQSSEError, Rejected


class CloudAPI(Protocol):
    """What owner and receiver need from a cloud connection."""

    def call(self, endpoint: str, obj: Any) -> Any: ...


class InProcessCloud:
    """Calls a CloudCore living in the same process. No state is shared besides messages."""

    def __init__(self, core: Any) -> None:
        self.core = core

    def call(self, endpoint: str, obj: Any) -> Any:
        return wire.dec(self.core.handle(endpoint, wire.enc(obj)))


class CloudUnavailable(PQSSEError):
    """The cloud process cannot be reached."""


class HttpCloud:
    """HTTP client for the local cloud process."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, timeout: float = 120.0,
                 admin_token: str | None = None) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.admin_token = admin_token

    def call(self, endpoint: str, obj: Any) -> Any:
        body = wire.enc(obj)
        headers = {"Content-Type": "application/octet-stream"}
        if self.admin_token and endpoint.startswith("admin_"):
            headers["X-Admin-Token"] = self.admin_token
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            conn.request("POST", "/api/" + endpoint, body=body, headers=headers)
            response = conn.getresponse()
            data = response.read()
        except (OSError, http.client.HTTPException) as exc:
            raise CloudUnavailable(f"cloud not reachable on {self.host}:{self.port}") from exc
        finally:
            conn.close()
        if response.status == 200:
            return wire.dec(data)
        if response.status == 403:
            err = wire.dec(data)
            raise Rejected(err["reason"], err["detail"])
        raise CloudUnavailable(f"cloud returned HTTP {response.status}")

    def alive(self) -> bool:
        try:
            self.call("info", None)
            return True
        except PQSSEError:
            return False


class HttpsCloud:
    """Client of the networked server (pqsse.server): HTTPS, the server certificate pinned by fingerprint.

    The pin comes from the invite. A server whose certificate does not match is refused before any
    request byte is sent. Replies: 200 wire body, 403 protocol refusal, 413/429/503 as clear errors."""

    def __init__(self, host: str, port: int, pin: str, timeout: float = 60.0) -> None:
        self.host, self.port, self.pin, self.timeout = host, port, pin, timeout

    def _connection(self):
        from .server.tls import PinnedHTTPSConnection   # imported late: the desktop app's local mode never needs it
        return PinnedHTTPSConnection(self.host, self.port, self.pin, timeout=self.timeout)

    def call(self, endpoint: str, obj: Any) -> Any:
        from .server.tls import PinMismatch
        conn = self._connection()
        try:
            conn.request("POST", "/v1/" + endpoint, body=wire.enc(obj), headers={"Content-Type": "application/octet-stream"})
            response = conn.getresponse()
            data = response.read()
        except PinMismatch as exc:
            raise CloudUnavailable(f"refused the server at {self.host}:{self.port}: {exc}") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise CloudUnavailable(f"cloud server not reachable at {self.host}:{self.port}") from exc
        finally:
            conn.close()
        if response.status == 200:
            return wire.dec(data)
        if response.status == 403:
            err = wire.dec(data)
            raise Rejected(err["reason"], err["detail"])
        messages = {413: "the request is larger than the server accepts", 429: "too many requests; try again shortly",
                    503: "the server is busy; try again shortly"}
        raise CloudUnavailable(messages.get(response.status, f"cloud server returned HTTP {response.status}"))

    def server_time(self) -> float:
        """The server's clock (unix seconds), for the clock-skew check."""
        import json
        conn = self._connection()
        try:
            conn.request("GET", "/v1/time")
            return float(json.loads(conn.getresponse().read())["time"])
        finally:
            conn.close()
