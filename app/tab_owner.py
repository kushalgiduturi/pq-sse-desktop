"""Owner tab: groups, documents, join approval, Publish, Revoke, epoch overview."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QSplitter, QVBoxLayout,
                               QWidget)

from pqsse import paths
from pqsse.core.errors import PQSSEError, VerifyError
from pqsse.owner import DocInput

from .glossary import term, tip
from .common import (DocumentDialog, TabBase, fill_table, make_table, password_field, read_document_file,
                     selected_value)

REVOKE_TEXT = {
    "R": ("Policy R (rotate keys): the receiver is deauthorized at the cloud, the current epoch is closed with a "
          "final state, and a new epoch key is sent to the remaining members. Old segments stay as they are.\n\n"
          "Known limit: data written before the revocation stays readable by the revoked user if they collude "
          "with the cloud."),
    "RE": ("Policy RE (rotate and re-encrypt): like R, and in addition every document and index entry of the "
           "group is re-encrypted under the new epoch. The cloud drops all older segments and documents.\n\n"
           "This costs one signature per document."),
}


class GroupDialog(QDialog):
    """Choose which groups a joining receiver may access."""

    def __init__(self, parent: QWidget | None, name: str, fingerprint: str, groups: list[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Approve join request")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Receiver: {name}\nKey fingerprint: {fingerprint}\n\n"
                                "Compare the fingerprint with the one shown on the receiver's side, "
                                "then choose the groups this receiver may search."))
        self.boxes = [QCheckBox(g) for g in groups]
        for box in self.boxes:
            layout.addWidget(box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen(self) -> list[str]:
        return [box.text() for box in self.boxes if box.isChecked()]


class OwnerTab(TabBase):
    INTRO = ("<b>You are Alice, the hospital records manager (the data owner).</b> You own the documents and decide "
             f"who may read what. Here you make a {term('group', 'group')} for each kind of document, add documents, "
             f"approve doctors, press Publish so doctors can verify answers, and change the locks "
             f"({term('revocation', 'revocation')}) when someone must lose access.")

    def __init__(self, session, runner) -> None:
        super().__init__(session, runner)
        self.joins: dict[str, dict] = {}

        self.passphrase = password_field("Owner passphrase (protects the owner's keys and data)")
        self.open_button = QPushButton("Open or create owner")
        self.pair_button = QPushButton("Pair: import cloud key (.pqpub)")
        self.identity = QLabel("Owner locked")
        self.open_button.clicked.connect(lambda: self.open_owner())
        self.pair_button.clicked.connect(lambda: self.pair_cloud_dialog())
        top = QHBoxLayout()
        top.addWidget(self.passphrase, 2)
        top.addWidget(self.open_button)
        top.addWidget(self.pair_button)

        # groups
        self.groups = QListWidget()
        self.groups.currentTextChanged.connect(lambda _: self.refresh_group())
        self.group_name = QLineEdit()
        self.group_name.setPlaceholderText("New group name")
        new_group = QPushButton("Create group")
        new_group.clicked.connect(lambda: self.create_group(self.group_name.text()))
        group_box = QGroupBox("Groups")
        group_layout = QVBoxLayout(group_box)
        group_layout.addWidget(self.groups, 1)
        group_layout.addWidget(self.group_name)
        group_layout.addWidget(new_group)

        # documents
        self.overview = QLabel("Select a group")
        self.overview.setWordWrap(True)
        self.segments = make_table(["Epoch", "Status", "Keywords", "Index entries", "Documents"])
        self.segments.setMaximumHeight(120)
        self.docs = make_table(["Id", "Title", "Epoch", "Keywords"])
        buttons = QHBoxLayout()
        for text, slot in (("Add document", self.add_dialog), ("Import files", self.import_dialog),
                           ("Edit", self.edit_dialog), ("Delete", self.delete_selected), ("Publish", self.publish)):
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, s=slot: s())
            buttons.addWidget(button)
            if text == "Publish":
                self.publish_button = button
        doc_box = QGroupBox("Documents and index of the selected group")
        doc_layout = QVBoxLayout(doc_box)
        doc_layout.addWidget(self.overview)
        doc_layout.addWidget(self.segments)
        doc_layout.addWidget(self.docs, 1)
        doc_layout.addLayout(buttons)

        # join requests and receivers
        self.join_table = make_table(["Receiver id", "Name", "Key fingerprint", "Proof"])
        refresh_joins = QPushButton("Refresh join requests")
        approve = QPushButton("Approve selected")
        refresh_joins.clicked.connect(lambda: self.refresh_joins())
        approve.clicked.connect(lambda: self.approve_dialog())
        join_buttons = QHBoxLayout()
        join_buttons.addWidget(refresh_joins)
        join_buttons.addWidget(approve)
        self.receiver_table = make_table(["Receiver id", "Name", "Groups", "Status"])
        self.policy = QComboBox()
        self.policy.addItem("Policy R: rotate keys", "R")
        self.policy.addItem("Policy RE: rotate and re-encrypt", "RE")
        revoke = QPushButton("Revoke selected receiver")
        revoke.clicked.connect(lambda: self.revoke_dialog())
        revoke_row = QHBoxLayout()
        revoke_row.addWidget(self.policy, 1)
        revoke_row.addWidget(revoke)
        people_box = QGroupBox("Receivers")
        people_layout = QVBoxLayout(people_box)
        people_layout.addWidget(QLabel("Join requests waiting at the cloud"))
        people_layout.addWidget(self.join_table, 1)
        people_layout.addLayout(join_buttons)
        people_layout.addWidget(QLabel("Approved receivers"))
        people_layout.addWidget(self.receiver_table, 1)
        people_layout.addLayout(revoke_row)

        splitter = QSplitter()
        for widget in (group_box, doc_box, people_box):
            splitter.addWidget(widget)
        splitter.setSizes([170, 520, 470])
        tip(self.pair_button, "pairing", "fingerprint")
        tip(self.policy, "revocation", "policy-r", "policy-re")
        tip(revoke, "revocation", "epoch")
        tip(self.segments, "epoch", "segment")
        tip(self.publish_button, "state", "freshness")
        tip(approve, "capability", "credential", "ml-kem")
        tip(self.docs, "ciphertext", "index")
        tip(self.passphrase, "passphrase", "ml-dsa")
        layout = QVBoxLayout(self)
        layout.addWidget(self.intro)
        layout.addLayout(top)
        layout.addWidget(self.identity)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.footer)

    # ------------------------------------------------------------------ helpers
    @property
    def owner(self):
        if self.session.owner is None:
            raise PQSSEError("Open the owner first (enter the passphrase).")
        return self.session.owner

    def current_group(self) -> str:
        item = self.groups.currentItem()
        if item is None:
            raise PQSSEError("Select a group first.")
        return item.text()

    def _guard(self, fn):
        """Run a GUI-thread precondition; show its error instead of raising."""
        try:
            return fn()
        except PQSSEError as exc:
            self.fail(exc)
            return None

    # ------------------------------------------------------------------ owner and pairing
    def open_owner(self, passphrase: str | None = None) -> None:
        secret = passphrase if passphrase is not None else self.passphrase.text()

        def done(created: bool) -> None:
            self.passphrase.clear()
            self.notify("Owner created (new ML-DSA key pair). Public key file: " + str(paths.pub_dir() / "owner.pqpub")
                        if created else "Owner unlocked.")
            self.refresh_all()

        self.task(lambda p: self.session.open_owner(secret), done, "Opening owner")

    def pair_cloud_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import cloud public key", str(paths.pub_dir()), "Public keys (*.pqpub)")
        if path:
            self.pair_cloud(Path(path))

    def pair_cloud(self, path: Path | None = None) -> None:
        def done(fingerprint: str) -> None:
            self.notify(f"Paired with cloud key {fingerprint}.")
            self.refresh_all()

        self.task(lambda p: self.session.owner_pair_cloud(path), done, "Pairing owner with cloud")

    # ------------------------------------------------------------------ refresh
    def reset_view(self) -> None:
        """Clear the tab (used when the app switches between your data and the lesson)."""
        self.joins = {}
        self.identity.setText("Owner locked")
        self.groups.clear()
        self.overview.setText("Select a group")
        for table in (self.docs, self.segments, self.join_table, self.receiver_table):
            fill_table(table, [])
        self.refresh_all()

    def refresh_all(self) -> None:
        owner = self.session.owner
        if owner is None:
            return
        cloud = owner.cloud_pub
        self.identity.setText(
            f"Owner key fingerprint: {owner.public_identity().fingerprint()} | Parameters: {owner.params.label()} | "
            + (f"Paired with cloud {cloud.fingerprint()}" if cloud else "Not paired with a cloud yet"))
        current = self.groups.currentItem().text() if self.groups.currentItem() else None
        self.groups.blockSignals(True)
        self.groups.clear()
        self.groups.addItems(sorted(owner.groups))
        self.groups.blockSignals(False)
        names = sorted(owner.groups)
        if names:
            self.groups.setCurrentRow(names.index(current) if current in names else 0)
        self.refresh_group()
        fill_table(self.receiver_table, [[uid, r["name"], ", ".join(r["groups"]), "revoked" if r["revoked"] else "active"]
                                         for uid, r in owner.receivers.items()])

    def refresh_group(self) -> None:
        owner = self.session.owner
        item = self.groups.currentItem()
        if owner is None or item is None:
            fill_table(self.docs, [])
            fill_table(self.segments, [])
            return
        info = owner.overview(item.text())
        expires = time.strftime("%Y-%m-%d %H:%M", time.localtime(info["expires"])) if info["expires"] else "never published"
        dirty = "UNPUBLISHED CHANGES, press Publish" if info["dirty"] else "published"
        self.overview.setText(
            f"Group {info['group']}: current epoch {info['epoch']}, live segments from epoch {info['base']}, "
            f"state version {info['version']} ({dirty}), fresh until {expires}, "
            f"{info['seq']} update batches, {len(info['members'])} member(s)")
        fill_table(self.segments, [[s["epoch"], "final (closed)" if s["final"] else "current", s["keywords"],
                                    s["entries"], s["docs"]] for s in info["segments"]])
        fill_table(self.docs, [[d["id"], d["title"], d["epoch"], d["keywords"]] for d in owner.documents(item.text())])

    # ------------------------------------------------------------------ groups and documents
    def create_group(self, name: str) -> None:
        name = name.strip()

        def done(_: object) -> None:
            self.group_name.clear()
            self.notify(f"Group {name} created at epoch 1 and its empty state published.")
            self.refresh_all()

        self.task(lambda p: self.owner.create_group(name), done, "Creating group")

    def add_dialog(self) -> None:
        if self._guard(self.current_group) is None:
            return
        dialog = DocumentDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.add_document(*dialog.values())

    def add_document(self, title: str, text: str) -> None:
        group = self._guard(self.current_group)
        if group is None:
            return

        def done(doc_id: int) -> None:
            self.notify(f"Document {doc_id} encrypted, indexed and sent (Update). Publish to make it searchable.")
            self.refresh_group()

        self.task(lambda p: self.owner.add_document(group, title, text), done, "Update: adding document")

    def import_dialog(self) -> None:
        paths_, _ = QFileDialog.getOpenFileNames(self, "Import documents", "", "Documents (*.txt *.md *.pdf)")
        if paths_:
            self.import_files(paths_)

    def import_files(self, files: list[str]) -> None:
        group = self._guard(self.current_group)
        if group is None:
            return

        def work(progress):
            docs = []
            for i, name in enumerate(files):
                progress(f"Reading {Path(name).name}", i / max(1, len(files)))
                title, text = read_document_file(name)
                docs.append(DocInput(title, text))
            progress("BuildIndex: deriving addresses and encrypting", 0.9)
            return self.owner.build_index(group, docs)

        def done(ids: list[int]) -> None:
            self.notify(f"{len(ids)} document(s) imported as one BuildIndex batch. Publish to make them searchable.")
            self.refresh_group()

        self.task(work, done, "BuildIndex: importing documents")

    def edit_dialog(self) -> None:
        doc_id = selected_value(self.docs)
        group = self._guard(self.current_group)
        if doc_id is None or group is None:
            self.notify("Select a document to edit.", error=True)
            return
        current = next(d for d in self.owner.documents(group) if d["id"] == doc_id)
        dialog = DocumentDialog(self, current["title"], current["text"])
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.edit_document(doc_id, *dialog.values())

    def edit_document(self, doc_id: int, title: str, text: str) -> None:
        group = self._guard(self.current_group)
        if group is None:
            return

        def done(new_id: int) -> None:
            self.notify(f"Document {doc_id} replaced by document {new_id} (delete plus add in one batch).")
            self.refresh_group()

        self.task(lambda p: self.owner.edit_document(group, doc_id, title, text), done, "Update: editing document")

    def delete_selected(self) -> None:
        doc_id = selected_value(self.docs)
        if doc_id is None:
            self.notify("Select a document to delete.", error=True)
            return
        self.delete_document(doc_id)

    def delete_document(self, doc_id: int) -> None:
        group = self._guard(self.current_group)
        if group is None:
            return

        def done(_: object) -> None:
            self.notify(f"Document {doc_id} deleted (masked delete entries appended). Publish to apply.")
            self.refresh_group()

        self.task(lambda p: self.owner.delete_document(group, doc_id), done, "Update: deleting document")

    def publish(self) -> None:
        group = self._guard(self.current_group)
        if group is None:
            return

        def done(version: int) -> None:
            self.notify(f"State version {version} of group {group} signed and published.")
            self.refresh_group()

        self.task(lambda p: self.owner.publish(group), done, "Publish: signing state")

    # ------------------------------------------------------------------ join
    def refresh_joins(self) -> None:
        def work(progress):
            checked = []
            for item in self.owner.pending_joins():
                try:
                    req = self.owner.check_join(item)
                    checked.append((item, req.uid, req.name, req.fingerprint, "valid"))
                except VerifyError as exc:
                    checked.append((item, item.get("uid", "?"), "?", "?", "INVALID: " + exc.detail))
            return checked

        def done(checked: list) -> None:
            self.joins = {uid: item for item, uid, _, _, proof in checked if proof == "valid"}
            fill_table(self.join_table, [[uid, name, fp, proof] for _, uid, name, fp, proof in checked])
            self.notify(f"{len(checked)} join request(s) at the cloud.")

        self.task(work, done, "Fetching join requests")

    def approve_dialog(self) -> None:
        uid = selected_value(self.join_table)
        if uid is None or uid not in self.joins:
            self.notify("Select a valid join request first.", error=True)
            return
        row = self.join_table.currentRow()
        dialog = GroupDialog(self, self.join_table.item(row, 1).text(), self.join_table.item(row, 2).text(),
                             sorted(self.owner.groups))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.approve(uid, dialog.chosen())

    def approve(self, uid: str, groups: list[str]) -> None:
        item = self.joins.get(uid)
        if item is None or not groups:
            self.notify("Choose a valid request and at least one group.", error=True)
            return

        def done(_: object) -> None:
            self.notify(f"Receiver {uid[:8]} approved for: {', '.join(groups)}. Capability sealed with ML-KEM and sent.")
            self.refresh_all()
            self.refresh_joins()

        self.task(lambda p: self.owner.approve_join(item, groups), done, "Join: issuing capability")

    # ------------------------------------------------------------------ revoke
    def revoke_dialog(self) -> None:
        uid = selected_value(self.receiver_table)
        if uid is None:
            self.notify("Select a receiver to revoke.", error=True)
            return
        policy = self.policy.currentData()
        name = self.owner.receivers[uid]["name"]
        answer = QMessageBox.question(self, "Confirm revocation",
                                      f"Revoke receiver '{name}' ({uid[:8]})?\n\n{REVOKE_TEXT[policy]}")
        if answer == QMessageBox.StandardButton.Yes:
            self.revoke(uid, policy)

    def revoke(self, uid: str, policy: str) -> None:
        def done(rotated: list[str]) -> None:
            self.notify(f"Receiver revoked with policy {policy}. Rotated group(s): {', '.join(rotated) or 'none'}.")
            self.refresh_all()

        self.task(lambda p: self.owner.revoke(uid, policy), done, f"Revoke ({policy})")
