from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QMimeData, Qt, QUrl
from PyQt6.QtGui import QColor, QDrag, QKeySequence, QPainter
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QListWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from .roles import MODIFIED_ROLE, PATH_ROLE, SIZE_ROLE


DATE_COLUMN_WIDTH = 148
SIZE_COLUMN_WIDTH = 92


class ExplorerColumnsDelegate(QStyledItemDelegate):
    """Dibuja Nombre, Fecha de modificación y Tamaño como en el Explorador.

    La vista sigue siendo una lista: el modelo, el arrastre, el renombrado y
    la selección múltiple no cambian.  Sólo se reparte el ancho de cada fila
    en tres columnas alineadas con sus encabezados.
    """

    def paint(self, painter, option, index):
        modified = str(index.data(MODIFIED_ROLE) or "")
        size = str(index.data(SIZE_ROLE) or "")
        if not modified and not size:
            super().paint(painter, option, index)
            return

        view_option = QStyleOptionViewItem(option)
        self.initStyleOption(view_option, index)
        label = view_option.text
        view_option.text = ""
        widget = view_option.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, view_option, painter, widget)

        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, view_option, widget
        )
        reserved = DATE_COLUMN_WIDTH + SIZE_COLUMN_WIDTH
        name_rect = text_rect.adjusted(0, 0, -reserved, 0)
        selected = bool(view_option.state & QStyle.StateFlag.State_Selected)

        painter.save()
        metrics = painter.fontMetrics()
        painter.setPen(QColor("#1F4034" if selected else "#2A332B"))
        painter.drawText(
            name_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(label, Qt.TextElideMode.ElideMiddle, max(name_rect.width(), 0)),
        )
        painter.setPen(QColor("#6B7A6E" if not selected else "#3E5A4B"))
        date_rect = text_rect.adjusted(
            max(name_rect.width(), 0), 0, -SIZE_COLUMN_WIDTH, 0
        )
        painter.drawText(
            date_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            modified,
        )
        size_rect = text_rect.adjusted(max(name_rect.width(), 0) + DATE_COLUMN_WIDTH, 0, 0, 0)
        painter.drawText(
            size_rect,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            size,
        )
        painter.restore()


class CaseFilesList(QListWidget):
    """Lista del expediente con arrastre y accesos de teclado."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setUniformItemSizes(True)
        self.setItemDelegate(ExplorerColumnsDelegate(self))

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
            "Arrastrá archivos acá\nSe guardan en la carpeta del caso",
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
