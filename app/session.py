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
import threading
import time
from pathlib import Path
from typing import Any

from pqsse import paths, pqbackend
from pqsse.core.errors import AccessDenied, BadPassphrase, PQSSEError, Rejected, VerifyError
from pqsse.core.keystore import Vault
from pqsse.core.pairing import PublicIdentity, export_pub, import_pub
from pqsse.gpu import get_prf, status
from pqsse.gpu.batchprf import BatchPRF, CpuPRF
from pqsse.owner import Owner
from pqsse.pqbackend import Params
from pqsse.receiver import Receiver, describe_rejection
from pqsse.transport import CloudUnavailable, HttpCloud

DEFAULTS = {"kem": "ML-KEM-768", "sig": "ML-DSA-65", "port": 8765, "engine": "auto", "state_ttl_hours": 24}


def explain(exc: BaseException) -> str:
    """Turn an exception into a clear message for the user."""
    if isinstance(exc, Rejected):
        return describe_rejection(exc)
    if isinstance(exc, VerifyError):
        return f"Verification failed at check '{exc.check}': {exc.detail}"
    if isinstance(exc, AccessDenied):
        return f"Access denied: {exc}"
    if isinstance(exc, BadPassphrase):
        return "Wrong passphrase."
    if isinstance(exc, CloudUnavailable):
        return "The cloud server is not reachable. Start it on the Cloud tab."
    if isinstance(exc, PQSSEError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


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
