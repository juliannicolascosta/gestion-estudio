"""Pestaña Pendientes: checklist de documentación pedida al cliente.

Primera pestaña extraída de ``MainWindow``. Es la de menor acoplamiento:
persiste sólo en los metadatos del caso (sin base de datos, hilos ni red),
de modo que puede vivir aparte recibiendo una referencia a la ventana para
lo que sí es compartido: el caso abierto, las pestañas, la barra de estado
y el refresco de Actividad.

``MainWindow`` conserva métodos delegados con los mismos nombres de
siempre, así que el resto de la aplicación y las pruebas no cambian.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
)

from ..icons import ui_icon
from ..services import read_case_metadata, save_case_metadata
from .empty_state_list import EmptyStateList
from .roles import PENDING_DUE_ROLE

PENDING_KEY = "Documentación pendiente"
RECEIVED_KEY = "Documentación recibida"
DUE_DATES_KEY = "Fechas de documentación pendiente"


def _lines(value: object) -> list[str]:
    return [" ".join(line.split()) for line in str(value or "").splitlines() if line.strip()]


def pending_document_due_dates(metadata: dict[str, str]) -> dict[str, datetime]:
    """Fechas de recordatorio guardadas, indexadas por nombre en minúsculas."""
    try:
        raw = json.loads(str(metadata.get(DUE_DATES_KEY, "{}")))
    except (json.JSONDecodeError, TypeError):
        return {}
    result = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            try:
                result[str(key).casefold()] = datetime.fromisoformat(str(value))
            except ValueError:
                continue
    return result


@dataclass(frozen=True)
class CardHelpers:
    """Piezas visuales compartidas con el resto de la ventana.

    Se inyectan para que este módulo no importe ``app`` (evita una
    dependencia circular y mantiene la pestaña probable por separado).
    """

    make_card: Callable
    section_heading: Callable
    decorate_button: Callable
    icon_button: Callable


class PendingDocumentsTab:
    def __init__(self, window, helpers: CardHelpers):
        self.window = window
        self.helpers = helpers
        self._loading = False

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------
    def build(self) -> QFrame:
        card, layout = self.helpers.make_card()
        header = QHBoxLayout()
        header.addLayout(
            self.helpers.section_heading(
                "Documentación pendiente",
                "Checklist de lo solicitado al cliente y todavía no recibido",
            )
        )
        header.addStretch()
        self.count_label = QLabel("Sin pendientes")
        self.count_label.setObjectName("muted")
        header.addWidget(self.count_label)
        layout.addLayout(header)

        self.list = EmptyStateList()
        self.list.setObjectName("pendingDocumentsList")
        self.list.setToolTip(
            "Arrastrá para reordenar · clic derecho para renombrar, fijar recordatorio o mover"
        )
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.show_menu)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.model().rowsMoved.connect(lambda: QTimer.singleShot(0, self.persist_order))
        self.list.itemSelectionChanged.connect(self.update_actions)
        self.list.itemChanged.connect(self.item_changed)
        layout.addWidget(self.list, 1)

        # Sólo quedan a la vista las tres acciones frecuentes. Reordenar se
        # hace arrastrando; renombrar, recordatorio, mover y vaciar viven en
        # el clic derecho, igual que las acciones secundarias de Archivos.
        actions = QHBoxLayout()
        add = QPushButton("Agregar pendiente")
        self.helpers.decorate_button(add, "plus")
        add.clicked.connect(self.add)
        self.delete_button = self.helpers.icon_button(
            "trash", "Borrar pendientes seleccionados", self.delete
        )
        self.received_button = QPushButton("Marcar como recibido")
        self.received_button.setObjectName("green")
        self.helpers.decorate_button(self.received_button, "check", "#FFFFFF")
        self.received_button.clicked.connect(self.complete)
        self.received_button.setEnabled(False)
        actions.addWidget(add)
        actions.addWidget(self.delete_button)
        actions.addStretch()
        actions.addWidget(self.received_button)
        layout.addLayout(actions)
        return card

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------
    @property
    def case(self):
        return self.window.case

    def reload(self):
        if not hasattr(self, "list"):
            return
        if self.case:
            self.list.set_empty_state(
                "Todavía no cargaste pendientes para este caso",
                "Agregar pendiente: lo que le pediste al cliente y aún no llegó",
            )
        else:
            self.list.set_empty_state("Elegí un caso para ver sus pendientes")
        self._loading = True
        self.list.clear()
        values: list[str] = []
        received: set[str] = set()
        due_dates: dict[str, datetime] = {}
        if self.case:
            metadata = read_case_metadata(self.case)
            values = _lines(metadata.get(PENDING_KEY, ""))
            received = set(_lines(metadata.get(RECEIVED_KEY, "")))
            due_dates = pending_document_due_dates(metadata)
        for value in values:
            is_received = value in received
            color = "#2B7564" if is_received else "#8A5B12"
            item = QListWidgetItem(ui_icon("check" if is_received else "file", color), value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if is_received else Qt.CheckState.Unchecked)
            item.setToolTip("Recibido" if is_received else "Pendiente de recibir")
            due_at = due_dates.get(value.casefold())
            item.setData(PENDING_DUE_ROLE, due_at.isoformat() if due_at else "")
            if due_at:
                item.setToolTip(
                    item.toolTip() + f" · recordatorio para el {due_at.strftime('%d/%m/%Y')}"
                )
            self.list.addItem(item)
        self._loading = False
        pending_count = sum(value not in received for value in values)
        received_count = len(values) - pending_count
        self.count_label.setText(
            "Sin documentos solicitados"
            if not values
            else f"{pending_count} pendientes · {received_count} recibidos"
        )
        window = self.window
        if hasattr(window, "work_tabs") and window.pending_tab_index >= 0:
            window.work_tabs.setTabText(window.pending_tab_index, f"Pendientes · {pending_count}")
        self.update_actions()
        window.reload_activity()

    def values_and_received(self) -> tuple[list[str], set[str]]:
        values = []
        received = set()
        for index in range(self.list.count()):
            item = self.list.item(index)
            values.append(item.text())
            if item.checkState() == Qt.CheckState.Checked:
                received.add(item.text())
        return values, received

    def update_actions(self):
        if not hasattr(self, "received_button"):
            return
        enabled = bool(self.list.selectedItems()) and self.case is not None
        self.received_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)

    def show_menu(self, position):
        if not self.case:
            return
        item = self.list.itemAt(position)
        if item is not None and not item.isSelected():
            self.list.setCurrentItem(item)
        selected = self.list.selectedItems()
        single = len(selected) == 1
        row = self.list.currentRow()
        count = self.list.count()
        menu = QMenu(self.window)
        menu.addAction("Marcar como recibido", self.complete).setEnabled(bool(selected))
        menu.addSeparator()
        menu.addAction("Renombrar…", self.rename).setEnabled(single)
        menu.addAction("Fecha objetivo y recordatorio…", self.set_due_date).setEnabled(single)
        menu.addSeparator()
        menu.addAction("Subir", lambda: self.move(-1)).setEnabled(single and row > 0)
        menu.addAction("Bajar", lambda: self.move(1)).setEnabled(single and 0 <= row < count - 1)
        menu.addSeparator()
        menu.addAction("Borrar", self.delete).setEnabled(bool(selected))
        menu.addAction("Vaciar la lista…", self.clear).setEnabled(count > 0)
        menu.exec(self.list.viewport().mapToGlobal(position))

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def add(self):
        if not self.window.require_case():
            return
        description, accepted = QInputDialog.getText(
            self.window, "Documentación pendiente", "Documento solicitado al cliente:"
        )
        normalized = " ".join(description.split()).strip()
        if not accepted or not normalized:
            return
        current = [self.list.item(index).text() for index in range(self.list.count())]
        if normalized.casefold() in {value.casefold() for value in current}:
            QMessageBox.information(
                self.window, "Documentación pendiente", "Ese documento ya figura como pendiente."
            )
            return
        current.append(normalized)
        self.save(current)
        # La persona se queda en la lista que está completando.
        for index in range(self.list.count()):
            if self.list.item(index).text() == normalized:
                self.list.setCurrentRow(index)
                break

    def complete(self):
        selected = self.list.selectedItems()
        if not selected or not self.case:
            return
        received = {item.text() for item in selected}
        stored_received = set(_lines(read_case_metadata(self.case).get(RECEIVED_KEY, "")))
        stored_received.update(received)
        values = [self.list.item(index).text() for index in range(self.list.count())]
        self.save(values, stored_received)
        label = next(iter(received)) if len(received) == 1 else f"{len(received)} documentos"
        self.window.statusBar().showMessage(f"Documentación recibida: {label}", 4500)

    def rename(self):
        selected = self.list.selectedItems()
        if len(selected) != 1 or not self.case:
            return
        item = selected[0]
        description, accepted = QInputDialog.getText(
            self.window, "Renombrar pendiente", "Nuevo nombre:", text=item.text()
        )
        normalized = " ".join(description.split()).strip()
        if not accepted or not normalized or normalized == item.text():
            return
        values, received = self.values_and_received()
        if normalized.casefold() in {value.casefold() for value in values if value != item.text()}:
            QMessageBox.information(
                self.window, "Documentación pendiente", "Ese documento ya figura en la lista."
            )
            return
        old = item.text()
        due_dates = pending_document_due_dates(read_case_metadata(self.case))
        values[values.index(old)] = normalized
        if old in received:
            received.remove(old)
            received.add(normalized)
        due = due_dates.pop(old.casefold(), None)
        if due:
            due_dates[normalized.casefold()] = due
        self.save(values, received, due_dates)

    def set_due_date(self):
        selected = self.list.selectedItems()
        if len(selected) != 1 or not self.case:
            return
        item = selected[0]
        current = str(item.data(PENDING_DUE_ROLE) or "")
        initial = datetime.fromisoformat(current).strftime("%d/%m/%Y") if current else ""
        raw, accepted = QInputDialog.getText(
            self.window,
            "Recordatorio de documentación",
            "Recordar en esta fecha (dd/mm/aaaa; vacío para quitar):",
            text=initial,
        )
        if not accepted:
            return
        due_at = None
        if raw.strip():
            try:
                due_at = datetime.strptime(raw.strip(), "%d/%m/%Y")
            except ValueError:
                QMessageBox.information(self.window, "Fecha inválida", "Usá el formato dd/mm/aaaa.")
                return
        values, received = self.values_and_received()
        due_dates = pending_document_due_dates(read_case_metadata(self.case))
        if due_at:
            due_dates[item.text().casefold()] = due_at
        else:
            due_dates.pop(item.text().casefold(), None)
        self.save(values, received, due_dates)

    def delete(self):
        selected = self.list.selectedItems()
        if not selected or not self.case:
            return
        if QMessageBox.question(
            self.window, "Borrar pendientes", "¿Querés borrar los pendientes seleccionados?"
        ) != QMessageBox.StandardButton.Yes:
            return
        removed = {item.text() for item in selected}
        values, received = self.values_and_received()
        self.save([value for value in values if value not in removed], received - removed)

    def clear(self):
        if not self.case or not self.list.count():
            return
        if QMessageBox.question(
            self.window, "Vaciar pendientes", "¿Querés vaciar toda la lista de documentación?"
        ) == QMessageBox.StandardButton.Yes:
            self.save([], set())

    def move(self, offset: int):
        row = self.list.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= self.list.count():
            return
        self._loading = True
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)
        self._loading = False
        self.persist_order()

    def persist_order(self):
        if self._loading or not self.case:
            return
        values, received = self.values_and_received()
        self.save(values, received)

    def item_changed(self, _item: QListWidgetItem):
        self.persist_order()

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------
    def save(
        self,
        values: list[str],
        received: set[str] | None = None,
        due_dates: dict[str, datetime] | None = None,
    ):
        if not self.case:
            return
        metadata = read_case_metadata(self.case)
        if values:
            metadata[PENDING_KEY] = "\n".join(values)
        else:
            metadata.pop(PENDING_KEY, None)
        if received is not None:
            ordered_received = [value for value in values if value in received]
            if ordered_received:
                metadata[RECEIVED_KEY] = "\n".join(ordered_received)
            else:
                metadata.pop(RECEIVED_KEY, None)
        stored_dates = due_dates if due_dates is not None else pending_document_due_dates(metadata)
        allowed = {value.casefold() for value in values}
        stored_dates = {
            key.casefold(): value for key, value in stored_dates.items() if key.casefold() in allowed
        }
        if stored_dates:
            metadata[DUE_DATES_KEY] = json.dumps(
                {key: value.isoformat() for key, value in stored_dates.items()},
                ensure_ascii=False,
                sort_keys=True,
            )
        else:
            metadata.pop(DUE_DATES_KEY, None)
        window = self.window
        try:
            save_case_metadata(self.case, metadata)
            window._loaded_metadata = read_case_metadata(self.case)
            window.sync_case_projection()
            window.update_more_metadata_count()
            window.update_case_badge()
            self.reload()
        except Exception as error:
            QMessageBox.warning(window, "No pudimos actualizar la documentación pendiente", str(error))
