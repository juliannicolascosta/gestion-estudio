"""Compilation list view, independent from the main-window controller."""

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from ..compilation_draft import CompilationHistoryEntry
from .roles import PATH_ROLE


class CompilationHistoryDialog(QDialog):
    def __init__(self, entries: tuple[CompilationHistoryEntry, ...], parent=None):
        super().__init__(parent)
        self.entries = entries
        self.setWindowTitle("Historial de compilaciones")
        self.setMinimumSize(620, 420)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Elegí un armado anterior para volver a cargar sus archivos y orden. "
            "No se modifica ni reemplaza ningún PDF existente."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.list = QListWidget()
        for index, entry in enumerate(entries):
            output = entry.output.name if entry.output else "PDF no disponible"
            item = QListWidgetItem(
                f"{entry.created_at.strftime('%d/%m/%Y %H:%M')} · {output}\n"
                f"{len(entry.items)} elementos · {entry.profile}"
            )
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Recuperar armado")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def selected_entry(self) -> CompilationHistoryEntry | None:
        item = self.list.currentItem()
        return self.entries[int(item.data(Qt.ItemDataRole.UserRole))] if item else None


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
