"""Settings tab: parameter set, engine mode, cloud port, freshness window, GPU self-test."""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QSpinBox, QVBoxLayout)

from pqsse import paths, pqbackend
from pqsse.gpu import status
from pqsse.gpu.calibrate import NEVER, calibrate
from pqsse.pqbackend import KEM_NAMES, SIG_NAMES

from .common import TabBase


class SettingsTab(TabBase):
    def __init__(self, session, runner, on_engine_changed) -> None:
        super().__init__(session, runner)
        self.on_engine_changed = on_engine_changed
        s = session.settings
        self.kem = QComboBox()
        self.kem.addItems(KEM_NAMES)
        self.kem.setCurrentText(s["kem"])
        self.sig = QComboBox()
        self.sig.addItems(SIG_NAMES)
        self.sig.setCurrentText(s["sig"])
        self.engine = QComboBox()
        self.engine.addItem("Auto: GPU for large batches, CPU otherwise", "auto")
        self.engine.addItem("CPU only", "cpu")
        self.engine.addItem("GPU for every batch (when usable)", "gpu")
        self.engine.setCurrentIndex(max(0, self.engine.findData(s["engine"])))
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(int(s["port"]))
        self.ttl = QSpinBox()
        self.ttl.setRange(1, 24 * 365)
        self.ttl.setSuffix(" hours")
        self.ttl.setValue(int(s["state_ttl_hours"]))
        save = QPushButton("Save settings")
        save.clicked.connect(lambda: self.save())
        form_box = QGroupBox("Settings")
        form = QFormLayout(form_box)
        form.addRow("ML-KEM parameter set (new identities)", self.kem)
        form.addRow("ML-DSA parameter set (new identities)", self.sig)
        form.addRow("Batch engine", self.engine)
        form.addRow("Cloud port on 127.0.0.1", self.port)
        form.addRow("State freshness window (delta)", self.ttl)
        form.addRow(save)
        form.addRow(QLabel("The parameter set applies to identities created from now on. Owner, cloud and receivers "
                           "must use the same set. The port applies the next time the cloud server starts."))

        self.info = QLabel("")
        self.info.setWordWrap(True)
        selftest = QPushButton("Run GPU self-test")
        recalibrate = QPushButton("Recalibrate GPU threshold")
        folder = QPushButton("Open data folder")
        selftest.clicked.connect(lambda: self.run_selftest())
        recalibrate.clicked.connect(lambda: self.recalibrate())
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data_dir()))))
        buttons = QHBoxLayout()
        for button in (selftest, recalibrate, folder):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setFont(QFont("Consolas", 9))
        gpu_box = QGroupBox("Batch engine and GPU")
        gpu_layout = QVBoxLayout(gpu_box)
        gpu_layout.addWidget(self.info)
        gpu_layout.addLayout(buttons)
        gpu_layout.addWidget(self.report, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(form_box)
        layout.addWidget(gpu_box, 1)
        layout.addWidget(self.message)
        self.refresh_info()

    def refresh_info(self) -> None:
        gpu = self.session.gpu
        lines = [f"PQ backend: {pqbackend.backend_name()}", f"Data folder: {paths.data_dir()}", self.session.engine_text()]
        if gpu is not None and gpu.available:
            lines.append(f"Device: {gpu.device} | Memory: {gpu.total_mem / 2**30:.2f} GB total, "
                         f"{gpu.free_mem / 2**30:.2f} GB free | CuPy {gpu.cupy_version} | {gpu.driver}")
        lines.append("Only the symmetric batch work (PRF addresses, masks, hash chain levels) can use the GPU. "
                     "ML-KEM and ML-DSA always run on the CPU.")
        self.info.setText("\n".join(lines))

    def save(self) -> None:
        self.session.settings.update(kem=self.kem.currentText(), sig=self.sig.currentText(),
                                     engine=self.engine.currentData(), port=self.port.value(),
                                     state_ttl_hours=self.ttl.value())
        self.session.save_settings()
        if self.session.owner is not None:
            self.session.owner.state_ttl = self.ttl.value() * 3600.0

        def done(text: str) -> None:
            self.refresh_info()
            self.on_engine_changed()
            self.notify("Settings saved.")

        self.task(lambda p: self.session.init_engine(), done, "Applying settings", locked=False)

    def run_selftest(self) -> None:
        def work(progress):
            info = status.gpu_status(refresh=True)
            self.session.init_engine()
            return info

        def done(info: status.GpuStatus) -> None:
            lines = [info.summary()]
            if info.selftest is not None:
                lines += info.selftest.lines
                lines.append(f"{info.selftest.checked} digests compared with hashlib / hmac, "
                             f"{info.selftest.mismatches} mismatches, {info.selftest.seconds:.2f} s")
            if not info.usable:
                lines.append("The GPU path is disabled. The application runs fully on the CPU.")
                lines.append("Reason: " + info.reason)
            self.report.setPlainText("\n".join(lines))
            self.refresh_info()
            self.on_engine_changed()
            if info.usable:
                self.notify("GPU self-test passed: output is byte for byte equal to hashlib and hmac.")
            elif info.available:
                self.notify("GPU SELF-TEST FAILED. The GPU path has been disabled, the app uses the CPU.", error=True)
            else:
                self.notify("No usable GPU. The app runs on the CPU. " + info.reason, error=True)

        self.task(work, done, "GPU self-test", locked=False)

    def recalibrate(self) -> None:
        def work(progress):
            info = status.gpu_status()
            if not info.usable or info.engine is None:
                return None
            result = calibrate(info.engine)
            self.session.init_engine()
            return result

        def done(result) -> None:
            if result is None:
                self.notify("No usable GPU to calibrate.", error=True)
                return
            lines = [f"{'batch':>8} {'CPU ms':>10} {'GPU ms':>10} {'speedup':>9}"]
            lines += [f"{r['n']:>8} {r['cpu_ms']:>10.3f} {r['gpu_ms']:>10.3f} {r['speedup']:>8.2f}x" for r in result.rows]
            lines.append("GPU never faster: auto mode stays on the CPU." if result.threshold == NEVER
                         else f"Threshold stored: GPU for batches of {result.threshold} messages or more.")
            self.report.setPlainText("\n".join(lines))
            self.refresh_info()
            self.on_engine_changed()
            self.notify("Calibration done.")

        self.task(work, done, "Calibrating GPU threshold", locked=False)
