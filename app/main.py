"""PQ-SSE Desktop main window and entry point.

Run with:  python -m app
The packaged executable also serves as the cloud process when started with --cloud.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow, QProgressBar, QTabWidget, QVBoxLayout, QWidget)

from .session import Session
from .tab_attack import AttackTab
from .tab_bench import BenchTab
from .tab_cloud import CloudTab
from .tab_owner import OwnerTab
from .tab_receiver import ReceiverTab
from .tab_settings import SettingsTab
from .workers import TaskRunner

STYLE = """
QWidget { font-size: 10pt; }
QGroupBox { font-weight: 600; border: 1px solid #c8ccd2; border-radius: 6px; margin-top: 10px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QPushButton { padding: 5px 12px; }
QLabel#header { font-weight: 600; padding: 4px 2px; }
QLabel#engine { padding: 0 2px 6px 2px; color: #3b4a5a; }
"""


class MainWindow(QMainWindow):
    """One window, six tabs: Owner, Receiver, Cloud, Attack Lab, Benchmarks, Settings."""

    def __init__(self, session: Session | None = None, sync: bool = False) -> None:
        super().__init__()
        self.session = session or Session()
        self.runner = TaskRunner(self.session.lock, sync=sync, parent=self)
        self.setWindowTitle("PQ-SSE Desktop: multi-user post-quantum searchable encryption")
        self.resize(1280, 820)

        self.header = QLabel(self.session.header_text())
        self.header.setObjectName("header")
        self.engine = QLabel("Engine: detecting the GPU")
        self.engine.setObjectName("engine")
        self.owner_tab = OwnerTab(self.session, self.runner)
        self.receiver_tab = ReceiverTab(self.session, self.runner)
        self.cloud_tab = CloudTab(self.session, self.runner)
        self.attack_tab = AttackTab(self.session, self.runner)
        self.bench_tab = BenchTab(self.session, self.runner)
        self.settings_tab = SettingsTab(self.session, self.runner, self.refresh_header)
        self.tabs = QTabWidget()
        for tab, name in ((self.owner_tab, "Owner"), (self.receiver_tab, "Receiver"), (self.cloud_tab, "Cloud"),
                          (self.attack_tab, "Attack Lab"), (self.bench_tab, "Benchmarks"), (self.settings_tab, "Settings")):
            self.tabs.addTab(tab, name)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.header)
        layout.addWidget(self.engine)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.busy_bar = QProgressBar()
        self.busy_bar.setMaximumWidth(220)
        self.busy_bar.setRange(0, 1)
        self.busy_bar.setTextVisible(False)
        self.statusBar().addPermanentWidget(self.busy_bar)
        self.statusBar().showMessage("Ready. Start on the Cloud tab: start the server, then open the owner.")
        self.runner.busy.connect(self.on_busy)
        self.runner.progress.connect(self.on_progress)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.setStyleSheet(STYLE)
        self.runner.run(lambda p: self.session.init_engine(), lambda _: self.refresh_header(),
                        lambda exc: self.refresh_header(), "Detecting GPU and running the self-test", locked=False)

    # ------------------------------------------------------------------ status
    def refresh_header(self) -> None:
        self.header.setText(self.session.header_text())
        self.engine.setText(self.session.engine_text())
        self.settings_tab.refresh_info()

    def on_busy(self, count: int, label: str) -> None:
        if count > 0:
            self.busy_bar.setRange(0, 0)          # indeterminate while work is running
            self.statusBar().showMessage(label + " ...")
        else:
            self.busy_bar.setRange(0, 1)
            self.busy_bar.setValue(0)
            self.statusBar().showMessage("Ready.")

    def on_progress(self, message: str, fraction: float) -> None:
        self.statusBar().showMessage(f"{message} ({fraction * 100:.0f}%)")
        self.bench_tab.on_progress(message, fraction)

    def on_tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is self.owner_tab:
            self.owner_tab.refresh_all()
        elif widget is self.receiver_tab:
            self.receiver_tab.reload_users()
        elif widget is self.cloud_tab:
            self.cloud_tab.refresh()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.cloud_tab.timer.stop()
        self.runner.wait(5000)
        self.session.close()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--cloud":
        from pqsse.cloud.__main__ import main as cloud_main

        return cloud_main(args[1:])
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    QTimer.singleShot(0, window.raise_)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
