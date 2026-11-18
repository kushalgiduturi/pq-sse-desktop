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

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication

from pqsse import applog, attacklab, narrator, paths, pqbackend, roles
from pqsse import invite as invites
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


def _taught(fn: Callable) -> Callable:
    """Results shown in QML pass through the "Teaching names" filter (pqsse.roles)."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return roles.teach_all(fn(*args, **kwargs))
    return wrapper

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
    insightsChanged = Signal()
    welcomeRequested = Signal()
    updateChanged = Signal()
    namesChanged = Signal()              # the Teaching names option changed

    def __init__(self, session: Session | None = None, sync: bool = False, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.session = session or Session()
        roles.set_teaching(bool(self.session.settings.get("teaching_names", False)))
        self.runner = TaskRunner(self.session.lock, sync=sync, parent=self)
        self._sync = sync                        # tests: run in line, never start programs
        self.events = EventLog(self)
        self._state: dict = {}
        self._results: dict[str, dict] = {}
        self._opened: dict[str, dict] = {}
        self._story = {"line": T["storyIdle"], "role": ""}
        self._busy = (0, "")
        self._software = False
        self._role = ROLE_ALICE
        self._server_note: dict = {}
        self._last_invite: dict = {}
        self._keys_note = ""
        self._activity_note = ""
        self._last_action = time.monotonic()
        self._autolock = QTimer(self)
        self._autolock.setInterval(30_000)
        self._autolock.timeout.connect(self.autolockTick)
        if not sync:
            self._autolock.start()
        self._ctx = lesson.Ctx(self.session)
        self._lesson_html = ""
        self.last_error: dict | None = None
        self._task: dict = {}
        self._check: dict = {}
        self._outcomes: dict[str, attacklab.Outcome] = {}
        self._attacks_running: set[str] = set()
        self._gpu_report = ""
        self._log_tail = ""
        self._update: dict = {"status": "idle"}
        self.update_config = None                # tests set an update_check.Config here
        self._bench_build: list[dict] = []
        self._bench_ops: list[dict] = []
        self._bench_raw_build: list[dict] = []
        self._bench_raw_ops: list[dict] = []
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
        self._last_action = time.monotonic()
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
                    pending.append({"uid": request.uid, "name": request.name, "fingerprint": request.fingerprint,
                                    "words": invites.words(request.fingerprint), "invite": request.invite_name})
            except Exception:
                pending = []
        return {"open": True, "exists": True, "paired": owner.cloud_pub is not None,
                "fingerprint": owner.public_identity().fingerprint(), "groups": groups, "people": people, "pending": pending}

    def _receiver_states(self) -> list[dict]:
        out = []
        for name in self.session.receiver_names():
            rec = self.session.receivers.get(name)
            out.append({"name": name, "display": roles.display(name), "open": rec is not None,
                        "words": invites.words(rec.public_identity().fingerprint()) if rec is not None else "",
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

    # ------------------------------------------------------------------ mode of use (REALLIFE_PLAN milestone 3)
    @Property(str, notify=settingsChanged)
    def use(self) -> str:
        return self.session.use

    @Property(bool, notify=stateChanged)
    def remote(self) -> bool:
        return self.session.remote

    @Property("QVariantMap", notify=stateChanged)
    def server(self) -> dict:
        info = dict(self.session.settings.get("server") or {})
        info["connected"] = bool(info.get("host")) and self.session.cloud_running()
        info.update(self._server_note)
        return info

    @Slot(str)
    def setUse(self, use: str) -> None:
        if use == self.session.use:
            return
        self.session.set_use(use)
        self._results, self._opened, self._server_note = {}, {}, {}
        self._role = ROLE_ALICE if use != "receiver" else ""
        self.settingsChanged.emit()
        self.roleChanged.emit()
        self.refresh_now()

    @Slot(str, int, str, str)
    def connectServer(self, host: str, port: int, pin: str, server_fp: str) -> None:
        def work() -> dict:
            return self.session.connect_server(host, port, pin, server_fp)

        def done(info: dict) -> None:
            self._server_note = {"clock": info["clock"], "level": info["level"]}
        self._run("connectServer", "Connecting to the cloud server", work, after=done)

    @Property("QVariantMap", notify=stateChanged)
    def lastInvite(self) -> dict:
        return dict(self._last_invite)

    @Slot(str)
    def createInvite(self, name: str) -> None:
        def done(info: dict) -> None:
            self._last_invite = info
        self._run("createInvite", "Making an invite", lambda: self.session.create_invite(name), after=done)

    @Slot(str, str, str, str)
    def joinWithInvite(self, text: str, code: str, name: str, passphrase: str) -> None:
        def done(info: dict) -> None:
            self._role = info["name"].strip().lower()
            self.roleChanged.emit()
        self._run("joinWithInvite", "Joining with the invite", lambda: self.session.join_with_invite(text, code, name, passphrase),
                  after=done)

    @Property(bool, notify=namesChanged)
    def teachingNames(self) -> bool:
        return roles.teaching()

    @Slot(bool)
    def setTeachingNames(self, on: bool) -> None:
        """Journey option: show the lesson cast's names (Alice, Bob, Carol, Cloud) instead of the plain role names."""
        roles.set_teaching(bool(on))
        self._set("teaching_names", bool(on))
        self.namesChanged.emit()
        self.stateChanged.emit()
        self.lessonChanged.emit()
        self.challengesChanged.emit()
        self.labChanged.emit()

    @Slot(str, result=str)
    def displayName(self, uid: str) -> str:
        """The name to show for a role key or user id (plain, or the cast name with Teaching names on)."""
        return roles.display(uid)

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
        self._run("openOwner", "Unlocking the data owner's keys", lambda: self.session.open_owner(passphrase))

    @Slot()
    def pairOwnerAndCloud(self) -> None:
        def work() -> None:
            self.session.owner_pair_cloud()
            if not self.session.remote:          # networked: the server's operator installs owner.pqpub
                self.session.cloud_pair_owner()

        self._run("pairOwnerAndCloud", "Exchanging public keys", work)

    def _owner(self):
        if self.session.owner is None:
            raise PQSSEError("Unlock the data owner's keys first.")
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
            raise PQSSEError(f"Unlock {roles.display(name)}'s keys first.")
        return rec

    @Slot(str, str)
    def openReceiver(self, name: str, passphrase: str) -> None:
        clean = name.strip().lower()

        def after(_: Any) -> None:
            self._role = clean or self._role
            self.roleChanged.emit()

        self._run("openReceiver", "Unlocking the receiver's keys", lambda: self.session.open_receiver(clean, passphrase), after)

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
    @Property("QVariantList", notify=namesChanged)
    @_taught
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
    @_taught
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
            self.session.set_profile(self.session.own_profile)
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
        """Show the lesson's last verified search in Receiver A's cards and on the Stage."""
        result = self._ctx.store.get("result")
        if result is None:
            return
        self._results["receiver-a"] = {"group": result.group, "keyword": result.keyword, "entries": result.entries, "failed": False,
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
    @_taught
    def paletteItems(self) -> list[dict]:
        items = [{"id": "go:" + d["key"], "group": "Go to", "label": d["label"], "hint": d["hint"]} for d in DESTINATIONS]
        roles = [ROLE_ALICE] + [r["name"] for r in self._state.get("receivers", [])] + [ROLE_CLOUD]
        items += [{"id": "role:" + r, "group": "Work as", "label": r[:1].upper() + r[1:], "hint": "Open the Workspace as this role"}
                  for r in roles]
        items += [{"id": "inspect", "group": "Do", "label": T["inspectorOpen"], "hint": T["inspectorOpenHint"]},
                  {"id": "welcome", "group": "Do", "label": "Show the welcome screen and take the tour", "hint": T["welcomeIdea"]}]
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
        elif kind == "welcome":
            self._set("show_welcome", True)
            self.welcomeRequested.emit()
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
    @_taught
    def glossaryEntry(self, key: str) -> dict:
        entry = GLOSSARY.get(key)
        if entry is None:
            return {}
        return {"key": key, "name": entry.name, "plain": entry.plain, "more": entry.more, "simplification": entry.simplification}

    @Property(bool, notify=settingsChanged)
    def showWelcome(self) -> bool:
        return bool(self.session.settings.get("show_welcome", True))

    @Slot(bool)
    def dismissWelcome(self, start_lesson: bool) -> None:
        self._set("show_welcome", False)
        if start_lesson:
            self.setLessonStep(0)
            self.navigate.emit("journey")

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
    @_taught
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
            if where in ("alice", "cloud", "receiver-a"):
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
    @_taught
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
    @_taught
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
    @_taught
    def attacks(self) -> list[dict]:
        out = []
        for key, _, _, _ in attacklab.SCENARIOS:
            outcome = self._outcomes.get(key)
            record = roles.teach_all(inspector.build_attack(key, outcome))
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

    # ------------------------------------------------------------------ Insights: engine, benchmarks, settings, logs, About
    @Property(str, notify=settingsChanged)
    def engineMode(self) -> str:
        return self.session.settings.get("engine", "auto")

    @Slot(str)
    def setEngineMode(self, mode: str) -> None:
        if mode not in ("auto", "cpu", "gpu"):
            return
        self.session.settings["engine"] = mode
        self.session.save_settings()
        self.settingsChanged.emit()
        self.runner.run(lambda p: self.session.init_engine(), lambda _: self.stateChanged.emit(),
                        lambda exc: self.stateChanged.emit(), "Switching the engine", locked=False)

    @Property(str, notify=insightsChanged)
    def gpuReport(self) -> str:
        return self._gpu_report

    @Slot()
    def runGpuSelfTest(self) -> None:
        """The same report as python -m pqsse.gpu.selftest: GPU results compared byte for byte with hashlib and hmac."""
        def work(progress) -> str:
            import contextlib
            import io

            from pqsse.gpu import selftest

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                selftest.main()
            self.session.init_engine()
            return buffer.getvalue()

        def done(text: str) -> None:
            self._gpu_report = text
            self.insightsChanged.emit()
            self.stateChanged.emit()

        self.runner.run(work, done, lambda exc: done(f"The self-test could not run: {type(exc).__name__}: {exc}"),
                        "Running the GPU self-test", locked=False)

    @Property("QVariantList", notify=insightsChanged)
    def benchBuild(self) -> list[dict]:
        return self._bench_build

    @Property("QVariantList", notify=insightsChanged)
    def benchOps(self) -> list[dict]:
        return self._bench_ops

    @Property(str, notify=insightsChanged)
    def benchSummary(self) -> str:
        """One plain sentence about the measured BuildIndex numbers (shown first in Beginner mode)."""
        gpu_rows = [r for r in self._bench_build if r["gpu"]]
        if not self._bench_build:
            return ""
        if not gpu_rows:
            return T["benchNoGpu"]
        big = max(gpu_rows, key=lambda r: r["occurrences"])
        if big["total_speedup"] >= 1.0:
            return T["benchSummary"].format(n=f"{big['occurrences']:,}", prf=f"{big['prf_speedup']:.1f}", total=f"{big['total_speedup']:.2f}")
        return T["benchSummarySlower"].format(n=f"{big['occurrences']:,}", prf=f"{big['prf_speedup']:.1f}",
                                              cpu=f"{big['total_s'] * big['total_speedup']:.2f}", gpu=f"{big['total_s']:.2f}")

    @Slot(bool)
    def runBuildBenchmark(self, quick: bool) -> None:
        from pqsse import bench

        sizes = bench.BUILD_SIZES[:2] if quick else bench.BUILD_SIZES

        def done(rows: list[dict]) -> None:
            self._bench_raw_build = rows
            self._bench_build = [{"occurrences": int(r["occurrences"]), "engine": str(r["engine"]),
                                  "gpu": str(r["engine"]).upper().startswith("GPU"),
                                  "prf_s": float(r["prf_s"]), "symmetric_s": float(r["prf_s"] + r["chain_s"]),
                                  "total_s": float(r["total_s"]), "prf_speedup": float(r["prf_speedup"]),
                                  "symmetric_speedup": float(r["symmetric_speedup"]), "total_speedup": float(r["total_speedup"])}
                                 for r in rows]
            self.insightsChanged.emit()

        def work(progress) -> list[dict]:
            with narrator.scope("practice"):            # measured on a throwaway copy, not on the user's system
                return bench.run_build_benchmarks(sizes, progress)

        self.runner.run(work, done, self._insight_error,
                        "Measuring BuildIndex on the CPU and the GPU", locked=False)

    @Slot()
    def runOperationBenchmark(self) -> None:
        from pqsse import bench

        def done(rows: list[dict]) -> None:
            self._bench_raw_ops = rows
            self._bench_ops = [{"operation": str(r["operation"]), "params": f"{r['kem']} + {r['sig']}",
                                "ms": float(r["milliseconds"])} for r in rows]
            self.insightsChanged.emit()

        def work(progress) -> list[dict]:
            with narrator.scope("practice"):
                return bench.run_operation_benchmarks(progress=progress)

        self.runner.run(work, done, self._insight_error,
                        "Measuring the ten operations", locked=False)

    def _insight_error(self, exc: BaseException) -> None:
        friendly = explain_full(exc)
        self.last_error = {"what": friendly.what, "why": friendly.why, "next": friendly.next,
                           "technical": friendly.technical, "where": "insights"}
        self.failed.emit(self.last_error)

    @Slot(result=str)
    def exportBenchmarks(self) -> str:
        """Write the measured rows as CSV files into the data folder and return that folder."""
        from pqsse import bench

        folder = paths.base_dir() / "bench_results"
        folder.mkdir(parents=True, exist_ok=True)
        if self._bench_raw_build:
            bench.write_csv(folder / "buildindex.csv", self._bench_raw_build, bench.BUILD_COLUMNS)
        if self._bench_raw_ops:
            bench.write_csv(folder / "operations.csv", self._bench_raw_ops, bench.OPS_COLUMNS)
        return str(folder)

    # ------------------------------------------------------------------ export, import, activity (M6)
    @Property("QVariantMap", notify=stateChanged)
    def activity(self) -> dict:
        owner = self.session.owner
        if owner is None:
            return {"open": False, "rows": [], "check": "", "ok": True, "note": self._activity_note}
        rows = []
        for e in owner.activity(limit=100):
            parts = []
            for k, v in sorted(e["detail"].items()):
                if k in ("uid", "ids") or v in ("", [], None):
                    continue
                parts.append(f"{k} {', '.join(map(str, v)) if isinstance(v, list) else v}")
            rows.append({"n": e["n"], "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(e["t"] / 1000)),
                         "what": T.get("act_" + e["what"].replace(".", "_"), e["what"]),
                         "detail": roles.teach(", ".join(parts)),
                         "refused": e["server"] not in ("accepted", "duplicate"), "server": e["server"]})
        ok, check = owner.verify_activity()
        return {"open": True, "rows": rows, "check": check, "ok": ok, "note": self._activity_note}

    def _note_activity(self, template: str) -> Callable[[Any], None]:
        def after(result: Any) -> None:
            self._activity_note = template.format(**result) if isinstance(result, dict) else template.format(result=result)
        return after

    @Slot(str, str)
    def exportGroup(self, group: str, passphrase: str) -> None:
        self._run("exportGroup", "Exporting the group", lambda: self.session.export_group(group, passphrase),
                  after=self._note_activity(T["exportDone"]))

    @Slot(str, str, str)
    def importGroup(self, source: str, passphrase: str, group: str) -> None:
        source = QUrl(source).toLocalFile() if source.startswith("file:") else source
        self._run("importGroup", "Importing documents", lambda: self.session.import_group(source, passphrase, group),
                  after=self._note_activity(T["importDone"]))

    @Slot()
    def exportActivity(self) -> None:
        self._run("exportActivity", "Writing the activity log", self.session.export_activity,
                  after=self._note_activity(T["activityExported"]))

    # ------------------------------------------------------------------ keys: passphrase, backup, auto-lock (M5)
    @Property("QVariantMap", notify=stateChanged)
    def keys(self) -> dict:
        return {"open": self.session.keys_open(), "autolock": int(self.session.settings.get("autolock_minutes", 15)),
                "note": self._keys_note, "backend": pqbackend.backend_name(), "coverage": pqbackend.coverage(),
                "fallback": pqbackend.is_fallback()}

    def _keys_done(self, note: str) -> Callable[[Any], None]:
        def after(result: Any) -> None:
            self._keys_note = note.format(result=result)
        return after

    @Slot(str, str, str)
    def changePassphrase(self, role: str, old: str, new: str) -> None:
        self._run("changePassphrase", "Changing the passphrase", lambda: self.session.change_passphrase(role, old, new),
                  after=self._keys_done(T["keysChanged"].format(role=roles.display(role))))

    @Slot(str, str)
    def backupKeys(self, role: str, backup_passphrase: str) -> None:
        self._run("backupKeys", "Writing the key backup", lambda: self.session.backup_keys(role, backup_passphrase),
                  after=self._keys_done(T["keysBackedUp"]))

    @Slot(str, str, str)
    def importKeys(self, source: str, backup_passphrase: str, new_passphrase: str) -> None:
        source = QUrl(source).toLocalFile() if source.startswith("file:") else source
        self._run("importKeys", "Restoring keys from a backup",
                  lambda: self.session.import_keys(source.strip().strip('"'), backup_passphrase, new_passphrase),
                  after=self._keys_done(T["keysImported"]))

    @Slot()
    def lockKeys(self) -> None:
        self._run("lockKeys", "Locking the keys", lambda: ", ".join(map(roles.display, self.session.lock_keys())) or "none", after=self._keys_done(T["keysLocked"]))

    @Slot(int)
    def setAutolock(self, minutes: int) -> None:
        self.session.settings["autolock_minutes"] = max(0, min(int(minutes), 24 * 60))
        self.session.save_settings()
        self.stateChanged.emit()

    @Slot()
    def autolockTick(self) -> None:
        """Lock every open key store after the chosen number of minutes without an action (0 turns it off)."""
        minutes = int(self.session.settings.get("autolock_minutes", 15))
        if minutes <= 0 or self.runner_busy() or not self.session.keys_open():
            return
        if time.monotonic() - self._last_action >= minutes * 60:
            self.session.lock_keys()
            self._keys_note = T["keysAutoLocked"].format(minutes=minutes)
            self._state = self._snapshot()
            self.stateChanged.emit()

    def runner_busy(self) -> bool:
        return self._busy[0] > 0

    @Property("QVariantMap", notify=settingsChanged)
    def advanced(self) -> dict:
        s = self.session.settings
        return {"kem": s["kem"], "sig": s["sig"], "port": int(s["port"]), "ttl": float(s["state_ttl_hours"]),
                "kems": list(pqbackend.KEM_NAMES), "sigs": list(pqbackend.SIG_NAMES)}

    @Slot(str, str, int, float)
    def setAdvanced(self, kem: str, sig: str, port: int, ttl_hours: float) -> None:
        if kem in pqbackend.KEM_NAMES and sig in pqbackend.SIG_NAMES and 1024 <= int(port) <= 65535 and ttl_hours > 0:
            self.session.settings.update(kem=kem, sig=sig, port=int(port), state_ttl_hours=float(ttl_hours))
            self.session.save_settings()
            self.settingsChanged.emit()

    @Slot(str)
    def openFolder(self, which: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.folder(which)))

    @Property(str, notify=insightsChanged)
    def logTail(self) -> str:
        return self._log_tail

    @Slot()
    def refreshLog(self) -> None:
        try:
            lines = applog.log_file().read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        self._log_tail = "\n".join(lines[-40:])
        self.insightsChanged.emit()

    @Property("QVariantList", notify=stateChanged)
    def aboutRows(self) -> list[dict]:
        from ..about import info_rows

        return [{"label": label, "value": value} for label, value in info_rows(self.session)]

    @Property(str, constant=True)
    def licenses(self) -> str:
        from ..about import license_text

        return license_text()

    # ------------------------------------------------------------------ update check (only when asked)
    @Property("QVariantMap", notify=updateChanged)
    def updateState(self) -> dict:
        return {key: value for key, value in self._update.items() if key != "manifest"}

    @Property(bool, notify=settingsChanged)
    def updateMenu(self) -> bool:
        return bool(self.session.settings.get("update_menu", True))

    @Slot(bool)
    def setUpdateMenu(self, on: bool) -> None:
        self._set("update_menu", bool(on))

    def _set_update(self, state: dict) -> None:
        self._update = state
        self.updateChanged.emit()

    @Slot()
    def checkForUpdates(self) -> None:
        """Started by the user only. Reads the signed file list from the site once."""
        from .. import update_check

        if self._update.get("status") == "checking":
            return
        self._set_update({"status": "checking"})
        config = self.update_config
        self._run("update-check", T["updateChecking"], lambda: update_check.check(get_version(), config), self._set_update)

    @Slot()
    def openDownloadPage(self) -> None:
        page = self._update.get("download_page") or ""
        if page.startswith("https://"):
            QDesktopServices.openUrl(QUrl(page))

    @Slot()
    def runWebInstaller(self) -> None:
        """Downloads the web installer named in the signed file list, checks it, and starts it."""
        from .. import update_check

        manifest = self._update.get("manifest")
        if not manifest:
            return
        config = self.update_config
        state = dict(self._update)

        def fetch() -> dict:
            try:
                path = update_check.download_web_setup(manifest, paths.base_dir() / "downloads", config)
            except update_check.UpdateError as exc:
                return {**state, "status": "error", "message": str(exc)}
            return {**state, "status": "web_ready", "path": str(path)}

        def done(result: dict) -> None:
            self._set_update(result)
            if result.get("status") == "web_ready" and not self._sync:
                import os
                os.startfile(result["path"])  # noqa: S606  (the user asked for it; size, hash and signature were checked)

        self._set_update({**state, "status": "downloading"})
        self._run("update-web-setup", T["updateDownloading"], fetch, done)

    # ------------------------------------------------------------------ end
    def shutdown(self) -> None:
        self.runner.wait(5000)
        self.events.close()
        self.session.close()
        if self.session.profile:
            self.session.set_profile(self.session.own_profile)
