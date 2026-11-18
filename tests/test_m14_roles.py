"""Milestone 0 of REALLIFE_PLAN.md: plain role names everywhere, the cast only behind "Teaching names"."""
from __future__ import annotations

import re

import pytest

from pqsse import attacklab, narrator, roles

STORY = re.compile(r"\b(Alice|Bob|Carol|doctors?|Doctors?|hospital|patient)\b")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def plain_names():
    roles.set_teaching(False)
    yield
    roles.set_teaching(False)


def test_display_names_plain_and_teaching():
    assert roles.display(roles.OWNER) == "Data owner" and roles.display(roles.CLOUD) == "Cloud server"
    assert roles.display(roles.RECEIVER_A) == "Receiver A" and roles.display("dana") == "Dana"
    assert roles.teach("The data owner approved Receiver A.") == "The data owner approved Receiver A."
    roles.set_teaching(True)
    assert roles.display(roles.OWNER) == "Alice" and roles.display(roles.RECEIVER_B) == "Carol"
    assert roles.teach("The data owner's stamp. Receiver B asked the data owner.") == "Alice's stamp. Carol asked Alice."
    assert roles.teach_all({"a": ["Data owner", 3], "b": "Receiver A's keys"}) == {"a": ["Alice", 3], "b": "Bob's keys"}


def _user_visible_strings() -> list[str]:
    from app import challenges, glossary, lesson, story
    from app.spatial import copy
    # the one label that names the cast on purpose: the description of the Teaching names switch
    texts: list[str] = [v for k, v in copy.T.items() if isinstance(v, str) and k != "journeyTeachingNote"]
    texts += [d["label"] + " " + d["hint"] for d in copy.DESTINATIONS]
    for spec in copy.INSPECT.values():
        texts += spec["steps"] + [spec["safe"], spec["metaphor"], spec.get("simplification", "")]
    texts += [text for _, text in copy.TRY.values()] + list(copy.CHALLENGE_HINTS.values())
    texts += [s.title + " " + s.explain for s in lesson.STEPS] + [lesson.SUMMARY] + list(lesson.CHECK_MEANING.values())
    texts += [c.title + " " + c.task + " " + c.hint for c in challenges.CHALLENGES]
    texts += [e.name + " " + e.plain + " " + e.more + " " + e.simplification for e in glossary.GLOSSARY.values()]
    texts += [story.IDEA, story.cast_html()]
    for s in narrator.STORIES.values():
        texts += [s.line, s.more, s.hood]
    for key, title, line, _ in attacklab.SCENARIOS:
        texts += [title, line]
    texts += [v for entry in attacklab.TEACH.values() for v in entry.values()] if hasattr(attacklab, "TEACH") else []
    return [t for t in texts if t]


def test_no_story_names_in_user_visible_text():
    found = sorted({m.group(0) + ": " + t[:80] for t in _user_visible_strings() for m in [STORY.search(t)] if m})
    assert found == []


def test_demo_data_is_neutral():
    from app import lesson
    titles = [title for docs in lesson.DEMO_DOCS.values() for title, _ in docs] + [lesson.NEW_DOC[0]]
    assert set(lesson.DEMO_DOCS) == {"Finance", "Legal"}
    assert not any(STORY.search(t) or re.search(r"MRI|radiology|nursing|pharmacy|vaccin|allergy", t, re.I) for t in titles)


def test_teaching_names_switch_in_the_bridge(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("PQSSE_DATA_DIR", str(tmp_path))
    from app.session import Session
    from app.spatial.bridge import AppBridge
    bridge = AppBridge(Session(), sync=True)
    assert bridge.teachingNames is False and bridge.displayName(roles.RECEIVER_A) == "Receiver A"
    plain = " ".join(s["title"] + s["explain"] for s in bridge.lessonSteps)
    assert "Alice" not in plain and "The data owner" in plain
    bridge.setTeachingNames(True)
    assert bridge.teachingNames is True and bridge.session.settings["teaching_names"] is True
    taught = " ".join(s["title"] + s["explain"] for s in bridge.lessonSteps)
    assert "Alice" in taught and bridge.displayName(roles.RECEIVER_A) == "Bob"
    bridge.setTeachingNames(False)
    assert bridge.displayName(roles.OWNER) == "Data owner"
