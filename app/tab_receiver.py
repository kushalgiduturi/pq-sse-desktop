"""Receiver tab: switch user, join, search with the verification panel, decrypt on open."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QSplitter, QTextEdit, QVBoxLayout)

from pqsse.core.errors import PQSSEError, VerifyError
from pqsse.receiver import CHECKS, Report

from .common import GREEN, GREY, RED, Light, TabBase, password_field

CHECK_LABELS = {
    "state signature": "State signature OK",
    "segments complete": "All segments present",
    "older segments final": "Older segments final",
    "freshness": "Current state fresh",
    "no rollback": "No rollback",
    "response signature": "Response signature OK",
    "completeness": "Completeness OK",
    "hash chain": "Hash chain OK",
}


class ReceiverTab(TabBase):
    def __init__(self, session, runner) -> None:
        super().__init__(session, runner)
        self.current: str | None = None

        self.user = QComboBox()
        self.user.setEditable(True)
        self.user.setMinimumWidth(160)
        self.user.lineEdit().setPlaceholderText("Receiver name")
        self.passphrase = password_field("Receiver passphrase")
        unlock = QPushButton("Unlock or create")
        pair = QPushButton("Pair devices")
        join = QPushButton("Send join request")
        mail = QPushButton("Fetch mailbox")
        unlock.clicked.connect(lambda: self.unlock())
        pair.clicked.connect(lambda: self.pair())
        join.clicked.connect(lambda: self.send_join())
        mail.clicked.connect(lambda: self.fetch_mail())
        self.user.activated.connect(lambda _: self.switch_user(self.user.currentText()))
        top = QHBoxLayout()
        top.addWidget(QLabel("User:"))
        top.addWidget(self.user)
        top.addWidget(self.passphrase, 1)
        for button in (unlock, pair, join, mail):
            top.addWidget(button)
        self.identity = QLabel("No receiver unlocked")
        self.identity.setWordWrap(True)

        self.group = QComboBox()
        self.group.setMinimumWidth(140)
        self.keyword = QLineEdit()
        self.keyword.setPlaceholderText("Keyword")
        self.keyword.returnPressed.connect(lambda: self.search())
        search = QPushButton("Search")
        search.clicked.connect(lambda: self.search())
        row = QHBoxLayout()
        row.addWidget(QLabel("Group:"))
        row.addWidget(self.group)
        row.addWidget(self.keyword, 1)
        row.addWidget(search)

        self.results = QListWidget()
        self.results.itemClicked.connect(self._open_item)
        results_box = QGroupBox("Results (click to fetch, verify and decrypt)")
        results_layout = QVBoxLayout(results_box)
        self.summary = QLabel("")
        results_layout.addWidget(self.summary)
        results_layout.addWidget(self.results, 1)

        verify_box = QGroupBox("Verification")
        grid = QGridLayout(verify_box)
        self.lights: dict[str, Light] = {}
        self.details: dict[str, QLabel] = {}
        for i, name in enumerate(CHECKS):
            self.lights[name] = Light()
            self.details[name] = QLabel("")
            self.details[name].setWordWrap(True)
            grid.addWidget(self.lights[name], i, 0)
            grid.addWidget(QLabel(CHECK_LABELS[name]), i, 1)
            grid.addWidget(self.details[name], i, 2)
        self.fresh = QLabel("Fresh until: not checked yet")
        grid.addWidget(self.fresh, len(CHECKS), 0, 1, 3)
        grid.setColumnStretch(2, 1)
        grid.setRowStretch(len(CHECKS) + 1, 1)

        self.viewer = QTextEdit()
        self.viewer.setReadOnly(True)
        viewer_box = QGroupBox("Document viewer")
        viewer_layout = QVBoxLayout(viewer_box)
        viewer_layout.addWidget(self.viewer)

        splitter = QSplitter()
        for widget in (results_box, verify_box, viewer_box):
            splitter.addWidget(widget)
        splitter.setSizes([280, 420, 460])
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.identity)
        layout.addLayout(row)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.message)
        self.reload_users()

    # ------------------------------------------------------------------ users
    @property
    def receiver(self):
        if self.current is None or self.current not in self.session.receivers:
            raise PQSSEError("Unlock a receiver first (name and passphrase).")
        return self.session.receivers[self.current]

    def reload_users(self) -> None:
        text = self.user.currentText()
        self.user.blockSignals(True)
        self.user.clear()
        self.user.addItems(self.session.receiver_names())
        self.user.setEditText(text)
        self.user.blockSignals(False)

    def switch_user(self, name: str) -> None:
        name = name.strip()
        if name in self.session.receivers:
            self.current = name
            self.refresh_identity()
            self.clear_results()
            self.notify(f"Now acting as receiver {name}.")
        else:
            self.current = None
            self.identity.setText(f"Receiver {name} is locked: enter its passphrase and press Unlock.")
            self.clear_results()

    def unlock(self, name: str | None = None, passphrase: str | None = None) -> None:
        name = (name if name is not None else self.user.currentText()).strip()
        secret = passphrase if passphrase is not None else self.passphrase.text()

        def done(rec) -> None:
            self.passphrase.clear()
            self.current = name
            self.reload_users()
            self.user.setEditText(name)
            self.refresh_identity()
            self.clear_results()
            self.notify(f"Receiver {name} unlocked. Key fingerprint {rec.public_identity().fingerprint()}.")

        self.task(lambda p: self.session.open_receiver(name, secret), done, "Opening receiver")

    def refresh_identity(self) -> None:
        rec = self.receiver
        state = "joined, groups: " + ", ".join(rec.groups) if rec.joined else "not joined yet"
        paired = "paired" if rec.paired else "NOT paired (press Pair devices)"
        self.identity.setText(f"Receiver {rec.name} | id {rec.uid[:16]} | key fingerprint "
                              f"{rec.public_identity().fingerprint()} | {paired} | {state}")
        selected = self.group.currentText()
        self.group.clear()
        self.group.addItems(rec.groups)
        if selected in rec.groups:
            self.group.setCurrentText(selected)

    # ------------------------------------------------------------------ join
    def pair(self) -> None:
        def work(progress):
            _ = self.receiver
            return self.session.receiver_pair(self.current)

        def done(text: str) -> None:
            self.notify("Paired: " + text)
            self.refresh_identity()

        self.task(work, done, "Pairing receiver")

    def send_join(self) -> None:
        self.task(lambda p: self.receiver.send_join(),
                  lambda uid: self.notify(f"Join request sent (ML-DSA proof of key ownership). Receiver id {uid[:16]}. "
                                          "Ask the owner to approve it, then fetch the mailbox."),
                  "Join: sending request")

    def fetch_mail(self) -> None:
        def done(events: list[str]) -> None:
            self.refresh_identity()
            self.notify("; ".join(events) if events else "Mailbox: nothing new.")

        self.task(lambda p: self.receiver.fetch_mail(), done, "Fetching mailbox")

    # ------------------------------------------------------------------ search
    def clear_results(self) -> None:
        self.results.clear()
        self.viewer.clear()
        self.summary.setText("")
        self.show_report(None)

    def show_report(self, report: Report | None) -> None:
        seen = {name: (ok, detail) for name, ok, detail in (report.checks if report else [])}
        for name in CHECKS:
            if name in seen:
                ok, detail = seen[name]
                self.lights[name].set(GREEN if ok else RED)
                self.details[name].setText(detail)
            else:
                self.lights[name].set(GREY)
                self.details[name].setText("not reached" if report and report.checks else "")
        if report and report.fresh_until:
            self.fresh.setText("Fresh until: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(report.fresh_until)))
        else:
            self.fresh.setText("Fresh until: not checked yet")

    def search(self, group: str | None = None, keyword: str | None = None) -> None:
        group = group if group is not None else self.group.currentText()
        keyword = keyword if keyword is not None else self.keyword.text()
        if not group or not keyword.strip():
            self.notify("Choose a group and enter a keyword.", error=True)
            return
        self.results.clear()
        self.viewer.clear()

        def done(result) -> None:
            self.show_report(result.report)
            self.summary.setText(f"'{result.keyword}' in {group}: {len(result.hits)} document(s), "
                                 f"{result.entries} index entries verified")
            for doc_id, epoch in result.hits:
                item = QListWidgetItem(f"Document {doc_id} (epoch {epoch})")
                item.setData(Qt.ItemDataRole.UserRole, (group, doc_id, epoch))
                self.results.addItem(item)
            self.notify("Search verified: all checks passed.")

        def failed(exc: BaseException) -> None:
            self.show_report(getattr(exc, "report", None) if isinstance(exc, VerifyError) else None)
            self.summary.setText("No result shown.")
            self.fail(exc)

        self.task(lambda p: self.receiver.search(group, keyword), done, "TokenGen, Search, Verify", on_error=failed)

    def _open_item(self, item: QListWidgetItem) -> None:
        self.open_hit(*item.data(Qt.ItemDataRole.UserRole))

    def open_hit(self, group: str, doc_id: int, epoch: int) -> None:
        def done(doc) -> None:
            self.viewer.setPlainText(f"{doc.title}\n{'-' * max(8, len(doc.title))}\n{doc.text}")
            self.notify(f"Document {doc_id}: owner signature verified, decrypted with the epoch {epoch} key.")

        def failed(exc: BaseException) -> None:
            self.viewer.clear()
            self.fail(exc)

        self.task(lambda p: self.receiver.open_document(group, doc_id, epoch), done, "Decrypt", on_error=failed)
