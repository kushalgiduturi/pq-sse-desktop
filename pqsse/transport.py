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


class OwnerTagged:
    """Names the data owner in every request (design note 004 A), so a server with several owners routes it.
    A one-owner server ignores the field."""

    def __init__(self, inner: Any, owner: str) -> None:
        self.inner, self.owner = inner, owner

    def call(self, endpoint: str, obj: Any) -> Any:
        if isinstance(obj, dict) and "owner" not in obj:
            obj = {**obj, "owner": self.owner}
        return self.inner.call(endpoint, obj)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


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


class ServerBusy(CloudUnavailable):
    """The server asked the client to slow down (429) or is at its connection limit (503)."""

    def __init__(self, message: str, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = retry_after


MAX_REPLY = 128 * 1024 * 1024    # bytes; the server's largest replies (a state, a document part) are far smaller


class ReplyTooLarge(PQSSEError):
    """The server sent more than any honest reply can be."""


class HttpsCloud:
    """Client of the networked server (pqsse.server): HTTPS, the server certificate pinned by fingerprint.

    The pin comes from the invite. A server whose certificate does not match is refused before any
    request byte is sent. Replies: 200 wire body, 403 protocol refusal, 413/429/503 as clear errors.

    Retries: a request that could not be completed (connection refused, reset or timed out; 429; 503) is
    sent again, the same bytes, up to ``attempts`` times with exponential backoff and jitter, honouring the
    server's Retry-After. This is safe for every endpoint: reads are repeatable, and the server answers the
    exact last accepted batch, control message or state as "already applied" (design note 002). A pin
    mismatch, a protocol refusal (403) or a too-large request (413) is never retried."""

    def __init__(self, host: str, port: int, pin: str, timeout: float = 60.0, attempts: int = 4,
                 backoff: float = 0.5, sleep=None) -> None:
        import time as _time
        self.host, self.port, self.pin, self.timeout = host, port, pin, timeout
        self.attempts, self.backoff = max(1, attempts), backoff
        self.sleep = sleep or _time.sleep
        self.online: bool | None = None          # last known reachability, for the app's offline state

    def _connection(self):
        from .server.tls import PinnedHTTPSConnection   # imported late: the desktop app's local mode never needs it
        return PinnedHTTPSConnection(self.host, self.port, self.pin, timeout=self.timeout)

    def _once(self, endpoint: str, body: bytes) -> Any:
        from .server.tls import PinMismatch
        conn = self._connection()
        try:
            conn.request("POST", "/v1/" + endpoint, body=body, headers={"Content-Type": "application/octet-stream"})
            response = conn.getresponse()
            data = response.read(MAX_REPLY + 1)   # review (milestone 7): a server cannot make the client hold any amount
            if len(data) > MAX_REPLY:
                raise ReplyTooLarge(f"the reply from {self.host}:{self.port} is larger than {MAX_REPLY // (1024 * 1024)} MB")
        except PinMismatch as exc:
            raise PinRefused(f"refused the server at {self.host}:{self.port}: {exc}") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise CloudUnavailable(f"cloud server not reachable at {self.host}:{self.port}") from exc
        finally:
            conn.close()
        if response.status == 200:
            return wire.dec(data)
        if response.status == 403:
            err = wire.dec(data)
            raise Rejected(err["reason"], err["detail"])
        if response.status in (429, 503):
            try:
                wait = float(response.getheader("Retry-After") or 1)
            except ValueError:
                wait = 1.0
            text = "too many requests; try again shortly" if response.status == 429 else "the server is busy; try again shortly"
            raise ServerBusy(text, wait)
        if response.status == 413:
            raise RequestTooLarge("the request is larger than the server accepts")
        raise CloudUnavailable(f"cloud server returned HTTP {response.status}")

    def call(self, endpoint: str, obj: Any) -> Any:
        import random
        body = wire.enc(obj)
        for attempt in range(1, self.attempts + 1):
            try:
                reply = self._once(endpoint, body)
                self.online = True
                return reply
            except (PinRefused, RequestTooLarge, ReplyTooLarge):
                raise
            except ServerBusy as exc:
                self.online = True
                if attempt == self.attempts:
                    raise
                self.sleep(min(30.0, max(exc.retry_after, self.backoff * 2 ** (attempt - 1))))
            except CloudUnavailable:
                self.online = False
                if attempt == self.attempts:
                    raise
                self.sleep(self.backoff * 2 ** (attempt - 1) * (0.5 + random.random()))
        raise CloudUnavailable("unreachable")   # not reached

    def server_time(self) -> float:
        """The server's clock (unix seconds), for the clock-skew check."""
        import json

        from .server.tls import PinMismatch
        conn = self._connection()
        try:
            conn.request("GET", "/v1/time")
            reply = conn.getresponse()
            if reply.status != 200:
                raise CloudUnavailable(f"cloud server returned HTTP {reply.status}")
            return float(json.loads(reply.read())["time"])
        except PinMismatch as exc:
            raise PinRefused(f"refused the server at {self.host}:{self.port}: {exc}") from exc
        except (OSError, http.client.HTTPException, ValueError, KeyError) as exc:
            raise CloudUnavailable(f"cloud server not reachable at {self.host}:{self.port}") from exc
        finally:
            conn.close()


class PinRefused(CloudUnavailable):
    """The server's TLS certificate is not the one pinned for it: possibly a different server or an attacker."""


class RequestTooLarge(CloudUnavailable):
    """The server refused the request size (413)."""


SKEW_WARN = 120.0     # seconds: tell the user to fix the clock
SKEW_REFUSE = 290.0   # seconds: requests would fall outside the server's 300 s token window


def clock_skew(api: "HttpsCloud", local_time=None) -> tuple[float, str, str]:
    """(skew in seconds, level "ok" | "warn" | "refuse", plain message)."""
    import time as _time
    local_time = local_time or _time.time
    before = local_time()
    server = api.server_time()
    after = local_time()
    skew = server - (before + after) / 2
    size = abs(skew)
    if size >= SKEW_REFUSE:
        return skew, "refuse", (f"This computer's clock is {size:.0f} seconds away from the server's. Requests would be "
                                "refused as stale. Set the clock automatically (Windows: Settings, Time, Set time "
                                "automatically), then connect again.")
    if size >= SKEW_WARN:
        return skew, "warn", (f"This computer's clock is {size:.0f} seconds away from the server's. Searches still work, "
                              "but set the clock automatically to avoid refused requests.")
    return skew, "ok", f"Clocks agree within {size:.1f} seconds."
