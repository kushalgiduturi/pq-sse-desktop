"""Application session: the non-GUI controller behind the window.

It owns the three role objects the user is acting as (owner, receivers) and the handle
of the cloud child process. The roles never share memory with the cloud: everything
goes through HttpCloud to the separate process on 127.0.0.1.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pqsse import narrator, paths, pqbackend
from pqsse.core.errors import AccessDenied, BadPassphrase, PQSSEError, Rejected, VerifyError
from pqsse.core import fileperm
from pqsse.core.keystore import Vault, import_backup
from pqsse.core.pairing import PublicIdentity, export_pub, import_pub
from pqsse.gpu import get_prf, status
from pqsse.gpu.batchprf import BatchPRF, CpuPRF
from pqsse.owner import Owner
from pqsse.pqbackend import Params
from pqsse.receiver import Receiver, describe_rejection
from pqsse import invite as invites
from pqsse.transport import CloudUnavailable, HttpCloud, HttpsCloud, clock_skew

from . import winjob

log = logging.getLogger("pqsse.app")

DEFAULTS = {"kem": "ML-KEM-768", "sig": "ML-DSA-65", "port": 8765, "engine": "auto", "state_ttl_hours": 24,
            "mode": "expert", "show_welcome": True, "font_size": "normal", "reduce_motion": False,
            "narrator": True, "lesson_step": 0, "lesson_done": [], "challenges_done": [],
            "autolock_minutes": 15}
LESSON_PROFILE = "lesson"
NETWORK_PROFILE = "network"           # data folder of the Data owner and Receiver modes
USES = ("demo", "owner", "receiver")
LESSON_PASSPHRASE = "lesson"


@dataclass(frozen=True)
class Friendly:
    """A three-part explanation of a problem, plus technical details for support."""

    what: str
    why: str
    next: str
    technical: str = ""

    def text(self) -> str:
        return f"What happened: {self.what}\nWhy it matters: {self.why}\nWhat to do next: {self.next}"


_GENERIC_WHY = "The app stopped instead of guessing, so nothing wrong was shown or stored."
_REJECTED = {
    "revoked": ("The data owner took this receiver's access away. The cloud no longer accepts the receiver's pass, so old "
                "and new requests are refused alike.",
                "Nothing to fix on this side. If access is still needed, the receiver sends a new join request "
                "and the data owner approves it."),
    "unknown_user": ("The cloud only answers receivers that the data owner approved. This protects the data from strangers.",
                     "Send a join request on the Receiver tab, let the data owner approve it on the Owner tab, then press Fetch mailbox."),
    "scope": ("Each receiver may only ask about the groups the data owner chose. The cloud enforces this even if the receiver's app is changed.",
              "Search a group you belong to, or ask the data owner to approve you for this group."),
    "bad_signature": ("Every update must carry the data owner's stamp. A missing or wrong stamp means it may be forged or was changed on the way.",
                      "If you are the data owner, check that the cloud is paired with your current key file, then try again."),
    "bad_sequence": ("Updates are numbered. A repeated or out-of-order update could bring back old data, so the cloud refuses it.",
                     "Nothing to do: the genuine update is already stored. If you are the data owner and this keeps happening, restart the app."),
    "stale_state": ("The cloud keeps only the newest stamped summary. An older or duplicate one is refused so old data cannot return.",
                    "Press Publish again to create a new version."),
    "stale_epoch": ("The group's locks were changed since this search slip was made, so the slip is out of date.",
                    "Press Fetch mailbox to receive the new key, then search again."),
    "bad_token": ("The request could not be opened with this receiver's pass. It may be damaged or made with the wrong pass.",
                  "Press Fetch mailbox to refresh the pass, then try again."),
    "stale_token": ("Requests carry a time. One that is too old is refused so that recordings cannot be replayed later.",
                    "Check that this computer's clock is right, then try again."),
    "no_such_doc": ("The cloud no longer stores this document. It was deleted or the group was re-locked.",
                    "Search again to get the current list of documents."),
    "bad_segment": ("That part of the index was dropped when the group was re-locked.",
                    "Press Fetch mailbox, then search again."),
    "not_paired": ("The cloud does not know the data owner's public key yet, so it cannot check their stamps.",
                   "On the Cloud tab press 'Pair: import owner key' and pick owner.pqpub."),
    "group_exists": ("Group names must be unique so that keys and documents cannot be mixed up.",
                     "Choose a different group name."),
}
_VERIFY = {
    "state signature": ("The summary of the index must carry the data owner's stamp. Without it the cloud could invent what the index contains.",
                        "Do not trust this answer. Search again; if it repeats, the cloud is misbehaving."),
    "segments complete": ("An answer must cover every live part of the index. A missing part could hide documents.",
                          "Search again; if it repeats, the cloud is withholding data."),
    "older segments final": ("Closed parts of the index must be marked final by the data owner, otherwise entries could be hidden in them.",
                             "Search again; if it repeats, the cloud is misbehaving."),
    "freshness": ("An expired summary could be an old copy that hides newer changes. The app refuses to rely on it.",
                  "The data owner presses Publish on the Owner tab to issue a fresh summary. Then search again."),
    "no rollback": ("The cloud showed an older version than one this app has already seen. That would hide recent changes.",
                    "Do not trust this answer. Search again; if it repeats, the cloud is serving old data."),
    "response signature": ("The cloud must stamp every answer. A missing or wrong stamp means the answer cannot be trusted or proven.",
                           "Search again; if it repeats, the cloud is misbehaving or the wrong cloud key is paired."),
    "completeness": ("The data owner's summary says exactly which entries must come back. Some were missing, extra or out of order.",
                     "No result is shown. Search again; if it repeats, the cloud is hiding or reordering results."),
    "hash chain": ("The running fingerprint of the entries does not match the one the data owner stamped, so an entry was changed or swapped.",
                   "No result is shown. Search again; if it repeats, the cloud is tampering with results."),
    "document signature": ("The document that came back is not the one the data owner stamped under that name. It may be swapped or altered.",
                           "The document was not opened. Try again; if it repeats, the cloud is tampering."),
    "join proof": ("A join request must prove that the sender really owns the key in it. This one does not, or it is too old.",
                   "Ask the receiver to send a new join request."),
    "capability": ("An access pass must be stamped by the data owner. This one is not, so it was ignored.",
                   "Ask the data owner to approve the join request again."),
}


def _sentence(text: str) -> str:
    text = text.strip() or "The step could not be completed"
    text = text[:1].upper() + text[1:]
    return text if text[-1] in ".!?" else text + "."


def explain_full(exc: BaseException) -> Friendly:
    """Three-part explanation for any error: what happened, why it matters, what to do next."""
    technical = f"{type(exc).__name__}: {exc}"
    trace = getattr(exc, "trace", "")
    if trace:
        technical += "\n" + trace
    if isinstance(exc, Rejected):
        why, nxt = _REJECTED.get(exc.reason, ("The cloud checks every request and refused this one.", "Try the step again."))
        return Friendly(describe_rejection(exc), why, nxt, technical)
    if isinstance(exc, VerifyError):
        why, nxt = _VERIFY.get(exc.check, ("A security check did not pass, so the data cannot be trusted.", "Try again."))
        return Friendly(_sentence(f"Verification failed at check '{exc.check}': {exc.detail}"), why, nxt, technical)
    if isinstance(exc, AccessDenied):
        return Friendly(_sentence(f"Access denied: {exc}"),
                        "Access is decided by keys. Without the key for a group, its data cannot be searched or read.",
                        "Use a group you were approved for, or ask the data owner to approve you for this one.", technical)
    if isinstance(exc, BadPassphrase):
        return Friendly("Wrong passphrase.",
                        "The passphrase unlocks the keys stored on this computer. Without it they stay locked.",
                        "Type the passphrase again. Passphrases cannot be recovered; a forgotten one means starting over.",
                        technical)
    if isinstance(exc, CloudUnavailable):
        return Friendly("The cloud server is not reachable. Start it on the Cloud tab.",
                        "Every step stores or fetches data at the cloud, so nothing can happen while it is off.",
                        "Open the Cloud tab, type the cloud passphrase and press Start server.", technical)
    if isinstance(exc, PQSSEError):
        return Friendly(_sentence(str(exc)), _GENERIC_WHY, "Fix the point mentioned above and try again.", technical)
    return Friendly("Something unexpected went wrong inside the app.", _GENERIC_WHY,
                    "Try the step again. If it keeps happening, press 'Copy technical details' and send them to support.",
                    technical)


def explain(exc: BaseException) -> str:
    """The one-line "what happened" part of explain_full."""
    return explain_full(exc).what


def explain_gpu(usable: bool, reason: str = "") -> Friendly:
    """Explanation shown when no usable GPU is found."""
    if usable:
        return Friendly("The graphics chip (GPU) is in use for batch work.",
                        "It speeds up building the index. It does not speed up the post-quantum steps.",
                        "Nothing to do.")
    return Friendly("No usable graphics chip (GPU) was found. The app is using the normal processor (CPU).",
                    "Everything still works and gives the same results. Only building a very large index is slower, "
                    "because the GPU only ever helps with that batch work.",
                    "Nothing is required. To use a GPU later, see the setup notes in README.md and run the GPU self-test "
                    "on the Settings tab.", reason)


class Session:
    """State of one running application."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.settings = dict(DEFAULTS)
        self.settings.update(self._read_settings())
        self.owner: Owner | None = None
        self.resumed: list[str] = []             # what opening the owner finished from last time
        self.receivers: dict[str, Receiver] = {}
        self.cloud_proc: subprocess.Popen | None = None
        self.cloud_line = ""
        self.admin_token = "adm-" + os.urandom(16).hex()
        self.prf: BatchPRF = CpuPRF()
        self.gpu: status.GpuStatus | None = None
        self.first_run = "mode" not in self._read_settings()
        self.profile = ""
        self._job: int | None = None
        self._https: HttpsCloud | None = None
        if self.networked:                      # real keys live apart from the demo's
            self.set_profile(NETWORK_PROFILE)

    # ------------------------------------------------------------------ settings
    @staticmethod
    def _read_settings() -> dict:
        try:
            return json.loads(paths.settings_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_settings(self) -> None:
        merged = self._read_settings()
        merged.update(self.settings)
        paths.settings_file().write_text(json.dumps(merged, indent=2), encoding="utf-8")

    @property
    def params(self) -> Params:
        return Params(self.settings["kem"], self.settings["sig"])

    @property
    def port(self) -> int:
        return int(self.settings["port"])

    def api(self, admin: bool = False) -> HttpCloud | HttpsCloud:
        if self.remote:
            if admin:
                raise PQSSEError("The server runs on another computer; its operator uses its own admin commands.")
            if self._https is None:
                server = self.settings.get("server") or {}
                if not server.get("host"):
                    raise PQSSEError("Connect to the cloud server first: enter its address and certificate fingerprint.")
                self._https = HttpsCloud(server["host"], int(server["port"]), server["pin"])
            return self._https
        return HttpCloud(port=self.port, admin_token=self.admin_token if admin else None)

    # ------------------------------------------------------------------ how this copy is used
    @property
    def use(self) -> str:
        """"demo" (all roles on this PC, the teaching mode), "owner" or "receiver" (networked)."""
        return self.settings.get("use", "demo")

    @property
    def networked(self) -> bool:
        return self.use in ("owner", "receiver")

    @property
    def own_profile(self) -> str:
        """The data folder of the user's own data: "network" in the Data owner and Receiver modes, else the base folder."""
        return NETWORK_PROFILE if self.networked else ""

    @property
    def remote(self) -> bool:
        """Talk to a server on another computer: networked modes, except inside the guided lesson's practice area."""
        return self.networked and self.profile != LESSON_PROFILE

    def set_use(self, use: str) -> None:
        if use not in USES:
            raise PQSSEError("unknown mode of use")
        if use == self.use:
            return
        self.close()
        self.owner, self.receivers, self._https = None, {}, None
        self.settings["use"] = use
        self.save_settings()
        self.set_profile(NETWORK_PROFILE if self.networked else "")

    def connect_server(self, host: str, port: int, pin: str, server_fp: str) -> dict:
        """Networked modes: pin the server's certificate, check the clock, check the server's key fingerprint."""
        host, pin = host.strip(), pin.replace(" ", "").replace(":", "").strip().lower()
        if not host or not 0 < int(port) < 65536 or len(pin) != 64:
            raise PQSSEError("Enter the server address, its port and the 64-character certificate fingerprint.")
        api = HttpsCloud(host, int(port), pin)
        skew, level, message = clock_skew(api)
        if level == "refuse":
            raise PQSSEError(message)
        ident = PublicIdentity.from_wire(api.call("pub", None))
        want = server_fp.replace(" ", "").upper()
        if want and ident.fingerprint().replace(" ", "").upper() != want:
            raise PQSSEError("The server's key does not match the fingerprint you were given. Do not continue; "
                             "ask the data owner or the server's operator.")
        self.settings["server"] = {"host": host, "port": int(port), "pin": pin, "server_fp": ident.fingerprint()}
        self.save_settings()
        self._https = api
        export_pub(paths.pub_dir() / "cloud.pqpub", ident)
        return {"fingerprint": ident.fingerprint(), "skew": round(skew, 1), "clock": message, "level": level,
                "kem": ident.params.kem, "sig": ident.params.sig}

    # ------------------------------------------------------------------ engine
    def init_engine(self, refresh: bool = False) -> str:
        """Detect the GPU (with self-test) and pick the engine for the configured mode."""
        self.gpu = status.gpu_status(refresh=refresh)
        self.prf = get_prf(self.settings["engine"])
        for role in [self.owner, *self.receivers.values()]:
            if role is not None:
                role.prf = self.prf
        return self.engine_text()

    def engine_text(self) -> str:
        if self.gpu is None:
            return "Engine: detecting"
        if self.prf.uses_gpu:
            return f"Engine: {self.prf.name} | {self.gpu.summary()}"
        if self.gpu.usable:
            return f"Engine: CPU (hashlib), GPU available but not selected | {self.gpu.summary()}"
        return f"Engine: CPU (hashlib) | {self.gpu.summary()}"

    # ------------------------------------------------------------------ cloud process
    def cloud_running(self) -> bool:
        if self.remote:
            return bool(self._https is not None and self._https.online)
        return self.cloud_proc is not None and self.cloud_proc.poll() is None

    def start_cloud(self, passphrase: str) -> str:
        """Start the cloud server as a separate process and wait until it answers."""
        if self.remote:
            raise PQSSEError("In this mode the cloud server runs on another computer. Connect to it instead.")
        if self.cloud_running():
            return self.cloud_line
        if not passphrase:
            raise PQSSEError("Enter the cloud passphrase first.")
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--cloud"]
        else:
            cmd = [sys.executable, "-m", "pqsse.cloud"]
        cmd += ["--port", str(self.port), "--kem", self.settings["kem"], "--sig", self.settings["sig"]]
        cmd += ["--db", str(paths.cloud_db()), "--pub", str(paths.pub_dir() / "cloud.pqpub")]
        root = str(Path(__file__).resolve().parent.parent)
        env = {**os.environ, "PQSSE_CLOUD_PASSPHRASE": passphrase, "PQSSE_CLOUD_ADMIN_TOKEN": self.admin_token}
        env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        # The child writes its one status line to a log file (not a pipe): this also works
        # for the packaged windowed executable, and nothing can block on an unread pipe.
        log_path = paths.data_dir() / "cloud_process.log"
        with open(log_path, "w", encoding="utf-8") as child_out:
            proc = subprocess.Popen(cmd, cwd=root if not getattr(sys, "frozen", False) else None, env=env,
                                    stdout=child_out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags)
        deadline = time.time() + 30
        while time.time() < deadline and proc.poll() is None and not self.api().alive():
            time.sleep(0.05)
        try:
            line = (log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines() or [""])[0]
        except OSError:
            line = ""
        if proc.poll() is not None or not self.api().alive():
            if proc.poll() is None:
                proc.kill()
            if "wrong passphrase" in line:
                raise BadPassphrase("wrong cloud passphrase")
            log.error("Cloud process did not start: %s", line or "no output")
            raise PQSSEError("The cloud server did not start: " + (line or "no output"))
        if "fingerprint=" not in line:
            line = "PQSSE-CLOUD READY fingerprint=" + self.cloud_identity().fingerprint()
        self.cloud_proc, self.cloud_line = proc, line
        if self._job is None:
            self._job = winjob.create()
        tied = winjob.assign(self._job, proc)       # the child ends whenever this app ends
        log.info("Cloud process started: pid %s, 127.0.0.1:%s, tied to the app: %s", proc.pid, self.port, tied)
        narrator.emit("cloud.started", "Cloud", port=self.port)
        if self.owner is not None:
            self.owner.cloud = self.api()
        return line

    def stop_cloud(self) -> None:
        proc, self.cloud_proc = self.cloud_proc, None
        if proc is None:
            return
        log.info("Cloud process stopped: pid %s", proc.pid)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def cloud_identity(self) -> PublicIdentity:
        return PublicIdentity.from_wire(self.api().call("pub", None))

    def cloud_admin(self, endpoint: str, obj: Any = None) -> Any:
        return self.api(admin=True).call("admin_" + endpoint, obj)

    def cloud_pair_owner(self, path: Path | None = None) -> str:
        """Pair devices, cloud side: import owner.pqpub into the cloud."""
        ident = import_pub(path or paths.pub_dir() / "owner.pqpub", expect_role="owner")
        self.cloud_admin("pair_owner", {"ident": ident.to_wire(), "replace": False})
        return ident.fingerprint()

    # ------------------------------------------------------------------ owner
    def owner_exists(self) -> bool:
        return paths.owner_db().exists()

    def open_owner(self, passphrase: str) -> bool:
        """Open the owner store, or create the owner (Setup) on first use. Returns True if created."""
        if not passphrase:
            raise PQSSEError("Enter the owner passphrase first.")
        vault = Vault(paths.owner_db(), passphrase)
        created = not Owner.exists(vault)
        ttl = float(self.settings["state_ttl_hours"]) * 3600.0
        if created:
            self.owner = Owner.create(vault, self.params, "owner", cloud=self.api(), prf=self.prf, state_ttl=ttl)
        else:
            self.owner = Owner(vault, cloud=self.api(), prf=self.prf, state_ttl=ttl)
        export_pub(paths.pub_dir() / "owner.pqpub", self.owner.public_identity())
        self.resumed = []
        if self.owner.has_pending:              # a message or a revocation left unfinished last time (design note 006 B)
            try:
                self.resumed = self.owner.resume_pending()
            except (CloudUnavailable, PQSSEError):
                self.resumed = ["unfinished work kept; it is sent when the cloud answers"]
        return created

    def owner_pair_cloud(self, path: Path | None = None) -> str:
        """Pair devices, owner side: import cloud.pqpub."""
        if self.owner is None:
            raise PQSSEError("Open the owner first.")
        if self.remote and path is None:
            ident = self._checked_server_identity()
        else:
            ident = import_pub(path or paths.pub_dir() / "cloud.pqpub", expect_role="cloud")
        self.owner.pair_cloud(ident)
        return ident.fingerprint()

    # ------------------------------------------------------------------ invites (design note 002)
    def create_invite(self, name: str, days: float = invites.DEFAULT_DAYS) -> dict:
        """Data owner mode: make an invite for one person. Saves a .pqinvite file without the code."""
        if self.owner is None:
            raise PQSSEError("Unlock the data owner's keys first.")
        server = self.settings.get("server") or {}
        if not self.remote or not server.get("host"):
            raise PQSSEError("Invites are for the Data owner mode, after connecting to the cloud server.")
        inv = self.owner.create_invite(server["host"], int(server["port"]), server["pin"], name.strip(), days)
        folder = paths.data_dir() / "invites"
        folder.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_") or "person"
        path = folder / f"{safe}-{inv.id[:8]}.pqinvite"
        path.write_text(inv.to_file(include_code=False), encoding="utf-8")
        return {"code": inv.code, "link": inv.to_link(include_code=False), "file": str(path), "name": name,
                "expires": inv.expires}

    def join_with_invite(self, text: str, code: str, name: str, passphrase: str) -> dict:
        """Receiver mode: connect as the invite says, check both public keys against it, then send the join request."""
        inv = invites.parse(text)
        if inv.expired:
            raise PQSSEError("This invite has expired. Ask the data owner for a new one.")
        code = code.strip() or inv.code
        if not code:
            raise PQSSEError("Enter the one-time code that came with the invite.")
        self.connect_server(inv.host, inv.port, inv.tls, inv.server_fp)
        owner = PublicIdentity.from_wire(self.api().call("owner_pub", {"fp": inv.owner_fp}))   # note 004 A: by fingerprint
        if owner.fingerprint().replace(" ", "") != inv.owner_fp.replace(" ", ""):
            raise PQSSEError("The data owner's key on the server does not match the invite. Do not continue; "
                             "ask the data owner.")
        rec = self.open_receiver(name, passphrase)
        rec.pair(owner, self._checked_server_identity())
        export_pub(paths.pub_dir() / "owner.pqpub", owner)
        rec.send_join(inv.id, code)
        fp = rec.public_identity().fingerprint()
        return {"name": name, "fingerprint": fp, "words": invites.words(fp)}

    def _checked_server_identity(self) -> PublicIdentity:
        """The server's public key over the pinned connection, accepted only if it matches the saved fingerprint."""
        ident = self.cloud_identity()
        want = (self.settings.get("server") or {}).get("server_fp", "")
        if not want or ident.fingerprint() != want:
            raise PQSSEError("The server's key changed since you connected. Do not continue; ask the server's operator.")
        return ident

    # ------------------------------------------------------------------ receivers
    def receiver_names(self) -> list[str]:
        names = {p.stem[len("receiver_"):] for p in paths.data_dir().glob("receiver_*.sqlite")}
        return sorted(names | set(self.receivers))

    def open_receiver(self, name: str, passphrase: str) -> Receiver:
        """Unlock a receiver store, or create the receiver (Setup) if it does not exist."""
        name = name.strip()
        if not name or not passphrase:
            raise PQSSEError("Enter a receiver name and passphrase.")
        vault = Vault(paths.receiver_db(name), passphrase)
        if Receiver.exists(vault):
            rec = Receiver(vault, cloud=self.api(), prf=self.prf)
        else:
            rec = Receiver.create(vault, self.params, name, cloud=self.api(), prf=self.prf)
        export_pub(paths.pub_dir() / f"receiver_{name}.pqpub", rec.public_identity())
        self.receivers[name] = rec
        return rec

    def receiver_pair(self, name: str, owner_path: Path | None = None, cloud_path: Path | None = None) -> str:
        """Pair devices, receiver side: import owner.pqpub and cloud.pqpub."""
        rec = self.receivers[name]
        owner = import_pub(owner_path or paths.pub_dir() / "owner.pqpub", expect_role="owner")
        if self.remote and cloud_path is None:
            cloud = self._checked_server_identity()
        else:
            cloud = import_pub(cloud_path or paths.pub_dir() / "cloud.pqpub", expect_role="cloud")
        rec.pair(owner, cloud)
        return f"owner {owner.fingerprint()} | cloud {cloud.fingerprint()}"

    # ------------------------------------------------------------------ profiles (Learn Mode)
    def set_profile(self, profile: str) -> None:
        """Switch between the user's own data ("") and the lesson sandbox ("lesson").

        Closes every open role and the cloud process first; nothing is shared between profiles.
        """
        if profile == self.profile:
            return
        self.close()
        self.owner, self.receivers = None, {}
        paths.set_profile(profile)
        self.profile = profile

    def reset_lesson(self) -> None:
        """Delete the lesson sandbox data and the saved lesson progress."""
        was_lesson = self.profile == LESSON_PROFILE
        self.close()
        self.owner, self.receivers = None, {}
        shutil.rmtree(paths.base_dir() / LESSON_PROFILE, ignore_errors=True)
        self.settings.update(lesson_step=0, lesson_done=[])
        self.save_settings()
        paths.set_profile(LESSON_PROFILE if was_lesson else self.own_profile)

    # ------------------------------------------------------------------ key lifecycle (milestone 5)
    def _role_vault(self, role: str):
        if role == "owner":
            if self.owner is None:
                raise PQSSEError("Unlock the data owner's keys first.")
            return self.owner.vault
        rec = self.receivers.get(role)
        if rec is None:
            raise PQSSEError(f"Unlock {role}'s keys first.")
        return rec.vault

    def keys_open(self) -> list[str]:
        return (["owner"] if self.owner is not None else []) + sorted(self.receivers)

    def change_passphrase(self, role: str, old: str, new: str) -> None:
        """Re-encrypt one role's keys under a new passphrase. The old passphrase is checked first."""
        if len(new) < 8:
            raise PQSSEError("Use a new passphrase of at least 8 characters.")
        self._role_vault(role).change_passphrase(old, new)
        if role == "owner":
            self.owner.log_event("passphrase.change", {})

    def backup_keys(self, role: str, backup_passphrase: str) -> str:
        """Write an encrypted copy of one role's keys and state to the backups folder; returns the file."""
        folder = paths.data_dir() / "backups"
        if not folder.exists():
            folder.mkdir(parents=True)
            fileperm.restrict(folder)
        safe = "".join(ch for ch in role if ch.isalnum() or ch in "-_") or "keys"
        dest = folder / f"{safe}-{time.strftime('%Y%m%d-%H%M%S')}.pqkeys"
        path = str(self._role_vault(role).export_backup(dest, backup_passphrase))
        if role == "owner":
            self.owner.log_event("backup", {"file": path})
        return path

    def import_keys(self, source: str, backup_passphrase: str, new_passphrase: str) -> str:
        """Restore a role from a backup file into this data folder. Never replaces existing keys. Returns the role."""
        if len(new_passphrase) < 8:
            raise PQSSEError("Use a passphrase of at least 8 characters for the restored keys.")
        tmp = paths.data_dir() / f"import-{os.urandom(4).hex()}.sqlite"
        vault = import_backup(source, backup_passphrase, tmp, new_passphrase)
        try:
            if vault.get("owner") is not None:
                role, dest = "owner", paths.owner_db()
            elif vault.get("receiver") is not None:
                role = vault.get("receiver")["name"]
                dest = paths.receiver_db(role)
            else:
                raise PQSSEError("This backup holds no data owner or receiver keys.")
        finally:
            vault.close()
        if dest.exists():
            tmp.unlink(missing_ok=True)
            raise PQSSEError(f"Keys for {role} already exist on this computer; nothing was replaced.")
        tmp.replace(dest)
        return role

    # ------------------------------------------------------------------ group export and import, activity (M6)
    def _folder(self, name: str) -> Path:
        folder = paths.data_dir() / name
        if not folder.exists():
            folder.mkdir(parents=True)
            fileperm.restrict(folder)
        return folder

    def export_group(self, g: str, passphrase: str) -> str:
        if self.owner is None:
            raise PQSSEError("Unlock the data owner's keys first.")
        safe = "".join(ch for ch in g if ch.isalnum() or ch in "-_") or "group"
        dest = self._folder("exports") / f"{safe}-{time.strftime('%Y%m%d-%H%M%S')}.pqgroup"
        return str(self.owner.export_group(g, dest, passphrase))

    def import_group(self, source: str, passphrase: str, g: str = "") -> dict:
        if self.owner is None:
            raise PQSSEError("Unlock the data owner's keys first.")
        group, ids = self.owner.import_group(source.strip().strip('"'), passphrase, g.strip() or None)
        if ids:
            self.owner.publish(group)
        return {"group": group, "count": len(ids)}

    def export_activity(self) -> str:
        if self.owner is None:
            raise PQSSEError("Unlock the data owner's keys first.")
        dest = self._folder("exports") / f"activity-{time.strftime('%Y%m%d-%H%M%S')}.csv"
        return str(self.owner.export_activity_csv(dest))

    def lock_keys(self) -> list[str]:
        """Close every open vault (auto-lock or the Lock button). The keys need the passphrase again."""
        locked = self.keys_open()
        for role in [self.owner, *self.receivers.values()]:
            if role is not None:
                try:
                    role.vault.close()
                except Exception:
                    pass
        self.owner, self.receivers = None, {}
        return locked

    def header_text(self) -> str:
        return f"PQ backend: {pqbackend.backend_name()} | New identities: {self.params.label()}"

    def close(self) -> None:
        self.stop_cloud()
        for role in [self.owner, *self.receivers.values()]:
            if role is not None:
                try:
                    role.vault.close()
                except Exception:
                    pass
