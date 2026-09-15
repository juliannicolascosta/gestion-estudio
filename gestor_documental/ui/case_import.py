from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

from ..services import human_size, safe_name


class ExternalCaseImportDialog(QDialog):
    def __init__(
        self,
        source: Path,
        study_root: Path,
        file_count: int,
        total_bytes: int,
        parent=None,
    ):
        super().__init__(parent)
        self.source = source
        self.study_root = study_root
        self.setWindowTitle("Incorporar carpeta como caso")
        self.setMinimumWidth(620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        title = QLabel("Vista previa de la copia")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        explanation = QLabel(
            "Se copiará la carpeta completa. El origen permanecerá exactamente donde está y no será modificado."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        layout.addWidget(QLabel(f"Origen: {source}"))
        layout.addWidget(QLabel(f"Contenido: {file_count} archivos · {human_size(total_bytes)}"))
        layout.addWidget(QLabel("Nombre del caso"))
        self.name_edit = QLineEdit(safe_name(source.name))
        self.name_edit.textChanged.connect(self.refresh_destination)
        layout.addWidget(self.name_edit)
        self.destination_label = QLabel()
        self.destination_label.setObjectName("muted")
        self.destination_label.setWordWrap(True)
        layout.addWidget(self.destination_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Copiar como caso")
        buttons.accepted.connect(self.accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh_destination()

    @property
    def case_name(self) -> str:
        return safe_name(self.name_edit.text().strip())

    def refresh_destination(self):
        name = self.case_name
        target = self.study_root / name if name else self.study_root
        self.destination_label.setText(f"Destino: {target}")

    def accept_if_valid(self):
        if self.case_name:
            self.accept()
