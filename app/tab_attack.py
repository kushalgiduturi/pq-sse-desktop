"""Attack Lab tab: one-click tampering demos with teaching.

Before a run: what the attacker tries, in the story. After a run: which check caught it
(with the matching indicator highlighted) and what would go wrong without that check.
Every demo runs on a throwaway in-memory world.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit, QPushButton, QSplitter,
                               QTableWidgetItem, QVBoxLayout)

from pqsse import attacklab, narrator
from pqsse.receiver import CHECKS

from .common import GREEN, GREY, RED, Light, TabBase, make_table, selected_value
from .glossary import term, tip

INTRO = ("Each demo builds its own small owner, cloud and receivers in memory (your real data is not touched), "
         "runs an honest baseline, then lets a malicious cloud or attacker tamper, and shows which check stops it. "
         "The demos use ML-KEM-512 and ML-DSA-44 so they finish in about a second.")
STORY = ("<b>Here the cloud, or an outsider, tries to cheat.</b> Pick an attack to read what the attacker tries, run it, "
         f"and see which check catches it. The checks rely on the data owner's {term('signature', 'stamp')} and the "
         f"{term('hash-chain', 'running fingerprint')} of the index.")
UNPROTECTED_NOTE = ("\n\nThis is an explanation only. The app's checks were not switched off, and no weaker version "
                    "of the system was run.")


class AttackTab(TabBase):
    INTRO = STORY

    def __init__(self, session, runner) -> None:
        super().__init__(session, runner)
        self.outcomes: dict[str, attacklab.Outcome] = {}
        self.table = make_table(["Key", "Attack", "What happens", "Result"])
        self.table.setColumnHidden(0, True)
        self.table.setRowCount(len(attacklab.SCENARIOS))
        for row, (key, title, description, _) in enumerate(attacklab.SCENARIOS):
            for col, value in enumerate((key, title, description, "not run")):
                item = QTableWidgetItem(value)
                item.setData(0x0100, value)
                self.table.setItem(row, col, item)
        self.table.itemSelectionChanged.connect(self._show_selected)
        run_one = QPushButton("Run selected attack")
        run_all = QPushButton("Run all attacks")
        unprotected = QPushButton("Try it without protection (explanation)")
        run_one.clicked.connect(lambda: self.run_selected())
        run_all.clicked.connect(lambda: self.run_all())
        unprotected.clicked.connect(lambda: self.explain_unprotected())
        buttons = QHBoxLayout()
        for button in (run_one, run_all, unprotected):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.tries = QLabel("Select an attack to read what the attacker tries.")
        self.tries.setWordWrap(True)
        left = QGroupBox("Attacks")
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.table, 1)
        left_layout.addWidget(self.tries)
        left_layout.addLayout(buttons)

        self.caught = QLabel("Which check caught it: run an attack to see.")
        self.caught.setWordWrap(True)
        checks_box = QGroupBox("Receiver A's Verify checks during the attack")
        grid = QGridLayout(checks_box)
        self.lights: dict[str, Light] = {}
        for i, name in enumerate(CHECKS):
            self.lights[name] = Light(GREY, {GREY: "Not involved"})
            grid.addWidget(self.lights[name], i // 2, (i % 2) * 2)
            grid.addWidget(QLabel(name), i // 2, (i % 2) * 2 + 1)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 10))
        right = QGroupBox("What happened")
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.caught)
        right_layout.addWidget(checks_box)
        right_layout.addWidget(self.output, 1)
        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([520, 640])
        intro = QLabel(INTRO)
        intro.setWordWrap(True)
        tip(self.table, "signature", "hash-chain", "freshness")
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.advanced = [intro]
        layout = QVBoxLayout(self)
        layout.addWidget(self.intro)
        layout.addWidget(self.show_advanced)
        layout.addWidget(intro)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.footer)

    def _row_of(self, key: str) -> int:
        return [s[0] for s in attacklab.SCENARIOS].index(key)

    def _show_selected(self) -> None:
        key = selected_value(self.table)
        if key is None:
            return
        self.tries.setText("<b>What the attacker tries:</b> " + attacklab.TEACH[key]["tries"])
        if key in self.outcomes:
            self.show_outcome(self.outcomes[key])

    def show_outcome(self, outcome: attacklab.Outcome) -> None:
        """Fill the right-hand side: which check caught it, the indicators, the full story."""
        self.caught.setText(f"<b>Which check caught it:</b> {outcome.caught_by or 'nothing (this would be a bug)'}.")
        reached = dict(outcome.checks)
        for name, light in self.lights.items():
            if name not in reached:
                light.set(GREY, "Not reached" if reached else "Not involved")
            elif reached[name]:
                light.set(GREEN, "OK")
            else:
                light.set(RED, "Caught here")
        self.output.setPlainText(outcome.text() + "\n" + outcome.lesson() + "\n")

    def record(self, outcome: attacklab.Outcome) -> None:
        """Store and display an outcome (also used by the guided lesson)."""
        self.outcomes[outcome.key] = outcome
        short = "AS DOCUMENTED" if outcome.verdict.startswith("AS DOCUMENTED") else outcome.verdict.split()[0].rstrip(":")
        item = QTableWidgetItem(short if outcome.passed else "FAILED")
        item.setForeground(QColor(GREEN if outcome.passed else RED))
        self.table.setItem(self._row_of(outcome.key), 3, item)
        self.show_outcome(outcome)
        narrator.emit("attack", "", key=outcome.key, title=outcome.title, ok=outcome.passed,
                      result="caught" if outcome.passed else "NOT caught", caught_by=outcome.caught_by or "nothing")

    _record = record

    def explain_unprotected(self) -> None:
        key = selected_value(self.table)
        if key is None:
            self.notify("Select an attack first.", error=True)
            return
        teach = attacklab.TEACH[key]
        self.output.setPlainText(f"WITHOUT PROTECTION\n==================\nThe attack: {teach['tries']}\n\n"
                                 f"{teach['unprotected']}\n\nWhy that is bad: {teach['without']}" + UNPROTECTED_NOTE)
        self.notify("Explanation shown. Run the attack to see the real system stop it.")

    def run_selected(self) -> None:
        key = selected_value(self.table)
        if key is None:
            self.notify("Select an attack first.", error=True)
            return
        self.run(key)

    def run(self, key: str) -> None:
        def done(outcome: attacklab.Outcome) -> None:
            self.record(outcome)
            self.notify(outcome.verdict, error=not outcome.passed)

        self.task(lambda p: attacklab.run_scenario(key), done, "Attack Lab: " + key, locked=False)

    def run_all(self) -> None:
        def work(progress):
            outcomes = []
            for i, (key, title, _, _) in enumerate(attacklab.SCENARIOS):
                progress("Attack Lab: " + title, i / len(attacklab.SCENARIOS))
                outcomes.append(attacklab.run_scenario(key))
            return outcomes

        def done(outcomes: list) -> None:
            for outcome in outcomes:
                self.record(outcome)
            good = sum(1 for o in outcomes if o.passed)
            self.output.setPlainText("\n\n".join(o.text() + "\n" + o.lesson() for o in outcomes))
            self.notify(f"{good} of {len(outcomes)} attacks were detected or rejected as claimed.", error=good != len(outcomes))

        self.task(work, done, "Attack Lab: running all attacks", locked=False)
