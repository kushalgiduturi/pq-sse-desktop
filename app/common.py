"""Shared GUI pieces: tab base class, indicator light, table helper, document import."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Sequence

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from pqsse import narrator

from .session import Session, explain_full
from .workers import ProgressFn, TaskRunner

# Chosen for contrast: white text on these, and these as text on a light background, are readable.
GREEN, RED, GREY, AMBER = "#1e7a44", "#c62828", "#5f6670", "#8a6500"


LIGHT_WORDS = {GREEN: "OK", RED: "Failed", GREY: "Not checked", AMBER: "Wait"}


class Light(QLabel):
    """Status indicator: a colored pill that always carries a word, never color alone."""

    def __init__(self, color: str = GREY, words: dict[str, str] | None = None) -> None:
        super().__init__()
        self.words = {**LIGHT_WORDS, **(words or {})}
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(92)
        self.color = color
        self.set(color)

    def set(self, color: str, word: str | None = None) -> None:
        self.color = color
        self.setText(word or self.words.get(color, ""))
        self.setAccessibleName(self.text())
        self.setStyleSheet(f"background-color: {color}; color: white; border-radius: 8px; padding: 1px 8px; font-weight: 600;")


def make_table(headers: Sequence[str], stretch_last: bool = True) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(stretch_last)
    return table


def fill_table(table: QTableWidget, rows: Sequence[Sequence[Any]]) -> None:
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(str(value))
            item.setData(Qt.ItemDataRole.UserRole, value)
            table.setItem(r, c, item)


def selected_value(table: QTableWidget, column: int = 0) -> Any:
    row = table.currentRow()
    if row < 0 or table.item(row, column) is None:
        return None
    return table.item(row, column).data(Qt.ItemDataRole.UserRole)


def password_field(placeholder: str) -> QLineEdit:
    field = QLineEdit()
    field.setEchoMode(QLineEdit.EchoMode.Password)
    field.setPlaceholderText(placeholder)
    return field


class TabBase(QWidget):
    """Base class of every tab: session, task runner, story intro, and the message footer.

    The footer shows one line (``message``), and for errors the two further parts of the
    explanation ("Why it matters", "What to do next") plus a "Copy technical details" button.
    """

    INTRO = ""          # story text shown in Beginner Mode

    def __init__(self, session: Session, runner: TaskRunner) -> None:
        super().__init__()
        self.session = session
        self.runner = runner
        self.beginner = False
        self.technical = ""
        self.advanced: list[QWidget] = []
        self.intro = QLabel(self.INTRO)
        self.intro.setWordWrap(True)
        self.intro.setObjectName("intro")
        self.intro.setOpenExternalLinks(False)
        self.intro.linkActivated.connect(self._link)
        self.intro.setHidden(True)
        self.show_advanced = QCheckBox("Show advanced")
        self.show_advanced.setHidden(True)
        self.show_advanced.toggled.connect(lambda _: self._apply_advanced())
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail.setHidden(True)
        self.copy_button = QPushButton("Copy technical details")
        self.copy_button.setHidden(True)
        self.copy_button.clicked.connect(lambda: self.copy_technical())
        self.footer = QWidget()
        box = QVBoxLayout(self.footer)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self.message)
        box.addWidget(self.detail)
        row = QHBoxLayout()
        row.addWidget(self.copy_button)
        row.addStretch(1)
        box.addLayout(row)

    def _link(self, href: str) -> None:
        window = self.window()
        if href.startswith("glossary:") and hasattr(window, "open_glossary"):
            window.open_glossary(href.split(":", 1)[1])

    def notify(self, text: str, error: bool = False) -> None:
        self.message.setText(text)
        self.message.setStyleSheet(f"color: {RED if error else GREEN}; font-weight: 600;")
        if not error:
            self.detail.setHidden(True)
            self.copy_button.setHidden(True)

    def fail(self, exc: BaseException) -> None:
        """Show an error as What happened / Why it matters / What to do next. Never a traceback."""
        friendly = explain_full(exc)
        self.notify(friendly.what, error=True)
        self.detail.setText(f"Why it matters: {friendly.why}\nWhat to do next: {friendly.next}")
        self.detail.setHidden(False)
        self.technical = friendly.technical
        self.copy_button.setHidden(False)
        logging.getLogger("pqsse.app").warning("Step failed: %s", friendly.technical.splitlines()[0] if friendly.technical else friendly.what)
        narrator.emit("blocked", "", what=friendly.what[:280])

    def copy_technical(self) -> str:
        QGuiApplication.clipboard().setText(self.technical)
        return self.technical

    def task(self, fn: Callable[[ProgressFn], Any], on_done: Callable[[Any], None] | None = None,
             label: str = "", on_error: Callable[[BaseException], None] | None = None, locked: bool = True) -> None:
        """Run ``fn`` on a worker thread; errors land in the message footer."""
        self.runner.run(fn, on_done, on_error or self.fail, label, locked)

    # ------------------------------------------------------------------ Beginner / Expert
    def set_beginner(self, beginner: bool) -> None:
        """Beginner Mode: story intro visible, advanced controls collapsed behind a checkbox."""
        self.beginner = beginner
        self.intro.setHidden(not (beginner and bool(self.INTRO)))
        self.show_advanced.setHidden(not (beginner and bool(self.advanced)))
        self._apply_advanced()

    def _apply_advanced(self) -> None:
        hide = self.beginner and not self.show_advanced.isChecked()
        for widget in self.advanced:
            widget.setHidden(hide)

    def flash(self, widget: QWidget, seconds: float = 4.0) -> None:
        """Highlight a control for "Let me try"."""
        previous = widget.styleSheet()
        widget.setStyleSheet(previous + "; border: 3px solid #d9a400;")
        widget.setFocus()
        QTimer.singleShot(int(seconds * 1000), lambda: widget.setStyleSheet(previous))


from pqsse.docimport import read_document_file  # noqa: E402,F401 (limits before parsing: pqsse/docimport.py)


class DocumentDialog(QDialog):
    """Add or edit a document: paste text or import a file."""

    def __init__(self, parent: QWidget | None = None, title: str = "", text: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Document")
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        self.title_edit = QLineEdit(title)
        self.title_edit.setPlaceholderText("Title")
        self.text_edit = QPlainTextEdit(text)
        self.text_edit.setPlaceholderText("Paste the document text here, or import a file")
        import_button = QPushButton("Import .txt / .md / .pdf")
        import_button.clicked.connect(self.import_file)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(self.title_edit)
        layout.addWidget(self.text_edit, 1)
        row = QHBoxLayout()
        row.addWidget(import_button)
        row.addStretch(1)
        row.addWidget(buttons)
        layout.addLayout(row)

    def import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import document", "", "Documents (*.txt *.md *.pdf)")
        if path:
            self.load(path)

    def load(self, path: str | Path) -> None:
        title, text = read_document_file(path)
        self.title_edit.setText(title)
        self.text_edit.setPlainText(text)

    def values(self) -> tuple[str, str]:
        return self.title_edit.text().strip() or "untitled", self.text_edit.toPlainText()
