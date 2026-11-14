"""Worker thread helper: long operations never run on the GUI thread.

``TaskRunner.run(fn, on_done, on_error)`` executes ``fn(progress)`` on a QThreadPool
thread and delivers the result back on the GUI thread through Qt signals. With
``sync=True`` (used by the offscreen smoke test) the task runs inline, which makes
tests deterministic.
"""
from __future__ import annotations

import threading
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

ProgressFn = Callable[[str, float], None]


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)
    progress = Signal(str, float)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[ProgressFn], Any], lock: threading.RLock) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.fn = fn
        self.lock = lock
        self.signals = _Signals()

    def run(self) -> None:
        try:
            with self.lock:
                result = self.fn(self.signals.progress.emit)
        except BaseException as exc:  # delivered to the GUI thread
            exc.trace = traceback.format_exc()  # type: ignore[attr-defined]
            self.signals.failed.emit(exc)
        else:
            self.signals.done.emit(result)


class TaskRunner(QObject):
    """Runs tasks on worker threads and reports busy state."""

    busy = Signal(int, str)            # number of running labelled tasks, label of the latest
    progress = Signal(str, float)

    def __init__(self, lock: threading.RLock, sync: bool = False, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.lock = lock
        self.sync = sync
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self._live: set[_Task] = set()
        self._visible = 0
        self.last_error: BaseException | None = None

    def _mark(self, delta: int, label: str) -> None:
        if label:
            self._visible += delta
            self.busy.emit(self._visible, label)

    def run(self, fn: Callable[[ProgressFn], Any], on_done: Callable[[Any], None] | None = None,
            on_error: Callable[[BaseException], None] | None = None, label: str = "",
            locked: bool = True) -> None:
        """Start a task. An empty ``label`` marks background polling (no busy indicator).

        ``locked=False`` is for work that does not touch the session's roles (polling the
        cloud log, benchmarks and the Attack Lab, which use their own sandbox worlds).
        """
        lock = self.lock if locked else threading.RLock()
        if self.sync:
            self._mark(+1, label)
            try:
                with lock:
                    result = fn(self.progress.emit)
            except Exception as exc:
                self.last_error = exc
                self._mark(-1, label)
                if on_error is not None:
                    on_error(exc)
                return
            self._mark(-1, label)
            if on_done is not None:
                on_done(result)
            return

        task = _Task(fn, lock)
        self._live.add(task)

        def done(result: Any) -> None:
            self._live.discard(task)
            self._mark(-1, label)
            if on_done is not None:
                on_done(result)

        def failed(exc: BaseException) -> None:
            self._live.discard(task)
            self._mark(-1, label)
            self.last_error = exc
            if on_error is not None:
                on_error(exc)

        task.signals.done.connect(done)
        task.signals.failed.connect(failed)
        if label:
            task.signals.progress.connect(self.progress)
        self._mark(+1, label)
        self.pool.start(task)

    def idle(self) -> bool:
        return not self._live

    def wait(self, msecs: int = 30000) -> bool:
        return self.pool.waitForDone(msecs)
