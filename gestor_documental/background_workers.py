from __future__ import annotations

from pathlib import Path
from threading import Event

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from .models import Case
from .services import CompilationCancelled, compile_documents
from .sisfe_extractor import extract_cedula_text
from .study_backup import create_study_backup, restore_study_backup


class CompileWorker(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self,
        case: Case,
        paths: list[Path],
        limit: int,
        output_name: str,
        replace_existing: bool = False,
    ):
        super().__init__()
        self.case = case
        self.paths = paths
        self.limit = limit
        self.output_name = output_name
        self.replace_existing = replace_existing
        self.cancel_event = Event()

    def cancel(self):
        self.cancel_event.set()

    @pyqtSlot()
    def run(self):
        try:
            result = compile_documents(
                self.case,
                self.paths,
                self.limit,
                self.output_name,
                self.progress.emit,
                self.cancel_event.is_set,
                self.replace_existing,
            )
            self.finished.emit(result)
        except CompilationCancelled:
            self.cancelled.emit()
        except Exception as error:
            self.failed.emit(str(error))


class CedulaExtractionWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, pdf: Path):
        super().__init__()
        self.pdf = pdf

    @pyqtSlot()
    def run(self):
        try:
            self.finished.emit(extract_cedula_text(self.pdf))
        except Exception as error:
            self.failed.emit(str(error))


class StudyBackupWorker(QObject):
    progress = pyqtSignal(int, int, str)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, operation: str, source: Path, destination: Path):
        super().__init__()
        self.operation = operation
        self.source = source
        self.destination = destination

    @pyqtSlot()
    def run(self):
        try:
            if self.operation == "backup":
                result = create_study_backup(self.source, self.destination, self.progress.emit)
            else:
                result = restore_study_backup(self.source, self.destination, self.progress.emit)
            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(str(error))
