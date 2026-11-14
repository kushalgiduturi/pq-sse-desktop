"""The Narrator dock: the data-flow diagram on top, plain-language lines below.

It subscribes to the narrator event bus. Events may arrive from worker threads, so they
cross into the GUI thread through a Qt signal.
"""
from __future__ import annotations

import html
import time
from typing import Callable

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget

from pqsse import narrator

from .flow import FlowView
from .story import TAG_COLORS


class NarratorPanel(QWidget):
    event_received = Signal(object)

    def __init__(self, reduce_motion: bool = False) -> None:
        super().__init__()
        self.lines: list[narrator.Rendered] = []
        self.events: list[narrator.Event] = []
        self.listeners: list[Callable[[narrator.Event], None]] = []
        self.flow = FlowView(reduce_motion)
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._anchor)
        self.browser.setAccessibleName("Narrator: what is happening, in plain words")
        self.detail = QTextBrowser()
        self.detail.setOpenLinks(False)
        self.detail.setHtml("<p>Press <b>Tell me more</b> on any line to see a deeper explanation here.</p>")
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: self.clear())
        head = QHBoxLayout()
        legend = QLabel("Each line says who did what. Tags: [Alice], [a doctor's name], [Cloud], [Security].")
        legend.setWordWrap(True)
        head.addWidget(legend, 1)
        head.addWidget(clear)
        lower = QWidget()
        lower_layout = QVBoxLayout(lower)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.addLayout(head)
        lower_layout.addWidget(self.browser, 3)
        lower_layout.addWidget(self.detail, 2)
        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Vertical)
        splitter.addWidget(self.flow)
        splitter.addWidget(lower)
        splitter.setSizes([380, 420])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(splitter)
        self.event_received.connect(self.on_event)
        self._unsubscribe = narrator.subscribe(self.event_received.emit)

    def on_event(self, event: narrator.Event) -> None:
        text = narrator.render(event)
        index = len(self.lines)
        self.lines.append(text)
        self.events.append(event)
        stamp = time.strftime("%H:%M:%S", time.localtime(text.ts))
        color = TAG_COLORS[text.tag]
        self.browser.append(
            f'<span style="color:#6b7280;">{stamp}</span> '
            f'<b style="color:{color};">[{html.escape(text.tag_label)}]</b> {html.escape(text.line)} '
            f'<a href="more:{index}">Tell me more</a>')
        if text.packet is not None:
            self.flow.add(text.packet, event.who)
        for listener in list(self.listeners):
            listener(event)

    def _anchor(self, url: QUrl) -> None:
        target = url.toString()
        if target.startswith("more:"):
            self.show_more(int(target.split(":", 1)[1]))

    def show_more(self, index: int) -> str:
        """Fill the detail pane for line ``index`` and return its HTML."""
        text = self.lines[index]
        body = (f"<p><b>{html.escape(text.line)}</b></p><p>{html.escape(text.more)}</p>"
                f"<p><b>Technical name:</b> {html.escape(text.technical)}</p>")
        if text.hood:
            body += f"<p><b>Under the hood:</b> {html.escape(text.hood)}</p>"
        self.detail.setHtml(body)
        return body

    def clear(self) -> None:
        self.lines.clear()
        self.events.clear()
        self.browser.clear()
        self.flow.clear()

    def close_panel(self) -> None:
        self._unsubscribe()
