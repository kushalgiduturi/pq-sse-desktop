"""TLS for the networked server, and certificate pinning for its clients.

The server makes a self-signed ECDSA P-256 certificate at first start (or uses one the operator gives).
Clients do not trust any certificate authority: they pin the SHA-256 fingerprint of the server's
certificate (DER), which reaches them in the invite, and they check it before sending any request byte.

Server settings: TLS 1.2 or 1.3 only; for TLS 1.2 only ECDHE key exchange with AES-GCM or ChaCha20-Poly1305;
no compression, no renegotiation. TLS here uses classical key exchange: it protects the transport, the
post-quantum protection of keys and data comes from the protocol itself (ML-KEM, ML-DSA) inside it.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import http.client
import ipaddress
import os
import socket
import ssl
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

TLS12_CIPHERS = "ECDHE+AESGCM:ECDHE+CHACHA20:!aNULL:!MD5:!DSS"


class PinMismatch(ssl.SSLError):
    """The server's certificate is not the one pinned in the invite."""


def make_self_signed(cert_path: Path, key_path: Path, names: list[str], years: int = 5) -> None:
    """ECDSA P-256 key and a self-signed certificate for ``names`` (host names and IP addresses)."""
    key = ec.generate_private_key(ec.SECP256R1())
    sans: list[x509.GeneralName] = []
    for name in dict.fromkeys(names or ["localhost"]):
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            sans.append(x509.DNSName(name))
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PQ-SSE cloud server")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(days=365 * years))
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    key_path.parent.mkdir(parents=True, exist_ok=True)
    _write_private(key_path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _write_private(path: Path, data: bytes) -> None:
    """Create the file readable by this account only (POSIX mode 600; on Windows an ACL for this user alone)."""
    from ..core import fileperm
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    fileperm.restrict(path)


def fingerprint_of_der(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()


def fingerprint(cert_path: Path) -> str:
    """SHA-256 of the certificate in DER form, 64 hex characters."""
    der = ssl.PEM_cert_to_DER_cert(Path(cert_path).read_text(encoding="ascii"))
    return fingerprint_of_der(der)


def pretty(fp: str) -> str:
    """Groups of four for reading aloud: ab12 cd34 ..."""
    return " ".join(fp[i:i + 4] for i in range(0, len(fp), 4))


def server_context(cert_path: Path, key_path: Path) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers(TLS12_CIPHERS)
    ctx.options |= ssl.OP_NO_COMPRESSION | ssl.OP_CIPHER_SERVER_PREFERENCE | getattr(ssl, "OP_NO_RENEGOTIATION", 0)
    ctx.load_cert_chain(str(cert_path), str(key_path))
    return ctx


def client_context() -> ssl.SSLContext:
    """No CA trust at all: the pin decides. Same version and cipher floor as the server."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers(TLS12_CIPHERS)
    return ctx


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that refuses a server whose certificate fingerprint differs from the pin."""

    def __init__(self, host: str, port: int, pin: str, timeout: float = 30.0) -> None:
        super().__init__(host, port, timeout=timeout, context=client_context())
        self.pin = pin.replace(" ", "").replace(":", "").lower()

    def connect(self) -> None:
        super().connect()
        der = self.sock.getpeercert(binary_form=True) or b""
        if not hmac.compare_digest(fingerprint_of_der(der), self.pin):
            self.sock.close()
            raise PinMismatch(f"the server's certificate does not match the pinned fingerprint "
                              f"(got {fingerprint_of_der(der)[:16]}..., expected {self.pin[:16]}...)")


def peer_fingerprint(host: str, port: int, timeout: float = 10.0) -> str:
    """Fetch the fingerprint a server presents (for the operator's own checks; never trust it blindly)."""
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with client_context().wrap_socket(raw, server_hostname=host) as sock:
            return fingerprint_of_der(sock.getpeercert(binary_form=True) or b"")
