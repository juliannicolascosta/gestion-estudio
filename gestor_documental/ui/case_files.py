from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QMimeData, QRect, Qt, QUrl
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
UNSUPPORTED_DROP_MESSAGE = (
    "Este elemento no puede arrastrarse directamente. "
    "Descargalo primero y luego agregalo a FORO."
)


class UnsafeFileDrop(ValueError):
    """Raised when a drop is not an unambiguous set of local files."""


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def local_file_paths_from_mime(mime_data) -> list[Path]:
    """Return only verified local files; never infer a path from other MIME data."""
    if mime_data is None or not mime_data.hasUrls():
        raise UnsafeFileDrop(UNSUPPORTED_DROP_MESSAGE)
    urls = list(mime_data.urls())
    if not urls:
        raise UnsafeFileDrop(UNSUPPORTED_DROP_MESSAGE)

    package_root = Path(__file__).resolve().parents[1]
    application_root = package_root.parent
    protected_roots = (package_root, application_root)
    paths: list[Path] = []
    for url in urls:
        if not url.isLocalFile():
            raise UnsafeFileDrop(UNSUPPORTED_DROP_MESSAGE)
        raw_path = url.toLocalFile().strip()
        if not raw_path or raw_path in {".", ".."}:
            raise UnsafeFileDrop(UNSUPPORTED_DROP_MESSAGE)
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            raise UnsafeFileDrop(UNSUPPORTED_DROP_MESSAGE)
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            raise UnsafeFileDrop(UNSUPPORTED_DROP_MESSAGE) from None
        if not resolved.is_file():
            raise UnsafeFileDrop(UNSUPPORTED_DROP_MESSAGE)
        if any(_is_within(resolved, root) for root in protected_roots):
            raise UnsafeFileDrop(UNSUPPORTED_DROP_MESSAGE)
        paths.append(resolved)
    return paths


def is_supported_file_drop(mime_data) -> bool:
    try:
        local_file_paths_from_mime(mime_data)
        return True
    except UnsafeFileDrop:
        return False


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
        name, separator, tags_text = label.partition("    · ")
        tags = [tag.strip() for tag in tags_text.split(" · ") if tag.strip()] if separator else []
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
            metrics.elidedText(name, Qt.TextElideMode.ElideMiddle, max(name_rect.width(), 0)),
        )
        if tags and name_rect.width() > 220:
            chip_x = name_rect.left() + min(metrics.horizontalAdvance(name) + 14, name_rect.width() - 80)
            for tag in tags:
                chip_width = metrics.horizontalAdvance(tag) + 14
                if chip_x + chip_width > name_rect.right():
                    break
                chip = QRect(chip_x, name_rect.center().y() - 10, chip_width, 20)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#E5F1EC" if tag != "FIRMADO" else "#DDEFE4"))
                painter.drawRoundedRect(chip, 7, 7)
                painter.setPen(QColor("#285E4C"))
                painter.drawText(chip, int(Qt.AlignmentFlag.AlignCenter), tag)
                chip_x += chip_width + 5
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
        if is_supported_file_drop(event.mimeData()):
            self.setStyleSheet("QListWidget { border: 2px solid #2B7564; background: #F1F8F5; }")
            event.acceptProposedAction()
        elif event.mimeData().hasUrls() or event.mimeData().hasHtml() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if is_supported_file_drop(event.mimeData()):
            event.acceptProposedAction()
        elif event.mimeData().hasUrls() or event.mimeData().hasHtml() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        self.setStyleSheet("")
        try:
            paths = local_file_paths_from_mime(event.mimeData())
        except UnsafeFileDrop:
            self.window().notify_unsupported_file_drop()
            event.ignore()
            return
        if paths:
            self.window().import_paths(paths)
            event.acceptProposedAction()

    def startDrag(self, supported_actions):
        paths = [Path(item.data(PATH_ROLE)) for item in self.selectedItems()]
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def dragLeaveEvent(self, event):
        self.setStyleSheet("")
        super().dragLeaveEvent(event)

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
        self.setStyleSheet("")
        try:
            paths = local_file_paths_from_mime(event.mimeData())
        except UnsafeFileDrop:
            self.window().notify_unsupported_file_drop()
            event.ignore()
            return
        if paths:
            self.window().import_quick_access_paths(paths)
            event.acceptProposedAction()

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
