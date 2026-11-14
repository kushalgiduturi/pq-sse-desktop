"""The guided lesson: 13 steps that drive the real system inside the lesson sandbox.

Every "Do it for me" action calls the same Session, Owner and Receiver methods the tabs
use, against the real cloud process. Actions run on a worker thread and return the text
for the "What just happened" box. They are written to be repeatable: running a step twice,
or resuming after a restart, does not break the lesson.
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Callable

from pqsse import attacklab
from pqsse.core.errors import AccessDenied, Rejected
from pqsse.owner import DocInput

from .glossary import term
from .session import LESSON_PASSPHRASE, Session, explain_full
from .story import IDEA, analogies_html, cast_html

FINANCE, MEDICAL = "Finance", "Medical"
DEMO_DOCS: dict[str, list[tuple[str, str]]] = {
    FINANCE: [
        ("Invoice 1042, MRI scanner", "Invoice for the MRI scanner service contract. Amount due in March."),
        ("Budget 2026, radiology", "Annual budget for the radiology department, with salary and equipment costs."),
        ("Payroll note, nursing", "Payroll summary for nursing staff, including overtime salary adjustments."),
        ("Supplier invoice, pharmacy", "Invoice from the pharmacy supplier for vaccines and gloves."),
    ],
    MEDICAL: [
        ("Allergy record, patient A", "The patient has a penicillin allergy. Avoid amoxicillin."),
        ("Lab result 77", "Blood test shows normal glucose and low iron."),
        ("Discharge summary, knee", "Patient discharged after knee surgery. Physiotherapy advised."),
        ("Vaccination log", "Vaccines given this season: influenza and tetanus."),
    ],
}
NEW_DOC = ("Invoice 1050, ultrasound probe", "Invoice for an ultrasound probe and its yearly maintenance.")
DELETED_TITLE = "Payroll note, nursing"
SEARCH_WORD = "invoice"

CHECK_MEANING = {
    "state signature": "Alice's stamp is on the summary of the index. The cloud cannot invent what the index contains.",
    "segments complete": "Every live part of the index is covered. The cloud cannot hide a whole part.",
    "older segments final": "Closed parts are marked final by Alice. Nothing can be slipped into them later.",
    "freshness": "The summary has not expired. The cloud cannot serve an old copy forever.",
    "no rollback": "The version is not older than one Bob has already seen. The cloud cannot go back in time.",
    "response signature": "The cloud stamped this exact answer to this exact slip. It cannot deny or reuse it.",
    "completeness": "Every entry the summary promises is present, in order. Nothing was dropped or added.",
    "hash chain": "The running fingerprint of the entries matches Alice's. Nothing was changed or swapped.",
}


class Ctx:
    """What a lesson action may use: the session and a small scratch store. No widgets."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.store: dict = {}
        self.seen: set[str] = set()        # narrator event kinds seen since the lesson started

    @property
    def owner(self):
        return self.session.owner

    @property
    def bob(self):
        return self.session.receivers["bob"]


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    explain: str
    do: Callable[[Ctx], str] | None = None
    try_tab: str = ""            # attribute name of the tab on the main window
    try_widget: str = ""         # attribute name of the control on that tab
    try_text: str = ""
    check: Callable[[Ctx], bool] | None = None


def p(*paragraphs: str) -> str:
    return "".join(f"<p>{text}</p>" for text in paragraphs)


def esc(text: object) -> str:
    return html.escape(str(text))


# ---------------------------------------------------------------- prerequisites
def ensure(ctx: Ctx, number: int) -> None:
    """Make sure everything step ``number`` builds on is running (also after a restart)."""
    s = ctx.session
    if number > 2 and not s.cloud_running():
        s.start_cloud(LESSON_PASSPHRASE)
    if number > 3 and s.owner is None:
        s.open_owner(LESSON_PASSPHRASE)
    if number > 5 and "bob" not in s.receivers:
        s.open_receiver("bob", LESSON_PASSPHRASE)


# ---------------------------------------------------------------- step actions
def do_cloud(ctx: Ctx) -> str:
    line = ctx.session.start_cloud(LESSON_PASSPHRASE)
    fingerprint = line.split("fingerprint=")[-1]
    return p("The cloud server is now running as its own program on this computer.",
             f"It made its own keys. Its {term('fingerprint', 'key fingerprint')} is <b>{esc(fingerprint)}</b>.",
             "Remember: the cloud stores things for Alice, but nobody trusts it. From now on, watch what it is given.")


def do_setup(ctx: Ctx) -> str:
    s = ctx.session
    created = s.open_owner(LESSON_PASSPHRASE)
    cloud_fp = s.owner_pair_cloud()
    owner_fp = s.cloud_pair_owner()
    return p(("Alice created her key pair." if created else "Alice unlocked her keys.")
             + f" Her key fingerprint is <b>{esc(owner_fp)}</b>.",
             "A key pair has two halves. The <b>private</b> half stays with Alice and makes her stamps. "
             "The <b>public</b> half can be given to anyone and lets them check those stamps.",
             f"Alice and the cloud also exchanged public keys ({term('pairing', 'pairing')}). "
             f"Alice now knows the cloud's key <b>{esc(cloud_fp)}</b>, and the cloud knows hers.",
             f"The keys are {term('post-quantum', 'post-quantum')}: the stamps use {term('ml-dsa', 'ML-DSA')} and sealed "
             f"messages use {term('ml-kem', 'ML-KEM')}.",
             "<i>Simplification: a key is really a long number, and the fingerprint is a short code computed from the public half.</i>")


def do_groups(ctx: Ctx) -> str:
    made = []
    for group in (FINANCE, MEDICAL):
        if group not in ctx.owner.groups:
            ctx.owner.create_group(group)
            made.append(group)
    rows = "".join(f"<li><b>{g}</b>: " + "; ".join(esc(t) for t, _ in docs) + "</li>" for g, docs in DEMO_DOCS.items())
    return p(f"Alice created the groups: {', '.join(made) or 'Finance and Medical (already there)'}. Each group got its own secret key.",
             "She also picked eight short demo documents. They are still only on Alice's side:",
             f"<ul>{rows}</ul>",
             "The cloud was told that two groups exist. It was not given any key. Step 6 locks the documents and sends them.")


def do_join(ctx: Ctx) -> str:
    s = ctx.session
    bob = s.open_receiver("bob", LESSON_PASSPHRASE)
    if not bob.paired:
        s.receiver_pair("bob")
    known = {r["name"]: r for r in ctx.owner.receivers.values()}
    if not bob.joined and not known.get("bob", {}).get("revoked"):
        uid = bob.send_join()
        item = next(i for i in ctx.owner.pending_joins() if i["uid"] == uid)
        request = ctx.owner.check_join(item)
        ctx.store["bob_fp"] = request.fingerprint
        ctx.owner.approve_join(item, [FINANCE])
        bob.fetch_mail()
    return p("Bob created his own keys and sent a join request. The request carries a stamp that proves the keys are his.",
             f"Alice saw the request with the key fingerprint <b>{esc(ctx.store.get('bob_fp', bob.public_identity().fingerprint()))}</b> "
             "and approved Bob for <b>Finance only</b>.",
             f"She sent Bob an access pass ({term('capability', 'capability')}): the Finance key and a secret pass for the cloud "
             f"({term('credential', 'credential')}). It is sealed so only Bob can open it, and stamped so Bob knows it is from Alice.",
             "The cloud passed the sealed pass along and was told one thing: Bob may ask about Finance. "
             "Bob holds no Medical key, so Medical is closed to him.")


def do_build(ctx: Ctx) -> str:
    owner = ctx.owner
    for group, docs in DEMO_DOCS.items():
        if not owner.documents(group):
            owner.build_index(group, [DocInput(title, text) for title, text in docs])
        if owner.overview(group)["dirty"]:
            owner.publish(group)
    stats = ctx.session.cloud_admin("stats")
    peek = ctx.session.cloud_admin("peek")
    entry = peek["entries"][0] if peek["entries"] else ["", 0, "", ""]
    doc = peek["docs"][0] if peek["docs"] else ["", 0, "", "", 0]
    return p("Alice put each document into its own locked box and built the locked index: one entry for every word of every document.",
             f"Then she published a stamped summary ({term('state', 'published state')}) for each group, so doctors can check the cloud's answers.",
             f"<b>What the cloud holds now:</b> {stats['docs']} locked documents and {stats['entries']} index entries. For example:",
             f"<ul><li>one index entry: address <code>{esc(entry[2][:32])}...</code> value <code>{esc(entry[3])}</code></li>"
             f"<li>one document: <code>{esc(doc[3][:48])}...</code> ({doc[4]} bytes)</li></ul>",
             "No word, no title, no text. Open the Cloud tab or the 'Who sees what' page to look for yourself.",
             f"<i>Simplification: the cloud does learn sizes and counts, for example that {stats['docs']} documents exist.</i>")


def _search(ctx: Ctx):
    result = ctx.bob.search(FINANCE, SEARCH_WORD)
    ctx.store["result"] = result
    return result


def do_search(ctx: Ctx) -> str:
    result = _search(ctx)
    recent = max(0, ctx.session.cloud_admin("stats")["requests"] - 40)
    rows = [r for r in ctx.session.cloud_admin("log", {"since": recent}) if r[2] in ("states_get", "search")][-2:]
    seen = "".join(f"<li>request '{esc(r[2])}': {r[3]} bytes in, {r[4]} bytes out</li>" for r in rows)
    return p(f"Bob searched Finance for <b>'{SEARCH_WORD}'</b>.",
             f"His app did not send the word. It computed the secret addresses where entries for that word live, wrote them on a "
             f"sealed search slip ({term('token', 'token')}) and sent the slip to the cloud.",
             f"<b>What the cloud saw:</b><ul>{seen}</ul>Only encrypted bytes and addresses. The word '{SEARCH_WORD}' never left Bob's computer.",
             f"The cloud returned {result.entries} scrambled entries. After checking them (next step), Bob's app found "
             f"<b>{len(result.hits)} matching documents</b>.",
             "<i>Simplification: the cloud can tell that two searches used the same addresses, so it can notice a repeated search.</i>")


def do_verify(ctx: Ctx) -> str:
    result = _search(ctx)
    rows = "".join(f"<li><b>OK: {esc(name)}.</b> {CHECK_MEANING[name]}</li>" for name, ok, _ in result.report.checks if ok)
    return p("Bob does not trust the cloud, so his app checked the answer before showing anything. All checks passed:",
             f"<ul>{rows}</ul>",
             "If any one of these fails, the app shows no result at all. The Attack Lab step later shows that happening.",
             "Look at the Receiver tab: the Verification panel shows the same checks, each with the word OK.")


def do_decrypt(ctx: Ctx) -> str:
    result = ctx.store.get("result") or _search(ctx)
    doc_id, epoch = result.hits[0]
    doc = ctx.bob.open_document(FINANCE, doc_id, epoch)
    try:
        ctx.bob.search(MEDICAL, "allergy")
        denied = "Unexpected: the Medical search was not refused."
    except AccessDenied as exc:
        denied = explain_full(exc).what
    return p(f"Bob opened document {doc_id}. His app fetched the locked box, checked Alice's stamp on it, and unlocked it with the Finance key:",
             f"<blockquote><b>{esc(doc.title)}</b><br>{esc(doc.text)}</blockquote>",
             "Then Bob tried to search <b>Medical</b> for 'allergy'. The answer:",
             f"<blockquote>{esc(denied)}</blockquote>",
             "Why: Alice never gave Bob the Medical key. Without it his app cannot even compute where to look, the cloud would "
             "refuse a request outside his permission, and a Medical box would stay random bytes even if someone handed it to him.")


def do_update(ctx: Ctx) -> str:
    owner = ctx.owner
    before = ctx.session.cloud_admin("stats")["entries"]
    docs = owner.documents(FINANCE)
    notes = []
    if not any(d["title"] == NEW_DOC[0] for d in docs):
        owner.add_document(FINANCE, *NEW_DOC)
        notes.append(f"added '{NEW_DOC[0]}'")
    old = next((d for d in docs if d["title"] == DELETED_TITLE), None)
    if old is not None:
        owner.delete_document(FINANCE, old["id"])
        notes.append(f"deleted '{DELETED_TITLE}'")
    if owner.overview(FINANCE)["dirty"]:
        owner.publish(FINANCE)
    after = ctx.session.cloud_admin("stats")["entries"]
    hits = len(_search(ctx).hits)
    return p(f"Alice changed Finance: {' and '.join(notes) or 'the change was already made'}. Then she published a new stamped summary.",
             f"The cloud now stores {after} index entries (before: {before}). Even the delete added entries: a delete is one more "
             "masked entry, so the cloud cannot tell which older entry it cancels.",
             f"Bob searched '{SEARCH_WORD}' again and now finds <b>{hits} documents</b>, including the new invoice.",
             f"<b>{term('forward-privacy', 'Forward privacy')}:</b> the new entries were stored at brand-new addresses. Bob's earlier "
             "search slip listed only the old addresses, so the cloud could not tell that the new document also contains "
             f"'{SEARCH_WORD}' until Bob searched again.",
             "This claim is measured by the project's test suite (tests/test_m2_protocol.py compares old slips with new entries).")


def do_revoke(ctx: Ctx) -> str:
    comparison = attacklab.collusion_demo()
    ctx.store.setdefault("outcomes", []).append(comparison)
    compare = "".join(f"<li>{esc(line)}</li>" for line in comparison.lines[1:3])
    bob_record = next((r for r in ctx.owner.receivers.values() if r["name"] == "bob"), None)
    if bob_record is not None and not bob_record["revoked"]:
        ctx.owner.revoke(ctx.bob.uid, "R")
    try:
        ctx.bob.search(FINANCE, SEARCH_WORD)
        refused = "Unexpected: Bob's search was still answered."
    except Rejected as exc:
        refused = explain_full(exc).what
    return p("First, a comparison on a <b>practice copy</b> (not on the lesson data). A doctor is revoked, keeps the old key, and "
             "teams up with the cloud:",
             f"<ul>{compare}</ul>",
             f"<b>{term('policy-r', 'Policy R')}</b> changes the key for everything written from now on. It is quick. Its honest limit: "
             "data from before the change is still locked with the old key, which the revoked doctor knows.",
             f"<b>{term('policy-re', 'Policy RE')}</b> also re-locks every existing document, and the cloud deletes the old copies. "
             "That closes the gap, but Alice must re-lock and re-stamp everything, which takes longer.",
             "Now on the lesson system: Alice revoked Bob with policy R. Bob searched again and got:",
             f"<blockquote>{esc(refused)}</blockquote>",
             f"Finance moved to a new {term('epoch', 'epoch')} with a new key. Doctors who stay would receive it in a sealed message. Bob did not.",
             "<i>Simplification: no policy can take back what a doctor already downloaded or remembers.</i>")


def do_attacks(ctx: Ctx) -> str:
    parts = []
    for key in ("replay", "modify"):
        outcome = attacklab.run_scenario(key)
        ctx.store.setdefault("outcomes", []).append(outcome)
        teach = attacklab.TEACH[key]
        parts.append(f"<p><b>{esc(outcome.title)}.</b> {esc(teach['tries'])}<br>"
                     f"Result: <b>{'caught' if outcome.passed else 'NOT caught'}</b>, by {esc(outcome.caught_by)}.<br>"
                     f"Without that check: {esc(teach['without'])}</p>")
    return p("Two attacks ran on a practice copy:") + "".join(parts) + p(
        "The Attack Lab tab has eleven of these. Each one shows what the attacker tried and which check stopped it.")


SUMMARY = (
    "<ul>"
    "<li><b>Alice</b> owns the documents. She locks them, builds a locked index, stamps everything, and decides who gets which key.</li>"
    "<li><b>Bob</b> searches with a sealed slip that does not contain the word, and his app checks every answer before showing it.</li>"
    "<li><b>The cloud</b> stores and looks up locked data. It sees sizes, counts, timing and which addresses are asked for, not words or text.</li>"
    "<li><b>Access is keys.</b> No key for a group means no search and no reading. Revoking means changing the locks: "
    "policy R for new data only, policy RE for everything.</li>"
    "<li><b>If the cloud cheats</b> (drops, changes, reorders, replays or serves old data), a check fails and nothing wrong is shown.</li>"
    "</ul>"
    "<p><b>Where to go next:</b> try the Challenges page, run the other attacks in the Attack Lab, open 'Who sees what', "
    "read docs/START_HERE.md and docs/concepts.md, or switch to Expert Mode in the toolbar to see every detail.</p>"
    "<p><i>Honest limits to remember: this is research software, not an audited product. \"Post-quantum\" means built on problems "
    "believed to be hard for quantum computers. The graphics chip only speeds up building the index, never the post-quantum steps.</i></p>")


def _has(ctx: Ctx, *names: str) -> bool:
    return ctx.owner is not None and all(name in ctx.owner.groups for name in names)


def _bob_record(ctx: Ctx) -> dict | None:
    if ctx.owner is None:
        return None
    return next((r for r in ctx.owner.receivers.values() if r["name"] == "bob"), None)


def _built(ctx: Ctx) -> bool:
    return _has(ctx, FINANCE, MEDICAL) and all(ctx.owner.documents(g) and not ctx.owner.overview(g)["dirty"]
                                               for g in (FINANCE, MEDICAL))


STEPS: list[Step] = [
    Step("meet", "Meet the three parties",
         f"<p style='font-size:12pt;'><i>{IDEA}</i></p>" + cast_html() + "<p><b>Think of it like this:</b></p>" + analogies_html()
         + p("The diagram on the right shows Alice, the doctors and the Cloud. During the lesson you will see packets "
             "travel between them. Nothing to do here: press <b>Next</b>.",
             "In this lesson every passphrase is the word <b>lesson</b>. The lesson uses its own practice area, so your own data is untouched.")),
    Step("cloud", "Start the cloud server",
         p("The Cloud is a rented storage company. Alice will keep everything there, because it is always online.",
           "But she does not trust it. It might peek, lie, drop results or send old data. So the cloud will only ever be given locked data.",
           "First it has to be switched on. In this app it is a separate program on your computer."),
         do_cloud, "cloud_tab", "start_button", "Type the passphrase 'lesson' and press Start server.",
         lambda ctx: ctx.session.cloud_running()),
    Step("setup", "Alice sets up her keys",
         p("Alice needs a way to prove that something really comes from her. She creates a <b>key pair</b>: "
           "a private key that only she holds, and a public key she can give to everyone.",
           f"With the private key she makes a {term('signature', 'signature')}, a tamper-proof stamp. With the public key anyone can check the stamp.",
           f"Why {term('post-quantum', 'post-quantum')}? Data stored today may still matter in twenty years. Some of today's locks could be "
           "broken by large quantum computers. This app uses newer standards that are built to resist them.",
           "Technical name: Setup."),
         do_setup, "owner_tab", "open_button",
         "Type the passphrase 'lesson' and press 'Open or create owner'. Then press 'Pair: import cloud key' and pick cloud.pqpub. "
         "On the Cloud tab press 'Pair: import owner key' and pick owner.pqpub.",
         lambda ctx: ctx.owner is not None and ctx.owner.cloud_pub is not None),
    Step("groups", "Alice creates two groups and picks documents",
         p(f"A hospital has different kinds of records. Alice makes a {term('group', 'group')} for each kind: "
           "<b>Finance</b> and <b>Medical</b>. Each group has its own secret key, like a folder with its own lock.",
           "Later she will give each doctor only the keys for the groups that doctor needs.",
           "This step also loads eight short, harmless demo documents on Alice's side."),
         do_groups, "owner_tab", "group_name", "Type Finance and press Create group. Do the same for Medical.",
         lambda ctx: _has(ctx, FINANCE, MEDICAL)),
    Step("join", "Bob asks to join, Alice approves him for Finance",
         p("Bob is a doctor who needs to look things up in Finance. He sends Alice a join request.",
           "Alice checks that the request is really from Bob's key, then decides what Bob may see. Here: Finance only.",
           f"She sends Bob an access pass ({term('capability', 'capability')}) sealed so only Bob can open it.",
           "Technical name: Join."),
         do_join, "receiver_tab", "user",
         "Type bob and the passphrase 'lesson', press Unlock or create, Pair devices, Send join request. "
         "On the Owner tab press Refresh join requests, Approve selected, and tick Finance only. Back here press Fetch mailbox.",
         lambda ctx: bool(_bob_record(ctx)) and _bob_record(ctx)["groups"] == [FINANCE]),
    Step("build", "Alice builds and publishes the searchable index",
         p("Now Alice locks the documents and sends them to the cloud. Each document goes into its own locked box "
           f"({term('ciphertext', 'ciphertext')}).",
           f"She also builds a locked {term('index', 'index')}: for every word, one entry at an address that looks random. "
           "This is what makes searching possible without unlocking anything.",
           "Finally she publishes a stamped summary of the index, so doctors can check that the cloud's answers are complete.",
           "Technical names: BuildIndex and Publish. This step can take a few seconds because every document gets its own stamp."),
         do_build, "owner_tab", "publish_button",
         "Select a group, use Add document (or Import files), then press Publish. Do this for Finance and Medical. "
         "'Do it for me' loads the eight demo documents instead.",
         _built),
    Step("search", "Bob searches for a word",
         p(f"Bob wants every Finance document that mentions <b>'{SEARCH_WORD}'</b>.",
           f"His app writes a sealed search slip ({term('token', 'token')}). The slip does not contain the word. "
           "It lists secret addresses that only someone with the Finance key can work out.",
           "The cloud looks up those addresses and returns what is stored there: scrambled entries.",
           "Technical names: TokenGen (Bob makes the slip) and Search (the cloud answers)."),
         do_search, "receiver_tab", "keyword", f"Choose the group Finance, type {SEARCH_WORD} and press Search.",
         lambda ctx: "verify" in ctx.seen),
    Step("verify", "Bob checks the answer",
         p("The cloud is not trusted. What if it left a result out, changed one, or sent an old answer?",
           "So Bob's app checks the answer against the summary that Alice stamped. Eight checks, each guarding against one kind of cheating.",
           "Only if all of them pass are the results shown. Technical name: Verify."),
         do_verify, "receiver_tab", "results", "Search again and read the Verification panel: each check shows the word OK.",
         lambda ctx: "verify" in ctx.seen),
    Step("decrypt", "Bob opens a document, and is refused another",
         p("Bob picks a result. His app fetches the locked box from the cloud, checks Alice's stamp on it, and unlocks it with the Finance key.",
           "Then we let Bob try something he is not allowed to do: search the Medical group.",
           "Technical name: Decrypt."),
         do_decrypt, "receiver_tab", "results", "Click a result to open it. Bob has only one group to choose, so use 'Do it for me' to see the refusal for Medical.",
         lambda ctx: "decrypt" in ctx.seen),
    Step("update", "Alice adds and deletes a document",
         p("Records change. Alice adds a new invoice and deletes the payroll note.",
           "Every change is numbered and stamped, so the cloud accepts only genuine changes, each exactly once, in order.",
           f"Two privacy points: new data cannot be linked to earlier searches ({term('forward-privacy', 'forward privacy')}), "
           f"and deleted documents stay hidden ({term('backward-privacy', 'backward privacy')}).",
           "Technical name: Update."),
         do_update, "owner_tab", "docs", "On the Owner tab select Finance, add a document, delete one, then press Publish.",
         lambda ctx: "update" in ctx.seen and _built(ctx)),
    Step("revoke", "Alice revokes Bob: policy R and policy RE",
         p(f"Bob leaves the hospital. Alice must take his access away ({term('revocation', 'revocation')}).",
           "Think of it as changing the locks and giving new keys only to the people still allowed in.",
           "There are two ways to do it, and they differ in an important, honest way. This step first compares both on a practice copy, "
           "then revokes Bob on the lesson system.",
           "Technical name: Revoke."),
         do_revoke, "owner_tab", "policy", "On the Owner tab select bob under Approved receivers, choose a policy and press Revoke selected receiver.",
         lambda ctx: bool(_bob_record(ctx)) and _bob_record(ctx)["revoked"]),
    Step("attacks", "Attack finale: cheating gets caught",
         p("Time to attack the system. Two attempts:",
           "1. An outsider records one of Alice's updates and sends it again (a replay).",
           "2. The cloud changes one entry in a search answer (tampering).",
           "Both run on a practice copy, so the lesson data stays clean."),
         do_attacks, "attack_tab", "table", "On the Attack Lab tab select an attack and press Run selected attack.",
         lambda ctx: "attack" in ctx.seen),
    Step("summary", "What you learned", SUMMARY),
]
