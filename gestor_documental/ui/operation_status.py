"""Compact, reusable visual state for background portal operations."""

from __future__ import annotations

from enum import Enum

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ..icons import ui_icon


class OperationState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


_PRESENTATION = {
    OperationState.IDLE: ("file", "#768681"),
    OperationState.RUNNING: ("refresh", "#2774A6"),
    OperationState.SUCCESS: ("check", "#2B7A55"),
    OperationState.ERROR: ("warning", "#C9493C"),
}


class OperationStatusIndicator(QWidget):
    """Icon and text that can later be fed by a background job manager."""

    def __init__(self, text: str = "", parent=None, *, compact: bool = False):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._compact = compact
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        self.message_label = QLabel()
        self.message_label.setObjectName("muted")
        self.message_label.setWordWrap(not compact)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.message_label, 1)
        if compact:
            # En la barra inferior el estado se lee por color; la explicación
            # completa queda en el tooltip para no ensuciar la interfaz.
            self.message_label.hide()
        self._state = OperationState.IDLE
        self.set_state(OperationState.IDLE, text)

    @property
    def state(self) -> OperationState:
        return self._state

    def set_state(self, state: OperationState, text: str):
        self._state = state
        icon_name, color = _PRESENTATION[state]
        if self._compact:
            icon_name = "refresh" if state is OperationState.RUNNING else "dot"
        self.icon_label.setPixmap(ui_icon(icon_name, color, 18).pixmap(QSize(18, 18)))
        self.message_label.setText(text)
        self.setToolTip(text)

    def setText(self, text: str):
        self.set_state(self._state, text)

    def text(self) -> str:
        return self.message_label.text()
