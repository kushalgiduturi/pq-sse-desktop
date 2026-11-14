"""Cloud tab: start and stop the server process, live request log, storage statistics,
and the "what the server can see" panel."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QFileDialog, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSplitter,
                               QTableWidgetItem, QVBoxLayout)

from pqsse import paths

from .glossary import term, tip
from .common import GREEN, GREY, RED, Light, TabBase, make_table, password_field

SEE_INTRO = (
    "Everything below is read straight from the cloud's database.\n"
    "The server holds: locked index entries (a secret-looking address and a masked value),\n"
    "locked documents (AES-GCM ciphertext), Alice's stamped summaries (states), sealed mailbox\n"
    "items and each doctor's wrapped pass (credential).\n"
    "It holds no group key, no index key, no document key, no keyword and no document text.\n"
)


class CloudTab(TabBase):
    INTRO = ("<b>This is the Cloud, a rented storage company.</b> It stores everything for Alice but is not trusted: "
             "it might peek, lie, drop results or send old data. So it only ever receives "
             f"{term('ciphertext', 'locked data')}. The panel on the right shows exactly what it holds.")

    def __init__(self, session, runner) -> None:
        super().__init__(session, runner)
        self.last_log_id = 0
        self.passphrase = password_field("Cloud passphrase (protects the cloud's own keys)")
        self.start_button = QPushButton("Start server")
        self.stop_button = QPushButton("Stop server")
        self.pair_button = QPushButton("Pair: import owner key (.pqpub)")
        self.light = Light(GREY, {GREEN: "Running", GREY: "Stopped", RED: "Not running"})
        self.status = QLabel("Server stopped")
        self.start_button.clicked.connect(lambda: self.start())
        self.stop_button.clicked.connect(lambda: self.stop())
        self.pair_button.clicked.connect(lambda: self.pair_owner_dialog())

        top = QHBoxLayout()
        for widget in (self.light, self.status):
            top.addWidget(widget)
        top.addStretch(1)
        controls = QHBoxLayout()
        controls.addWidget(self.passphrase, 2)
        for widget in (self.start_button, self.stop_button, self.pair_button):
            controls.addWidget(widget)

        self.stats = QLabel("No statistics yet")
        self.stats.setWordWrap(True)
        self.log = make_table(["Time", "Endpoint", "Request bytes", "Reply bytes", "Result", "Reason"])
        self.see = QPlainTextEdit()
        self.see.setReadOnly(True)
        self.see.setFont(QFont("Consolas", 9))
        self.see.setPlainText(SEE_INTRO)

        log_box = QGroupBox("Live request log (every request the server sees)")
        log_layout = QVBoxLayout(log_box)
        log_layout.addWidget(self.log)
        see_box = QGroupBox("What the server can see")
        see_layout = QVBoxLayout(see_box)
        see_layout.addWidget(self.see)
        splitter = QSplitter()
        splitter.addWidget(log_box)
        splitter.addWidget(see_box)
        splitter.setSizes([600, 500])

        tip(self.see, "ciphertext", "index", "credential")
        tip(self.log, "token", "signature")
        tip(self.pair_button, "pairing", "fingerprint")
        self.advanced = [self.stats]
        layout = QVBoxLayout(self)
        layout.addWidget(self.intro)
        layout.addLayout(top)
        layout.addLayout(controls)
        layout.addWidget(self.show_advanced)
        layout.addWidget(self.stats)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.footer)

        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.refresh)
        self._polling = False

    # ------------------------------------------------------------------ actions
    def start(self, passphrase: str | None = None) -> None:
        secret = passphrase if passphrase is not None else self.passphrase.text()

        def done(line: str) -> None:
            self.passphrase.clear()
            self.sync_state()
            self.notify("Cloud server started. Its public key file is in " + str(paths.pub_dir() / "cloud.pqpub"))

        self.task(lambda p: self.session.start_cloud(secret), done, "Starting the cloud server", locked=False)

    def sync_state(self) -> None:
        """Make the light, status line and log timer match whether the server is running."""
        if self.session.cloud_running():
            fingerprint = self.session.cloud_line.split("fingerprint=")[-1]
            self.light.set(GREEN)
            self.status.setText(f"Server running on 127.0.0.1:{self.session.port} (local only), key fingerprint {fingerprint}")
            self.timer.start()
            self.refresh()
        else:
            self.timer.stop()
            self.light.set(GREY)
            self.status.setText("Server stopped")

    def reset_view(self) -> None:
        """Clear the log (used when the app switches between your data and the lesson)."""
        self.log.setRowCount(0)
        self.last_log_id = 0
        self.see.setPlainText(SEE_INTRO)
        self.stats.setText("No statistics yet")
        self.sync_state()

    def stop(self) -> None:
        self.timer.stop()
        self.session.stop_cloud()
        self.light.set(GREY)
        self.status.setText("Server stopped")
        self.notify("Cloud server stopped.")

    def pair_owner_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import owner public key", str(paths.pub_dir()), "Public keys (*.pqpub)")
        if path:
            self.pair_owner(Path(path))

    def pair_owner(self, path: Path | None = None) -> None:
        self.task(lambda p: self.session.cloud_pair_owner(path),
                  lambda fp: self.notify(f"Paired with owner key {fp}."), "Pairing cloud with owner", locked=False)

    def refresh(self) -> None:
        if self._polling or not self.session.cloud_running():
            if not self.session.cloud_running() and self.light.color == GREEN:
                self.light.set(RED)
                self.status.setText("Server process is not running")
                self.timer.stop()
            return
        self._polling = True

        def work(progress):
            return (self.session.cloud_admin("log", {"since": self.last_log_id}),
                    self.session.cloud_admin("stats"), self.session.cloud_admin("peek"))

        def done(result) -> None:
            self._polling = False
            rows, stats, peek = result
            self.add_log_rows(rows)
            self.show_stats(stats)
            self.show_peek(peek)

        def failed(exc: BaseException) -> None:
            self._polling = False

        self.task(work, done, "", on_error=failed, locked=False)

    # ------------------------------------------------------------------ rendering
    def add_log_rows(self, rows: list) -> None:
        for log_id, ts_ms, endpoint, n_in, n_out, ok, reason in rows:
            self.last_log_id = max(self.last_log_id, log_id)
            row = self.log.rowCount()
            self.log.insertRow(row)
            stamp = time.strftime("%H:%M:%S", time.localtime(ts_ms / 1000.0))
            values = [stamp, endpoint, n_in, n_out, "accepted" if ok else "REJECTED", reason]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if not ok:
                    item.setForeground(QColor(RED))
                self.log.setItem(row, col, item)
        if rows:
            self.log.scrollToBottom()
        while self.log.rowCount() > 2000:
            self.log.removeRow(0)

    def show_stats(self, s: dict) -> None:
        groups = ", ".join(f"{g['g']} (epoch {g['cur']}, live from {g['base']}, {g['seq']} batches)" for g in s["groups"]) or "none"
        self.stats.setText(
            f"Index entries: {s['entries']:,} | Documents: {s['docs']:,} ({s['doc_bytes']:,} bytes ciphertext) | "
            f"States: {s['states']} ({s['state_bytes']:,} bytes) | Receivers: {s['receivers']} active, {s['revoked']} revoked | "
            f"Mailbox items: {s['mail']} | Requests: {s['requests']:,} ({s['rejected']:,} rejected)\nGroups: {groups}")

    def show_peek(self, peek: dict) -> None:
        lines = [SEE_INTRO, "INDEX ENTRIES  group | epoch | address (32 bytes) | masked value (5 bytes)"]
        lines += [f"  {g} | {e} | {a} | {v}" for g, e, a, v in peek["entries"]] or ["  (none)"]
        lines += ["", "DOCUMENTS  group | epoch | handle | ciphertext (first bytes) | size"]
        lines += [f"  {g} | {e} | {h} | {b}... | {size} bytes" for g, e, h, b, size in peek["docs"]] or ["  (none)"]
        lines += ["", "STATES  group | epoch | version | final | ciphertext (first bytes) | size"]
        lines += [f"  {g} | {e} | v{ver} | {'final' if final else 'open'} | {ct}... | {size} bytes"
                  for g, e, ver, final, ct, size in peek["states"]] or ["  (none)"]
        lines += ["", "CREDENTIALS  receiver id | scope | revoked | wrapped a_u (first bytes)"]
        lines += [f"  {uid} | {scope} | {'yes' if revoked else 'no'} | {a}..." for uid, scope, revoked, a in peek["creds"]] or ["  (none)"]
        scroll = self.see.verticalScrollBar().value()
        self.see.setPlainText("\n".join(lines))
        self.see.verticalScrollBar().setValue(scroll)
