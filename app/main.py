"""PQ-SSE Desktop main window and entry point.

Run with:  python -m app
The packaged executable also serves as the cloud process when started with --cloud.

Two modes share one window and one session. Beginner Mode adds the Learn tab, the
Narrator dock, story intros and collapses advanced controls. Expert Mode is the plain
six-tab window. Switching never restarts anything.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QDockWidget, QLabel, QLineEdit, QMainWindow, QProgressBar, QTabWidget,
                               QToolBar, QVBoxLayout, QWidget, QWidgetAction)

from .glossary import GlossaryDialog
from .narrator_panel import NarratorPanel
from .session import Session, explain_gpu
from .tab_attack import AttackTab
from .tab_bench import BenchTab
from .tab_cloud import CloudTab
from .tab_learn import LearnTab
from .tab_owner import OwnerTab
from .tab_receiver import ReceiverTab
from .tab_settings import SettingsTab
from .welcome import Tour, WelcomeDialog
from .workers import TaskRunner

FONT_POINTS = {"small": 9, "normal": 10, "large": 13}
STYLE = """
QWidget {{ font-size: {pt}pt; }}
QGroupBox {{ font-weight: 600; border: 1px solid #8f96a0; border-radius: 6px; margin-top: 10px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QPushButton {{ padding: 5px 12px; }}
QLabel#header {{ font-weight: 600; padding: 4px 2px; }}
QLabel#engine {{ padding: 0 2px 6px 2px; color: #2c3845; }}
QLabel#intro {{ background: #eef4fb; color: #16293d; border: 1px solid #9db7d3; border-radius: 6px; padding: 8px; }}
QFrame#tour {{ background: #fff6d6; color: #3a2e00; border: 2px solid #b58900; border-radius: 6px; }}
"""
TAB_NAMES = [("Owner", "Owner (Alice)"), ("Receiver", "Receiver (Bob, Carol)"), ("Cloud", "Cloud (storage)"),
             ("Attack Lab", "Attack Lab"), ("Benchmarks", "Benchmarks"), ("Settings", "Settings")]


def use_light_colors(app: QApplication) -> None:
    """Ask Qt for the light color scheme. The app's colors are chosen for contrast on a light
    background, so it does not follow a dark system theme."""
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except (AttributeError, TypeError):
        pass          # older Qt: keep the system colors


class MainWindow(QMainWindow):
    """One window. Tabs: (Learn,) Owner, Receiver, Cloud, Attack Lab, Benchmarks, Settings."""

    def __init__(self, session: Session | None = None, sync: bool = False, mode: str | None = None) -> None:
        super().__init__()
        self.session = session or Session()
        self.runner = TaskRunner(self.session.lock, sync=sync, parent=self)
        self.setWindowTitle("PQ-SSE Desktop: multi-user post-quantum searchable encryption")
        self.resize(1480, 880)
        self.mode = ""
        self.glossary: GlossaryDialog | None = None

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
        self.learn_tab = LearnTab(self.session, self.runner, self)
        self.tabs = QTabWidget()
        self.main_tabs = [self.owner_tab, self.receiver_tab, self.cloud_tab, self.attack_tab, self.bench_tab, self.settings_tab]
        for tab, (name, _) in zip(self.main_tabs, TAB_NAMES):
            self.tabs.addTab(tab, name)
        self.tour = Tour(self.tabs)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.header)
        layout.addWidget(self.engine)
        layout.addWidget(self.tour)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.narrator = NarratorPanel(bool(self.session.settings.get("reduce_motion")))
        self.narrator.listeners.append(self.learn_tab.on_event)
        self.dock = QDockWidget("Narrator: what is happening, in plain words", self)
        self.dock.setObjectName("narratorDock")
        self.dock.setWidget(self.narrator)
        self.dock.setMinimumWidth(380)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

        self._build_actions()
        self.busy_bar = QProgressBar()
        self.busy_bar.setMaximumWidth(220)
        self.busy_bar.setRange(0, 1)
        self.busy_bar.setTextVisible(False)
        self.busy_bar.setAccessibleName("Work in progress")
        self.statusBar().addPermanentWidget(self.busy_bar)
        self.statusBar().showMessage("Ready. Start on the Cloud tab: start the server, then open the owner.")
        self.runner.busy.connect(self.on_busy)
        self.runner.progress.connect(self.on_progress)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.apply_font()
        self.set_mode(mode or self.session.settings.get("mode", "expert"), save=False)
        self.runner.run(lambda p: self.session.init_engine(), lambda _: self.refresh_header(),
                        lambda exc: self.refresh_header(), "Detecting GPU and running the self-test", locked=False)

    # ------------------------------------------------------------------ menus and toolbar
    def _build_actions(self) -> None:
        self.mode_action = QAction("Beginner Mode", self)
        self.mode_action.setCheckable(True)
        self.mode_action.setToolTip("Beginner Mode: Learn tab, Narrator and plain explanations. Switch off for Expert Mode.")
        self.mode_action.toggled.connect(lambda on: self.set_mode("beginner" if on else "expert"))
        glossary_action = QAction("Glossary", self)
        glossary_action.setShortcut(QKeySequence("F1"))
        glossary_action.triggered.connect(lambda: self.open_glossary())
        welcome_action = QAction("Welcome screen", self)
        welcome_action.triggered.connect(lambda: self.show_welcome())
        tour_action = QAction("Take the tour", self)
        tour_action.triggered.connect(lambda: self.tour.start())
        learn_action = QAction("Open the guided lesson", self)
        learn_action.setShortcut(QKeySequence("Ctrl+L"))
        learn_action.triggered.connect(lambda: self.open_lesson())
        self.narrator_action = self.dock.toggleViewAction()
        self.narrator_action.setText("Narrator panel")

        toolbar = QToolBar("Main toolbar")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.addAction(self.mode_action)
        toolbar.addAction(learn_action)
        toolbar.addAction(glossary_action)
        toolbar.addAction(self.narrator_action)
        self.addToolBar(toolbar)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.mode_action)
        view_menu.addAction(self.narrator_action)
        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(welcome_action)
        help_menu.addAction(learn_action)
        help_menu.addAction(tour_action)
        help_menu.addAction(glossary_action)
        self.glossary_search = QLineEdit()
        self.glossary_search.setPlaceholderText("Search the glossary, then press Enter")
        self.glossary_search.returnPressed.connect(lambda: self.open_glossary(query=self.glossary_search.text()))
        search_action = QWidgetAction(self)
        search_action.setDefaultWidget(self.glossary_search)
        help_menu.addAction(search_action)

    # ------------------------------------------------------------------ modes
    def set_mode(self, mode: str, save: bool = True) -> None:
        """Switch between Beginner and Expert Mode. Nothing is restarted and no state is lost."""
        beginner = mode == "beginner"
        self.mode = "beginner" if beginner else "expert"
        self.mode_action.blockSignals(True)
        self.mode_action.setChecked(beginner)
        self.mode_action.blockSignals(False)
        index = self.tabs.indexOf(self.learn_tab)
        if beginner and index < 0:
            self.tabs.insertTab(0, self.learn_tab, "Learn")
            self.tabs.setCurrentIndex(0)
        elif not beginner and index >= 0:
            self.tabs.removeTab(index)
        for tab, (expert_name, beginner_name) in zip(self.main_tabs, TAB_NAMES):
            self.tabs.setTabText(self.tabs.indexOf(tab), beginner_name if beginner else expert_name)
            tab.set_beginner(beginner)
        self.learn_tab.set_beginner(beginner)
        self.dock.setVisible(beginner and bool(self.session.settings.get("narrator", True)))
        self.setWindowTitle("PQ-SSE Desktop: search locked files without unlocking them" if beginner
                            else "PQ-SSE Desktop: multi-user post-quantum searchable encryption")
        self.refresh_header()
        if save:
            self.session.settings["mode"] = self.mode
            self.session.save_settings()

    def apply_font(self) -> None:
        points = FONT_POINTS.get(self.session.settings.get("font_size", "normal"), 10)
        self.setStyleSheet(STYLE.format(pt=points))
        self.narrator.flow.reduce_motion = bool(self.session.settings.get("reduce_motion"))

    def open_glossary(self, key: str | None = None, query: str | None = None) -> GlossaryDialog:
        if self.glossary is None:
            self.glossary = GlossaryDialog(self)
        if key is not None:
            self.glossary.open_at(key)
        else:
            self.glossary.search_box.setText(query or "")
            self.glossary.show()
            self.glossary.raise_()
        return self.glossary

    def open_lesson(self) -> None:
        if self.mode != "beginner":
            self.set_mode("beginner")
        self.tabs.setCurrentWidget(self.learn_tab)
        self.learn_tab.pages.setCurrentIndex(0)

    def show_welcome(self, execute: bool = True) -> WelcomeDialog:
        """Show the welcome dialog. ``execute=False`` only builds it (used by tests)."""
        dialog = WelcomeDialog(self, bool(self.session.settings.get("show_welcome", True)))
        if execute:
            dialog.exec()
            self.apply_welcome(dialog)
        return dialog

    def apply_welcome(self, dialog: WelcomeDialog) -> None:
        self.session.settings["show_welcome"] = not dialog.dont_show.isChecked()
        self.session.save_settings()
        if dialog.choice == "lesson":
            self.open_lesson()
            self.learn_tab.start_lesson()
        else:
            self.tour.start()

    # ------------------------------------------------------------------ views
    def reset_views(self) -> None:
        """Clear every tab after the session switched between the user's data and the lesson."""
        self.owner_tab.reset_view()
        self.receiver_tab.reset_view()
        self.cloud_tab.reset_view()
        self.learn_tab.refresh_lists()
        self.refresh_header()

    def refresh_views(self) -> None:
        """Bring every tab up to date after the lesson acted on the session."""
        self.owner_tab.refresh_all()
        self.receiver_tab.sync()
        self.cloud_tab.sync_state()
        self.refresh_header()

    def refresh_header(self) -> None:
        if self.mode == "beginner":
            gpu = self.session.gpu
            where = "your own data" if not self.session.profile else "the lesson practice area"
            self.header.setText(f"You are working with {where}. Mode: Beginner (switch in the toolbar).")
            self.engine.setText("Checking for a graphics chip..." if gpu is None
                                else explain_gpu(self.session.prf.uses_gpu, gpu.reason).what)
        else:
            self.header.setText(self.session.header_text())
            self.engine.setText(self.session.engine_text())
        self.settings_tab.refresh_info()
        self.apply_font()

    def on_busy(self, count: int, label: str) -> None:
        if count > 0:
            self.busy_bar.setRange(0, 0)          # indeterminate while work is running
            self.statusBar().showMessage(label + " ... (the window stays usable while this runs)")
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
        self.narrator.close_panel()
        self.session.close()
        if self.session.profile:
            self.session.set_profile("")
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--cloud":
        from pqsse.cloud.__main__ import main as cloud_main

        return cloud_main(args[1:])
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    use_light_colors(app)
    session = Session()
    if session.first_run:
        session.settings["mode"] = "beginner"      # a new user starts in Beginner Mode
        session.save_settings()
    window = MainWindow(session)
    window.show()
    QTimer.singleShot(0, window.raise_)
    if session.settings.get("show_welcome", True):
        QTimer.singleShot(200, window.show_welcome)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
