"""AppBridge: the one object QML talks to.

It wraps the existing Session (owner, receivers, cloud child process). State goes out as
plain properties (strings, numbers, lists and maps of those); actions come in as slots
and run on TaskRunner worker threads; results come back as a fresh state snapshot, as
narrator events in the EventLog, or as a three-part friendly error.

QML never computes protocol facts and never receives key material: the snapshot holds
names, counts, sizes, fingerprints (public), document text for the role that may read
it, and the stored ciphertext exactly as the cloud holds it.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication

from pqsse import attacklab, narrator, paths
from pqsse.core.errors import PQSSEError, VerifyError
from pqsse.owner import DocInput
from pqsse.version import get_version

from .. import challenges, lesson
from ..glossary import GLOSSARY
from ..session import LESSON_PASSPHRASE, LESSON_PROFILE, Session, explain_full
from ..workers import TaskRunner
from . import inspector
from . import settings as ui_settings
from .copy import CHALLENGE_HINTS, CHALLENGE_PLACES, DESTINATIONS, TRY, T
from .events import EventLog

log = logging.getLogger("pqsse.app")
ROLE_ALICE, ROLE_CLOUD = "alice", "cloud"
PEEK_ROWS = 6
LOG_ROWS = 30


class AppBridge(QObject):
    stateChanged = Signal()
    storyChanged = Signal()
    busyChanged = Signal()
    settingsChanged = Signal()
    lessonChanged = Signal()
    roleChanged = Signal()
    failed = Signal("QVariantMap")           # what, why, next, technical, where
    succeeded = Signal(str)                  # name of the action that finished
    navigate = Signal(str)                   # destination key
    glossaryRequested = Signal("QVariantMap")
    inspectRequested = Signal(int)           # index into the event log
    labChanged = Signal()
    challengesChanged = Signal()
    attackFinished = Signal(str)

    def __init__(self, session: Session | None = None, sync: bool = False, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.session = session or Session()
        self.runner = TaskRunner(self.session.lock, sync=sync, parent=self)
        self.events = EventLog(self)
        self._state: dict = {}
        self._results: dict[str, dict] = {}
        self._opened: dict[str, dict] = {}
        self._story = {"line": T["storyIdle"], "role": ""}
        self._busy = (0, "")
        self._software = False
        self._role = ROLE_ALICE
        self._ctx = lesson.Ctx(self.session)
        self._lesson_html = ""
        self.last_error: dict | None = None
        self._task: dict = {}
        self._check: dict = {}
        self._outcomes: dict[str, attacklab.Outcome] = {}
        self._attacks_running: set[str] = set()
        self.events.added.connect(self._on_record)
        self.runner.busy.connect(self._on_busy)
        self._state = self._snapshot()
        self.runner.run(lambda p: self.session.init_engine(), lambda _: self.stateChanged.emit(),
                        lambda exc: self.stateChanged.emit(), "", locked=False)

    # ------------------------------------------------------------------ plumbing
    def _on_record(self, record: dict) -> None:
        self._ctx.seen.add(record["kind"])
        self._update_challenges()
        if record.get("scope") == "practice" and record["kind"] != "attack":
            return                      # a throwaway copy is at work: the Story bar keeps describing the real system
        role = {"alice": "alice", "cloud": "cloud", "security": "security"}.get(record["tag"], (record["who"] or "").lower())
        if record["kind"] == "verify":
            role = "passed"                 # a passed check must not look like an alarm
        self._story = {"line": record["line"], "role": role}
        self.storyChanged.emit()

    def _on_busy(self, count: int, label: str) -> None:
        self._busy = (count, label)
        self.busyChanged.emit()

    def _run(self, name: str, label: str, fn: Callable[[], Any], after: Callable[[Any], None] | None = None) -> None:
        """Run an action on a worker thread, then publish a fresh snapshot or a friendly error."""
        first = self.events.count
        started = time.perf_counter()

        def work(progress) -> tuple[Any, dict]:
            result = fn()
            return result, self._snapshot()

        def done(payload: tuple[Any, dict]) -> None:
            result, snapshot = payload
            self.events.set_duration(first, (time.perf_counter() - started) * 1000.0)
            self._state = snapshot
            if after is not None:
                after(result)
            self._update_challenges()
            self.stateChanged.emit()
            self.succeeded.emit(name)

        def error(exc: BaseException) -> None:
            friendly = explain_full(exc)
            log.warning("Step failed (%s): %s", name, friendly.technical.splitlines()[0] if friendly.technical else friendly.what)
            self.last_error = {"what": friendly.what, "why": friendly.why, "next": friendly.next,
                               "technical": friendly.technical, "where": name}
            if isinstance(exc, VerifyError) and getattr(exc, "report", None) is not None and name.startswith("search:"):
                who = name.split(":", 1)[1]
                self._results[who] = {"group": "", "keyword": "", "hits": [], "failed": True,
                                      "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in exc.report.checks]}
            self.refresh_now()
            self.failed.emit(self.last_error)

        self.runner.run(work, done, error, label)

    def refresh_now(self) -> None:
        """Take a snapshot on this thread (used after errors and by tests)."""
        with self.session.lock:
            self._state = self._snapshot()
        self.stateChanged.emit()

    # ------------------------------------------------------------------ snapshot
    def _snapshot(self) -> dict:
        s = self.session
        running = s.cloud_running()
        return {"owner": self._owner_state(running), "receivers": self._receiver_states(),
                "cloud": self._cloud_state(running), "practice": s.profile == LESSON_PROFILE}

    def _owner_state(self, cloud_running: bool) -> dict:
        s = self.session
        owner = s.owner
        if owner is None:
            return {"open": False, "exists": s.owner_exists(), "paired": False, "fingerprint": "", "groups": [],
                    "people": [], "pending": []}
        now = time.time()
        groups = []
        for name in sorted(owner.groups):
            view = owner.overview(name)
            left = view["expires"] - now
            groups.append({"name": name, "epoch": view["epoch"], "version": view["version"], "dirty": bool(view["dirty"]),
                           "entries": sum(seg["entries"] for seg in view["segments"]),
                           "freshHours": round(max(0.0, left) / 3600.0, 1), "expired": left <= 0 < view["expires"],
                           "docs": [{"id": d["id"], "title": d["title"], "text": d["text"], "epoch": d["epoch"]}
                                    for d in owner.documents(name)]})
        people = [{"uid": uid, "name": r["name"], "groups": list(r["groups"]), "revoked": bool(r["revoked"])}
                  for uid, r in owner.receivers.items()]
        pending = []
        if cloud_running and owner.cloud_pub is not None:
            try:
                for item in owner.pending_joins():
                    try:
                        request = owner.check_join(item)
                    except PQSSEError:
                        continue
                    pending.append({"uid": request.uid, "name": request.name, "fingerprint": request.fingerprint})
            except Exception:
                pending = []
        return {"open": True, "exists": True, "paired": owner.cloud_pub is not None,
                "fingerprint": owner.public_identity().fingerprint(), "groups": groups, "people": people, "pending": pending}

    def _receiver_states(self) -> list[dict]:
        out = []
        for name in self.session.receiver_names():
            rec = self.session.receivers.get(name)
            out.append({"name": name, "display": name[:1].upper() + name[1:], "open": rec is not None,
                        "paired": bool(rec and rec.paired), "joined": bool(rec and rec.joined),
                        "groups": list(rec.groups) if rec is not None and rec.joined else [],
                        "result": self._results.get(name, {}), "opened": self._opened.get(name, {})})
        return out

    def _cloud_state(self, running: bool) -> dict:
        state = {"running": running, "line": self.session.cloud_line if running else "", "port": self.session.port,
                 "docs": 0, "entries": 0, "requests": 0, "storedDocs": [], "storedEntries": [], "log": []}
        if not running:
            return state
        try:
            stats = self.session.cloud_admin("stats")
            peek = self.session.cloud_admin("peek")
            rows = self.session.cloud_admin("log", {"since": max(0, stats["requests"] - LOG_ROWS)})
        except Exception:
            return state
        state.update(docs=stats["docs"], entries=stats["entries"], requests=stats["requests"])
        state["storedDocs"] = [{"hex": str(d[3])[:96], "bytes": int(d[4])} for d in peek["docs"][:PEEK_ROWS]]
        state["storedEntries"] = [{"address": str(e[2])[:32], "value": str(e[3])} for e in peek["entries"][:PEEK_ROWS]]
        state["log"] = [{"time": time.strftime("%H:%M:%S", time.localtime(int(r[1]) / 1000.0)), "endpoint": str(r[2]),
                         "bytesIn": int(r[3]), "bytesOut": int(r[4])} for r in rows][::-1]
        return state

    # ------------------------------------------------------------------ properties: state
    @Property("QVariantMap", notify=stateChanged)
    def state(self) -> dict:
        return self._state

    @Property(bool, notify=stateChanged)
    def cloudRunning(self) -> bool:
        return bool(self._state.get("cloud", {}).get("running"))

    @Property(bool, notify=stateChanged)
    def practice(self) -> bool:
        return self.session.profile == LESSON_PROFILE

    @Property(str, notify=stateChanged)
    def engine(self) -> str:
        if self.session.gpu is None:
            return ""
        return "GPU" if self.session.prf.uses_gpu else "CPU"

    @Property(str, notify=stateChanged)
    def engineDetail(self) -> str:
        return self.session.engine_text()

    @Property(str, notify=stateChanged)
    def backend(self) -> str:
        return self.session.header_text()

    @Property(str, constant=True)
    def version(self) -> str:
        return get_version()

    @Property("QVariantMap", notify=storyChanged)
    def story(self) -> dict:
        return self._story

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy[0] > 0

    @Property(str, notify=busyChanged)
    def busyLabel(self) -> str:
        return self._busy[1] if self._busy[0] > 0 else ""

    @Property(str, notify=roleChanged)
    def role(self) -> str:
        return self._role

    @Slot(str)
    def setRole(self, role: str) -> None:
        self._role = role.strip().lower() or ROLE_ALICE
        self.roleChanged.emit()

    # ------------------------------------------------------------------ properties: settings
    @Property(str, notify=settingsChanged)
    def theme(self) -> str:
        return self.session.settings.get("theme", "system")

    @Property(bool, notify=settingsChanged)
    def dark(self) -> bool:
        theme = self.theme
        return ui_settings.windows_prefers_dark() if theme == "system" else theme == "dark"

    @Property(bool, notify=settingsChanged)
    def reduceMotionSetting(self) -> bool:
        return bool(self.session.settings.get("reduce_motion"))

    @Property(bool, notify=settingsChanged)
    def reduceMotion(self) -> bool:
        return self.reduceMotionSetting or self._software or not ui_settings.windows_animations_enabled()

    @Property(str, notify=settingsChanged)
    def motionReason(self) -> str:
        if self._software:
            return T["settingsMotionSoftware"]
        if not ui_settings.windows_animations_enabled():
            return T["settingsMotionWindows"]
        return ""

    @Property(bool, notify=settingsChanged)
    def software(self) -> bool:
        return self._software

    @Property(str, notify=settingsChanged)
    def textSize(self) -> str:
        return self.session.settings.get("font_size", "normal")

    @Property(float, notify=settingsChanged)
    def textScale(self) -> float:
        return ui_settings.TEXT_SCALES.get(self.textSize, 1.0)

    @Property(str, notify=settingsChanged)
    def mode(self) -> str:
        return self.session.settings.get("mode", "beginner")

    @Property(int, notify=settingsChanged)
    def detailLevel(self) -> int:
        return int(self.session.settings.get("detail_level", 1))

    def _set(self, key: str, value: Any) -> None:
        self.session.settings[key] = value
        self.session.save_settings()
        self.settingsChanged.emit()

    @Slot(str)
    def setTheme(self, theme: str) -> None:
        if theme in ui_settings.THEMES:
            self._set("theme", theme)

    @Slot(bool)
    def setReduceMotion(self, on: bool) -> None:
        self._set("reduce_motion", bool(on))

    @Slot(str)
    def setTextSize(self, size: str) -> None:
        if size in ui_settings.TEXT_SCALES:
            self._set("font_size", size)

    @Slot(str)
    def setMode(self, mode: str) -> None:
        if mode in ("beginner", "expert"):
            self._set("mode", mode)

    @Slot(int)
    def setDetailLevel(self, level: int) -> None:
        self._set("detail_level", max(0, min(3, int(level))))

    @Slot(bool)
    def setSoftware(self, software: bool) -> None:
        """Called by QML once it knows which renderer is in use."""
        if software != self._software:
            self._software = bool(software)
            self.settingsChanged.emit()

    # ------------------------------------------------------------------ actions: cloud
    @Slot(str)
    def startCloud(self, passphrase: str) -> None:
        self._run("startCloud", "Starting the cloud", lambda: self.session.start_cloud(passphrase))

    @Slot()
    def stopCloud(self) -> None:
        self._run("stopCloud", "Stopping the cloud", self.session.stop_cloud)

    @Slot()
    def refresh(self) -> None:
        self._run("refresh", "", lambda: None)

    # ------------------------------------------------------------------ actions: Alice
    @Slot(str)
    def openOwner(self, passphrase: str) -> None:
        self._run("openOwner", "Unlocking Alice's keys", lambda: self.session.open_owner(passphrase))

    @Slot()
    def pairOwnerAndCloud(self) -> None:
        def work() -> None:
            self.session.owner_pair_cloud()
            self.session.cloud_pair_owner()

        self._run("pairOwnerAndCloud", "Exchanging public keys", work)

    def _owner(self):
        if self.session.owner is None:
            raise PQSSEError("Unlock Alice's keys first.")
        return self.session.owner

    @Slot(str)
    def createGroup(self, name: str) -> None:
        def work() -> None:
            if not name.strip():
                raise PQSSEError("Type a group name first.")
            self._owner().create_group(name.strip())

        self._run("createGroup", "Creating the group", work)

    @Slot(str, str, str)
    def addDocument(self, group: str, title: str, text: str) -> None:
        def work() -> None:
            if not text.strip():
                raise PQSSEError("Type the text of the document first.")
            self._owner().add_document(group, title.strip() or "untitled", text)

        self._run("addDocument", "Locking and uploading the document", work)

    @Slot(str, "QVariantList")
    def importDocuments(self, group: str, urls: list) -> None:
        def work() -> int:
            from ..common import read_document_file

            docs = []
            for url in urls:
                path = QUrl(url).toLocalFile() if str(url).startswith("file:") else str(url)
                title, text = read_document_file(path)
                if text:
                    docs.append(DocInput(title, text))
            if not docs:
                raise PQSSEError("None of the chosen files contained text.")
            self._owner().build_index(group, docs)
            return len(docs)

        self._run("importDocuments", "Locking and uploading the documents", work)

    @Slot(str, int)
    def deleteDocument(self, group: str, doc_id: int) -> None:
        self._run("deleteDocument", "Deleting the document", lambda: self._owner().delete_document(group, int(doc_id)))

    @Slot(str, int, str, str)
    def editDocument(self, group: str, doc_id: int, title: str, text: str) -> None:
        self._run("editDocument", "Replacing the document",
                  lambda: self._owner().edit_document(group, int(doc_id), title.strip() or "untitled", text))

    @Slot(str)
    def publish(self, group: str) -> None:
        self._run("publish", "Publishing the stamped summary", lambda: self._owner().publish(group))

    @Slot(str, "QVariantList")
    def approveJoin(self, uid: str, groups: list) -> None:
        def work() -> None:
            chosen = [str(g) for g in groups]
            if not chosen:
                raise PQSSEError("Tick at least one group for this person.")
            owner = self._owner()
            for item in owner.pending_joins():
                try:
                    request = owner.check_join(item)
                except PQSSEError:
                    continue
                if request.uid == uid:
                    owner.approve_join(item, chosen)
                    return
            raise PQSSEError("That request is no longer waiting. Look for new requests.")

        self._run("approveJoin", "Approving the request", work)

    @Slot(str, str)
    def revoke(self, uid: str, policy: str) -> None:
        self._run("revoke", "Taking away access and changing the locks",
                  lambda: self._owner().revoke(uid, "RE" if policy.upper() == "RE" else "R"))

    # ------------------------------------------------------------------ actions: doctors
    def _receiver(self, name: str):
        rec = self.session.receivers.get(name)
        if rec is None:
            raise PQSSEError(f"Unlock {name[:1].upper() + name[1:]}'s keys first.")
        return rec

    @Slot(str, str)
    def openReceiver(self, name: str, passphrase: str) -> None:
        clean = name.strip().lower()

        def after(_: Any) -> None:
            self._role = clean or self._role
            self.roleChanged.emit()

        self._run("openReceiver", "Unlocking the doctor's keys", lambda: self.session.open_receiver(clean, passphrase), after)

    @Slot(str)
    def pairReceiver(self, name: str) -> None:
        def work() -> None:
            self._receiver(name)
            self.session.receiver_pair(name)

        self._run("pairReceiver", "Importing the public keys", work)

    @Slot(str)
    def sendJoin(self, name: str) -> None:
        self._run("sendJoin", "Sending the join request", lambda: self._receiver(name).send_join())

    @Slot(str)
    def fetchMail(self, name: str) -> None:
        self._run("fetchMail", "Fetching the mailbox", lambda: self._receiver(name).fetch_mail())

    @Slot(str, str, str)
    def search(self, name: str, group: str, keyword: str) -> None:
        def work() -> None:
            if not keyword.strip():
                raise PQSSEError("Type a word to search for.")
            result = self._receiver(name).search(group, keyword.strip())
            self._results[name] = {"group": result.group, "keyword": result.keyword, "entries": result.entries, "failed": False,
                                   "hits": [{"id": doc_id, "epoch": epoch} for doc_id, epoch in result.hits],
                                   "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in result.report.checks]}
            self._opened.pop(name, None)

        self._run("search:" + name, "Searching", work)

    @Slot(str, str, int, int)
    def openDocument(self, name: str, group: str, doc_id: int, epoch: int) -> None:
        def work() -> None:
            doc = self._receiver(name).open_document(group, int(doc_id), int(epoch))
            self._opened[name] = {"id": doc.doc_id, "title": doc.title, "text": doc.text, "group": group}

        self._run("openDocument", "Opening the document", work)

    # ------------------------------------------------------------------ lesson (Journey, and "Play the story" on the Stage)
    @Property("QVariantList", constant=True)
    def lessonSteps(self) -> list[dict]:
        return [{"key": step.key, "title": step.title, "explain": step.explain, "runnable": step.do is not None}
                for step in lesson.STEPS]

    @Property(int, notify=lessonChanged)
    def lessonStep(self) -> int:
        return max(0, min(len(lesson.STEPS) - 1, int(self.session.settings.get("lesson_step", 0))))

    @Property("QVariantList", notify=lessonChanged)
    def lessonDone(self) -> list:
        return list(self.session.settings.get("lesson_done", []))

    @Property(str, notify=lessonChanged)
    def lessonResult(self) -> str:
        return self._lesson_html

    @Slot(int)
    def setLessonStep(self, index: int) -> None:
        self.session.settings["lesson_step"] = max(0, min(len(lesson.STEPS) - 1, int(index)))
        self.session.save_settings()
        self._lesson_html = ""
        self.lessonChanged.emit()

    def _enter_practice(self) -> None:
        if self.session.profile != LESSON_PROFILE:
            self.session.set_profile(LESSON_PROFILE)
            self._results.clear()
            self._opened.clear()

    @Slot()
    def enterPractice(self) -> None:
        self._run("enterPractice", "Opening the practice area", self._enter_practice)

    @Slot()
    def leavePractice(self) -> None:
        def work() -> None:
            self.session.set_profile("")
            self._results.clear()
            self._opened.clear()

        self._run("leavePractice", "Going back to your own data", work)

    @Slot(int)
    def runLessonStep(self, index: int) -> None:
        """Run one lesson step on the real system, in the practice area."""
        index = max(0, min(len(lesson.STEPS) - 1, int(index)))
        step = lesson.STEPS[index]

        def work() -> str:
            self._enter_practice()
            lesson.ensure(self._ctx, index + 1)
            html = step.do(self._ctx) if step.do is not None else ""
            self._remember_lesson_search()
            return html

        def after(html: str) -> None:
            done = set(self.session.settings.get("lesson_done", []))
            done.add(step.key)
            self.session.settings["lesson_done"] = sorted(done)
            self.session.settings["lesson_step"] = index
            self.session.save_settings()
            self._lesson_html = html or ""
            self.lessonChanged.emit()

        self._run("lesson:" + step.key, step.title, work, after)

    def _remember_lesson_search(self) -> None:
        """Show the lesson's last verified search in Bob's cards and on the Stage."""
        result = self._ctx.store.get("result")
        if result is None:
            return
        self._results["bob"] = {"group": result.group, "keyword": result.keyword, "entries": result.entries, "failed": False,
                                "hits": [{"id": doc_id, "epoch": epoch} for doc_id, epoch in result.hits],
                                "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in result.report.checks]}

    @Slot()
    def resetLesson(self) -> None:
        def work() -> None:
            self.session.reset_lesson()
            self._ctx.store.clear()
            self._ctx.seen.clear()
            self._results.clear()
            self._opened.clear()

        def after(_: Any) -> None:
            self._lesson_html = ""
            self.events.clear()
            self.lessonChanged.emit()

        self._run("resetLesson", "Resetting the lesson", work, after)

    @Property(str, constant=True)
    def lessonPassphrase(self) -> str:
        return LESSON_PASSPHRASE

    # ------------------------------------------------------------------ palette, glossary, clipboard, folders
    @Property("QVariantList", notify=stateChanged)
    def paletteItems(self) -> list[dict]:
        items = [{"id": "go:" + d["key"], "group": "Go to", "label": d["label"], "hint": d["hint"]} for d in DESTINATIONS]
        roles = [ROLE_ALICE] + [r["name"] for r in self._state.get("receivers", [])] + [ROLE_CLOUD]
        items += [{"id": "role:" + r, "group": "Work as", "label": r[:1].upper() + r[1:], "hint": "Open the Workspace as this role"}
                  for r in roles]
        items += [{"id": "inspect", "group": "Do", "label": T["inspectorOpen"], "hint": T["inspectorOpenHint"]}]
        items += [{"id": f"lesson:{i}", "group": "Lesson step", "label": f"{i + 1}. {s.title}", "hint": "Open this step in Journey"}
                  for i, s in enumerate(lesson.STEPS)]
        items += [{"id": "set:theme:" + t, "group": "Setting", "label": "Theme: " + T["theme" + t.capitalize()], "hint": ""}
                  for t in ui_settings.THEMES]
        items += [{"id": "set:motion:" + v, "group": "Setting", "label": "Reduce motion: " + v, "hint": T["settingsMotionNote"]}
                  for v in ("on", "off")]
        items += [{"id": "set:text:" + s, "group": "Setting", "label": "Text size: " + T["text" + s.capitalize()], "hint": ""}
                  for s in ui_settings.TEXT_SCALES]
        items += [{"id": "set:mode:" + m, "group": "Setting", "label": T["mode" + m.capitalize()], "hint": ""}
                  for m in ("beginner", "expert")]
        items += [{"id": "glossary:" + key, "group": "Glossary", "label": entry.name, "hint": entry.plain}
                  for key, entry in sorted(GLOSSARY.items(), key=lambda kv: kv[1].name.lower())]
        return items

    @Slot(str)
    def runPalette(self, item: str) -> None:
        kind, _, rest = item.partition(":")
        if kind == "go":
            self.navigate.emit(rest)
        elif kind == "role":
            self.setRole(rest)
            self.navigate.emit("workspace")
        elif kind == "inspect":
            self.inspectRequested.emit(self.events.count - 1)
        elif kind == "lesson":
            self.setLessonStep(int(rest))
            self.navigate.emit("journey")
        elif kind == "glossary":
            self.glossaryRequested.emit(self.glossaryEntry(rest))
        elif kind == "set":
            name, _, value = rest.partition(":")
            {"theme": self.setTheme, "text": self.setTextSize, "mode": self.setMode,
             "motion": lambda v: self.setReduceMotion(v == "on")}[name](value)

    @Slot(str, result="QVariantMap")
    def glossaryEntry(self, key: str) -> dict:
        entry = GLOSSARY.get(key)
        if entry is None:
            return {}
        return {"key": key, "name": entry.name, "plain": entry.plain, "more": entry.more, "simplification": entry.simplification}

    @Slot(str)
    def copyText(self, text: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    @Slot(str, result=str)
    def folder(self, which: str) -> str:
        return str(paths.logs_dir() if which == "logs" else paths.base_dir())

    # ------------------------------------------------------------------ Journey: let me try, check my work, challenges
    @Property("QVariantMap", notify=lessonChanged)
    def task(self) -> dict:
        """The "Let me try" task that is open right now: {step, title, text}, or empty."""
        return self._task

    @Slot(int)
    def tryLessonStep(self, index: int) -> None:
        """Send the learner to the place where this step is done by hand, in the practice area."""
        index = max(0, min(len(lesson.STEPS) - 1, int(index)))
        step = lesson.STEPS[index]
        where, text = TRY.get(step.key, ("journey", ""))

        def work() -> None:
            self._enter_practice()
            lesson.ensure(self._ctx, index)             # everything the earlier steps built

        def after(_: Any) -> None:
            self._task = {"step": index, "title": step.title, "text": text}
            self._check = {}
            self.lessonChanged.emit()
            if where in ("alice", "cloud", "bob"):
                self.setRole(where)
                self.navigate.emit("workspace")
            else:
                self.navigate.emit(where)

        self._run("try:" + step.key, "Getting the practice area ready", work, after)

    @Slot()
    def clearTask(self) -> None:
        self._task = {}
        self.lessonChanged.emit()

    @Property("QVariantMap", notify=lessonChanged)
    def lessonCheck(self) -> dict:
        """Result of the last "Check my work": {step, ok, text}, or empty."""
        return self._check

    @Slot(int)
    def checkLessonStep(self, index: int) -> None:
        index = max(0, min(len(lesson.STEPS) - 1, int(index)))
        step = lesson.STEPS[index]
        try:
            with self.session.lock:
                ok = bool(step.check(self._ctx)) if step.check is not None else True
        except Exception:
            ok = False
        if ok:
            done = set(self.session.settings.get("lesson_done", []))
            done.add(step.key)
            self.session.settings["lesson_done"] = sorted(done)
            self.session.save_settings()
            self._task = {}
        self._check = {"step": index, "ok": ok, "text": T["checkYes"] if ok else T["checkNo"]}
        self.lessonChanged.emit()

    def _update_challenges(self) -> None:
        saved = set(self.session.settings.get("challenges_done", []))
        if not self.session.lock.acquire(blocking=False):
            return                      # a worker is busy: checked again when it finishes
        try:
            now = challenges.completed(self.session, self.events.raw)
        finally:
            self.session.lock.release()
        if not now <= saved:
            self.session.settings["challenges_done"] = sorted(saved | now)
            self.session.save_settings()
            self.challengesChanged.emit()

    @Property("QVariantList", notify=challengesChanged)
    def challengeList(self) -> list[dict]:
        done = set(self.session.settings.get("challenges_done", []))
        return [{"key": c.key, "title": c.title, "task": c.task, "hint": CHALLENGE_HINTS.get(c.key, ""),
                 "where": CHALLENGE_PLACES.get(c.key, "workspace"), "done": c.key in done} for c in challenges.CHALLENGES]

    @Slot()
    def resetChallenges(self) -> None:
        self.session.settings["challenges_done"] = []
        self.session.save_settings()
        self.challengesChanged.emit()

    @Slot()
    def noteCloudView(self) -> None:
        """The learner looked through the cloud's eyes at real stored data (Stage lens)."""
        stored = self._state.get("cloud", {}).get("storedDocs", [])
        if stored:
            narrator.emit("cloud_view", "Cloud", bytes=int(stored[0]["bytes"]))

    # ------------------------------------------------------------------ Security Lab
    @Property("QVariantList", notify=labChanged)
    def attacks(self) -> list[dict]:
        out = []
        for key, _, _, _ in attacklab.SCENARIOS:
            outcome = self._outcomes.get(key)
            record = inspector.build_attack(key, outcome)
            record.update(key=key, ran=outcome is not None, lines=list(outcome.lines) if outcome else [],
                          caughtBy=outcome.caught_by if outcome else "", verdict=outcome.verdict if outcome else "",
                          tries=attacklab.TEACH[key]["tries"], without=attacklab.TEACH[key]["without"],
                          running=key in self._attacks_running)
            out.append(record)
        return out

    @Slot(str)
    def runAttack(self, key: str) -> None:
        """Run one attack on a throwaway copy of the system (never on the user's data)."""
        if key not in attacklab.TEACH or key in self._attacks_running:
            return
        self._attacks_running.add(key)
        self.labChanged.emit()

        def done(outcome: attacklab.Outcome) -> None:
            self._attacks_running.discard(key)
            self._outcomes[key] = outcome
            narrator.emit("attack", "", key=outcome.key, title=outcome.title, ok=outcome.passed,
                          result="caught" if outcome.passed else "NOT caught", caught_by=outcome.caught_by or "nothing")
            self.labChanged.emit()
            self.attackFinished.emit(key)

        def error(exc: BaseException) -> None:
            self._attacks_running.discard(key)
            self.labChanged.emit()
            friendly = explain_full(exc)
            self.last_error = {"what": friendly.what, "why": friendly.why, "next": friendly.next,
                               "technical": friendly.technical, "where": "attack:" + key}
            self.failed.emit(self.last_error)

        self.runner.run(lambda progress: attacklab.run_scenario(key), done, error, "Trying the attack on a practice copy", locked=False)

    # ------------------------------------------------------------------ end
    def shutdown(self) -> None:
        self.runner.wait(5000)
        self.events.close()
        self.session.close()
        if self.session.profile:
            self.session.set_profile("")
