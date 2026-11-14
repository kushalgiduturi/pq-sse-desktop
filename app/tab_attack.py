"""Attack Lab tab: one-click tampering demos, each on a throwaway in-memory world."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSplitter,
                               QTableWidgetItem, QVBoxLayout)

from pqsse import attacklab

from .common import GREEN, RED, TabBase, make_table, selected_value

INTRO = ("Each demo builds its own small owner, cloud and receivers in memory (your real data is not touched), "
         "runs an honest baseline, then lets a malicious cloud or attacker tamper, and shows which check stops it. "
         "The demos use ML-KEM-512 and ML-DSA-44 so they finish in about a second.")


class AttackTab(TabBase):
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
        run_one.clicked.connect(lambda: self.run_selected())
        run_all.clicked.connect(lambda: self.run_all())
        buttons = QHBoxLayout()
        buttons.addWidget(run_one)
        buttons.addWidget(run_all)
        buttons.addStretch(1)
        left = QGroupBox("Attacks")
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.table, 1)
        left_layout.addLayout(buttons)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 10))
        right = QGroupBox("What happened")
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.output)
        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([520, 640])
        intro = QLabel(INTRO)
        intro.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.message)

    def _row_of(self, key: str) -> int:
        return [s[0] for s in attacklab.SCENARIOS].index(key)

    def _show_selected(self) -> None:
        key = selected_value(self.table)
        if key in self.outcomes:
            self.output.setPlainText(self.outcomes[key].text())

    def _record(self, outcome: attacklab.Outcome) -> None:
        self.outcomes[outcome.key] = outcome
        short = "AS DOCUMENTED" if outcome.verdict.startswith("AS DOCUMENTED") else outcome.verdict.split()[0].rstrip(":")
        item = QTableWidgetItem(short if outcome.passed else "FAILED")
        item.setForeground(QColor(GREEN if outcome.passed else RED))
        self.table.setItem(self._row_of(outcome.key), 3, item)
        self.output.setPlainText(outcome.text())

    def run_selected(self) -> None:
        key = selected_value(self.table)
        if key is None:
            self.notify("Select an attack first.", error=True)
            return
        self.run(key)

    def run(self, key: str) -> None:
        def done(outcome: attacklab.Outcome) -> None:
            self._record(outcome)
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
                self._record(outcome)
            good = sum(1 for o in outcomes if o.passed)
            self.output.setPlainText("\n\n".join(o.text() for o in outcomes))
            self.notify(f"{good} of {len(outcomes)} attacks were detected or rejected as claimed.", error=good != len(outcomes))

        self.task(work, done, "Attack Lab: running all attacks", locked=False)
