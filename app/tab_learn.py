"""Learn tab: the guided lesson, the 'Who sees what' view and the challenges."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QPushButton, QSplitter, QTabWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from pqsse import narrator

from .challenges import CHALLENGES, completed
from .common import TabBase
from .lesson import STEPS, Ctx, ensure
from .party_view import PartyView
from .session import LESSON_PROFILE
from .story import IDEA


class LearnTab(TabBase):
    def __init__(self, session, runner, window) -> None:
        super().__init__(session, runner)
        self.win = window
        self.ctx = Ctx(session)
        self.events: list[narrator.Event] = []
        self.index = min(int(session.settings.get("lesson_step", 0)), len(STEPS) - 1)
        self.done: set[int] = {int(i) for i in session.settings.get("lesson_done", [])}
        self.challenges_done: set[str] = set(session.settings.get("challenges_done", []))

        idea = QLabel(f"<b>The big idea:</b> <i>{IDEA}</i>")
        idea.setWordWrap(True)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.start_button = QPushButton("Start or resume the lesson")
        self.exit_button = QPushButton("Leave the lesson (back to my own data)")
        self.reset_button = QPushButton("Reset lesson")
        self.start_button.clicked.connect(lambda: self.start_lesson())
        self.exit_button.clicked.connect(lambda: self.exit_lesson())
        self.reset_button.clicked.connect(lambda: self.reset_lesson())
        top = QHBoxLayout()
        top.addWidget(self.status, 1)
        for button in (self.start_button, self.exit_button, self.reset_button):
            top.addWidget(button)

        # ---- guided lesson page
        self.steps = QListWidget()
        self.steps.setAccessibleName("Lesson steps")
        self.steps.setWordWrap(True)
        self.steps.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.steps.currentRowChanged.connect(lambda row: self.goto(row) if row >= 0 and row != self.index else None)
        self.title = QLabel("")
        self.title.setObjectName("stepTitle")
        self.explain = QTextBrowser()
        self.explain.setOpenLinks(False)
        self.explain.anchorClicked.connect(self._anchor)
        self.do_button = QPushButton("Do it for me")
        self.try_button = QPushButton("Let me try")
        self.check_button = QPushButton("Check my work")
        self.back_button = QPushButton("Back")
        self.next_button = QPushButton("Next")
        self.do_button.clicked.connect(lambda: self.do_it())
        self.try_button.clicked.connect(lambda: self.let_me_try())
        self.check_button.clicked.connect(lambda: self.check_work())
        self.back_button.clicked.connect(lambda: self.goto(self.index - 1))
        self.next_button.clicked.connect(lambda: self.next_step())
        buttons = QHBoxLayout()
        for button in (self.do_button, self.try_button, self.check_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.next_button)
        self.happened = QTextBrowser()
        self.happened.setOpenLinks(False)
        self.happened.anchorClicked.connect(self._anchor)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.title)
        right_layout.addWidget(self.explain, 3)
        right_layout.addLayout(buttons)
        right_layout.addWidget(QLabel("<b>What just happened</b>"))
        right_layout.addWidget(self.happened, 3)
        lesson_page = QSplitter()
        lesson_page.addWidget(self.steps)
        lesson_page.addWidget(right)
        lesson_page.setSizes([300, 720])

        # ---- challenges page
        self.challenge_list = QListWidget()
        self.challenge_list.setAccessibleName("Challenges")
        self.challenge_list.currentRowChanged.connect(lambda _: self.show_challenge())
        self.challenge_text = QLabel("")
        self.challenge_text.setWordWrap(True)
        hint = QPushButton("Show a hint")
        recheck = QPushButton("Check now")
        hint.clicked.connect(lambda: self.show_challenge(hint=True))
        recheck.clicked.connect(lambda: self.check_challenges())
        challenge_buttons = QHBoxLayout()
        challenge_buttons.addWidget(hint)
        challenge_buttons.addWidget(recheck)
        challenge_buttons.addStretch(1)
        challenge_page = QWidget()
        challenge_layout = QVBoxLayout(challenge_page)
        practice = QLabel("Optional practice. No score and no time limit. A task is marked 'Done' as soon as the app "
                          "sees that you did it, in the lesson or with your own data.")
        practice.setWordWrap(True)
        challenge_layout.addWidget(practice)
        challenge_layout.addWidget(self.challenge_list, 1)
        challenge_layout.addWidget(self.challenge_text)
        challenge_layout.addLayout(challenge_buttons)

        self.party = PartyView(session, runner)
        self.pages = QTabWidget()
        self.pages.addTab(lesson_page, "Guided lesson")
        self.pages.addTab(self.party, "Who sees what")
        self.pages.addTab(challenge_page, "Challenges")

        layout = QVBoxLayout(self)
        layout.addWidget(idea)
        layout.addLayout(top)
        layout.addWidget(self.pages, 1)
        layout.addWidget(self.footer)
        self.refresh_lists()
        self.show_step()

    # ------------------------------------------------------------------ events
    def on_event(self, event: narrator.Event) -> None:
        """Called by the Narrator panel for every event (GUI thread)."""
        self.events.append(event)
        self.ctx.seen.add(event.kind)
        self.check_challenges(quiet=True)

    def _anchor(self, url: QUrl) -> None:
        self._link(url.toString())

    # ------------------------------------------------------------------ lesson state
    def lesson_active(self) -> bool:
        return self.session.profile == LESSON_PROFILE

    def _save(self) -> None:
        self.session.settings.update(lesson_step=self.index, lesson_done=sorted(self.done),
                                     challenges_done=sorted(self.challenges_done))
        self.session.save_settings()

    def refresh_lists(self) -> None:
        self.steps.blockSignals(True)
        self.steps.clear()
        for i, step in enumerate(STEPS):
            self.steps.addItem(("Done: " if i in self.done else "") + f"{i + 1}. {step.title}")
        self.steps.setCurrentRow(self.index)
        self.steps.blockSignals(False)
        row = max(0, self.challenge_list.currentRow())
        self.challenge_list.blockSignals(True)
        self.challenge_list.clear()
        for challenge in CHALLENGES:
            mark = "Done: " if challenge.key in self.challenges_done else "To do: "
            self.challenge_list.addItem(mark + challenge.title)
        self.challenge_list.setCurrentRow(row)
        self.challenge_list.blockSignals(False)
        if self.lesson_active():
            self.status.setText("<b>Lesson practice area is active.</b> Every tab now shows the lesson's own data. "
                                "All passphrases here are the word <b>lesson</b>. Your own data is untouched.")
        else:
            self.status.setText("You are looking at your own data. Press 'Start or resume the lesson' to enter the practice area.")
        self.exit_button.setEnabled(self.lesson_active())

    def show_step(self) -> None:
        step = STEPS[self.index]
        self.title.setText(f"<h2>Step {self.index + 1} of {len(STEPS)}: {step.title}</h2>")
        self.explain.setHtml(step.explain)
        self.do_button.setEnabled(step.do is not None)
        self.try_button.setEnabled(bool(step.try_tab))
        self.check_button.setEnabled(step.check is not None)
        self.back_button.setEnabled(self.index > 0)
        self.next_button.setEnabled(self.index < len(STEPS) - 1)
        self.happened.setHtml("<p>Press <b>Do it for me</b> to run this step on the real system, or <b>Let me try</b> to do it yourself.</p>"
                              if step.do else "<p>Nothing to run in this step. Read it, then press <b>Next</b>.</p>")

    def goto(self, index: int) -> None:
        self.index = max(0, min(len(STEPS) - 1, index))
        if STEPS[self.index].do is None:
            self.done.add(self.index)
        self.refresh_lists()
        self.show_step()
        self._save()

    def next_step(self) -> None:
        self.goto(self.index + 1)

    # ------------------------------------------------------------------ profile
    def start_lesson(self) -> None:
        """Enter the lesson practice area (its own data folder) and show the current step."""
        if not self.lesson_active():
            self.session.set_profile(LESSON_PROFILE)
            self.ctx = Ctx(self.session)
            self.ctx.seen = {e.kind for e in self.events}
            self.win.reset_views()
        self.pages.setCurrentIndex(0)
        self.refresh_lists()
        self.show_step()
        self.notify("You are in the lesson practice area. Follow the steps on the left.")

    def exit_lesson(self) -> None:
        self.session.set_profile("")
        self.win.reset_views()
        self.refresh_lists()
        self.notify("Back to your own data. The lesson progress is saved.")

    def reset_lesson(self) -> None:
        """Delete the lesson data and progress: a clean demo state."""
        self.session.reset_lesson()
        self.ctx = Ctx(self.session)
        self.events.clear()
        self.done.clear()
        self.index = 0
        self.win.reset_views()
        self.refresh_lists()
        self.show_step()
        self._save()
        self.notify("The lesson was reset: practice data deleted, progress back to step 1.")

    # ------------------------------------------------------------------ actions
    def do_it(self) -> None:
        """Run this step on the real system. Earlier steps that were skipped are run first."""
        target = self.index
        if STEPS[target].do is None:
            self.goto(target)
            return
        if not self.lesson_active():
            self.start_lesson()
        todo = [j for j in range(target + 1) if STEPS[j].do is not None and (j == target or j not in self.done)]

        def work(progress):
            text = ""
            for n, j in enumerate(todo):
                progress(f"Lesson step {j + 1}: {STEPS[j].title}", n / len(todo))
                ensure(self.ctx, j + 1)
                text = STEPS[j].do(self.ctx)
            return text

        def finished(text: str) -> None:
            self.done.update(todo)
            self.win.refresh_views()
            for outcome in self.ctx.store.pop("outcomes", []):
                self.win.attack_tab.record(outcome)
            self.refresh_lists()
            self.happened.setHtml(text)
            self._save()
            self.notify(f"Step {target + 1} is done. Read 'What just happened', then press Next.")

        def failed(exc: BaseException) -> None:
            self.win.refresh_views()
            self.fail(exc)
            self.happened.setHtml("<p>This step could not finish. The message below says what happened, why it matters "
                                  "and what to do next.</p>")

        self.task(work, finished, f"Lesson step {target + 1}: {STEPS[target].title}", on_error=failed)

    def let_me_try(self) -> None:
        """Switch to the right tab and highlight the control to use."""
        step = STEPS[self.index]
        if not step.try_tab:
            return
        if not self.lesson_active():
            self.start_lesson()
        tab = getattr(self.win, step.try_tab)
        self.win.tabs.setCurrentWidget(tab)
        tab.flash(getattr(tab, step.try_widget))
        tab.notify(f"Lesson step {self.index + 1}: {step.try_text} Then return to the Learn tab and press 'Check my work'.")
        self.happened.setHtml(f"<p><b>Your turn.</b> {step.try_text}</p><p>The control to start with is highlighted on the "
                              "other tab. When you are done, come back here and press <b>Check my work</b>.</p>")

    def check_work(self) -> bool:
        step = STEPS[self.index]
        ok = step.check is None or bool(step.check(self.ctx))
        if ok:
            self.done.add(self.index)
            self.refresh_lists()
            self._save()
            self.notify(f"Step {self.index + 1} is done. Well done. Press Next.")
        else:
            self.notify("Not done yet. Follow the instruction above, or press 'Do it for me'.", error=True)
            self.detail.setText("Why it matters: later steps build on this one.\nWhat to do next: " + step.try_text)
            self.detail.setHidden(False)
        return ok

    def run_all(self) -> None:
        """Run the whole lesson from the first to the last step (used by the tests and for a quick demo)."""
        for i in range(len(STEPS)):
            self.goto(i)
            self.do_it()

    # ------------------------------------------------------------------ challenges
    def check_challenges(self, quiet: bool = False) -> set[str]:
        now = completed(self.session, self.events)
        fresh = now - self.challenges_done
        if fresh:
            self.challenges_done |= fresh
            self.refresh_lists()
            self.show_challenge()
            self._save()
            titles = ", ".join(c.title for c in CHALLENGES if c.key in fresh)
            self.notify(f"Challenge completed: {titles}.")
        elif not quiet:
            self.notify(f"{len(self.challenges_done)} of {len(CHALLENGES)} challenges done.")
        return self.challenges_done

    def show_challenge(self, hint: bool = False) -> None:
        row = self.challenge_list.currentRow()
        if row < 0:
            return
        challenge = CHALLENGES[row]
        state = "Done." if challenge.key in self.challenges_done else "Not done yet."
        text = f"<b>{challenge.title}.</b> {challenge.task} <i>{state}</i>"
        if hint:
            text += f"<br><b>Hint:</b> {challenge.hint}"
        self.challenge_text.setText(text)
