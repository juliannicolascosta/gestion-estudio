"""Lista que, vacía, orienta hacia la acción que la completa."""

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QListWidget


class EmptyStateList(QListWidget):
    """QListWidget que muestra un texto tenue y centrado cuando no hay filas.

    El texto informa por qué la lista está vacía y nombra la acción que la
    llena con el mismo verbo del botón, para que alguien nuevo conecte una
    cosa con la otra sin leer el manual. No altera datos ni selección.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._empty_title = ""
        self._empty_hint = ""

    def set_empty_state(self, title: str, hint: str = "") -> None:
        if (title, hint) == (self._empty_title, self._empty_hint):
            return
        self._empty_title = title
        self._empty_hint = hint
        self.viewport().update()

    def empty_state(self) -> tuple[str, str]:
        return self._empty_title, self._empty_hint

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() or not self._empty_title:
            return
        painter = QPainter(self.viewport())
        try:
            area = self.viewport().rect().adjusted(24, 0, -24, 0)
            title_font = QFont(self.font())
            hint_font = QFont(self.font())
            hint_font.setPointSizeF(max(hint_font.pointSizeF() - 0.5, 7.0))
            line = self.fontMetrics().height()
            block = line * (2 if self._empty_hint else 1) + (6 if self._empty_hint else 0)
            top = area.center().y() - block // 2
            painter.setFont(title_font)
            painter.setPen(QColor("#6F7A70"))
            painter.drawText(
                QRect(area.left(), top, area.width(), line + 4),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                self._empty_title,
            )
            if self._empty_hint:
                painter.setFont(hint_font)
                painter.setPen(QColor("#9AA39B"))
                painter.drawText(
                    QRect(area.left(), top + line + 6, area.width(), line + 4),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                    self._empty_hint,
                )
        finally:
            painter.end()
