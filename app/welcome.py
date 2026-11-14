"""First-run welcome dialog and the short, skippable tour of the window."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QTabWidget, QVBoxLayout,
                               QWidget)

from .glossary import term
from .story import IDEA, analogies_html, cast_html


class WelcomeDialog(QDialog):
    """Welcome screen: the idea in one sentence, the characters, and two ways to begin."""

    def __init__(self, parent: QWidget | None = None, show_again: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to PQ-SSE Desktop")
        self.resize(640, 520)
        self.choice = "explore"
        idea = QLabel(f"<h2>Welcome</h2><p style='font-size:13pt;'><i>{IDEA}</i></p>")
        idea.setWordWrap(True)
        cast = QLabel("<h3>The story</h3>" + cast_html())
        cast.setWordWrap(True)
        likes = QLabel("<h3>Think of it like this</h3>" + analogies_html()
                       + f"<p>This is called {term('sse', 'searchable encryption')}, and the locks are "
                         f"{term('post-quantum', 'post-quantum')}. You do not need to know those words yet.</p>")
        likes.setWordWrap(True)
        likes.setTextFormat(Qt.TextFormat.RichText)
        self.lesson_button = QPushButton("Start the guided lesson")
        self.lesson_button.setDefault(True)
        self.explore_button = QPushButton("Explore on my own")
        self.lesson_button.clicked.connect(lambda: self._pick("lesson"))
        self.explore_button.clicked.connect(lambda: self._pick("explore"))
        self.dont_show = QCheckBox("Do not show again")
        self.dont_show.setChecked(not show_again)
        buttons = QHBoxLayout()
        buttons.addWidget(self.dont_show)
        buttons.addStretch(1)
        buttons.addWidget(self.explore_button)
        buttons.addWidget(self.lesson_button)
        layout = QVBoxLayout(self)
        for widget in (idea, cast, likes):
            layout.addWidget(widget)
        layout.addStretch(1)
        layout.addLayout(buttons)

    def _pick(self, choice: str) -> None:
        self.choice = choice
        self.accept()


TOUR_TEXT = {
    "Learn": "Learn: the guided lesson. It walks through the whole story on the real system, one step at a time.",
    "Owner": "Owner: this is Alice's desk. She creates groups, adds documents, approves doctors and changes the locks.",
    "Receiver": "Receiver: this is where a doctor (Bob or Carol) searches. The Verification panel shows every check on the cloud's answer.",
    "Cloud": "Cloud: start and stop the storage server, watch every request it receives, and see that it holds only locked data.",
    "Attack Lab": "Attack Lab: one-click attacks by a cheating cloud or an outsider, each shown being caught.",
    "Benchmarks": "Benchmarks: measured speed on this computer, including what the graphics chip does and does not speed up.",
    "Settings": "Settings: text size, reduced motion, the freshness window, and advanced choices.",
}


class Tour(QFrame):
    """A banner above the tabs that walks through them. Can be skipped at any time."""

    def __init__(self, tabs: QTabWidget) -> None:
        super().__init__()
        self.tabs = tabs
        self.steps: list[int] = []
        self.position = -1
        self.setObjectName("tour")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.text = QLabel("")
        self.text.setWordWrap(True)
        self.next_button = QPushButton("Next")
        self.skip_button = QPushButton("Skip tour")
        self.next_button.clicked.connect(lambda: self.next())
        self.skip_button.clicked.connect(lambda: self.skip())
        row = QHBoxLayout(self)
        row.addWidget(self.text, 1)
        row.addWidget(self.next_button)
        row.addWidget(self.skip_button)
        self.setHidden(True)

    def active(self) -> bool:
        return not self.isHidden()

    def start(self) -> None:
        self.steps = list(range(self.tabs.count()))
        self.position = -1
        self.setHidden(False)
        self.next()

    def next(self) -> None:
        self.position += 1
        if self.position >= len(self.steps):
            self.skip()
            return
        index = self.steps[self.position]
        self.tabs.setCurrentIndex(index)
        name = self.tabs.tabText(index).split(" (")[0]
        self.text.setText(f"<b>Tour, stop {self.position + 1} of {len(self.steps)}.</b> "
                          + TOUR_TEXT.get(name, name) + " The highlighted tab is the one being described.")
        self.next_button.setText("Finish" if self.position == len(self.steps) - 1 else "Next")

    def skip(self) -> None:
        self.setHidden(True)
        self.position = -1
