"""Milestone 7: the server's TLS configuration, probed from the outside like a scanner would.

Each probe offers the server one kind of handshake and checks what it accepts. Probes this PC's OpenSSL
cannot even offer are skipped, and the reason is printed.
"""
from __future__ import annotations

import socket
import ssl

import pytest
from test_m16_server import Running

from pqsse.server import tls

ACCEPTED_TLS12 = ("ECDHE-ECDSA-AES256-GCM-SHA384", "ECDHE-ECDSA-AES128-GCM-SHA256", "ECDHE-ECDSA-CHACHA20-POLY1305")
REFUSED_TLS12 = ("ECDHE-ECDSA-AES256-SHA384", "ECDHE-ECDSA-AES128-SHA", "AES256-GCM-SHA384", "AES128-SHA",
                 "DHE-RSA-AES256-GCM-SHA384", "ECDHE-RSA-AES256-GCM-SHA384")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    running = Running(tmp_path_factory.mktemp("tls"))
    yield running
    running.close()


def probe(server, version: ssl.TLSVersion, ciphers: str | None = None):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    try:
        ctx.minimum_version = ctx.maximum_version = version
        if ciphers:
            ctx.set_ciphers(ciphers)
    except (ValueError, ssl.SSLError) as exc:
        pytest.skip(f"this OpenSSL cannot offer {version.name} {ciphers or ''}: {exc}")
    with socket.create_connection(("127.0.0.1", server.config.port), timeout=10) as raw:
        try:
            with ctx.wrap_socket(raw) as sock:
                return sock.version(), sock.cipher()[0], sock.compression()
        except (ssl.SSLError, ConnectionResetError, OSError):
            return None


def test_tls13_is_accepted_with_an_aead_cipher_and_no_compression(server):
    got = probe(server, ssl.TLSVersion.TLSv1_3)
    assert got is not None and got[0] == "TLSv1.3" and ("GCM" in got[1] or "CHACHA20" in got[1]) and got[2] is None


@pytest.mark.parametrize("cipher", ACCEPTED_TLS12)
def test_tls12_accepts_only_forward_secret_aead(server, cipher):
    got = probe(server, ssl.TLSVersion.TLSv1_2, cipher)
    assert got is not None and got[1] == cipher and got[2] is None


@pytest.mark.parametrize("cipher", REFUSED_TLS12)
def test_tls12_refuses_cbc_static_rsa_dhe_and_rsa_certificates(server, cipher):
    assert probe(server, ssl.TLSVersion.TLSv1_2, cipher) is None


@pytest.mark.parametrize("version", ["TLSv1", "TLSv1_1"])
def test_old_versions_are_refused(server, version):
    assert probe(server, getattr(ssl.TLSVersion, version)) is None


def test_the_certificate_is_ecdsa_p256_self_signed_and_pinned_by_sha256(server):
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec
    pem = (server.config.data_dir / "server.crt").read_bytes()
    cert = x509.load_pem_x509_certificate(pem)
    assert isinstance(cert.public_key(), ec.EllipticCurvePublicKey) and cert.public_key().curve.name == "secp256r1"
    assert cert.issuer == cert.subject
    assert len(server.pin) == 64 and tls.fingerprint(server.config.data_dir / "server.crt") == server.pin
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "127.0.0.1" in [str(ip) for ip in names.get_values_for_type(x509.IPAddress)]


def test_server_options(server):
    ctx = tls.server_context(server.config.data_dir / "server.crt", server.config.data_dir / "server.key")
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2
    assert ctx.options & ssl.OP_NO_COMPRESSION and ctx.options & ssl.OP_CIPHER_SERVER_PREFERENCE
    if hasattr(ssl, "OP_NO_RENEGOTIATION"):
        assert ctx.options & ssl.OP_NO_RENEGOTIATION
    names = {c["name"] for c in ctx.get_ciphers()}
    assert names and all(("GCM" in n or "CHACHA20" in n) for n in names)
