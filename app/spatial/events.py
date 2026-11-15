"""EventLog: the recorded session, fed by the narrator bus and read by QML.

Events arrive on worker threads. They cross to the GUI thread through a queued Qt signal
and are stored as Step Inspector records. The record list is what the Stage, the Story
bar, the timeline scrubber and every replay read from: animations never run on timers
of their own, they replay these records.
"""
from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from pqsse import narrator

from . import inspector

MAX_EVENTS = 400


class EventLog(QObject):
    incoming = Signal(object)            # narrator.Event, any thread
    added = Signal("QVariantMap")        # inspector record, GUI thread
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.raw: list[narrator.Event] = []
        self._records: list[dict] = []
        self.incoming.connect(self._on_event)
        self._unsubscribe = narrator.subscribe(self.incoming.emit)

    def _on_event(self, event: narrator.Event) -> None:
        record = inspector.build(event)
        record["index"] = len(self._records)
        self.raw.append(event)
        self._records.append(record)
        if len(self._records) > MAX_EVENTS:
            del self._records[0], self.raw[0]
            for i, item in enumerate(self._records):
                item["index"] = i
        self.changed.emit()
        self.added.emit(record)

    @Property("QVariantList", notify=changed)
    def records(self) -> list[dict]:
        return self._records

    @Property(int, notify=changed)
    def count(self) -> int:
        return len(self._records)

    @Slot(int, result="QVariantMap")
    def record(self, index: int) -> dict:
        return self._records[index] if 0 <= index < len(self._records) else {}

    def set_duration(self, first: int, took_ms: float) -> None:
        """Attach the measured time of an operation to the events it produced."""
        for index in range(max(0, first), len(self._records)):
            self._records[index] = inspector.build(self.raw[index], took_ms) | {"index": index}
        if first < len(self._records):
            self.changed.emit()

    @Slot()
    def clear(self) -> None:
        self.raw.clear()
        self._records.clear()
        self.changed.emit()

    def close(self) -> None:
        self._unsubscribe()
