from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..case_activity import DEFAULT_ACTIVITY_SETTINGS, normalized_activity_settings


PROFESSIONAL_PROFILE_FIELDS = (
    ("name", "Nombre y apellido"),
    ("dni", "DNI"),
    ("cuit", "CUIT"),
    ("address", "Domicilio"),
    ("city", "Localidad"),
    ("province", "Provincia"),
    ("phone", "Teléfono"),
    ("tax_status", "Condición fiscal"),
    ("email", "Correo"),
    ("license_santa_fe", "Matrícula Santa Fe"),
    ("license_buenos_aires", "Matrícula Buenos Aires"),
    ("license_federal", "Matrícula Federal"),
    ("bank", "Banco"),
    ("account_type", "Tipo de cuenta"),
    ("account_number", "Número de cuenta"),
    ("cbu", "CBU"),
)


def _heading(title: str, subtitle: str) -> QVBoxLayout:
    layout = QVBoxLayout()
    heading = QLabel(title)
    heading.setObjectName("sectionTitle")
    layout.addWidget(heading)
    description = QLabel(subtitle)
    description.setObjectName("muted")
    description.setWordWrap(True)
    layout.addWidget(description)
    return layout


class ActivitySettingsDialog(QDialog):
    def __init__(self, settings: dict[str, object], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Semáforo de casos")
        self.setMinimumWidth(480)
        policy = normalized_activity_settings(settings)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.addLayout(_heading(
            "Semáforo del directorio",
            "La actividad considera archivos, datos del caso y novedades del portal.",
        ))
        form = QFormLayout()
        self.yellow_days = QSpinBox()
        self.yellow_days.setRange(1, 3650)
        self.yellow_days.setValue(int(policy["yellow_days"]))
        self.red_days = QSpinBox()
        self.red_days.setRange(2, 3650)
        self.red_days.setValue(int(policy["red_days"]))
        form.addRow("Amarillo desde (días)", self.yellow_days)
        form.addRow("Rojo desde (días)", self.red_days)
        self.color_edits: dict[str, QLineEdit] = {}
        for key, label in (
            ("green_color", "Color reciente"),
            ("yellow_color", "Color atención"),
            ("red_color", "Color inactivo"),
            ("archived_color", "Color archivado"),
        ):
            edit = QLineEdit(str(policy[key]))
            edit.setPlaceholderText("#RRGGBB")
            self.color_edits[key] = edit
            form.addRow(label, edit)
        layout.addLayout(form)
        self.show_recent = QCheckBox("Mostrar casos recientes (verdes)")
        self.show_recent.setChecked(bool(policy["show_recent"]))
        self.show_archived = QCheckBox("Mostrar casos archivados")
        self.show_archived.setChecked(bool(policy["show_archived"]))
        layout.addWidget(self.show_recent)
        layout.addWidget(self.show_archived)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict[str, object]:
        values = {
            "yellow_days": self.yellow_days.value(),
            "red_days": max(self.red_days.value(), self.yellow_days.value() + 1),
            "show_recent": self.show_recent.isChecked(),
            "show_archived": self.show_archived.isChecked(),
        }
        for key, edit in self.color_edits.items():
            color = QColor(edit.text().strip())
            values[key] = color.name() if color.isValid() else DEFAULT_ACTIVITY_SETTINGS[key]
        return values


class ProfessionalProfileDialog(QDialog):
    def __init__(self, profile: dict[str, str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Perfil del profesional")
        self.setMinimumSize(650, 620)
        profile = profile or {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.addLayout(_heading(
            "Datos del profesional",
            "Se cargan una vez y quedan disponibles en todos los modelos Word.",
        ))
        tabs = QTabWidget()
        self.edits: dict[str, QLineEdit] = {}
        groups = (
            ("Identidad y contacto", PROFESSIONAL_PROFILE_FIELDS[:9]),
            ("Matrículas y banco", PROFESSIONAL_PROFILE_FIELDS[9:]),
        )
        for title, fields in groups:
            tab = QWidget()
            form = QFormLayout(tab)
            form.setContentsMargins(16, 16, 16, 16)
            form.setSpacing(10)
            for key, label in fields:
                edit = QLineEdit(str(profile.get(key, "")))
                if key == "name":
                    edit.setPlaceholderText("Ej.: Julián Nicolás Costa")
                self.edits[key] = edit
                form.addRow(label, edit)
            tabs.addTab(tab, title)
        layout.addWidget(tabs, 1)
        note = QLabel("El PIN del token no se almacena. El acceso SISFE se configura por separado.")
        note.setObjectName("muted")
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar perfil")
        buttons.accepted.connect(self.accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.edits["name"].setFocus()

    def accept_if_valid(self):
        if self.edits["name"].text().strip():
            self.accept()

    def values(self) -> dict[str, str]:
        return {
            key: edit.text().strip()
            for key, edit in self.edits.items()
            if edit.text().strip()
        }


class SisfeAccessDialog(QDialog):
    """Preferencias locales; el CAPTCHA permanece dentro de la página SISFE."""

    def __init__(self, profile: dict[str, str] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Acceso SISFE")
        self.setMinimumWidth(460)
        profile = profile or {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.addLayout(_heading(
            "Acceso SISFE",
            "Se precarga en Matriculados; el CAPTCHA siempre se completa manualmente.",
        ))
        form = QFormLayout()
        self.user = QLineEdit(profile.get("user", ""))
        self.user.setPlaceholderText("Usuario SISFE")
        self.password = QLineEdit(profile.get("password", ""))
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Contraseña SISFE")
        form.addRow("Usuario", self.user)
        form.addRow("Contraseña", self.password)
        layout.addLayout(form)
        note = QLabel(
            "Por tu autorización, estos datos se guardan localmente en texto plano para agilizar el acceso."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.user.setFocus()

    def values(self) -> dict[str, str]:
        return {"user": self.user.text().strip(), "password": self.password.text()}
