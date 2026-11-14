"""Typed errors used across the three parties."""
from __future__ import annotations


class PQSSEError(Exception):
    """Base class for all PQ-SSE errors."""


class WireError(PQSSEError):
    """Malformed or non-canonical wire data."""


class VerifyError(PQSSEError):
    """A receiver or owner side verification check failed.

    ``check`` names the failed check (for the verification panel in the UI).
    """

    def __init__(self, check: str, detail: str = "") -> None:
        super().__init__(f"{check}: {detail}" if detail else check)
        self.check = check
        self.detail = detail


class Rejected(PQSSEError):
    """The cloud (or the owner) refused a request. ``reason`` is a short code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class AccessDenied(PQSSEError):
    """The caller holds no key or capability for the requested object."""


class BadPassphrase(PQSSEError):
    """The passphrase does not open the key store."""
