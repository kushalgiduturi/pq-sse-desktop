"""Shared GUI pieces: tab base class, indicator light, table helper, document import."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from .session import Session, explain
from .workers import ProgressFn, TaskRunner

GREEN, RED, GREY, AMBER = "#2e9e5b", "#d64545", "#9aa0a6", "#d9a400"


class Light(QLabel):
    """Round status indicator."""

    def __init__(self, color: str = GREY) -> None:
        super().__init__()
        self.setFixedSize(14, 14)
        self.color = color
        self.set(color)

    def set(self, color: str) -> None:
        self.color = color
        self.setStyleSheet(f"background-color: {color}; border-radius: 7px;")


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
    """Base class of every tab: access to the session, the task runner and a message line."""

    def __init__(self, session: Session, runner: TaskRunner) -> None:
        super().__init__()
        self.session = session
        self.runner = runner
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def notify(self, text: str, error: bool = False) -> None:
        self.message.setText(text)
        self.message.setStyleSheet(f"color: {RED if error else GREEN}; font-weight: 600;")

    def fail(self, exc: BaseException) -> None:
        self.notify(explain(exc), error=True)

    def task(self, fn: Callable[[ProgressFn], Any], on_done: Callable[[Any], None] | None = None,
             label: str = "", on_error: Callable[[BaseException], None] | None = None, locked: bool = True) -> None:
        """Run ``fn`` on a worker thread; errors land in the message line."""
        self.runner.run(fn, on_done, on_error or self.fail, label, locked)


def read_document_file(path: str | Path) -> tuple[str, str]:
    """Import a .txt, .md or .pdf file as (title, text). PDF text comes from pypdf."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    return path.stem, text.strip()


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
