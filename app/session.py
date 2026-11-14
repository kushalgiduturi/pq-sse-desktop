"""Application session: the non-GUI controller behind the window.

It owns the three role objects the user is acting as (owner, receivers) and the handle
of the cloud child process. The roles never share memory with the cloud: everything
goes through HttpCloud to the separate process on 127.0.0.1.
"""
from __future__ import annotations

import json
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
from pqsse.core.keystore import Vault
from pqsse.core.pairing import PublicIdentity, export_pub, import_pub
from pqsse.gpu import get_prf, status
from pqsse.gpu.batchprf import BatchPRF, CpuPRF
from pqsse.owner import Owner
from pqsse.pqbackend import Params
from pqsse.receiver import Receiver, describe_rejection
from pqsse.transport import CloudUnavailable, HttpCloud

DEFAULTS = {"kem": "ML-KEM-768", "sig": "ML-DSA-65", "port": 8765, "engine": "auto", "state_ttl_hours": 24,
            "mode": "expert", "show_welcome": True, "font_size": "normal", "reduce_motion": False,
            "narrator": True, "lesson_step": 0, "lesson_done": [], "challenges_done": []}
LESSON_PROFILE = "lesson"
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
    "revoked": ("Alice took this doctor's access away. The cloud no longer accepts the doctor's pass, so old "
                "and new requests are refused alike.",
                "Nothing to fix on this side. If access is still needed, the doctor sends a new join request "
                "and Alice approves it."),
    "unknown_user": ("The cloud only answers doctors that Alice approved. This protects the data from strangers.",
                     "Send a join request on the Receiver tab, let Alice approve it on the Owner tab, then press Fetch mailbox."),
    "scope": ("Each doctor may only ask about the groups Alice chose. The cloud enforces this even if the doctor's app is changed.",
              "Search a group you belong to, or ask Alice to approve you for this group."),
    "bad_signature": ("Every update must carry Alice's stamp. A missing or wrong stamp means it may be forged or was changed on the way.",
                      "If you are Alice, check that the cloud is paired with your current key file, then try again."),
    "bad_sequence": ("Updates are numbered. A repeated or out-of-order update could bring back old data, so the cloud refuses it.",
                     "Nothing to do: the genuine update is already stored. If you are Alice and this keeps happening, restart the app."),
    "stale_state": ("The cloud keeps only the newest stamped summary. An older or duplicate one is refused so old data cannot return.",
                    "Press Publish again to create a new version."),
    "stale_epoch": ("The group's locks were changed since this search slip was made, so the slip is out of date.",
                    "Press Fetch mailbox to receive the new key, then search again."),
    "bad_token": ("The request could not be opened with this doctor's pass. It may be damaged or made with the wrong pass.",
                  "Press Fetch mailbox to refresh the pass, then try again."),
    "stale_token": ("Requests carry a time. One that is too old is refused so that recordings cannot be replayed later.",
                    "Check that this computer's clock is right, then try again."),
    "no_such_doc": ("The cloud no longer stores this document. It was deleted or the group was re-locked.",
                    "Search again to get the current list of documents."),
    "bad_segment": ("That part of the index was dropped when the group was re-locked.",
                    "Press Fetch mailbox, then search again."),
    "not_paired": ("The cloud does not know Alice's public key yet, so it cannot check her stamps.",
                   "On the Cloud tab press 'Pair: import owner key' and pick owner.pqpub."),
    "group_exists": ("Group names must be unique so that keys and documents cannot be mixed up.",
                     "Choose a different group name."),
}
_VERIFY = {
    "state signature": ("The summary of the index must carry Alice's stamp. Without it the cloud could invent what the index contains.",
                        "Do not trust this answer. Search again; if it repeats, the cloud is misbehaving."),
    "segments complete": ("An answer must cover every live part of the index. A missing part could hide documents.",
                          "Search again; if it repeats, the cloud is withholding data."),
    "older segments final": ("Closed parts of the index must be marked final by Alice, otherwise entries could be hidden in them.",
                             "Search again; if it repeats, the cloud is misbehaving."),
    "freshness": ("An expired summary could be an old copy that hides newer changes. The app refuses to rely on it.",
                  "Alice presses Publish on the Owner tab to issue a fresh summary. Then search again."),
    "no rollback": ("The cloud showed an older version than one this app has already seen. That would hide recent changes.",
                    "Do not trust this answer. Search again; if it repeats, the cloud is serving old data."),
    "response signature": ("The cloud must stamp every answer. A missing or wrong stamp means the answer cannot be trusted or proven.",
                           "Search again; if it repeats, the cloud is misbehaving or the wrong cloud key is paired."),
    "completeness": ("Alice's summary says exactly which entries must come back. Some were missing, extra or out of order.",
                     "No result is shown. Search again; if it repeats, the cloud is hiding or reordering results."),
    "hash chain": ("The running fingerprint of the entries does not match the one Alice stamped, so an entry was changed or swapped.",
                   "No result is shown. Search again; if it repeats, the cloud is tampering with results."),
    "document signature": ("The document that came back is not the one Alice stamped under that name. It may be swapped or altered.",
                           "The document was not opened. Try again; if it repeats, the cloud is tampering."),
    "join proof": ("A join request must prove that the sender really owns the key in it. This one does not, or it is too old.",
                   "Ask the doctor to send a new join request."),
    "capability": ("An access pass must be stamped by Alice. This one is not, so it was ignored.",
                   "Ask Alice to approve the join request again."),
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
                        "Use a group you were approved for, or ask Alice to approve you for this one.", technical)
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
        self.receivers: dict[str, Receiver] = {}
        self.cloud_proc: subprocess.Popen | None = None
        self.cloud_line = ""
        self.admin_token = "adm-" + os.urandom(16).hex()
        self.prf: BatchPRF = CpuPRF()
        self.gpu: status.GpuStatus | None = None
        self.first_run = "mode" not in self._read_settings()
        self.profile = ""

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

    def api(self, admin: bool = False) -> HttpCloud:
        return HttpCloud(port=self.port, admin_token=self.admin_token if admin else None)

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
        return self.cloud_proc is not None and self.cloud_proc.poll() is None

    def start_cloud(self, passphrase: str) -> str:
        """Start the cloud server as a separate process and wait until it answers."""
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
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.Popen(cmd, cwd=root if not getattr(sys, "frozen", False) else None, env=env,
                                    stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags)
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
            raise PQSSEError("The cloud server did not start: " + (line or "no output"))
        if "fingerprint=" not in line:
            line = "PQSSE-CLOUD READY fingerprint=" + self.cloud_identity().fingerprint()
        self.cloud_proc, self.cloud_line = proc, line
        narrator.emit("cloud.started", "Cloud", port=self.port)
        if self.owner is not None:
            self.owner.cloud = self.api()
        return line

    def stop_cloud(self) -> None:
        proc, self.cloud_proc = self.cloud_proc, None
        if proc is None:
            return
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
        return created

    def owner_pair_cloud(self, path: Path | None = None) -> str:
        """Pair devices, owner side: import cloud.pqpub."""
        if self.owner is None:
            raise PQSSEError("Open the owner first.")
        ident = import_pub(path or paths.pub_dir() / "cloud.pqpub", expect_role="cloud")
        self.owner.pair_cloud(ident)
        return ident.fingerprint()

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
        paths.set_profile(LESSON_PROFILE if was_lesson else "")

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
