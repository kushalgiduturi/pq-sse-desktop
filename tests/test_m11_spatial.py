"""Spatial UI: bridge, event log, Step Inspector content, QML shell (offscreen), feature map."""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QObject, QThread, QTimer
from PySide6.QtWidgets import QApplication

from app import glossary, lesson
from app.session import Session
from app.spatial import copy as ui_copy
from app.spatial import inspector
from app.spatial import settings as ui_settings
from app.spatial.bridge import AppBridge
from app.spatial.window import SpatialWindow, qml_path
from pqsse import attacklab, narrator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_feature_map  # noqa: E402

LONG_DASH = chr(0x2014)
LAYERS = ("plain", "moved", "hood", "safe")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def new_session() -> Session:
    session = Session()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        session.settings["port"] = sock.getsockname()[1]
    return session


def strings(value) -> list[str]:
    """Every string inside a nested structure. Fails on bytes: they must never reach QML."""
    assert not isinstance(value, (bytes, bytearray, memoryview)), "bytes in data meant for QML"
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in strings(k) + strings(v)]
    if isinstance(value, (list, tuple, set)):
        return [s for v in value for s in strings(v)]
    return []


# ---------------------------------------------------------------- Step Inspector content
def test_every_event_kind_has_inspector_content_with_four_layers():
    assert set(ui_copy.INSPECT) == set(narrator.STORIES)
    for kind in narrator.STORIES:
        record = inspector.build(narrator.Event(kind, "Bob", {}, time.time()))
        assert record["anim"] in inspector.ANIMATIONS, kind
        assert len(record["steps"]) >= 1, kind
        for name, text in inspector.layers(record).items():
            assert len(text.strip()) > 20, (kind, name)
        assert record["metaphor"], kind
        assert LONG_DASH not in json.dumps(record)


def test_all_ten_algorithms_have_an_inspector_timeline():
    by_algorithm = {}
    for kind in narrator.STORIES:
        number = narrator.algorithm_of(kind)
        if number:
            by_algorithm.setdefault(number, []).append(kind)
    assert sorted(by_algorithm) == list(range(1, 11))
    for number, kinds in by_algorithm.items():
        record = inspector.build(narrator.Event(kinds[0], "Bob", {}, 0.0))
        assert narrator.ALGORITHMS[number] in record["technical"]
        assert len(record["steps"]) >= 3, (number, kinds[0])
        assert record["algorithm"] == number


def test_every_attack_has_an_inspector_timeline():
    keys = [key for key, _, _, _ in attacklab.SCENARIOS]
    assert len(keys) == 11
    for key in keys:
        record = inspector.build_attack(key)
        assert len(record["steps"]) == 3
        for name, text in inspector.layers(record).items():
            assert len(text.strip()) > 20, (key, name)
    outcome = attacklab.run_scenario("modify")
    record = inspector.build_attack("modify", outcome)
    assert outcome.caught_by in record["steps"][1]
    assert record["passed"] is True
    assert LONG_DASH not in json.dumps(record)


def test_honest_limits_are_in_the_inspector_text():
    revoke = inspector.build(narrator.Event("revoke", "Bob", {"policy": "R", "groups": ["Finance"]}, 0.0))
    assert "teams up with the cloud" in revoke["safe"] and "Policy RE" in revoke["safe"]
    build = inspector.build(narrator.Event("build_index", "Alice", {"engine": "GPU", "docs": 4, "entries": 43}, 0.0))
    assert any("ML-KEM and ML-DSA always run on the CPU" in line for line in build["hood"])
    assert "picture" in build["metaphor"].lower()
    assert ui_copy.T["revokeQuickNote"].startswith("Honest limit")
    assert "ML-KEM and ML-DSA always run on the normal processor" in ui_copy.T["insightsEngineNote"]


def test_no_long_dash_in_any_new_user_visible_text():
    assert LONG_DASH not in json.dumps(ui_copy.T) + json.dumps(ui_copy.INSPECT) + json.dumps(ui_copy.DESTINATIONS)
    for path in qml_path().parent.iterdir():
        assert LONG_DASH not in path.read_text(encoding="utf-8"), path.name


def test_glossary_covers_the_terms_the_new_ui_uses(qapp):
    for word in ("ML-KEM", "ML-DSA", "signature", "token", "capability", "epoch", "group", "index", "ciphertext", "revocation"):
        assert glossary.search(word), word
    for step in lesson.STEPS:
        for part in step.explain.split('href="glossary:')[1:]:
            assert part.split('"')[0] in glossary.GLOSSARY
    bridge = AppBridge(new_session(), sync=True)
    try:
        ids = {item["id"] for item in bridge.paletteItems}
        assert {"glossary:" + key for key in glossary.GLOSSARY} <= ids
        assert {"go:journey", "go:stage", "go:workspace", "go:lab", "go:insights", "role:alice", "role:cloud"} <= ids
        entry = bridge.glossaryEntry(next(iter(glossary.GLOSSARY)))
        assert entry["name"] and entry["plain"]
    finally:
        bridge.shutdown()


# ---------------------------------------------------------------- narrator scope hook
def test_practice_copies_are_labelled_and_the_real_system_is_not():
    seen: list[narrator.Event] = []
    stop = narrator.subscribe(seen.append)
    try:
        narrator.emit("group", "Alice", g="Finance")
        with narrator.scope("practice"):
            narrator.emit("group", "Alice", g="Finance")
        narrator.emit("group", "Alice", g="Finance")
        assert [e.scope for e in seen] == ["", "practice", ""]
        seen.clear()
        attacklab.run_scenario("replay")
        assert seen and all(e.scope == "practice" for e in seen)
    finally:
        stop()


# ---------------------------------------------------------------- bridge on the real system
def test_bridge_runs_the_real_flow_and_never_exposes_secrets(qapp):
    session = new_session()
    bridge = AppBridge(session, sync=True)
    changes, failures, done = [], [], []
    bridge.stateChanged.connect(lambda: changes.append(1))
    bridge.failed.connect(failures.append)
    bridge.succeeded.connect(done.append)
    try:
        for index in range(1, 9):                       # cloud, setup, groups, join, build, search, verify, decrypt
            bridge.runLessonStep(index)
        assert failures == []
        assert len(done) == 8 and changes
        state = bridge.state
        assert bridge.practice and bridge.cloudRunning
        assert [g["name"] for g in state["owner"]["groups"]] == ["Finance", "Medical"]
        assert all(len(g["docs"]) == 4 and not g["dirty"] for g in state["owner"]["groups"])
        assert state["owner"]["people"][0]["name"] == "bob" and state["owner"]["people"][0]["groups"] == ["Finance"]
        bob = state["receivers"][0]
        assert bob["open"] and bob["joined"] and bob["groups"] == ["Finance"]
        assert bob["result"]["keyword"] == lesson.SEARCH_WORD and len(bob["result"]["hits"]) == 2
        assert len(bob["result"]["checks"]) >= 8 and all(c["ok"] for c in bob["result"]["checks"])
        assert state["cloud"]["docs"] == 8 and state["cloud"]["storedDocs"] and state["cloud"]["log"]
        assert bridge.lessonStep == 8 and "decrypt" in bridge.lessonDone

        kinds = [r["kind"] for r in bridge.events.records]
        for kind in ("cloud.started", "setup.owner", "join.approved", "build_index", "publish", "tokengen", "search", "verify", "decrypt"):
            assert kind in kinds
        record = next(r for r in bridge.events.records if r["kind"] == "build_index")
        assert record["tookMs"] > 0 and "real operation took" in record["replayNote"]
        assert record["index"] == bridge.events.records.index(record)
        assert bridge.story["line"] and bridge.story["role"]

        # The workspace actions on the same system: a new document, publish, a second doctor.
        bridge.addDocument("Finance", "Invoice 2000, test", "An invoice for a test device.")
        bridge.publish("Finance")
        bridge.openReceiver("Carol", "lesson")
        bridge.pairReceiver("carol")
        bridge.sendJoin("carol")
        pending = bridge.state["owner"]["pending"]
        assert [p["name"] for p in pending] == ["carol"] and pending[0]["fingerprint"]
        bridge.approveJoin(pending[0]["uid"], ["Medical"])
        bridge.fetchMail("carol")
        bridge.search("carol", "Medical", "allergy")
        carol = next(r for r in bridge.state["receivers"] if r["name"] == "carol")
        assert carol["groups"] == ["Medical"] and len(carol["result"]["hits"]) == 1
        hit = carol["result"]["hits"][0]
        bridge.openDocument("carol", "Medical", hit["id"], hit["epoch"])
        carol = next(r for r in bridge.state["receivers"] if r["name"] == "carol")
        assert "penicillin" in carol["opened"]["text"]
        assert failures == []

        # A refused action gives the three-part message, not an exception.
        bridge.search("carol", "Finance", "invoice")
        assert len(failures) == 1
        assert all(failures[0][part] for part in ("what", "why", "next", "technical"))
        bridge.revoke(pending[0]["uid"], "RE")
        assert next(p for p in bridge.state["owner"]["people"] if p["name"] == "carol")["revoked"]

        # Nothing that reaches QML may contain key material.
        everything = strings(bridge.state) + strings(bridge.events.records) + strings(bridge.paletteItems) + strings(failures)
        blob = "\n".join(everything).lower()
        owner = session.owner
        secrets = [owner._sk]
        for group in owner.groups.values():
            secrets += list(group["keys"].values())
        for record in owner.receivers.values():
            secrets += [record["a"], record["m"]]
        for receiver in session.receivers.values():
            secrets += [receiver._sk, receiver._dk]
        assert len(secrets) >= 8
        for secret in secrets:
            assert isinstance(secret, (bytes, bytearray)) and len(secret) >= 16
            assert secret.hex()[:32] not in blob and secret.hex()[-32:] not in blob
        assert LONG_DASH not in blob
    finally:
        bridge.shutdown()


def test_bridge_delivers_worker_results_on_the_gui_thread(qapp):
    bridge = AppBridge(new_session(), sync=False)
    threads, finished = [], []
    loop = QEventLoop()
    bridge.events.added.connect(lambda record: threads.append(QThread.currentThread()))
    bridge.succeeded.connect(lambda name: (finished.append(name), loop.quit()))
    bridge.failed.connect(lambda error: (finished.append("failed: " + error["what"]), loop.quit()))
    try:
        bridge.runLessonStep(1)                          # start the cloud, on a worker thread
        assert bridge.busy or finished
        QTimer.singleShot(60000, loop.quit)
        loop.exec()
        assert finished == ["lesson:cloud"]
        assert threads and all(thread is qapp.thread() for thread in threads)
        assert bridge.cloudRunning and not bridge.busy
    finally:
        bridge.shutdown()


def test_settings_properties_and_signals(qapp):
    bridge = AppBridge(new_session(), sync=True)
    changed = []
    bridge.settingsChanged.connect(lambda: changed.append(1))
    try:
        bridge.setTheme("light")
        assert bridge.theme == "light" and bridge.dark is False
        bridge.setTheme("dark")
        assert bridge.dark is True
        bridge.setTheme("nonsense")
        assert bridge.theme == "dark"
        bridge.setTextSize("large")
        assert bridge.textScale == ui_settings.TEXT_SCALES["large"]
        bridge.setReduceMotion(True)
        assert bridge.reduceMotion is True
        bridge.setReduceMotion(False)
        bridge.setSoftware(True)                         # no GPU rendering: effects reduce by themselves
        assert bridge.reduceMotion is True and bridge.motionReason
        bridge.setDetailLevel(9)
        assert bridge.detailLevel == 3
        bridge.setMode("expert")
        assert bridge.mode == "expert"
        assert len(changed) >= 7
        assert isinstance(ui_settings.windows_animations_enabled(), bool)
        assert Session().settings["theme"] == "dark"     # saved
    finally:
        bridge.shutdown()


# ---------------------------------------------------------------- the QML window, offscreen
def running_animations(window) -> list[str]:
    names = []
    for child in window.findChildren(QObject):
        name = child.metaObject().className()
        if "Animation" in name and child.property("running") is True:
            names.append(name)
    return names


def test_window_loads_and_visits_all_five_destinations(qapp):
    session = new_session()
    session.settings["reduce_motion"] = True
    view = SpatialWindow(session, sync=True)
    try:
        window = view.window
        qapp.processEvents()
        assert view.warnings == []
        for key in ("journey", "stage", "workspace", "lab", "insights"):
            window.setProperty("page", key)
            qapp.processEvents()
            assert window.property("page") == key
        view.bridge.navigate.emit("stage")
        qapp.processEvents()
        assert window.property("page") == "stage"
        view.bridge.runLessonStep(1)
        view.bridge.runLessonStep(2)
        qapp.processEvents()
        view.bridge.runPalette("inspect")
        qapp.processEvents()
        assert window.property("inspectorOpen") is True
        assert window.property("inspectIndex") == view.bridge.events.count - 1
        view.bridge.runPalette("role:cloud")
        qapp.processEvents()
        assert window.property("page") == "workspace" and view.bridge.role == "cloud"
        view.bridge.runPalette("lesson:5")
        qapp.processEvents()
        assert window.property("page") == "journey" and view.bridge.lessonStep == 5
        view.bridge.runPalette("inspect")
        deadline = time.time() + 6.0                     # short fades may finish; after that nothing may move
        while time.time() < deadline and running_animations(window):
            qapp.processEvents()
            time.sleep(0.02)
        assert view.warnings == []
        assert running_animations(window) == []          # Reduce motion: no ambient motion, no looping animation
    finally:
        view.close()


def test_feature_map_has_a_new_place_for_every_old_feature():
    text = (ROOT / "SPATIAL_PLAN.md").read_text(encoding="utf-8")
    assert check_feature_map.check(text) == []
    assert len(check_feature_map.rows(text)) >= 40
    broken = text.replace("| Workspace > Alice > Publish |", "|  |", 1)
    assert broken != text and check_feature_map.check(broken)


# ---------------------------------------------------------------- milestone 5: Security Lab, tasks, challenges
def test_security_lab_tasks_and_challenges_through_the_bridge(qapp):
    bridge = AppBridge(new_session(), sync=True)
    navigations, finished = [], []
    bridge.navigate.connect(navigations.append)
    bridge.attackFinished.connect(finished.append)
    try:
        assert len(bridge.attacks) == 11 and not any(a["ran"] for a in bridge.attacks)
        assert len(bridge.challengeList) == 7 and not any(c["done"] for c in bridge.challengeList)
        for item in bridge.challengeList:
            assert item["hint"] and "tab" not in item["hint"].lower()        # hints describe the new window

        bridge.runAttack("modify")
        bridge.runAttack("collusion")
        assert finished == ["modify", "collusion"]
        modify = next(a for a in bridge.attacks if a["key"] == "modify")
        assert modify["ran"] and modify["passed"] and "hash chain" in modify["caughtBy"]
        assert modify["checks"] and modify["checks"][-1][1] is False          # the check that caught it is the last one reached
        assert modify["tries"] and modify["without"]
        collusion = next(a for a in bridge.attacks if a["key"] == "collusion")
        assert collusion["ran"] and len(collusion["lines"]) >= 3
        attack_records = [r for r in bridge.events.records if r["kind"] == "attack"]
        assert len(attack_records) == 2 and attack_records[0]["scope"] == ""
        assert all(r["scope"] == "practice" for r in bridge.events.records if r["kind"] != "attack")
        done = {c["key"] for c in bridge.challengeList if c["done"]}
        assert {"attack", "compare"} <= done

        # "Let me try": the task opens where it is done, in the practice area, and "Check my work" follows reality.
        bridge.tryLessonStep(1)
        assert bridge.practice and bridge.task["step"] == 1 and "Start the cloud" in bridge.task["text"]
        assert navigations[-1] == "workspace" and bridge.role == "cloud"
        bridge.checkLessonStep(1)
        assert bridge.lessonCheck == {"step": 1, "ok": False, "text": ui_copy.T["checkNo"]}
        bridge.startCloud("lesson")
        bridge.checkLessonStep(1)
        assert bridge.lessonCheck["ok"] is True and bridge.task == {} and "cloud" in bridge.lessonDone
        for key, (where, text) in ui_copy.TRY.items():
            assert key in {s.key for s in lesson.STEPS} and where in ("alice", "bob", "cloud", "lab") and text

        for index in range(2, 6):
            bridge.runLessonStep(index)
        bridge.noteCloudView()
        assert "cloudview" in {c["key"] for c in bridge.challengeList if c["done"]}
        bridge.resetChallenges()
        assert not any(c["done"] for c in bridge.challengeList)
        assert LONG_DASH not in json.dumps(bridge.attacks) + json.dumps(ui_copy.TRY) + json.dumps(ui_copy.CHALLENGE_HINTS)
    finally:
        bridge.shutdown()


# ---------------------------------------------------------------- milestone 6: Insights
def test_insights_engine_benchmark_settings_and_about(qapp, monkeypatch):
    from pqsse import bench

    bridge = AppBridge(new_session(), sync=True)
    try:
        fake = [dict(occurrences=1000, engine="CPU (hashlib)", prf_s=0.01, chain_s=0.002, documents_s=0.1, batch_sign_s=0.05,
                     cloud_store_s=0.01, total_s=0.2, prf_speedup=1.0, symmetric_speedup=1.0, total_speedup=1.0),
                dict(occurrences=1000, engine="GPU (CUDA)", prf_s=0.002, chain_s=0.001, documents_s=0.1, batch_sign_s=0.05,
                     cloud_store_s=0.01, total_s=0.25, prf_speedup=5.0, symmetric_speedup=4.0, total_speedup=0.8)]
        monkeypatch.setattr(bench, "run_build_benchmarks", lambda sizes, progress: fake)
        bridge.runBuildBenchmark(True)
        rows = bridge.benchBuild
        assert [r["gpu"] for r in rows] == [False, True] and rows[1]["prf_speedup"] == 5.0
        assert "not faster in this run" in bridge.benchSummary          # the summary does not turn a slowdown into a speedup
        fake[1].update(total_s=0.1, total_speedup=2.0)
        bridge.runBuildBenchmark(True)
        assert "2.00 times faster" in bridge.benchSummary and "stay on the CPU" in bridge.benchSummary
        folder = Path(bridge.exportBenchmarks())
        assert (folder / "buildindex.csv").read_text(encoding="utf-8").startswith("occurrences,engine")

        bridge.setEngineMode("cpu")
        assert bridge.engineMode == "cpu" and bridge.engine == "CPU"
        bridge.setEngineMode("warp")
        assert bridge.engineMode == "cpu"
        advanced = bridge.advanced
        bridge.setAdvanced(advanced["kems"][0], advanced["sigs"][0], 8790, 12.0)
        assert bridge.advanced["port"] == 8790 and bridge.advanced["ttl"] == 12.0
        bridge.setAdvanced("nonsense", advanced["sigs"][0], 80, -1.0)
        assert bridge.advanced["port"] == 8790
        labels = [row["label"] for row in bridge.aboutRows]
        assert "Version" in labels and "Data folder" in labels and "GPU" in labels
        assert "MIT License" in bridge.licenses
        bridge.refreshLog()
        assert isinstance(bridge.logTail, str)
        assert bridge.folder("logs").endswith("logs")
    finally:
        bridge.shutdown()


# ---------------------------------------------------------------- milestone 7: contrast, welcome, terms
def test_theme_tokens_meet_wcag_contrast():
    import check_contrast

    lines, failures = check_contrast.check()
    assert len(lines) >= 50 and failures == []


def test_welcome_terms_and_palette_extras(qapp):
    bridge = AppBridge(new_session(), sync=True)
    navigations, welcomes = [], []
    bridge.navigate.connect(navigations.append)
    bridge.welcomeRequested.connect(lambda: welcomes.append(1))
    try:
        assert bridge.showWelcome is True
        bridge.dismissWelcome(True)
        assert bridge.showWelcome is False and navigations == ["journey"] and bridge.lessonStep == 0
        bridge.runPalette("welcome")
        assert welcomes == [1] and bridge.showWelcome is True
        record = inspector.build(narrator.Event("join.approved", "Bob", {"groups": ["Finance"]}, 0.0))
        keys = [term["key"] for term in record["terms"]]
        assert "ml-kem" in keys and "ml-dsa" in keys and all(key in glossary.GLOSSARY for key in keys)
    finally:
        bridge.shutdown()
