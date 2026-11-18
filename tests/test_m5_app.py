"""Milestones 5 and 6: offscreen smoke test of the desktop app, Attack Lab and Benchmarks tabs."""
from __future__ import annotations

import os
import socket
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from app.common import GREEN, GREY, RED, DocumentDialog, read_document_file
from app.main import MainWindow
from app.session import Session, explain
from pqsse import attacklab
from pqsse.core.errors import AccessDenied, BadPassphrase, Rejected, VerifyError
from pqsse.pqbackend import FAST_PARAMS
from pqsse.receiver import CHECKS
from pqsse.transport import CloudUnavailable


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def make_window(sync: bool) -> MainWindow:
    session = Session()
    session.settings.update(kem=FAST_PARAMS.kem, sig=FAST_PARAMS.sig, port=free_port(), state_ttl_hours=1)
    window = MainWindow(session, sync=sync)
    window.show()
    return window


def minimal_pdf(text: str) -> bytes:
    """Hand built one page PDF with a text object (enough for pypdf text extraction)."""
    stream = f"BT /F1 18 Tf 10 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF\n"
    return bytes(out)


def test_app_end_to_end_offscreen(qapp, tmp_path):
    win = make_window(sync=True)
    session = win.session
    try:
        assert win.tabs.count() == 6
        assert [win.tabs.tabText(i) for i in range(6)] == ["Owner", "Receiver", "Cloud", "Attack Lab", "Benchmarks", "Settings"]
        assert "PQ backend" in win.header.text() and "Engine" in win.engine.text()

        # nothing works before the cloud is up, and the message says why
        win.owner_tab.open_owner("owner-pass")
        win.owner_tab.create_group("research")
        assert "cloud server is not reachable" in win.owner_tab.message.text()

        # Cloud tab: start the separate server process, pair both ways
        win.cloud_tab.start("cloud-pass")
        assert session.cloud_running() and win.cloud_tab.light.color == GREEN
        assert "127.0.0.1" in win.cloud_tab.status.text()
        win.owner_tab.pair_cloud()
        assert "Paired with cloud" in win.owner_tab.identity.text()
        win.cloud_tab.pair_owner()
        assert "Paired with owner" in win.cloud_tab.message.text()

        # Owner tab: group, documents (typed, .txt and .pdf import), publish
        win.owner_tab.create_group("research")
        win.owner_tab.create_group("finance")
        assert win.owner_tab.groups.count() == 2
        win.owner_tab.groups.setCurrentRow(1)
        assert win.owner_tab.current_group() == "research"
        win.owner_tab.add_document("Lattice notes", "module lattice signatures and kyber")
        (tmp_path / "memo.txt").write_text("a memo about lattice reduction", encoding="utf-8")
        (tmp_path / "paper.pdf").write_bytes(minimal_pdf("Hello lattice world from a pdf"))
        assert read_document_file(tmp_path / "paper.pdf") == ("paper", "Hello lattice world from a pdf")
        win.owner_tab.import_files([str(tmp_path / "memo.txt"), str(tmp_path / "paper.pdf")])
        assert win.owner_tab.docs.rowCount() == 3
        assert "UNPUBLISHED" in win.owner_tab.overview.text()
        win.owner_tab.publish()
        assert "published" in win.owner_tab.overview.text() and "UNPUBLISHED" not in win.owner_tab.overview.text()
        dialog = DocumentDialog(win)
        dialog.load(tmp_path / "memo.txt")
        assert dialog.values() == ("memo", "a memo about lattice reduction")

        # Receiver tab: two users, join, approve with group choice
        uids = {}
        for name in ("alice", "receiver-a"):
            win.receiver_tab.unlock(name, name + "-pass")
            assert win.receiver_tab.current == name
            win.receiver_tab.pair()
            assert "NOT paired" not in win.receiver_tab.identity.text()
            win.receiver_tab.send_join()
            uids[name] = session.receivers[name].uid
        win.owner_tab.refresh_joins()
        assert win.owner_tab.join_table.rowCount() == 2
        win.owner_tab.approve(uids["alice"], ["research"])
        win.owner_tab.approve(uids["receiver-a"], ["research", "finance"])
        assert win.owner_tab.receiver_table.rowCount() == 2 and win.owner_tab.join_table.rowCount() == 0

        win.receiver_tab.switch_user("alice")
        win.receiver_tab.fetch_mail()
        assert "capability received" in win.receiver_tab.message.text()
        assert win.receiver_tab.group.count() == 1
        win.receiver_tab.search("research", "Lattice")
        assert win.receiver_tab.results.count() == 3
        assert all(win.receiver_tab.lights[name].color == GREEN for name in CHECKS)
        assert "Fresh until: 20" in win.receiver_tab.fresh.text()
        win.receiver_tab._open_item(win.receiver_tab.results.item(0))
        assert "lattice" in win.receiver_tab.viewer.toPlainText().lower()
        win.receiver_tab.search("finance", "lattice")           # outside alice's capability
        assert "Access denied" in win.receiver_tab.message.text()

        # edit and delete through the Owner tab, then search again
        first_id = win.owner_tab.docs.item(0, 0).data(0x0100)
        win.owner_tab.edit_document(first_id, "Notes v2", "now about isogenies only")
        win.owner_tab.docs.selectRow(0)
        win.owner_tab.delete_selected()
        win.owner_tab.publish()
        win.receiver_tab.search("research", "lattice")
        assert win.receiver_tab.results.count() == 1
        win.receiver_tab.search("research", "isogenies")
        assert win.receiver_tab.results.count() == 1

        # Cloud tab: live log, statistics and the ciphertext-only view
        win.cloud_tab.refresh()
        assert win.cloud_tab.log.rowCount() > 10
        assert "Index entries" in win.cloud_tab.stats.text()
        seen = win.cloud_tab.see.toPlainText()
        assert "INDEX ENTRIES" in seen and "DOCUMENTS" in seen
        for plain in ("lattice", "isogenies", "memo", "Lattice notes"):
            assert plain not in seen
        rejected = [win.cloud_tab.log.item(r, 5).text() for r in range(win.cloud_tab.log.rowCount())
                    if win.cloud_tab.log.item(r, 4).text() == "REJECTED"]
        assert "scope" not in rejected       # alice's client refused locally, the cloud was never asked

        # Revoke alice with policy R: clear message for her, bob keeps working
        win.owner_tab.revoke(uids["alice"], "R")
        assert "revoked" in win.owner_tab.message.text().lower()
        win.receiver_tab.search("research", "lattice")
        assert "revoked by the data owner" in win.receiver_tab.message.text()
        assert all(win.receiver_tab.lights[name].color == GREY for name in CHECKS)
        assert win.receiver_tab.results.count() == 0
        win.receiver_tab.switch_user("receiver-a")
        win.receiver_tab.fetch_mail()
        win.receiver_tab.search("research", "lattice")
        assert win.receiver_tab.results.count() == 1 and win.receiver_tab.lights["hash chain"].color == GREEN
        win.owner_tab.groups.setCurrentRow(1)
        assert win.owner_tab.segments.rowCount() == 2          # epoch 1 final, epoch 2 current
        win.owner_tab.revoke(uids["receiver-a"], "RE")
        win.owner_tab.groups.setCurrentRow(1)
        assert win.owner_tab.segments.rowCount() == 1

        # wrong passphrase is reported, not crashed on
        win.receiver_tab.unlock("alice", "not-her-passphrase")
        assert win.receiver_tab.message.text() == "Wrong passphrase."

        # Attack Lab tab
        win.attack_tab.run("drop")
        assert win.attack_tab.outcomes["drop"].passed and "DETECTED" in win.attack_tab.output.toPlainText()
        win.attack_tab.run("replay")
        assert "REJECTED" in win.attack_tab.message.text()

        # Benchmarks tab: run small sizes, chart, table, CSV export
        assert win.bench_tab.export_csv(tmp_path) == []
        win.bench_tab.run_build(sizes=(300, 600))
        assert win.bench_tab.build_table.rowCount() >= 2 and len(win.bench_tab.chart.series()) == 1
        win.bench_tab.run_ops(param_sets=[FAST_PARAMS], repeats=1)
        assert win.bench_tab.ops_table.rowCount() >= 8
        written = win.bench_tab.export_csv(tmp_path)
        assert [p.name for p in written] == ["buildindex.csv", "operations.csv"]
        assert (tmp_path / "buildindex.csv").read_text(encoding="utf-8").startswith("occurrences,engine")

        # Settings tab
        win.settings_tab.engine.setCurrentIndex(win.settings_tab.engine.findData("cpu"))
        win.settings_tab.save()
        assert session.settings["engine"] == "cpu" and not session.prf.uses_gpu
        assert "CPU" in win.engine.text()
        win.settings_tab.run_selftest()
        assert win.settings_tab.report.toPlainText()
        win.settings_tab.recalibrate()

        for index in range(win.tabs.count()):
            win.tabs.setCurrentIndex(index)
        win.cloud_tab.stop()
        assert not session.cloud_running() and win.cloud_tab.light.color == GREY
    finally:
        win.close()


def test_worker_threads_deliver_results(qapp):
    """Real worker threads: the UI thread stays free and results arrive through signals."""
    win = make_window(sync=False)
    try:
        win.attack_tab.run("forge")
        win.attack_tab.run("expired")
        deadline = time.time() + 120
        ticks = 0
        while time.time() < deadline and not (win.runner.idle() and len(win.attack_tab.outcomes) == 2):
            QCoreApplication.processEvents()
            ticks += 1
            time.sleep(0.01)
        assert ticks >= 1                              # results arrived only through the spinning event loop (native crypto makes the work short)
        assert set(win.attack_tab.outcomes) == {"forge", "expired"}
        assert all(o.passed for o in win.attack_tab.outcomes.values()), [o.text() for o in win.attack_tab.outcomes.values()]
        assert win.runner.last_error is None
    finally:
        win.close()


def test_every_attack_lab_scenario_behaves_as_claimed():
    assert len(attacklab.SCENARIOS) == 11
    for key, title, _, _ in attacklab.SCENARIOS:
        outcome = attacklab.run_scenario(key)
        assert outcome.passed, outcome.text()
        assert outcome.title and outcome.lines and outcome.verdict
    with pytest.raises(KeyError):
        attacklab.run_scenario("nope")


def test_error_messages_are_clear():
    assert "revoked" in explain(Rejected("revoked"))
    assert "outside your capability" in explain(Rejected("scope"))
    assert "hash chain" in explain(VerifyError("hash chain", "mismatch"))
    assert explain(BadPassphrase("x")) == "Wrong passphrase."
    assert "Cloud tab" in explain(CloudUnavailable("x"))
    assert explain(AccessDenied("no key")).startswith("Access denied")
    assert RED != GREEN
