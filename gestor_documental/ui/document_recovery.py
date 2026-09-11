"""Background recovery of document links; the worker owns no UI state."""
from PyQt6.QtCore import QThread, pyqtSignal

from ..case_documents import recover_document_links


class DocumentRecoveryWorker(QThread):
    recovered = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, case, parent=None):
        super().__init__(parent)
        self.case = case

    def run(self):
        try:
            result = recover_document_links(self.case)
        except Exception as error:
            self.failed.emit(str(error))
        else:
            self.recovered.emit(result)
