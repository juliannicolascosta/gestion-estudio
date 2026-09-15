from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QMimeData, Qt, QUrl
from PyQt6.QtGui import QColor, QDrag, QKeySequence, QPainter
from PyQt6.QtWidgets import QAbstractItemView, QListWidget

from .roles import PATH_ROLE


class CaseFilesList(QListWidget):
    """Lista del expediente con arrastre y accesos de teclado."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
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
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
            self.window().import_paths(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def startDrag(self, supported_actions):
        paths = [Path(item.data(PATH_ROLE)) for item in self.selectedItems()]
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count():
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor("#7A8984"))
        painter.drawText(
            self.viewport().rect().adjusted(24, 24, -24, -24),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            "Arrastrá archivos acá\nSe guardarán directamente en la carpeta del caso",
        )

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.window().copy_selected_case_files()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Cut):
            self.window().cut_selected_case_files()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.window().paste_case_files()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.window().open_selected_file()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Delete:
            self.window().remove_selected_case_files()
            event.accept()
            return
        super().keyPressEvent(event)


class QuickAccessList(CaseFilesList):
    """Biblioteca cotidiana del Estudio, separada de la documental del caso."""

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
            self.window().import_quick_access_paths(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def paintEvent(self, event):
        QListWidget.paintEvent(self, event)
        if self.count():
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor("#7A8984"))
        painter.drawText(
            self.viewport().rect().adjusted(16, 16, -16, -16),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            "Arrastrá DNI, matrícula, CBU u otros archivos de uso cotidiano",
        )

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.window().open_selected_quick_file()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Delete:
            self.window().remove_selected_quick_files()
            event.accept()
            return
        QListWidget.keyPressEvent(self, event)
