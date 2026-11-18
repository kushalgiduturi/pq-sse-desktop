"""About dialog: version, engines, where the data lives, and the licenses of bundled libraries."""
from __future__ import annotations

import platform
import sys
from importlib import metadata

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

from pqsse import applog, paths, pqbackend
from pqsse.version import APP_NAME, get_version

from .session import Session

LICENSE_FILE = "THIRD-PARTY-LICENSES.txt"
LIBRARIES = ("PySide6", "shiboken6", "cryptography", "kyber-py", "dilithium-py", "numpy", "pypdf", "cupy-cuda12x")


def open_folder(path) -> bool:
    """Show a folder in the file manager."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def gpu_line(session: Session) -> str:
    if session.gpu is None:
        return "Still detecting"
    if session.prf.uses_gpu:
        return f"In use: {session.gpu.device} (self-test passed)"
    if session.gpu.usable:
        return f"Available, not selected: {session.gpu.device}"
    return f"Not used, running on the CPU ({session.gpu.reason})"


def info_rows(session: Session) -> list[tuple[str, str]]:
    """The facts shown in the dialog, as (label, value)."""
    backend = pqbackend.backend_name()
    return [
        ("Version", get_version()),
        ("Build", "Installed or portable program" if paths.frozen() else "Running from source"),
        ("Post-quantum backend", f"{backend}. {pqbackend.coverage()}"),
        ("GPU", gpu_line(session)),
        ("Python / Qt binding", f"{platform.python_version()} / PySide6 {PYSIDE_VERSION}"),
        ("Windows", platform.platform()),
        ("Data folder", str(paths.base_dir())),
        ("Log file", str(applog.log_file())),
    ]


def license_text() -> str:
    """License notes for the bundled libraries: the shipped file, or a short list from the environment."""
    parts = []
    own = paths.resource("LICENSE")
    if own.exists():
        parts.append(f"{APP_NAME}\n" + "=" * 60 + "\n" + own.read_text(encoding="utf-8", errors="replace"))
    bundled = paths.resource(LICENSE_FILE)
    if bundled.exists():
        parts.append(bundled.read_text(encoding="utf-8", errors="replace"))
        return "\n\n".join(parts)
    lines = ["Libraries in this environment (the packaged program ships the full license texts):", ""]
    for name in LIBRARIES:
        try:
            meta = metadata.metadata(name)
        except metadata.PackageNotFoundError:
            continue
        lines.append(f"{meta['Name']} {meta['Version']}: {meta.get('License-Expression') or meta.get('License') or 'see the project page'}"[:160])
    lines.append(f"Python {sys.version.split()[0]}: PSF License")
    parts.append("\n".join(lines))
    return "\n\n".join(parts)


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None, session: Session) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.resize(720, 560)
        layout = QVBoxLayout(self)
        title = QLabel(f"<h2>{APP_NAME} {get_version()}</h2>"
                       "Search encrypted documents through an untrusted cloud, with post-quantum keys and stamps.<br>"
                       "Research software: not audited, not for protecting real records.")
        title.setWordWrap(True)
        layout.addWidget(title)
        form = QFormLayout()
        self.values: dict[str, QLabel] = {}
        for label, value in info_rows(session):
            widget = QLabel(value)
            widget.setWordWrap(True)
            widget.setTextInteractionFlags(widget.textInteractionFlags() | widget.textInteractionFlags().TextSelectableByMouse)
            self.values[label] = widget
            form.addRow(label + ":", widget)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.data_button = QPushButton("Open data folder")
        self.data_button.clicked.connect(lambda: open_folder(paths.base_dir()))
        self.log_button = QPushButton("Open log folder")
        self.log_button.clicked.connect(lambda: open_folder(paths.logs_dir()))
        row.addWidget(self.data_button)
        row.addWidget(self.log_button)
        row.addStretch(1)
        # Check for updates: only when clicked; the setting hides it (Insights in the spatial window)
        from .spatial.copy import T

        self.update_text = T
        self.update_result: dict = {}
        self.update_button = QPushButton(T["updateCheck"])
        self.update_button.setToolTip(T["updateNote"])
        self.update_button.clicked.connect(self.check_for_updates)
        self.update_button.setVisible(bool(session.settings.get("update_menu", True)))
        self.page_button = QPushButton(T["updateOpenPage"])
        self.page_button.clicked.connect(self.open_download_page)
        self.page_button.setVisible(False)
        row.addWidget(self.update_button)
        row.addWidget(self.page_button)
        layout.addLayout(row)
        self.update_label = QLabel("")
        self.update_label.setWordWrap(True)
        layout.addWidget(self.update_label)
        layout.addWidget(QLabel("Licenses of this program and of the libraries shipped with it:"))
        self.licenses = QPlainTextEdit(license_text())
        self.licenses.setReadOnly(True)
        layout.addWidget(self.licenses, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def check_for_updates(self) -> None:
        """Started by the user. Reads the signed file list from the site once; nothing else is sent."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        from . import update_check

        T = self.update_text
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = update_check.check(get_version())
        finally:
            QApplication.restoreOverrideCursor()
        self.update_result = result
        if result["status"] == "newer":
            text = T["updateNewer"].format(version=result["version"], current=result["current"])
        elif result["status"] == "current":
            text = T["updateCurrent"].format(current=result["current"])
        else:
            text = T["updateError"].format(message=result["message"])
        self.update_label.setText(text)
        self.page_button.setVisible(result["status"] in ("newer", "error"))

    def open_download_page(self) -> None:
        page = self.update_result.get("download_page") or ""
        if not page.startswith("https://"):
            from .update_check import load_config

            page = load_config().manifest_url.rsplit("/", 1)[0] + "/download.html"
        QDesktopServices.openUrl(QUrl(page))
