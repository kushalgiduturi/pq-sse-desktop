"""Smoke test of the whole program without a window:  PQ-SSE-Desktop.exe --smoke-test

It starts the real cloud child process and runs Setup, Join, BuildIndex, Publish,
TokenGen, Search, Verify, Decrypt, an update and Revoke on the demo documents, with the
default parameter set. All data goes to a temporary folder that is deleted afterwards;
the user's own data folder is never touched.

Exit code 0 = every step passed, 1 = a step failed. The report goes to standard output
when there is one, and to the file given with --report (the packaged program is a
windowed program, so it has no console of its own).

Also here:  --gpu-selftest  (the same report as python -m pqsse.gpu.selftest)
            --version
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Callable

from pqsse import applog, paths, pqbackend
from pqsse.core.errors import AccessDenied, Rejected
from pqsse.owner import DocInput
from pqsse.version import APP_NAME, get_version

from .lesson import DELETED_TITLE, DEMO_DOCS, FINANCE, MEDICAL, NEW_DOC, SEARCH_WORD
from .session import Session

SMOKE_PASSPHRASE = "smoke-test-only"       # protects throwaway keys in a temporary folder
PLAINTEXT_PROBES = ("invoice", "penicillin", "radiology", "payroll")


def write_report(text: str, report: Path | None) -> None:
    """Send a report to standard output (when there is one) and to the report file."""
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(text, encoding="utf-8")
    if sys.stdout is not None:
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except (OSError, ValueError):
            pass


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def listening_addresses(port: int) -> list[str]:
    """Local addresses with a listening TCP socket on ``port``, from netstat."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=30,
                         creationflags=flags, stdin=subprocess.DEVNULL).stdout
    found = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0].upper() == "TCP" and parts[1].endswith(f":{port}") and parts[2].endswith(":0"):
            found.append(parts[1])
    return found


def other_addresses() -> list[str]:
    try:
        return [ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")]
    except OSError:
        return []


def reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def folder_snapshot(folder: Path) -> dict[str, tuple[int, int]]:
    snap = {}
    for path in folder.rglob("*"):
        if path.is_file():
            stat = path.stat()
            snap[str(path.relative_to(folder))] = (stat.st_size, stat.st_mtime_ns)
    return snap


def expected_titles(group: str, word: str, docs: list[tuple[str, str]]) -> set[str]:
    return {title for title, text in docs if word in (title + " " + text).lower()}


class Flow:
    """Runs the steps in order and records PASS or FAIL for each."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []
        self.failed = False

    def step(self, name: str, fn: Callable[[], str]) -> None:
        if self.failed:
            self.rows.append((name, False, "skipped: an earlier step failed"))
            return
        try:
            detail = fn()
            self.rows.append((name, True, detail))
        except Exception as exc:                      # a smoke test reports, it never crashes
            self.failed = True
            last = traceback.extract_tb(exc.__traceback__)[-1]
            self.rows.append((name, False, f"{type(exc).__name__}: {exc} ({Path(last.filename).name}:{last.lineno})"))


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_flow(flow: Flow, data_dir: Path) -> None:
    session = Session()
    session.settings["port"] = free_port()
    port = session.port
    install_before = folder_snapshot(paths.install_dir()) if paths.frozen() else {}
    docs = {group: list(items) for group, items in DEMO_DOCS.items()}
    state: dict = {}

    def engine() -> str:
        return session.init_engine()

    def cloud_start() -> str:
        line = session.start_cloud(SMOKE_PASSPHRASE)
        check(session.cloud_running(), "the cloud process is not running")
        return f"separate process, pid {session.cloud_proc.pid}, port {port}"

    def loopback_only() -> str:
        listening = listening_addresses(port)
        check(listening == [f"127.0.0.1:{port}"], f"expected one listener on 127.0.0.1:{port}, found {listening}")
        others = other_addresses()
        open_on = [ip for ip in others if reachable(ip, port)]
        check(not open_on, f"the cloud answers on non-loopback addresses: {open_on}")
        return f"listens on 127.0.0.1:{port} only; refused on {len(others)} other local address(es)"

    def setup() -> str:
        created = session.open_owner(SMOKE_PASSPHRASE)
        check(created, "the owner was not newly created")
        session.owner_pair_cloud()
        session.cloud_pair_owner()
        for group in docs:
            session.owner.create_group(group)
        return f"owner created ({session.params.label()}), paired with the cloud, groups {', '.join(docs)}"

    def join() -> str:
        bob = session.open_receiver("bob", SMOKE_PASSPHRASE)
        session.receiver_pair("bob")
        uid = bob.send_join()
        item = next(i for i in session.owner.pending_joins() if i["uid"] == uid)
        session.owner.check_join(item)
        session.owner.approve_join(item, [FINANCE])
        bob.fetch_mail()
        check(bob.joined, "the receiver did not receive its capability")
        state["bob"] = bob
        return "receiver bob joined, approved for Finance only"

    def build_publish() -> str:
        for group, items in docs.items():
            session.owner.build_index(group, [DocInput(title, text) for title, text in items])
            session.owner.publish(group)
        stats = session.cloud_admin("stats")
        check(stats["docs"] == sum(len(v) for v in docs.values()), f"cloud holds {stats['docs']} documents")
        return f"cloud holds {stats['docs']} encrypted documents and {stats['entries']} index entries"

    def search_verify() -> str:
        result = state["bob"].search(FINANCE, SEARCH_WORD)
        bad = [name for name, ok, _ in result.report.checks if not ok]
        check(not bad, f"verification checks failed: {bad}")
        check(len(result.report.checks) >= 8, f"only {len(result.report.checks)} checks ran")
        state["result"] = result
        want = expected_titles(FINANCE, SEARCH_WORD, docs[FINANCE])
        check(len(result.hits) == len(want), f"{len(result.hits)} hits, expected {len(want)}")
        return f"'{SEARCH_WORD}': {len(result.hits)} hits, {len(result.report.checks)} verification checks passed"

    def decrypt() -> str:
        plain = dict(docs[FINANCE])
        titles = set()
        for doc_id, epoch in state["result"].hits:
            doc = state["bob"].open_document(FINANCE, doc_id, epoch)
            check(plain.get(doc.title) == doc.text, f"document {doc_id} does not match the original")
            titles.add(doc.title)
        check(titles == expected_titles(FINANCE, SEARCH_WORD, docs[FINANCE]), "wrong set of documents")
        return f"{len(titles)} documents decrypted and equal to the originals"

    def cloud_blind() -> str:
        blob = b""
        for path in data_dir.glob("cloud.sqlite*"):
            blob += path.read_bytes()
        check(len(blob) > 0, "the cloud database was not found")
        lowered = blob.lower()
        leaked = [word for word in PLAINTEXT_PROBES if word.encode() in lowered]
        check(not leaked, f"plaintext words found in the cloud database: {leaked}")
        return f"{len(blob)} bytes of cloud database scanned, none of {len(PLAINTEXT_PROBES)} plaintext words found"

    def access_control() -> str:
        try:
            state["bob"].search(MEDICAL, "allergy")
        except AccessDenied:
            return "search in a group without a key was refused"
        raise AssertionError("a search in a group without a key was answered")

    def update() -> str:
        owner = session.owner
        owner.add_document(FINANCE, *NEW_DOC)
        old = next(d for d in owner.documents(FINANCE) if d["title"] == DELETED_TITLE)
        owner.delete_document(FINANCE, old["id"])
        owner.publish(FINANCE)
        current = [item for item in docs[FINANCE] if item[0] != DELETED_TITLE] + [NEW_DOC]
        result = state["bob"].search(FINANCE, SEARCH_WORD)
        check(len(result.hits) == len(expected_titles(FINANCE, SEARCH_WORD, current)), f"{len(result.hits)} hits after the update")
        gone = state["bob"].search(FINANCE, "payroll")
        check(len(gone.hits) == 0, "a deleted document is still found")
        return f"add and delete applied; '{SEARCH_WORD}' now has {len(result.hits)} hits, the deleted document is gone"

    def revoke() -> str:
        session.owner.revoke(state["bob"].uid, "R")
        try:
            state["bob"].search(FINANCE, SEARCH_WORD)
        except Rejected as exc:
            return f"revoked receiver refused by the cloud (reason: {exc.reason})"
        raise AssertionError("a revoked receiver was still answered")

    def cloud_stop() -> str:
        proc = session.cloud_proc
        session.stop_cloud()
        check(proc.poll() is not None, "the cloud process is still running")
        check(not listening_addresses(port), "the port is still open")
        return "cloud process ended, port closed"

    def install_untouched() -> str:
        if not paths.frozen():
            return "not a packaged build, skipped"
        after = folder_snapshot(paths.install_dir())
        changed = sorted(set(install_before.items()) ^ set(after.items()))
        check(not changed, f"files changed in the install folder: {[name for name, _ in changed][:5]}")
        return f"{len(after)} files in the install folder, none added or changed"

    try:
        flow.step("Engine", engine)
        flow.step("Cloud child process", cloud_start)
        flow.step("Cloud binds to 127.0.0.1 only", loopback_only)
        flow.step("Setup and pairing", setup)
        flow.step("Join", join)
        flow.step("BuildIndex and Publish", build_publish)
        flow.step("TokenGen, Search, Verify", search_verify)
        flow.step("Decrypt", decrypt)
        flow.step("Cloud database holds no plaintext", cloud_blind)
        flow.step("Access control", access_control)
        flow.step("Update (add, delete)", update)
        flow.step("Revoke", revoke)
        flow.step("Cloud stop", cloud_stop)
        flow.step("Install folder not written to", install_untouched)
    finally:
        session.close()


def run_smoke(report: Path | None = None) -> int:
    start = time.perf_counter()
    data_dir = Path(tempfile.mkdtemp(prefix="pqsse-smoke-"))
    previous = os.environ.get("PQSSE_DATA_DIR")
    os.environ["PQSSE_DATA_DIR"] = str(data_dir)
    paths.set_profile("")
    flow = Flow()
    try:
        run_flow(flow, data_dir)
    finally:
        if previous is None:
            os.environ.pop("PQSSE_DATA_DIR", None)
        else:
            os.environ["PQSSE_DATA_DIR"] = previous
        shutil.rmtree(data_dir, ignore_errors=True)
    passed = sum(1 for _, ok, _ in flow.rows if ok)
    ok = passed == len(flow.rows)
    lines = [f"{APP_NAME} smoke test",
             f"version {get_version()} | packaged: {'yes' if paths.frozen() else 'no'} | PQ backend: {pqbackend.backend_name()}",
             f"program: {sys.executable}",
             f"forced CPU: {'yes' if os.environ.get('PQSSE_FORCE_CPU') == '1' else 'no'}",
             "-" * 72]
    lines += [f"{'PASS' if good else 'FAIL'}  {name}: {detail}" for name, good, detail in flow.rows]
    lines += ["-" * 72, f"RESULT: {'PASS' if ok else 'FAIL'} ({passed} of {len(flow.rows)} steps, {time.perf_counter() - start:.1f} s)", ""]
    write_report("\n".join(lines), report)
    applog.log.info("Smoke test: %s (%s of %s steps)", "PASS" if ok else "FAIL", passed, len(flow.rows))
    return 0 if ok else 1


def run_gpu_selftest(report: Path | None = None) -> int:
    from pqsse.gpu import selftest

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        try:
            code = selftest.main()
        except Exception as exc:
            print(f"RESULT: FAIL, the self-test could not run ({type(exc).__name__}: {exc})")
            code = 1
    header = (f"{APP_NAME} {get_version()} | packaged: {'yes' if paths.frozen() else 'no'}\n"
              f"program: {sys.executable}\n")
    write_report(header + buffer.getvalue(), report)
    return code


def run_ui_selftest(report: Path | None = None) -> int:
    """Open the spatial (Qt Quick) window for a few seconds on throwaway data and check it.

    Proves that a build contains Qt Quick, the QML files and every QML module they import:
    the window must load without a QML warning, draw frames, show all five destinations,
    run two real steps (cloud start, owner setup) and open the Step Inspector.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    data_dir = Path(tempfile.mkdtemp(prefix="pqsse-ui-"))
    previous = os.environ.get("PQSSE_DATA_DIR")
    os.environ["PQSSE_DATA_DIR"] = str(data_dir)
    paths.set_profile("")
    rows: list[tuple[str, bool, str]] = []
    frames = [0]
    try:
        app = QApplication.instance() or QApplication(sys.argv[:1])
        session = Session()
        session.settings.update(port=free_port(), show_welcome=False, theme="dark")
        try:
            from .spatial.window import SpatialWindow

            view = SpatialWindow(session, sync=True)
        except Exception as exc:
            rows.append(("Spatial window loads", False, f"{type(exc).__name__}: {exc}"))
            view = None
        if view is not None:
            window, bridge = view.window, view.bridge
            rows.append(("Spatial window loads", True, f"{window.width()} x {window.height()}, renderer: "
                         f"{'software' if window.property('software') else 'graphics chip'}"))
            window.frameSwapped.connect(lambda: frames.__setitem__(0, frames[0] + 1))
            visited: list[str] = []
            plan = [lambda key=key: (window.setProperty("page", key), visited.append(str(window.property("page"))))
                    for key in ("journey", "stage", "workspace", "lab", "insights", "stage")]
            plan += [lambda: bridge.runLessonStep(1), lambda: bridge.runLessonStep(2),
                     lambda: bridge.runPalette("inspect"), None, None]

            def step() -> None:
                if not plan:
                    app.quit()
                    return
                action = plan.pop(0)
                if action is not None:
                    action()
                QTimer.singleShot(350, step)

            QTimer.singleShot(600, step)
            QTimer.singleShot(60000, app.quit)
            app.exec()
            kinds = [record["kind"] for record in bridge.events.records]
            rows.append(("All five destinations open", visited[:5] == ["journey", "stage", "workspace", "lab", "insights"], ", ".join(visited[:5])))
            rows.append(("Real steps run through the bridge", "cloud.started" in kinds and "setup.owner" in kinds and bridge.last_error is None,
                         f"{len(kinds)} events recorded; last error: {bridge.last_error}"))
            rows.append(("Step Inspector opens", window.property("inspectorOpen") is True, f"on event {window.property('inspectIndex')}"))
            rows.append(("Frames were drawn", frames[0] > 5, f"{frames[0]} frames"))
            rows.append(("No QML warning", not view.warnings, "; ".join(view.warnings[:3]) or "none"))
            view.close()
    finally:
        if previous is None:
            os.environ.pop("PQSSE_DATA_DIR", None)
        else:
            os.environ["PQSSE_DATA_DIR"] = previous
        shutil.rmtree(data_dir, ignore_errors=True)
    ok = bool(rows) and all(good for _, good, _ in rows)
    lines = [f"{APP_NAME} spatial window self-test", f"version {get_version()} | packaged: {'yes' if paths.frozen() else 'no'}",
             f"program: {sys.executable}", "-" * 72]
    lines += [f"{'PASS' if good else 'FAIL'}  {name}: {detail}" for name, good, detail in rows]
    lines += ["-" * 72, f"RESULT: {'PASS' if ok else 'FAIL'}", ""]
    write_report("\n".join(lines), report)
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="PQ-SSE-Desktop", add_help=False)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--gpu-selftest", action="store_true")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--ui-selftest", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.version:
        write_report(get_version() + "\n", args.report)
        return 0
    if args.gpu_selftest:
        return run_gpu_selftest(args.report)
    if args.ui_selftest:
        return run_ui_selftest(args.report)
    return run_smoke(args.report)
