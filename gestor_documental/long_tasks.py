"""Small cooperative task primitive for FORO's long-running operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Condition
from typing import Callable, Iterable

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class TaskState(str, Enum):
    PENDING = "PENDIENTE"
    RUNNING = "EN_EJECUCION"
    PAUSED = "PAUSADO"
    CANCELLING = "CANCELANDO"
    CANCELLED = "CANCELADO"
    COMPLETED = "COMPLETADO"
    ERROR = "ERROR"


ACTIVE_TASK_STATES = {
    TaskState.PENDING,
    TaskState.RUNNING,
    TaskState.PAUSED,
    TaskState.CANCELLING,
}


@dataclass(frozen=True)
class TaskDetail:
    item: str
    result: str
    message: str = ""
    payload: object | None = None


class GlobalTaskError(RuntimeError):
    """Stops the whole batch; ordinary exceptions only fail one unit."""


class LongTask(QObject):
    state_changed = pyqtSignal(object)
    progress_changed = pyqtSignal(int, int, str)
    detail_added = pyqtSignal(object)
    finished = pyqtSignal(object)

    def __init__(self, name: str, total: int):
        super().__init__()
        self.name = name
        self.total = max(0, int(total))
        self.current = 0
        self.details: list[TaskDetail] = []
        self.state = TaskState.PENDING
        self.error = ""
        self._condition = Condition()

    @property
    def active(self) -> bool:
        return self.state in ACTIVE_TASK_STATES

    def start(self):
        with self._condition:
            if self.state is not TaskState.PENDING:
                return
            self.state = TaskState.RUNNING
        self.state_changed.emit(self.state)
        self.progress_changed.emit(self.current, self.total, self.name)

    def pause(self):
        with self._condition:
            if self.state is not TaskState.RUNNING:
                return
            self.state = TaskState.PAUSED
        self.state_changed.emit(self.state)

    def resume(self):
        with self._condition:
            if self.state is not TaskState.PAUSED:
                return
            self.state = TaskState.RUNNING
            self._condition.notify_all()
        self.state_changed.emit(self.state)

    def cancel(self):
        with self._condition:
            if self.state not in ACTIVE_TASK_STATES:
                return
            self.state = TaskState.CANCELLING
            self._condition.notify_all()
        self.state_changed.emit(self.state)

    def before_next_unit(self) -> bool:
        with self._condition:
            while self.state is TaskState.PAUSED:
                self._condition.wait()
            return self.state is not TaskState.CANCELLING

    def complete_unit(
        self, item: str, result: str, message: str = "", payload: object | None = None
    ):
        detail = TaskDetail(item, result, message, payload)
        with self._condition:
            self.current += 1
            self.details.append(detail)
            current = self.current
        self.detail_added.emit(detail)
        self.progress_changed.emit(current, self.total, self.name)

    def complete(self):
        self._finish(TaskState.COMPLETED)

    def cancelled(self):
        self._finish(TaskState.CANCELLED)

    def fail(self, message: str):
        self.error = str(message)
        self._finish(TaskState.ERROR)

    def _finish(self, state: TaskState):
        with self._condition:
            self.state = state
            summary = {
                "name": self.name,
                "state": state,
                "current": self.current,
                "total": self.total,
                "details": tuple(self.details),
                "error": self.error,
            }
            self._condition.notify_all()
        self.state_changed.emit(state)
        self.finished.emit(summary)


class BatchTaskWorker(QObject):
    stopped = pyqtSignal()

    def __init__(
        self,
        task: LongTask,
        items: Iterable[object],
        processor: Callable[[object], tuple[str, str, object | None]],
        labeler: Callable[[object], str] = str,
    ):
        super().__init__()
        self.task = task
        self.items = list(items)
        self.processor = processor
        self.labeler = labeler

    @pyqtSlot()
    def run(self):
        self.task.start()
        try:
            for item in self.items:
                if not self.task.before_next_unit():
                    self.task.cancelled()
                    return
                label = self.labeler(item)
                try:
                    result, message, payload = self.processor(item)
                except GlobalTaskError as error:
                    self.task.fail(str(error))
                    return
                except Exception as error:
                    self.task.complete_unit(label, "error", str(error))
                else:
                    self.task.complete_unit(label, result, message, payload)
            if self.task.state is TaskState.CANCELLING:
                self.task.cancelled()
            else:
                self.task.complete()
        finally:
            self.stopped.emit()
