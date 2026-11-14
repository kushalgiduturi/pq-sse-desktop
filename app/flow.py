"""Animated data-flow diagram: Alice, the doctors and the Cloud, with packets moving between them.

Every packet is also listed as text under the diagram, so nothing depends on watching the
animation. With "Reduce motion" a packet appears at its destination without moving.
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, Qt, QVariantAnimation
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem,
                               QGraphicsView, QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget)

from pqsse.narrator import Packet

from .story import TAG_COLORS

NODES = {
    "alice": (QPointF(20, 20), "Alice\ndata owner", TAG_COLORS["alice"]),
    "receiver": (QPointF(20, 150), "Doctors\nBob, Carol", TAG_COLORS["receiver"]),
    "cloud": (QPointF(300, 85), "Cloud\nstorage, not trusted", TAG_COLORS["cloud"]),
}
NODE_W, NODE_H = 130, 54
ICON_MEANING = {"BOX": "locked data", "STAMP": "signed message", "SLIP": "sealed search slip", "KEY": "sealed key", "NOTE": "notice"}
NORMAL_MS, SLOW_MS = 1300, 4200
PARTY = {"alice": "Alice", "receiver": "the doctor", "cloud": "the Cloud"}


def describe(packet: Packet, who: str = "") -> str:
    src = who if packet.src == "receiver" and who else PARTY[packet.src]
    dst = who if packet.dst == "receiver" and who else PARTY[packet.dst]
    return (f"{packet.icon} ({ICON_MEANING[packet.icon]}): {packet.label}, from {src} to {dst}.\n"
            f"Contains: {packet.contents}\nWho can read it: {packet.readers}")


class _FitView(QGraphicsView):
    """A view that always shows the whole diagram, whatever its size."""

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class FlowView(QWidget):
    """The diagram with its controls and the text list of packets."""

    def __init__(self, reduce_motion: bool = False) -> None:
        super().__init__()
        self.reduce_motion = reduce_motion
        self.history: list[tuple[Packet, str]] = []
        self.queue: list[tuple[Packet, str]] = []
        self.moving: QGraphicsRectItem | None = None
        self.scene = QGraphicsScene(0, 0, 450, 225)
        self.view = _FitView(self.scene)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setBackgroundBrush(QBrush(QColor("#f7f9fc")))
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setMinimumHeight(200)
        self.view.setAccessibleName("Data-flow diagram: Alice, the doctors and the Cloud")
        self._draw_nodes()
        self.scene.selectionChanged.connect(self._selection)
        self.anim = QVariantAnimation(self)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim.valueChanged.connect(self._step)
        self.anim.finished.connect(self._next)
        self._path = (QPointF(), QPointF())

        self.slow = QCheckBox("Slow motion")
        self.pause = QPushButton("Pause")
        self.pause.setCheckable(True)
        self.pause.toggled.connect(self._toggle_pause)
        self.info = QLabel("Click a packet in the diagram or in the list to see what it contains and who can read it.")
        self.info.setWordWrap(True)
        self.listing = QListWidget()
        self.listing.setMaximumHeight(92)
        self.listing.setAccessibleName("List of packets sent so far")
        self.listing.currentRowChanged.connect(self.select)
        controls = QHBoxLayout()
        controls.addWidget(self.slow)
        controls.addWidget(self.pause)
        controls.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        layout.addLayout(controls)
        layout.addWidget(self.listing)
        layout.addWidget(self.info)

    # ------------------------------------------------------------------ drawing
    def _draw_nodes(self) -> None:
        font = QFont()
        font.setBold(True)
        pen = QPen(QColor("#8892a0"), 1.5, Qt.PenStyle.DashLine)
        centers = {k: v[0] + QPointF(NODE_W / 2, NODE_H / 2) for k, v in NODES.items()}
        for a, b in (("alice", "cloud"), ("receiver", "cloud")):
            self.scene.addLine(centers[a].x(), centers[a].y(), centers[b].x(), centers[b].y(), pen)
        for pos, text, color in NODES.values():
            rect = self.scene.addRect(pos.x(), pos.y(), NODE_W, NODE_H, QPen(QColor(color), 2), QBrush(QColor("#ffffff")))
            rect.setZValue(1)
            label = QGraphicsSimpleTextItem(text)
            label.setFont(font)
            label.setBrush(QBrush(QColor(color)))
            label.setPos(pos.x() + 8, pos.y() + 8)
            label.setZValue(2)
            self.scene.addItem(label)

    def _make_item(self, packet: Packet, index: int) -> QGraphicsRectItem:
        item = QGraphicsRectItem(0, 0, 46, 22)
        item.setBrush(QBrush(QColor("#fff3c4")))
        item.setPen(QPen(QColor("#6b5200"), 1.5))
        item.setZValue(5)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        item.setData(0, index)
        item.setToolTip(packet.label)
        text = QGraphicsSimpleTextItem(packet.icon, item)
        text.setPos(4, 3)
        return item

    def _anchor(self, node: str) -> QPointF:
        # Beside the node, on the side that faces the other party, so labels stay readable.
        offset = QPointF(-54, NODE_H / 2 - 11) if node == "cloud" else QPointF(NODE_W + 8, NODE_H / 2 - 11)
        return NODES[node][0] + offset

    # ------------------------------------------------------------------ packets
    def add(self, packet: Packet, who: str = "") -> None:
        """Queue a packet. It is listed at once and animated when its turn comes."""
        self.history.append((packet, who))
        self.listing.addItem(describe(packet, who).splitlines()[0])
        self.listing.scrollToBottom()
        self.queue.append((packet, who))
        while len(self.queue) > 12:        # never build up a long backlog of animations
            self.queue.pop(0)
        if self.anim.state() == QVariantAnimation.State.Stopped and not self.pause.isChecked():
            self._next()

    def pending(self) -> int:
        return len(self.queue)

    def _next(self) -> None:
        if not self.queue or self.pause.isChecked():
            return
        packet, _ = self.queue.pop(0)
        if self.moving is not None:
            self.scene.removeItem(self.moving)
        index = len(self.history) - len(self.queue) - 1
        self.moving = self._make_item(packet, index)
        self.scene.addItem(self.moving)
        self._path = (self._anchor(packet.src), self._anchor(packet.dst))
        if self.reduce_motion:
            self.moving.setPos(self._path[1])
            self._next()
            return
        self.moving.setPos(self._path[0])
        self.anim.setDuration(SLOW_MS if self.slow.isChecked() else NORMAL_MS)
        self.anim.start()

    def _step(self, value: float) -> None:
        if self.moving is not None:
            start, end = self._path
            self.moving.setPos(start + (end - start) * float(value))

    def _toggle_pause(self, paused: bool) -> None:
        self.pause.setText("Resume" if paused else "Pause")
        if paused and self.anim.state() == QVariantAnimation.State.Running:
            self.anim.pause()
        elif not paused:
            if self.anim.state() == QVariantAnimation.State.Paused:
                self.anim.resume()
            else:
                self._next()

    def _selection(self) -> None:
        items = self.scene.selectedItems()
        if items:
            self.select(items[0].data(0))

    def select(self, index: int) -> None:
        """Show what packet ``index`` contains and who can read it."""
        if 0 <= index < len(self.history):
            self.info.setText(describe(*self.history[index]))

    def clear(self) -> None:
        self.queue.clear()
        self.history.clear()
        self.listing.clear()
        self.anim.stop()
        if self.moving is not None:
            self.scene.removeItem(self.moving)
            self.moving = None
