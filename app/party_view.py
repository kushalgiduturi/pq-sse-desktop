"""'What can each party see?': three columns for the current data.

Alice's column shows plain text. The doctors' column shows which groups each doctor
holds keys for. The Cloud's column shows the real stored bytes, sizes and request timing.
"""
from __future__ import annotations

import time

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from pqsse import narrator
from pqsse.core.errors import PQSSEError

from .common import TabBase
from .glossary import term

HEAD = ("<b>The key idea of the whole app.</b> The same data, seen by three parties. Alice sees everything in plain text. "
        "A doctor sees only the groups Alice gave them keys for. The Cloud stores all of it and sees only "
        f"{term('ciphertext', 'locked bytes')}, sizes and timing.")


def gather(session) -> dict:
    """Collect the three views (runs on a worker thread)."""
    owner = session.owner
    if owner is None:
        raise PQSSEError("Open the owner first, or start the guided lesson, so there is data to look at.")
    alice = {g: owner.documents(g) for g in sorted(owner.groups)}
    doctors = [{"name": r["name"], "groups": r["groups"], "revoked": r["revoked"]} for r in owner.receivers.values()]
    peek = session.cloud_admin("peek")
    stats = session.cloud_admin("stats")
    recent = session.cloud_admin("log", {"since": max(0, stats["requests"] - 8)})
    return {"alice": alice, "doctors": doctors, "peek": peek, "stats": stats, "log": recent}


class PartyView(TabBase):
    def __init__(self, session, runner) -> None:
        super().__init__(session, runner)
        self.data: dict | None = None
        head = QLabel(HEAD)
        head.setWordWrap(True)
        head.linkActivated.connect(self._link)
        refresh = QPushButton("Refresh the three views")
        self.cloud_button = QPushButton("Show a document as the cloud sees it")
        refresh.clicked.connect(lambda: self.refresh())
        self.cloud_button.clicked.connect(lambda: self.show_as_cloud())
        buttons = QHBoxLayout()
        buttons.addWidget(refresh)
        buttons.addWidget(self.cloud_button)
        buttons.addStretch(1)
        mono = QFont("Consolas", 9)
        self.alice, self.doctors, self.cloud = QPlainTextEdit(), QPlainTextEdit(), QPlainTextEdit()
        columns = QHBoxLayout()
        for title, box, font in (("Alice sees (plain text)", self.alice, None),
                                 ("Doctors see (only their groups)", self.doctors, None),
                                 ("The Cloud sees (locked bytes, sizes, timing)", self.cloud, mono)):
            box.setReadOnly(True)
            if font is not None:
                box.setFont(font)
            group = QGroupBox(title)
            inner = QVBoxLayout(group)
            inner.addWidget(box)
            columns.addWidget(group, 1)
        self.aha = QPlainTextEdit()
        self.aha.setReadOnly(True)
        self.aha.setFont(mono)
        self.aha.setMaximumHeight(150)
        self.aha.setPlaceholderText("Press 'Show a document as the cloud sees it'.")
        layout = QVBoxLayout(self)
        layout.addWidget(head)
        layout.addLayout(buttons)
        layout.addLayout(columns, 1)
        layout.addWidget(self.aha)
        layout.addWidget(self.footer)

    def refresh(self, then=None) -> None:
        def done(data: dict) -> None:
            self.data = data
            self.render()
            self.notify("The three views were refreshed from the live system.")
            if then is not None:
                then()

        self.task(lambda p: gather(self.session), done, "Collecting what each party sees")

    def render(self) -> None:
        data = self.data or {}
        lines = []
        for group, docs in data["alice"].items():
            lines.append(f"GROUP {group}  ({len(docs)} documents)")
            for d in docs:
                lines.append(f"  #{d['id']}  {d['title']}\n      {d['text']}")
            lines.append("")
        self.alice.setPlainText("\n".join(lines) or "No groups yet.")

        lines = []
        for doc in data["doctors"]:
            name = doc["name"].capitalize()
            if doc["revoked"]:
                lines.append(f"{name}: REVOKED. The cloud refuses every request. {name} still knows the old keys of: "
                             f"{', '.join(doc['groups'])}. See policy R and RE for what that means.\n")
                continue
            lines.append(f"{name}: holds keys for {', '.join(doc['groups'])}.")
            for group, docs in data["alice"].items():
                if group in doc["groups"]:
                    lines.append(f"  {group}: can search and open all {len(docs)} documents (after checking the cloud's answer).")
                else:
                    lines.append(f"  {group}: nothing. No key, so no search and no reading.")
            lines.append("")
        self.doctors.setPlainText("\n".join(lines) or "No doctors approved yet.")

        peek, stats = data["peek"], data["stats"]
        lines = [f"{stats['docs']} documents, {stats['entries']} index entries, {stats['states']} summaries stored.", "",
                 "INDEX ENTRIES (address | value):"]
        lines += [f"  {a[:40]}... | {v}" for _, _, a, v in peek["entries"][:6]] or ["  (none)"]
        lines += ["", "DOCUMENTS (first bytes | size):"]
        lines += [f"  {b[:40]}... | {size} bytes" for _, _, _, b, size in peek["docs"]] or ["  (none)"]
        lines += ["", "TIMING (what was asked, when, how big):"]
        lines += [f"  {time.strftime('%H:%M:%S', time.localtime(ts / 1000))}  {ep}  {n_in} bytes in, {n_out} out"
                  for _, ts, ep, n_in, n_out, _, _ in data["log"]] or ["  (none)"]
        lines += ["", "The cloud also knows group names, how many doctors exist and which groups each may ask about.",
                  "It does not know any word, title, text or key."]
        self.cloud.setPlainText("\n".join(lines))

    def show_as_cloud(self) -> None:
        """The 'aha' button: one stored document, exactly as the cloud holds it."""
        if self.data is None:
            self.refresh(then=self.show_as_cloud)
            return
        docs = self.data["peek"]["docs"]
        if not docs:
            self.notify("The cloud stores no document yet. Add one and publish, or run the lesson.", error=True)
            return
        group, _, handle, blob, size = docs[0]
        plain = next((d for d in self.data["alice"].get(group, [])), None)
        text = [f"ONE DOCUMENT OF GROUP {group}, AS THE CLOUD STORES IT ({size} bytes):",
                f"  stored under the name: {handle}",
                f"  content: {blob}...",
                "", "The cloud cannot tell which of Alice's documents this is. For comparison, Alice sees documents like:"]
        if plain:
            text.append(f"  {plain['title']}: {plain['text']}")
        text.append("Same data. Without the group key, the bytes above cannot be turned back into text.")
        self.aha.setPlainText("\n".join(text))
        narrator.emit("cloud_view", "Cloud", bytes=size)
        self.notify("This is real stored data, read from the cloud's database.")
