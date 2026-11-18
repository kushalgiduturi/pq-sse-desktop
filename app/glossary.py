"""The glossary: one place for every plain-language definition.

``term(key)`` returns rich text with a link that opens the glossary at that term.
``tip(widget, key)`` sets a hover tooltip. Both raise KeyError for an unknown key, and both
record the key in ``USED`` so a test can check that every term used in the UI is defined.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QTextBrowser,
                               QVBoxLayout, QWidget)


@dataclass(frozen=True)
class Entry:
    name: str
    plain: str                      # one sentence, plain language
    more: str                       # a short paragraph
    simplification: str = ""        # what the plain sentence leaves out, if anything


GLOSSARY: dict[str, Entry] = {
    "sse": Entry(
        "Searchable encryption (SSE)",
        "A way to search through locked files without unlocking them.",
        "SSE stands for searchable symmetric encryption. The data owner locks their documents and also builds a locked "
        "index. The cloud can use the index to find matching boxes when Receiver A sends a search slip, but it never "
        "sees the documents or the search word.",
        "The cloud still learns a little: how many entries matched, how big things are, and when requests happen."),
    "post-quantum": Entry(
        "Post-quantum",
        "Built to stay safe even if large quantum computers are built one day.",
        "Some of today's locks could be broken by a large quantum computer. Post-quantum methods use different "
        "math problems that are believed to be hard for quantum computers too. This app uses the standards "
        "ML-KEM and ML-DSA.",
        "\"Believed to be hard\" is the honest wording: it rests on current knowledge, not on a proof."),
    "ml-kem": Entry(
        "ML-KEM",
        "A post-quantum way to send a secret key to someone using only their public key.",
        "ML-KEM (standard FIPS 203) is used whenever a secret must travel: the data owner uses it to send Receiver A their "
        "access pass, and to send new keys after a revocation. Only the person holding the matching private "
        "key can open what was sent."),
    "ml-dsa": Entry(
        "ML-DSA",
        "A post-quantum digital signature: a stamp that proves who made something and that it was not changed.",
        "ML-DSA (standard FIPS 204) is used for every stamp in the app. The data owner stamps their updates, their "
        "documents and her published summaries. The cloud stamps its answers. Anyone with the public key "
        "can check a stamp, nobody else can make one."),
    "signature": Entry(
        "Signature",
        "A tamper-proof stamp: it shows who made a message and that nobody changed it afterwards.",
        "A signature is made with a private key and checked with the matching public key. If even one bit of "
        "the message changes, the check fails. In this app signatures are ML-DSA signatures."),
    "key": Entry(
        "Key",
        "A secret number that locks and unlocks data.",
        "Some keys come in pairs: a public key that everyone may know and a private key that stays secret. "
        "Other keys are single secrets shared by the people allowed to read something, like a group key."),
    "passphrase": Entry(
        "Passphrase",
        "The password that protects a role's keys on this computer.",
        "Each role (the data owner, each receiver, the cloud) stores its keys in its own file. The file is locked with a "
        "key made from the passphrase, so the keys are never stored in readable form."),
    "ciphertext": Entry(
        "Ciphertext",
        "Locked data: it looks like random bytes to anyone without the key.",
        "When the data owner locks a document the result is ciphertext. The cloud stores ciphertext only. The readable "
        "original is called plaintext."),
    "group": Entry(
        "Group",
        "A folder of documents that share one lock, such as Finance or Legal.",
        "The data owner gives each receiver access to chosen groups. A receiver without a group's key can neither search "
        "nor read that group."),
    "epoch": Entry(
        "Epoch",
        "A period during which a group uses one key; changing the locks starts a new epoch.",
        "Every group starts at epoch 1. When the data owner revokes someone the owner creates a new key, and the group "
        "moves to the next epoch. People still allowed in receive the new key."),
    "segment": Entry(
        "Segment",
        "The part of a group's index that was written during one epoch.",
        "After a revocation with policy R the old segment stays at the cloud, closed, and new entries go into "
        "a new segment. A search then covers every live segment."),
    "index": Entry(
        "Index",
        "A locked lookup table that lets the cloud find matching boxes without reading them.",
        "For every word in every document the data owner stores one entry at a secret-looking address. Without the "
        "group key the addresses and values are meaningless bytes."),
    "token": Entry(
        "Search token",
        "A sealed search slip: Receiver A makes it, and only the cloud can read it.",
        "The token lists the secret addresses for one word. It is encrypted for the cloud, so nobody "
        "listening on the network learns anything. The cloud sees addresses, not the word.",
        "The cloud can notice when the same addresses are asked for again, so it can tell that a search was repeated."),
    "credential": Entry(
        "Credential",
        "Receiver A's secret pass for talking to the cloud.",
        "The data owner gives the same secret to Receiver A and to the cloud when the owner approves them. Receiver A encrypts every "
        "request with it. When the data owner revokes Receiver A, the cloud stops accepting it."),
    "capability": Entry(
        "Capability",
        "Receiver A's access pass: a sealed package with the keys for the groups the receiver may read.",
        "The data owner seals the capability with ML-KEM so that only Receiver A can open it, and stamps it so Receiver A knows it "
        "is genuine. It holds his credential and the group keys."),
    "hash-chain": Entry(
        "Hash chain",
        "A running fingerprint over all index entries of a word, in order.",
        "Each new entry is mixed into the fingerprint of the entries before it. The data owner publishes the final "
        "fingerprint with their stamp. If the cloud changes, swaps or forges an entry, Receiver A's recomputed "
        "fingerprint no longer matches."),
    "state": Entry(
        "Published state",
        "The data owner's stamped summary of the index: how many entries each word has, and their fingerprint.",
        "The state is encrypted for group members and signed by the data owner. Receiver A uses it to know exactly what a "
        "complete, untampered answer must look like. It carries a version number and an expiry time."),
    "freshness": Entry(
        "Freshness",
        "A guarantee that the answer is recent, not an old copy.",
        "Every published state expires after a set time, and Receiver A remembers the newest version the receiver has seen. "
        "So the cloud cannot keep serving an old state forever.",
        "Inside the time window the cloud could still show the newest state Receiver A has already seen instead of a newer one."),
    "forward-privacy": Entry(
        "Forward privacy",
        "New data cannot be linked to searches made in the past.",
        "When the data owner adds a document, its index entries go to brand-new addresses. The search slips the cloud "
        "saw earlier listed only old addresses, so the cloud cannot tell that the new document contains a "
        "word someone searched for before."),
    "backward-privacy": Entry(
        "Backward privacy",
        "Deleted documents stay hidden from later searches.",
        "A delete is stored as one more masked entry, so the cloud cannot tell which earlier entry it cancels. "
        "Receiver A's app applies the deletes after checking the answer.",
        "The cloud does see that an update happened, when, and how large it was."),
    "revocation": Entry(
        "Revocation",
        "Taking away someone's access: changing the locks and telling only the people still allowed in.",
        "The cloud stops accepting the revoked receiver's pass at once, the group gets a new key, and everyone "
        "else receives it. There are two policies, R and RE."),
    "policy-r": Entry(
        "Policy R (rotate)",
        "Change the key for everything written from now on; leave old data as it is.",
        "Fast and cheap. The honest limit: old data is still locked with the old key, which the revoked "
        "receiver knows. If that receiver teams up with the cloud, they can still read what existed before the revocation."),
    "policy-re": Entry(
        "Policy RE (rotate and re-encrypt)",
        "Change the key and also re-lock every existing document with the new key.",
        "The cloud throws away the old copies, so the old key opens nothing that is still stored. This closes "
        "the gap of policy R, at the cost of re-locking and re-stamping every document.",
        "RE cannot take back what the revoked receiver already downloaded or remembers."),
    "nonce": Entry(
        "Nonce",
        "A number used only once, so that two locked messages never look the same.",
        "Every encryption uses a fresh random nonce. Without it, locking the same text twice would give the "
        "same bytes and leak that the texts are equal."),
    "fingerprint": Entry(
        "Key fingerprint",
        "A short code that identifies a public key, for comparing by eye.",
        "When two devices are paired, each shows the fingerprint of the other's key. If the codes match on "
        "both sides, the right keys were exchanged."),
    "pairing": Entry(
        "Pairing",
        "Exchanging public keys so that each side knows who it is talking to.",
        "The data owner, the cloud and each receiver export a small public key file. Importing each other's files is "
        "the one moment that needs a trusted path, like handing over a card in person."),
    "aes-gcm": Entry(
        "AES-256-GCM",
        "The standard lock used for documents: it hides the content and detects any change.",
        "AES is a widely used symmetric cipher. GCM mode adds a built-in check, so a document that was "
        "altered will not open at all."),
    "gpu": Entry(
        "GPU",
        "The graphics chip, which can do many small identical calculations at the same time.",
        "Building the index means computing thousands of secret addresses. The app can do that batch on the "
        "GPU. Only that batch work is sped up. The post-quantum steps (ML-KEM, ML-DSA) always run on the "
        "normal processor, and the app works fully without a GPU."),
    "cuda": Entry(
        "CUDA",
        "NVIDIA's system for running calculations on its graphics chips.",
        "The app's GPU engine is a small CUDA program. Before it is used, its results are compared with the "
        "normal processor's results, byte for byte."),
}

USED: set[str] = set()


def define(key: str) -> Entry:
    return GLOSSARY[key]


def term(key: str, label: str | None = None) -> str:
    """Rich text for a term: underlined, linked to the glossary (href glossary:key)."""
    entry = GLOSSARY[key]
    USED.add(key)
    return f'<a href="glossary:{key}" title="{entry.plain}">{label or entry.name}</a>'


def tooltip(*keys: str, extra: str = "") -> str:
    """Tooltip text for one or more terms."""
    parts = [extra] if extra else []
    for key in keys:
        entry = GLOSSARY[key]
        USED.add(key)
        parts.append(f"<b>{entry.name}</b>: {entry.plain}")
    return "<qt>" + "<br>".join(parts) + "<br><i>Press F1 to learn more in the glossary.</i></qt>"


def tip(widget: QWidget, *keys: str, extra: str = "") -> QWidget:
    """Attach a glossary tooltip to a widget and return the widget."""
    widget.setToolTip(tooltip(*keys, extra=extra))
    return widget


def search(query: str) -> list[str]:
    """Keys whose name or text contains the query, names first."""
    q = query.strip().lower()
    if not q:
        return sorted(GLOSSARY, key=lambda k: GLOSSARY[k].name.lower())
    by_name = [k for k, e in GLOSSARY.items() if q in e.name.lower() or q in k]
    by_text = [k for k, e in GLOSSARY.items() if k not in by_name and (q in e.plain.lower() or q in e.more.lower())]
    return sorted(by_name, key=lambda k: GLOSSARY[k].name.lower()) + sorted(by_text)


def entry_html(key: str) -> str:
    entry = GLOSSARY[key]
    html = f"<h3>{entry.name}</h3><p><b>In one sentence:</b> {entry.plain}</p><p>{entry.more}</p>"
    if entry.simplification:
        html += f"<p><i>Simplification: {entry.simplification}</i></p>"
    return html


class GlossaryDialog(QDialog):
    """Searchable glossary. Non-modal, so it can stay open next to the app."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Glossary")
        self.resize(720, 460)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search the glossary, for example: epoch")
        self.search_box.textChanged.connect(self.filter)
        self.listing = QListWidget()
        self.listing.currentItemChanged.connect(lambda item, _: self._show(item))
        self.detail = QTextBrowser()
        self.detail.setOpenLinks(False)
        row = QHBoxLayout()
        row.addWidget(self.listing, 1)
        row.addWidget(self.detail, 2)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Every special word used in the app, in plain language."))
        layout.addWidget(self.search_box)
        layout.addLayout(row, 1)
        self.filter("")

    def filter(self, query: str) -> None:
        self.listing.clear()
        for key in search(query):
            item = QListWidgetItem(GLOSSARY[key].name)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.listing.addItem(item)
        if self.listing.count():
            self.listing.setCurrentRow(0)
        else:
            self.detail.setHtml("<p>No entry matches. Try a shorter word.</p>")

    def _show(self, item: QListWidgetItem | None) -> None:
        if item is not None:
            self.detail.setHtml(entry_html(item.data(Qt.ItemDataRole.UserRole)))

    def open_at(self, key: str) -> None:
        """Show the dialog with one term selected."""
        self.search_box.clear()
        for row in range(self.listing.count()):
            if self.listing.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self.listing.setCurrentRow(row)
        self.show()
        self.raise_()
