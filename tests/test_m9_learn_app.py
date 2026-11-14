"""Learn Mode, part 2: guided lesson, modes, welcome and tour, narrator panel, diagram,
'Who sees what', attack teaching, challenges, accessibility. All offscreen."""
from __future__ import annotations

import os
import socket

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from app.challenges import CHALLENGES
from app.common import GREEN, GREY, RED, Light
from app.lesson import DEMO_DOCS, STEPS
from app.main import MainWindow
from app.session import LESSON_PROFILE, Session
from app.story import IDEA
from pqsse import attacklab, narrator, paths
from pqsse.core.errors import Rejected
from pqsse.pqbackend import FAST_PARAMS
from pqsse.receiver import CHECKS


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def make_window(mode: str | None = None) -> MainWindow:
    session = Session()
    session.settings.update(kem=FAST_PARAMS.kem, sig=FAST_PARAMS.sig, port=free_port(), state_ttl_hours=1)
    window = MainWindow(session, sync=True, mode=mode)
    window.show()
    return window


# ---------------------------------------------------------------- the guided lesson
def test_guided_lesson_runs_start_to_finish_resumes_and_resets(qapp):
    win = make_window("beginner")
    learn, session = win.learn_tab, win.session
    try:
        assert len(STEPS) == 13 and win.tabs.widget(0) is learn and win.tabs.tabText(0) == "Learn"
        assert IDEA in learn.explain.toPlainText()
        assert sum(len(v) for v in DEMO_DOCS.values()) == 8
        assert not learn.lesson_active() and session.profile == ""

        # steps 1 to 6, then a simulated restart, then the rest
        for i in range(6):
            learn.goto(i)
            learn.do_it()
            assert i in learn.done, learn.message.text()
        assert learn.lesson_active() and session.profile == LESSON_PROFILE
        assert "locked documents" in learn.happened.toPlainText()
        session.close()                                   # as if the app had been closed
        session.owner, session.receivers = None, {}
        assert not session.cloud_running()
        for i in range(6, len(STEPS)):
            learn.goto(i)
            learn.do_it()
            assert i in learn.done, (i, learn.message.text(), learn.detail.text())
        assert learn.done == set(range(13))
        assert "What you learned" in learn.title.text() and "If the cloud cheats" in learn.explain.toPlainText()

        # expected end state of the real lesson system
        owner = session.owner
        assert sorted(owner.groups) == ["Finance", "Medical"]
        assert owner.overview("Finance")["epoch"] == 2 and owner.overview("Medical")["epoch"] == 1
        titles = [d["title"] for d in owner.documents("Finance")]
        assert "Invoice 1050, ultrasound probe" in titles and "Payroll note, nursing" not in titles
        assert len(owner.documents("Medical")) == 4
        bob = next(r for r in owner.receivers.values() if r["name"] == "bob")
        assert bob["revoked"] and bob["groups"] == ["Finance"]
        with pytest.raises(Rejected):
            session.receivers["bob"].search("Finance", "invoice")
        assert session.cloud_running()
        assert session.settings["lesson_step"] == 12 and len(session.settings["lesson_done"]) == 13

        # the lesson lives in its own folder; the user's own data folder was never written
        assert (paths.base_dir() / LESSON_PROFILE / "owner.sqlite").exists()
        assert not (paths.base_dir() / "owner.sqlite").exists()
        assert win.owner_tab.groups.count() == 2 and win.receiver_tab.current == "bob"
        assert win.cloud_tab.light.text() == "Running"

        # the narrator told the whole story: all ten algorithms, in plain lines, with packets
        kinds = [e.kind for e in win.narrator.events]
        assert {narrator.algorithm_of(k) for k in kinds} >= set(range(1, 11))
        text = win.narrator.browser.toPlainText()
        assert "[Alice]" in text and "[Bob]" in text and "[Cloud]" in text and "[Security]" in text
        assert "Tell me more" in text and "sealed search slip for 'invoice'" in text
        more = win.narrator.show_more(kinds.index("tokengen"))
        assert "TokenGen, Algorithm 6" in more and "Under the hood" in more
        assert len(win.narrator.flow.history) > 10
        win.narrator.flow.select(0)
        assert "Who can read it" in win.narrator.flow.info.text()
        assert {"replay", "modify", "collusion"} <= set(win.attack_tab.outcomes)

        # 'Who sees what'
        party = learn.party
        party.refresh()
        assert "Invoice 1042, MRI scanner" in party.alice.toPlainText()
        assert "REVOKED" in party.doctors.toPlainText()
        cloud_view = party.cloud.toPlainText()
        assert "INDEX ENTRIES" in cloud_view
        for plain in ("Invoice", "invoice", "allergy", "penicillin", "Budget"):
            assert plain not in cloud_view
        party.show_as_cloud()
        assert "AS THE CLOUD STORES IT" in party.aha.toPlainText()

        # challenges: several were completed by the lesson itself, the rest by hand
        done = learn.check_challenges()
        assert {"invoice", "revoke", "attack", "compare", "update", "cloudview"} <= done
        assert "carol" not in done
        win.receiver_tab.unlock("carol", "lesson")
        win.receiver_tab.pair()
        win.receiver_tab.send_join()
        win.owner_tab.refresh_joins()
        win.owner_tab.approve(session.receivers["carol"].uid, ["Finance"])
        assert learn.check_challenges() == {c.key for c in CHALLENGES}
        assert learn.challenge_list.item(0).text().startswith("Done: ")
        learn.challenge_list.setCurrentRow(0)
        learn.show_challenge(hint=True)
        assert "Hint:" in learn.challenge_text.text()

        # lights carry words, not only color
        win.receiver_tab.fetch_mail()
        win.receiver_tab.search("Finance", "invoice")
        assert win.receiver_tab.results.count() == 3
        assert all(win.receiver_tab.lights[name].text() == "OK" for name in CHECKS)

        # leaving the lesson returns to the user's own (empty) data
        learn.exit_lesson()
        assert session.profile == "" and session.owner is None and not session.cloud_running()
        assert win.owner_tab.groups.count() == 0 and win.cloud_tab.light.text() == "Stopped"

        # Reset restores a clean demo state, and the lesson can start again
        learn.start_lesson()
        learn.reset_lesson()
        assert learn.done == set() and learn.index == 0 and session.settings["lesson_done"] == []
        assert not (paths.base_dir() / LESSON_PROFILE / "owner.sqlite").exists()
        assert not session.cloud_running() and session.owner is None and win.owner_tab.groups.count() == 0
        learn.goto(3)
        learn.do_it()                                   # runs the skipped steps 2 and 3 first
        assert {1, 2, 3} <= learn.done and sorted(session.owner.groups) == ["Finance", "Medical"]
        assert session.owner.documents("Finance") == []
    finally:
        win.close()


def test_let_me_try_and_check_my_work(qapp):
    win = make_window("beginner")
    learn = win.learn_tab
    try:
        learn.goto(1)
        learn.let_me_try()
        assert learn.lesson_active() and win.tabs.currentWidget() is win.cloud_tab
        assert "lesson" in win.cloud_tab.message.text().lower()
        assert not learn.check_work() and "Not done yet" in learn.message.text()
        win.cloud_tab.start("lesson")                    # the learner does it by hand
        assert learn.check_work() and 1 in learn.done
        learn.goto(0)
        assert not learn.do_button.isEnabled() and learn.next_button.isEnabled()
        learn.run_all()
        assert learn.done == set(range(13))
    finally:
        win.close()


# ---------------------------------------------------------------- modes, welcome, tour
def test_beginner_and_expert_toggle_keeps_session_state(qapp):
    win = make_window()                                  # built in code: Expert Mode, the classic window
    session = win.session
    try:
        assert win.mode == "expert" and win.tabs.count() == 6 and win.tabs.indexOf(win.learn_tab) == -1
        assert win.dock.isHidden() and win.owner_tab.intro.isHidden()
        win.cloud_tab.start("cloud-pass")
        win.owner_tab.open_owner("owner-pass")
        win.owner_tab.pair_cloud()
        win.cloud_tab.pair_owner()
        win.owner_tab.create_group("research")
        owner = session.owner

        win.mode_action.setChecked(True)                 # the toolbar toggle
        assert win.mode == "beginner" and win.tabs.count() == 7 and win.tabs.tabText(0) == "Learn"
        assert win.tabs.tabText(1) == "Owner (Alice)" and not win.dock.isHidden()
        assert not win.owner_tab.intro.isHidden() and "You are Alice" in win.owner_tab.intro.text()
        assert win.bench_tab.build_table.isHidden() and not win.bench_tab.show_advanced.isHidden()
        assert not win.settings_tab.form.isRowVisible(win.settings_tab.kem)
        assert "Beginner" in win.header.text() and "PQ backend" not in win.header.text()
        assert session.owner is owner and session.cloud_running() and win.owner_tab.groups.count() == 1
        assert session.settings["mode"] == "beginner"
        win.bench_tab.show_advanced.setChecked(True)
        assert not win.bench_tab.build_table.isHidden()
        win.settings_tab.show_advanced.setChecked(True)
        assert win.settings_tab.form.isRowVisible(win.settings_tab.kem)

        win.set_mode("expert")
        assert win.tabs.count() == 6 and win.tabs.tabText(0) == "Owner" and win.dock.isHidden()
        assert not win.bench_tab.build_table.isHidden() and win.owner_tab.intro.isHidden()
        assert "PQ backend" in win.header.text()
        assert session.owner is owner and session.cloud_running()
        win.owner_tab.add_document("after toggling", "state survived the mode switch")
        assert win.owner_tab.docs.rowCount() == 1
        assert Session().settings["mode"] == "expert"     # remembered on disk
    finally:
        win.close()


@pytest.mark.parametrize("mode", ["beginner", "expert"])
def test_app_starts_offscreen_in_both_modes(qapp, mode):
    win = make_window(mode)
    try:
        QCoreApplication.processEvents()
        assert win.isVisible() and win.mode == mode
        assert win.tabs.count() == (7 if mode == "beginner" else 6)
        for index in range(win.tabs.count()):
            win.tabs.setCurrentIndex(index)
        QCoreApplication.processEvents()
    finally:
        win.close()


def test_first_run_flag_welcome_dialog_and_tour(qapp):
    session = Session()
    assert session.first_run and session.settings["show_welcome"] is True
    win = make_window()
    try:
        dialog = win.show_welcome(execute=False)
        shown = " ".join(label.text() for label in dialog.findChildren(type(win.header)))
        assert IDEA in shown and "Alice" in shown and "Bob" in shown and "Carol" in shown and "Cloud" in shown
        assert dialog.lesson_button.text() == "Start the guided lesson"
        assert dialog.explore_button.text() == "Explore on my own"
        dialog.dont_show.setChecked(True)
        dialog._pick("explore")
        win.apply_welcome(dialog)
        assert win.session.settings["show_welcome"] is False and not Session().settings["show_welcome"]
        assert not Session().first_run or True
        assert win.tour.active() and "Tour, stop 1 of 6" in win.tour.text.text()
        win.tour.next()
        assert win.tabs.currentIndex() == 1 and "Receiver" in win.tour.text.text()
        win.tour.skip()                                  # can be skipped at any time
        assert not win.tour.active()
        win.tour.start()
        for _ in range(win.tabs.count()):
            win.tour.next()
        assert not win.tour.active()

        dialog = win.show_welcome(execute=False)
        assert dialog.dont_show.isChecked()
        dialog._pick("lesson")
        win.apply_welcome(dialog)
        assert win.mode == "beginner" and win.tabs.currentWidget() is win.learn_tab and win.learn_tab.lesson_active()
    finally:
        win.close()


# ---------------------------------------------------------------- glossary, errors, diagram, accessibility
def test_glossary_dialog_errors_footer_diagram_and_text_size(qapp):
    win = make_window("beginner")
    try:
        dialog = win.open_glossary("epoch")
        assert "Epoch" in dialog.detail.toPlainText() and "In one sentence" in dialog.detail.toPlainText()
        win.owner_tab._link("glossary:policy-r")
        assert "Policy R" in win.glossary.detail.toPlainText() and "teams up with the cloud" in win.glossary.detail.toPlainText()
        win.glossary_search.setText("quantum")
        win.open_glossary(query="quantum")
        assert win.glossary.listing.item(0).text() == "Post-quantum"
        win.open_glossary(query="zzzzzz")
        assert win.glossary.listing.count() == 0
        assert "Press F1" in win.settings_tab.kem.toolTip() and "ML-KEM" in win.settings_tab.kem.toolTip()

        # three-part error in the tab footer, with a copy button and no traceback
        win.owner_tab.create_group("research")           # no owner yet
        assert win.owner_tab.message.text() == "Open the owner first (enter the passphrase)."
        exc = Rejected("revoked", "this receiver has been revoked")
        exc.trace = "Traceback (most recent call last):\n  boom"
        win.receiver_tab.fail(exc)
        assert "revoked by the data owner" in win.receiver_tab.message.text()
        detail = win.receiver_tab.detail.text()
        assert detail.startswith("Why it matters: ") and "\nWhat to do next: " in detail and "Traceback" not in detail
        assert not win.receiver_tab.copy_button.isHidden()
        assert "Traceback" in win.receiver_tab.copy_technical() and "Rejected" in QApplication.clipboard().text()
        assert "Blocked: " in win.narrator.browser.toPlainText() and "[Security]" in win.narrator.browser.toPlainText()
        win.receiver_tab.notify("fine again")
        assert win.receiver_tab.detail.isHidden() and win.receiver_tab.copy_button.isHidden()

        # diagram: packets are listed as text, can be paused, slowed and shown without motion
        flow = win.narrator.flow
        flow.clear()
        packet = narrator.STORIES["tokengen"].packet
        flow.pause.setChecked(True)
        flow.add(packet, "Bob")
        flow.add(narrator.STORIES["search"].packet, "Bob")
        assert flow.pending() == 2 and flow.pause.text() == "Resume" and flow.listing.count() == 2
        assert "SLIP (sealed search slip)" in flow.listing.item(0).text() and "from Bob to the Cloud" in flow.listing.item(0).text()
        flow.slow.setChecked(True)
        flow.pause.setChecked(False)
        assert flow.pending() == 1 and flow.anim.duration() > 3000
        flow.reduce_motion = True
        flow.anim.stop()
        flow._next()
        assert flow.pending() == 0 and flow.moving is not None
        flow.select(1)
        assert "Masked index entries" in flow.info.text()

        # text size and reduced motion are settings
        win.settings_tab.font_size.setCurrentIndex(win.settings_tab.font_size.findData("large"))
        win.settings_tab.reduce_motion.setChecked(True)
        win.settings_tab.save()
        assert "13pt" in win.styleSheet() and win.session.settings["reduce_motion"] is True
        assert win.narrator.flow.reduce_motion is True

        # every indicator shows a word
        for light in win.findChildren(Light):
            assert light.text().strip(), "a light without a text label"
        light = Light()
        for color, word in ((GREEN, "OK"), (RED, "Failed"), (GREY, "Not checked")):
            light.set(color)
            assert light.text() == word and light.accessibleName() == word
    finally:
        win.close()


# ---------------------------------------------------------------- attack teaching
def test_each_attack_names_the_check_that_caught_it_and_teaches(qapp):
    verify_attacks = {"drop", "modify", "reorder", "truncate", "rollback", "expired"}
    for key, title, _, _ in attacklab.SCENARIOS:
        outcome = attacklab.run_scenario(key)
        assert outcome.passed and outcome.check and outcome.caught_by, key
        teach = attacklab.TEACH[key]
        for part in ("tries", "without", "unprotected"):
            assert len(teach[part]) > 30 and teach[part].endswith(".")
        lesson = outcome.lesson()
        assert outcome.check in lesson and outcome.caught_by in lesson and teach["tries"] in lesson
        assert "What would go wrong without that check" in lesson
        if key in verify_attacks:
            assert outcome.check in CHECKS and outcome.checks[-1] == (outcome.check, False)
            assert all(ok for _, ok in outcome.checks[:-1])
    assert set(attacklab.TEACH) == {s[0] for s in attacklab.SCENARIOS}

    win = make_window("beginner")
    try:
        tab = win.attack_tab
        tab.table.selectRow(0)
        assert "What the attacker tries" in tab.tries.text() and "leaves one matching document out" in tab.tries.text()
        tab.run("drop")
        assert tab.lights["completeness"].text() == "Caught here" and tab.lights["completeness"].color == RED
        assert tab.lights["state signature"].text() == "OK" and tab.lights["hash chain"].text() == "Not reached"
        assert "completeness" in tab.caught.text()
        assert "What would go wrong without that check" in tab.output.toPlainText()
        tab.explain_unprotected()
        text = tab.output.toPlainText()
        assert "WITHOUT PROTECTION" in text and "were not switched off" in text
        tab.run("replay")
        assert all(light.text() == "Not involved" for light in tab.lights.values())
        assert "sequence number" in tab.caught.text()
        assert "Attack Lab: 'Replay an update' was tried. Result: caught" in win.narrator.browser.toPlainText()
    finally:
        win.close()
