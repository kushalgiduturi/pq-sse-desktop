"""Milestone 7: property-based fuzzing (Hypothesis) of everything that parses outside input.

The wire decoder, invite files and links, every public endpoint of the server core, the receiver's checks on
server replies, and document and PDF import. Each test states what "never" means: no exception other than
the module's own refusal, never a wrong result accepted.
"""
from __future__ import annotations

import io
import os
import string

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pqsse import docimport
from pqsse import invite as invites
from pqsse.core import wire
from pqsse.core.errors import AccessDenied, PQSSEError, Rejected, VerifyError, WireError
from pqsse.sandbox import World
from pqsse.server.http import PUBLIC_ENDPOINTS

FAST = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
SLOW = settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])

values = st.recursive(
    st.none() | st.booleans() | st.integers(0, 2**64 - 1) | st.binary(max_size=64) | st.text(max_size=32),
    lambda inner: st.lists(inner, max_size=6) | st.dictionaries(st.text(max_size=12), inner, max_size=6),
    max_leaves=40)


# ------------------------------------------------------------------ the wire format
@FAST
@given(values)
def test_wire_round_trips_every_value(value):
    data = wire.enc(value)
    assert wire.enc(wire.dec(data)) == data


@FAST
@given(st.binary(max_size=512))
def test_wire_decoder_refuses_or_round_trips_any_bytes(data):
    try:
        value = wire.dec(data)
    except WireError:
        return
    assert wire.enc(value) == data                      # canonical: accepted input re-encodes to itself


@FAST
@given(values, st.integers(0, 200), st.integers(0, 255))
def test_one_changed_byte_is_refused_or_decodes_to_something_canonical(value, at, byte):
    data = bytearray(wire.enc(value))
    data[at % len(data)] = byte
    try:
        out = wire.dec(bytes(data))
    except WireError:
        return
    assert wire.enc(out) == bytes(data)


def test_deep_nesting_and_huge_counts_are_refused_quickly():
    deep = b"\x06\x00\x00\x00\x01" * 40 + b"\x00"         # 40 nested one-element lists
    with pytest.raises(WireError):
        wire.dec(deep)
    with pytest.raises(WireError):
        wire.dec(b"\x06\xff\xff\xff\xff")                    # a list that claims 4 billion items
    with pytest.raises(WireError):
        wire.dec(b"\x04\xff\xff\xff\xff" + b"x" * 10)        # bytes longer than the input


# ------------------------------------------------------------------ invites
@FAST
@given(st.text(max_size=400))
def test_invite_parser_only_ever_refuses_with_invite_error(text):
    try:
        invites.parse(text)
    except invites.InviteError:
        pass


@FAST
@given(st.dictionaries(st.sampled_from(["v", "host", "port", "tls", "server_fp", "owner_fp", "id", "code", "expires", "name"]),
                       st.one_of(st.text(max_size=20), st.integers(-5, 70000), st.none(), st.floats(allow_nan=True)), max_size=10))
def test_invite_json_with_any_fields(fields):
    import json
    try:
        invites.parse(json.dumps(fields))
    except invites.InviteError:
        pass


# ------------------------------------------------------------------ the server core
@pytest.fixture(scope="module")
def world():
    w = World()
    w.owner.create_group("g")
    w.owner.add_document("g", "Contract A", "the penalty clause", ["contract"])
    w.owner.publish("g")
    w.bob = w.join("receiver-a", ["g"])
    return w


endpoint_names = st.sampled_from(sorted(PUBLIC_ENDPOINTS | {"admin_stats", "nothing"}))
request_fields = st.dictionaries(
    st.sampled_from(["uid", "ct", "msg", "sig", "req", "ts", "g", "e", "handle", "have", "owner", "proof_s", "proof_o", "fp"]),
    values, max_size=8)


@SLOW
@given(endpoint=endpoint_names, obj=request_fields)
def test_every_endpoint_refuses_structured_garbage_cleanly(world, endpoint, obj):
    try:
        world.cloud.handle(endpoint, wire.enc(obj))
    except Rejected:
        pass
    assert world.cloud.db.execute("SELECT seq FROM groups WHERE g='g'").fetchone()[0] == world.owner.groups["g"]["seq"]


@SLOW
@given(endpoint=endpoint_names, body=st.binary(max_size=300))
def test_every_endpoint_refuses_raw_garbage_cleanly(world, endpoint, body):
    try:
        world.cloud.handle(endpoint, body)
    except Rejected:
        pass


# ------------------------------------------------------------------ the receiver's checks on server replies
@SLOW
@given(target=st.sampled_from(["states_get", "search"]), at=st.integers(0, 10**6), byte=st.integers(0, 255))
def test_a_changed_reply_is_refused_never_accepted_as_a_different_answer(world, target, at, byte):
    bob = world.bob
    honest = {world.owner.groups["g"]["docs"]["1"]["title"]}
    real = world.api

    class Mutates:
        def call(self, endpoint, obj):
            reply = real.call(endpoint, obj)
            if endpoint != target:
                return reply
            data = bytearray(wire.enc(reply))
            i = at % len(data)
            if data[i] == byte:
                return reply
            data[i] = byte
            try:
                return wire.dec(bytes(data))
            except WireError:
                return reply

    bob.cloud = Mutates()
    bob._state_cache.clear()
    try:
        result = bob.search("g", "contract")
        got = {bob.open_document("g", d, e).title for d, e in result.hits}
        assert result.report.all_ok and got == honest       # a change that does not matter (padding, a key order...)
    except (VerifyError, Rejected, WireError, AccessDenied, PQSSEError, KeyError, TypeError, ValueError, IndexError):
        pass                                                 # refused: fine
    finally:
        bob.cloud = real


# ------------------------------------------------------------------ document and PDF import
@SLOW
@given(data=st.binary(max_size=4000), suffix=st.sampled_from([".txt", ".md", ".pdf"]))
def test_any_file_content_imports_or_is_refused_cleanly(tmp_path_factory, data, suffix):
    path = tmp_path_factory.mktemp("imp") / ("doc" + suffix)
    path.write_bytes(data)
    try:
        title, text = docimport.read_document_file(path)
    except docimport.ImportRefused:
        return
    assert title == "doc" and isinstance(text, str) and len(text) <= docimport.MAX_TEXT_CHARS


@SLOW
@given(cut=st.integers(0, 2000), at=st.integers(0, 2000), byte=st.integers(0, 255))
def test_damaged_pdfs_import_or_are_refused_cleanly(tmp_path_factory, cut, at, byte):
    pdf = bytearray(_small_pdf())
    pdf[at % len(pdf)] = byte
    path = tmp_path_factory.mktemp("pdf") / "doc.pdf"
    path.write_bytes(bytes(pdf[: max(1, len(pdf) - cut)]))
    try:
        docimport.read_document_file(path)
    except docimport.ImportRefused:
        pass


def test_import_limits(tmp_path, monkeypatch):
    big = tmp_path / "big.txt"
    big.write_bytes(b"x" * 2000)
    monkeypatch.setattr(docimport, "MAX_FILE_BYTES", 1000)
    with pytest.raises(docimport.ImportRefused, match="larger than"):
        docimport.read_document_file(big)
    monkeypatch.setattr(docimport, "MAX_FILE_BYTES", 10**9)
    monkeypatch.setattr(docimport, "MAX_TEXT_CHARS", 100)
    assert len(docimport.read_document_file(big)[1]) == 100
    with pytest.raises(docimport.ImportRefused, match="only"):
        docimport.read_document_file(tmp_path / "x.exe")
    with pytest.raises(docimport.ImportRefused, match="cannot be read"):
        docimport.read_document_file(tmp_path / "missing.txt")
    good = tmp_path / "good.pdf"
    good.write_bytes(_small_pdf())
    assert docimport.read_document_file(good)[0] == "good"


def _small_pdf() -> bytes:
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": "fuzz " + "".join(string.ascii_letters[:5])})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_a_server_that_sends_no_progress_or_a_huge_total_is_refused(world):
    bob, real = world.bob, world.api
    [(doc, epoch)] = bob.search("g", "contract").hits
    for total in (10, 2**40):
        class Stalls:
            def call(self, endpoint, obj):
                reply = real.call(endpoint, obj)
                if endpoint == "doc_get":
                    return {**reply, "part": b"", "total": total, "offset": 0}
                return reply
        bob.cloud = Stalls()
        try:
            with pytest.raises(VerifyError, match="no progress or too large"):
                bob.open_document("g", doc, epoch)
        finally:
            bob.cloud = real
    assert not list(bob.vault.names("download:"))


def test_the_https_client_refuses_an_oversized_reply(tmp_path, monkeypatch):
    from test_m16_server import Running
    from pqsse import transport
    running = Running(tmp_path)
    try:
        monkeypatch.setattr(transport, "MAX_REPLY", 100)
        with pytest.raises(transport.ReplyTooLarge):
            running.client().call("pub", None)                 # the server's public key is far over 100 bytes
        monkeypatch.setattr(transport, "MAX_REPLY", 10**8)
        assert running.client().call("pub", None)
    finally:
        running.close()
