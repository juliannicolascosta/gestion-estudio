from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..case_spreadsheet_import import (
    FIELD_LABELS,
    ImportOutcome,
    ImportRow,
    ImportStatus,
    SpreadsheetData,
    classify_rows,
    existing_cases,
    mapped_rows,
    read_spreadsheet,
)


STATUS_TEXT = {
    ImportStatus.NEW: "✓ Nuevo",
    ImportStatus.POSSIBLE_DUPLICATE: "≈ Posible duplicado",
    ImportStatus.EXISTS: "= Ya existe",
    ImportStatus.REVIEW: "! Requiere revisión",
}


class ColumnMappingDialog(QDialog):
    def __init__(self, data: SpreadsheetData, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Asignar columnas")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.combos: dict[str, QComboBox] = {}
        for field in ("actor", "defendant", "cause", "case_number", "notes", "original_caption"):
            combo = QComboBox()
            combo.addItem("No importar", None)
            for index, header in enumerate(data.headers):
                combo.addItem(header or f"Columna {index + 1}", index)
            detected = data.mapping.get(field)
            combo.setCurrentIndex(combo.findData(detected) if detected is not None else 0)
            self.combos[field] = combo
            form.addRow(FIELD_LABELS[field], combo)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continuar")
        buttons.accepted.connect(self._accept_mapping)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def mapping(self) -> dict[str, int]:
        return {
            field: int(combo.currentData())
            for field, combo in self.combos.items()
            if combo.currentData() is not None
        }

    def _accept_mapping(self):
        if "actor" not in self.mapping:
            QMessageBox.information(self, "Falta Actor", "Seleccioná la columna que contiene el actor.")
            return
        self.accept()


class CaseSpreadsheetImportDialog(QDialog):
    def __init__(self, study_root: Path, professional: str = "", parent=None):
        super().__init__(parent)
        self.study_root = study_root
        self.professional = professional
        self.rows: list[ImportRow] = []
        self.outcomes: list[ImportOutcome] = []
        self.setWindowTitle("Importar casos")
        self.setMinimumSize(920, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        header = QHBoxLayout()
        title = QLabel("IMPORTAR CASOS")
        title.setObjectName("eyebrow")
        header.addWidget(title)
        header.addStretch()
        choose = QPushButton("Seleccionar archivo…")
        choose.clicked.connect(self.choose_file)
        header.addWidget(choose)
        layout.addLayout(header)
        self.summary = QLabel("Seleccioná una planilla XLSX o CSV.")
        self.summary.setObjectName("muted")
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ("Importar", "Actor", "Demandado", "Causa", "Expediente", "Estado")
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._selection_changed)
        layout.addWidget(self.table, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.import_button = self.buttons.addButton("Importar casos", QDialogButtonBox.ButtonRole.AcceptRole)
        self.import_button.setObjectName("primary")
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self.run_import)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def choose_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar planilla", str(self.study_root), "Planillas (*.xlsx *.csv)"
        )
        if filename:
            self.load_file(Path(filename))

    def load_file(self, path: Path):
        try:
            data = read_spreadsheet(path)
            mapping = data.mapping
            if "actor" not in mapping or data.ambiguous:
                dialog = ColumnMappingDialog(data, self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                mapping = dialog.mapping
            self.rows = classify_rows(mapped_rows(data, mapping), existing_cases(self.study_root))
            self._fill_preview()
        except Exception as error:
            QMessageBox.warning(self, "No pudimos leer la planilla", str(error))

    def _fill_preview(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked if row.selected else Qt.CheckState.Unchecked)
            self.table.setItem(index, 0, check)
            values = (row.actor, row.defendant, row.cause, row.case_number or "—", STATUS_TEXT[row.status])
            for column, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 5 and row.reason:
                    item.setToolTip(row.reason)
                self.table.setItem(index, column, item)
        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()
        total = len(self.rows)
        numbered = sum(bool(row.case_number) for row in self.rows)
        duplicates = sum(row.status in {ImportStatus.EXISTS, ImportStatus.POSSIBLE_DUPLICATE} for row in self.rows)
        review = sum(row.status == ImportStatus.REVIEW for row in self.rows)
        self.summary.setText(
            f"{total} casos detectados · {numbered} con expediente · "
            f"{total - numbered} sin número · {duplicates} duplicados · {review} para revisar"
        )
        self._update_import_button()

    def _selection_changed(self, item: QTableWidgetItem):
        if item.column() == 0 and item.row() < len(self.rows):
            self.rows[item.row()].selected = item.checkState() == Qt.CheckState.Checked
            self._update_import_button()

    def _update_import_button(self):
        self.import_button.setEnabled(any(row.selected for row in self.rows))

    def run_import(self):
        # La ventana sólo confirma la selección. MainWindow ejecuta el lote en
        # segundo plano y concentra allí progreso, pausa y cancelación.
        self.accept()
