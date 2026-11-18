"""Learn Mode, part 1: glossary, friendly three-part errors, narrator event bus."""
from __future__ import annotations

import os
import re
import string
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app import glossary
from app.session import Friendly, explain, explain_full, explain_gpu
from helpers import filled_world
from pqsse import narrator
from pqsse.attacks import TamperCloud
from pqsse.core.errors import AccessDenied, BadPassphrase, PQSSEError, Rejected, VerifyError
from pqsse.transport import CloudUnavailable

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_TERMS = ["ml-kem", "ml-dsa", "post-quantum", "epoch", "segment", "token", "credential", "capability",
                  "hash-chain", "forward-privacy", "backward-privacy", "revocation", "policy-r", "policy-re",
                  "signature", "nonce", "ciphertext", "gpu", "cuda", "sse"]


# ---------------------------------------------------------------- glossary
def test_glossary_has_every_required_term_and_no_empty_text():
    for key in REQUIRED_TERMS:
        assert key in glossary.GLOSSARY, key
    for key, entry in glossary.GLOSSARY.items():
        assert entry.name.strip() and len(entry.plain) > 20 and len(entry.more) > 40, key
        assert entry.plain.rstrip().endswith("."), key
        assert key == key.lower()


def test_every_glossary_term_used_in_the_ui_is_defined():
    """Scan the app sources for term(...), tooltip(...), tip(...) calls and glossary: links."""
    used = set()
    for path in (ROOT / "app").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        used |= set(re.findall(r'glossary:([a-z0-9-]+)', source))
        for call in re.findall(r'(?<![\w.])(?:term|tooltip|tip)\(([^()]*)\)', source):
            used |= set(re.findall(r'"([a-z0-9-]+)"', call))
    assert len(used) >= 15, sorted(used)
    missing = sorted(k for k in used if k not in glossary.GLOSSARY)
    assert missing == []
    with pytest.raises(KeyError):
        glossary.term("no-such-term")


def test_term_and_tooltip_helpers():
    html = glossary.term("epoch")
    assert 'href="glossary:epoch"' in html and "Epoch" in html
    assert glossary.term("epoch", "epochs").endswith(">epochs</a>")
    tip = glossary.tooltip("ml-kem", "ml-dsa")
    assert "ML-KEM" in tip and "ML-DSA" in tip and "F1" in tip
    assert "epoch" in glossary.USED
    assert glossary.search("quantum")[0] == "post-quantum"
    assert glossary.search("") and glossary.search("zzzz") == []
    assert "Simplification" in glossary.entry_html("token")


def test_no_em_dash_in_user_visible_text():
    needle = chr(0x2014)
    for folder in ("app", "docs", "pqsse"):
        for path in (ROOT / folder).rglob("*"):
            if path.suffix in (".py", ".md"):
                assert needle not in path.read_text(encoding="utf-8"), path
    for entry in glossary.GLOSSARY.values():
        assert needle not in entry.plain + entry.more + entry.simplification
    for story in narrator.STORIES.values():
        assert needle not in story.line + story.more + story.technical + story.hood


# ---------------------------------------------------------------- friendly errors
ERROR_CASES = {
    "revoked user searching": Rejected("revoked", "this receiver has been revoked"),
    "wrong group": Rejected("scope", "group is outside this receiver's capability"),
    "wrong group, local": AccessDenied("group Legal is outside this receiver's capability"),
    "bad signature": Rejected("bad_signature", "owner batch signature invalid"),
    "expired state": VerifyError("freshness", "the current state has expired"),
    "rolled-back state": VerifyError("no rollback", "version 3 is older than 4 seen before"),
    "replayed update": Rejected("bad_sequence", "expected seq 5, got 4"),
    "cloud not running": CloudUnavailable("cloud not reachable on 127.0.0.1:8765"),
    "wrong passphrase": BadPassphrase("wrong passphrase for owner.sqlite"),
    "tampered result": VerifyError("hash chain", "epoch 1: chain head does not match the signed state"),
    "dropped result": VerifyError("completeness", "epoch 1: expected 3 entries in order, got 2"),
    "swapped document": VerifyError("document signature", "document is not the one signed by the owner"),
    "plain app error": PQSSEError("Select a group first."),
    "unexpected crash": ZeroDivisionError("division by zero"),
}


@pytest.mark.parametrize("name", sorted(ERROR_CASES))
def test_every_error_has_three_parts_and_no_traceback(name):
    exc = ERROR_CASES[name]
    exc.trace = 'Traceback (most recent call last):\n  File "x.py", line 1, in <module>\nBoom'
    friendly = explain_full(exc)
    assert isinstance(friendly, Friendly)
    for part in (friendly.what, friendly.why, friendly.next):
        assert len(part) > 10 and part.strip().endswith(".")
        assert "Traceback" not in part and "File \"" not in part and "Error:" not in part
    text = friendly.text()
    assert text.startswith("What happened: ") and "\nWhy it matters: " in text and "\nWhat to do next: " in text
    assert "Traceback" not in text
    assert "Traceback" in friendly.technical and type(exc).__name__ in friendly.technical
    assert explain(exc) == friendly.what


def test_unexpected_errors_never_show_python_names():
    friendly = explain_full(ZeroDivisionError("division by zero"))
    assert "ZeroDivisionError" not in friendly.text() and "division" not in friendly.text()
    assert "ZeroDivisionError" in friendly.technical


def test_gpu_not_found_explanation_says_the_app_still_works():
    friendly = explain_gpu(False, "no CUDA device found")
    assert "CPU" in friendly.what and "still works" in friendly.why and "self-test" in friendly.next
    assert "no CUDA device" in friendly.technical and "no CUDA device" not in friendly.what
    assert "post-quantum" in explain_gpu(True).why


# ---------------------------------------------------------------- narrator
@pytest.fixture()
def events():
    seen: list[narrator.Event] = []
    stop = narrator.subscribe(seen.append)
    yield seen
    stop()


def run_story(events):
    """One pass through all ten algorithms on an in-memory world."""
    world, _ = filled_world(["Finance", "Legal"], docs_per_group=3, seed=91)
    bob = world.join("receiver-a", ["Finance"])
    carol = world.join("receiver-b", ["Finance", "Legal"])
    doc_id = world.owner.add_document("Finance", "Invoice", "invoice for the scanner")
    world.owner.publish("Finance")
    result = bob.search("Finance", "invoice")
    bob.open_document("Finance", *result.hits[0])
    with pytest.raises(AccessDenied):
        bob.search("Legal", "report")
    with pytest.raises(AccessDenied):
        bob.open_document("Legal", 1, 1)
    world.owner.delete_document("Finance", doc_id)
    world.owner.publish("Finance")
    world.owner.revoke(bob.uid, "R")
    carol.search("Finance", "invoice")
    world.owner.revoke(world.join("dave", ["Finance"]).uid, "RE")
    carol.search("Finance", "token")
    return world, bob, carol


def test_each_of_the_ten_algorithms_emits_its_event(events):
    run_story(events)
    kinds = [e.kind for e in events]
    emitted = {narrator.algorithm_of(k) for k in kinds}
    for number, name in narrator.ALGORITHMS.items():
        assert number in emitted, f"no event for {name}"
    expected = {"setup.owner": 1, "join.approved": 2, "build_index": 3, "update": 4, "publish": 5,
                "tokengen": 6, "search": 7, "verify": 8, "decrypt": 9, "revoke": 10}
    for kind, number in expected.items():
        assert kind in kinds and narrator.algorithm_of(kind) == number
        assert narrator.ALGORITHMS[number].split()[0] in narrator.STORIES[kind].technical
    for kind in ("setup.receiver", "pair", "group", "join.request", "join.capability", "rekey", "reencrypt",
                 "search.denied", "decrypt.denied"):
        assert kind in kinds, kind
    order = [k for k in kinds if k in ("tokengen", "search", "verify")][:3]
    assert order == ["tokengen", "search", "verify"]


def test_narration_is_complete_text_and_names_the_actor(events):
    run_story(events)
    for event in events:
        text = narrator.render(event)
        for part in (text.line, text.more, text.technical, text.hood):
            assert "{" not in part and "?" not in part, (event.kind, part)
        assert text.line.endswith(".") and text.tag_label
    bob_lines = [narrator.render(e) for e in events if e.kind == "tokengen"]
    assert bob_lines[0].tag_label == "Receiver A" and "'invoice'" in bob_lines[0].line
    assert narrator.render([e for e in events if e.kind == "revoke"][0]).line.startswith("The data owner revoked Receiver A using policy R")
    assert any(narrator.render(e).packet is not None for e in events)


def test_events_never_contain_key_material(events):
    world, bob, carol = run_story(events)
    # private parts: a 32-byte ML-DSA seed whole (or bytes 32..64 of an older expanded key), ML-KEM d and z
    sig_part = lambda k: k if len(k) == 32 else k[32:64]  # noqa: E731
    secrets = [sig_part(world.owner._sk), sig_part(world.cloud._sk), world.cloud._dk[:32], bob._dk[:32],
               sig_part(bob._sk), carol._dk[-32:]]
    assert all(len(s) >= 16 for s in secrets)
    for g in ("Finance", "Legal"):
        secrets += list(world.owner._group(g)["keys"].values())
    for rec in world.owner.receivers.values():
        secrets += [rec["a"], rec["m"]]
    haystack = ""
    for event in events:
        text = narrator.render(event)
        haystack += repr(event) + text.line + text.more + text.hood + text.technical
        for value in event.data.values():
            assert not isinstance(value, (bytes, bytearray))
    assert len(haystack) > 5000
    for secret in secrets:
        assert secret.hex() not in haystack and secret.hex().upper() not in haystack
        assert repr(secret)[2:-1] not in haystack
        assert secret[:8].hex() not in haystack


def test_emit_refuses_bytes_and_unknown_kinds(events):
    with pytest.raises(TypeError):
        narrator.emit("group", "The data owner", g=b"\x00" * 32)
    with pytest.raises(TypeError):
        narrator.emit("group", "The data owner", g=["ok", b"key"])
    with pytest.raises(TypeError):
        narrator.emit("group", "The data owner", g="x" * 5000)
    with pytest.raises(KeyError):
        narrator.emit("no.such.event", "The data owner")
    assert events == []


def test_every_story_renders_and_a_broken_listener_is_harmless(events):
    def broken(event):
        raise RuntimeError("listener bug")

    stop = narrator.subscribe(broken)
    try:
        for kind, story in narrator.STORIES.items():
            fields = {name for text in (story.line, story.more, story.hood)
                      for _, name, _, _ in string.Formatter().parse(text) if name}
            fields.discard("who")
            narrator.emit(kind, "receiver-a", **{name: "value" for name in fields})
    finally:
        stop()
    assert [e.kind for e in events] == list(narrator.STORIES)
    for event in events:
        text = narrator.render(event)
        assert "?" not in text.line + text.more + text.hood and event.who == "Receiver A"
        assert text.technical and text.tag in narrator.TAGS


def test_verify_failure_is_narrated(events):
    world, _ = filled_world(["Finance"], docs_per_group=6, seed=92)
    tamper = TamperCloud(world.cloud, seed=1)
    bob = world.join("receiver-a", ["Finance"], api=tamper)
    tamper.mode = "drop"
    with pytest.raises(VerifyError):
        for word in ("token", "cloud", "epoch", "chain", "state", "index"):
            bob.search("Finance", word)
    failed = [e for e in events if e.kind == "verify.failed"]
    assert failed and failed[0].data["check"] == "completeness"
    assert "'completeness' check failed" in narrator.render(failed[0]).line
