"""Compilation list view, independent from the main-window controller."""

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QAbstractItemView, QListWidget

from .roles import PATH_ROLE


class CompilationList(QListWidget):
    filesDropped = pyqtSignal(object)
    removeRequested = pyqtSignal()
    openRequested = pyqtSignal(object)
    orderChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.filesDropped.emit([Path(url.toLocalFile()) for url in event.mimeData().urls()])
            event.acceptProposedAction()
            return
        super().dropEvent(event)
        self.orderChanged.emit()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count():
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor("#768681"))
        font = QFont(self.font())
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(
            self.viewport().rect().adjusted(24, 24, -24, -24),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            "Arrastrá documental desde Archivos del caso o desde afuera\n"
            "El escrito nuevo se agrega al final",
        )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.removeRequested.emit()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.currentItem()
            if item:
                self.openRequested.emit(Path(item.data(PATH_ROLE)))
            event.accept()
            return
        super().keyPressEvent(event)
