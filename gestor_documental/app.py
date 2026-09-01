from __future__ import annotations

import hashlib
import sys
import re
import sqlite3
import json
from datetime import date, datetime
from pathlib import Path
from threading import Event

from PyQt6.QtCore import QMimeData, QObject, QSize, QThread, QTimer, Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QColor, QDrag, QFont, QIcon, QKeySequence, QPainter, QPalette, QShortcut
from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest, QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import (
    CASE_FIELDS,
    CASE_FIELD_LABELS,
    DEFAULT_PROFILE,
    PRESENTATION_PROFILES,
    VISIBLE_CASE_FIELDS,
    Case,
)
from .case_data import (
    GENERAL_REPEATED,
    GENERAL_SECTIONS,
    INTERVIEW_REPEATED,
    INTERVIEW_SECTIONS,
    RAEO_REPEATED,
    RAEO_SECTIONS,
    SYSTEM_METADATA_KEYS,
    FieldSpec,
    RepeatedSpec,
    all_defined_keys,
    build_case_caption,
    case_suggestions,
    computed_values,
    ensure_system_metadata,
    field_initial_value,
    raeo_effective_values,
    raeo_missing_fields,
)
from .case_registry import recent_case_novedades, register_case_as_expediente
from .sisfe_session import ManualSisfeSession
from .sisfe_sync import SisfeSessionRequired, SisfeSnapshotProviderMissing, SisfeSyncCoordinator
from .sisfe_browser import (
    browser_movement_detail_script,
    browser_sync_script,
    browser_validation_script,
    snapshot_from_browser_payload,
)
from .icons import file_icon_name, ui_icon
from .signing import (
    DigitalSignatureSession,
    SigningCertificate,
    SigningError,
    SigningUnavailable,
    discover_signing_certificates,
    select_current_certificates,
    signed_output_path,
)
from .services import (
    SettingsStore,
    CompilationCancelled,
    PDF_EXTENSIONS,
    add_model,
    can_convert_to_pdf,
    case_matches,
    compile_documents,
    create_case,
    create_writing,
    ensure_default_writing_template,
    focus_or_launch_signer,
    human_size,
    import_file,
    import_directory,
    list_cases,
    list_models,
    move_to_recycle_bin,
    normalize_filename,
    open_file,
    read_case_metadata,
    rename_case,
    rename_case_entry,
    rename_case_file,
    save_case_metadata,
    suggested_presentation_name,
    template_variable_name,
    split_pdf,
    study_library_path,
    unique_path,
)
from .sisfe_extractor import extract_cedula_text
from .study_database import StudyDatabase, study_database_path


PATH_ROLE = int(Qt.ItemDataRole.UserRole)
TYPE_ROLE = PATH_ROLE + 1
ROOT_ROLE = TYPE_ROLE + 1
MOVEMENT_ROLE = ROOT_ROLE + 1


def _format_sisfe_date(value: object) -> str:
    if not value:
        return "Sin fecha"
    text = str(value).strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            pass
    for pattern in ("%d/%m/%Y", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, pattern).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            pass
    return text

APP_STYLE = """
QMainWindow, QWidget#appRoot { background: #F4F5F3; color: #17211F; }
QWidget { font-family: "Segoe UI Variable Text", "Segoe UI"; font-size: 13px; }
QFrame#topBar { background: #163C35; border: 0; }
QLabel#brand { color: #FFFFFF; font-size: 20px; font-weight: 700; }
QLabel#brandSub { color: #BDD0CA; font-size: 11px; }
QLabel#professionalLabel { color: #BDD0CA; font-size: 10px; font-weight: 700; }
QFrame#sidebar { background: #E9EDE9; border-right: 1px solid #D4DCD7; }
QFrame#card { background: #FFFFFF; border: 1px solid #DDE3DF; border-radius: 14px; }
QFrame#softCard { background: #EEF5F1; border: 1px solid #D6E6DD; border-radius: 12px; }
QFrame#actionCard { background: #173F37; border: 0; border-radius: 14px; }
QLabel#eyebrow { color: #6D7E78; font-size: 10px; font-weight: 700; }
QLabel#sectionTitle { color: #17211F; font-size: 15px; font-weight: 700; }
QLabel#caseTitle { color: #17211F; font-size: 24px; font-weight: 700; }
QLabel#muted { color: #71817C; font-size: 11px; }
QLabel#actionTitle { color: white; font-size: 15px; font-weight: 700; }
QLabel#actionMuted { color: #BCD0C9; font-size: 11px; }
QLabel#caseBadge { background: #E9F2EE; color: #286454; border-radius: 8px; padding: 4px 8px; font-size: 10px; font-weight: 700; }
QLabel#caseBadge[pending="true"] { background: #FFF0D7; color: #8A5B12; }
QLabel#warning { background: #FFF0D7; color: #7B5316; border-radius: 8px; padding: 8px 10px; }
QLineEdit, QComboBox { background: #FFFFFF; border: 1px solid #C9D3CE; border-radius: 8px; padding: 8px 10px; min-height: 18px; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #2C7767; }
QLineEdit:read-only { background: #F5F7F5; color: #4F5E59; border-color: #E0E5E2; }
QComboBox#professional { background: #234E46; color: white; border: 1px solid #557A72; min-width: 210px; }
QPushButton { background: #FFFFFF; color: #25332F; border: 1px solid #C7D1CC; border-radius: 8px; padding: 9px 13px; font-weight: 600; }
QPushButton:hover { background: #F7F9F7; border-color: #8FA29B; }
QPushButton#primary { background: #CB5A36; color: white; border-color: #CB5A36; padding: 10px 16px; }
QPushButton#primary:hover { background: #B94B2B; border-color: #B94B2B; }
QPushButton#green { background: #2B7564; color: white; border-color: #2B7564; }
QPushButton#green:hover { background: #236353; border-color: #236353; }
QPushButton#onDark { background: #FFFFFF; color: #173F37; border: 0; padding: 11px 14px; }
QPushButton#onDark:hover { background: #ECF3F0; }
QPushButton#quiet { background: transparent; border: 0; color: #61716C; padding: 6px 8px; }
QPushButton#quiet:hover { background: #E8EEEA; color: #17211F; }
QPushButton#iconOnly { min-width: 38px; max-width: 38px; min-height: 38px; max-height: 38px; padding: 0; border-radius: 10px; }
QPushButton#iconQuiet { min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; padding: 0; border: 0; background: transparent; }
QPushButton#iconQuiet:hover { background: #E8EEEA; }
QTreeWidget, QListWidget { background: transparent; border: 0; outline: 0; }
QTreeWidget#caseTree { show-decoration-selected: 0; }
QTreeView::branch:selected, QTreeWidget::branch:selected { background: transparent; border: 0; }
QTreeWidget::item, QListWidget::item { border-radius: 7px; padding: 7px 7px; margin: 1px 0; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #EDF2EF; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #DCEAE4; color: #164D41; }
QListWidget#modelList { background: #F7F9F7; border: 1px solid #DDE3DF; border-radius: 10px; padding: 5px; }
QListWidget#modelList::item { background: #FFFFFF; border: 1px solid transparent; padding: 11px; margin: 2px; }
QListWidget#modelList::item:hover { background: #EDF4F1; color: #173F37; border-color: #C8DED5; }
QListWidget#modelList::item:selected { background: #DCEAE4; color: #173F37; border-color: #87B6A7; }
QFrame#actionCard QComboBox, QFrame#actionCard QLineEdit { background: #FFFFFF; color: #17211F; border: 0; }
QSplitter::handle { background: transparent; width: 8px; }
QScrollArea { border: 0; background: transparent; }
QTabWidget::pane { border: 0; background: transparent; top: -1px; }
QTabBar::tab { background: #E7ECE9; color: #53635E; border: 0; border-radius: 8px; padding: 9px 14px; margin: 0 5px 7px 0; font-weight: 600; }
QTabBar::tab:hover { background: #DDE7E2; color: #173F37; }
QTabBar::tab:selected { background: #2B7564; color: white; }
QPlainTextEdit { background: #FFFFFF; border: 1px solid #C9D3CE; border-radius: 8px; padding: 8px 10px; }
QPlainTextEdit:focus { border: 1px solid #2C7767; }
QMenu { background: white; border: 1px solid #D6DDD9; padding: 5px; }
QMenu::item { padding: 8px 24px 8px 10px; border-radius: 6px; }
QMenu::item:selected { background: #DCEAE4; color: #164D41; }
QStatusBar { background: white; color: #61716C; border-top: 1px solid #DDE3DF; }
"""


def make_card(object_name: str = "card") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName(object_name)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(9)
    return frame, layout


def section_heading(title: str, subtitle: str = "") -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setSpacing(1)
    heading = QLabel(title)
    heading.setObjectName("sectionTitle")
    layout.addWidget(heading)
    if subtitle:
        note = QLabel(subtitle)
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
    return layout


def decorate_button(button: QPushButton, icon_name: str, color: str = "#2B7564") -> QPushButton:
    button.setIcon(ui_icon(icon_name, color))
    button.setIconSize(QSize(19, 19))
    return button


def icon_button(
    icon_name: str,
    tooltip: str,
    slot,
    *,
    bordered: bool = False,
    color: str = "#2B7564",
) -> QPushButton:
    button = QPushButton()
    button.setObjectName("iconOnly" if bordered else "iconQuiet")
    button.setIcon(ui_icon(icon_name, color))
    button.setIconSize(QSize(19, 19))
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.clicked.connect(slot)
    return button


class ImportFileDialog(QDialog):
    def __init__(self, source: Path, parent=None):
        super().__init__(parent)
        self.source = source
        self.setWindowTitle("Agregar al caso")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        title = QLabel("Normalizar archivo")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        origin = QLabel(f"Original: {source.name}")
        origin.setObjectName("muted")
        origin.setWordWrap(True)
        layout.addWidget(origin)
        layout.addWidget(QLabel("Nombre dentro del caso"))
        self.name_edit = QLineEdit(normalize_filename(source.name))
        self.name_edit.selectAll()
        layout.addWidget(self.name_edit)
        self.convert = QCheckBox("Convertir a PDF al agregar")
        self.convert.setVisible(can_convert_to_pdf(source))
        self.convert.setChecked(can_convert_to_pdf(source))
        layout.addWidget(self.convert)
        hint = QLabel("El original no se modifica. Si el nombre ya existe, se agrega un número.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Agregar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def normalized_name(self) -> str:
        return self.name_edit.text().strip()

    @property
    def convert_to_pdf(self) -> bool:
        return can_convert_to_pdf(self.source) and self.convert.isChecked()


class RepeatedRowsWidget(QFrame):
    changed = pyqtSignal()

    def __init__(self, spec: RepeatedSpec, value: str = "", parent=None):
        super().__init__(parent)
        self.spec = spec
        self.setObjectName("softCard")
        self.rows: list[tuple[QWidget, list[QLineEdit]]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 11, 13, 11)
        layout.setSpacing(7)
        title_row = QHBoxLayout()
        title = QLabel(spec.title)
        title.setObjectName("sectionTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        add = icon_button("plus", f"Agregar {spec.title.casefold()}", self.add_row)
        title_row.addWidget(add)
        layout.addLayout(title_row)
        if spec.description:
            note = QLabel(spec.description)
            note.setObjectName("muted")
            note.setWordWrap(True)
            layout.addWidget(note)
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(6)
        layout.addLayout(self.rows_layout)
        for line in str(value or "").splitlines():
            if not line.strip():
                continue
            parts = [part.strip() for part in re.split(r"\s*[|│]\s*", line)]
            self.add_row(parts)

    def add_row(self, values=None):
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        supplied = list(values) if isinstance(values, (list, tuple)) else []
        edits = []
        for index, column in enumerate(self.spec.columns):
            edit = QLineEdit(supplied[index] if index < len(supplied) else "")
            edit.setPlaceholderText(column)
            edit.textChanged.connect(self.changed.emit)
            edits.append(edit)
            row.addWidget(edit, 1)
        remove = icon_button("trash", "Quitar esta fila", lambda: self.remove_row(row_widget))
        row.addWidget(remove)
        self.rows_layout.addWidget(row_widget)
        self.rows.append((row_widget, edits))
        if not supplied:
            edits[0].setFocus()

    def remove_row(self, widget: QWidget):
        self.rows = [row for row in self.rows if row[0] is not widget]
        widget.deleteLater()
        self.changed.emit()

    def value(self) -> str:
        lines = []
        for _, edits in self.rows:
            values = [" ".join(edit.text().split()).strip() for edit in edits]
            while values and not values[-1]:
                values.pop()
            if any(values):
                lines.append(" | ".join(values))
        return "\n".join(lines)


class ExtendedMetadataDialog(QDialog):
    def __init__(
        self,
        metadata: dict[str, str],
        parent=None,
        *,
        case_name: str = "",
        professional: str = "",
    ):
        super().__init__(parent)
        self.case_name = case_name
        self.professional = professional
        self._base_metadata = ensure_system_metadata(metadata, professional=professional)
        self.setWindowTitle("Datos ampliados del caso")
        self.setMinimumSize(820, 720)
        self.resize(940, 790)
        self._custom_rows: list[tuple[QWidget, QLineEdit, QLineEdit]] = []
        self.edits: dict[str, QWidget] = {}
        self._field_specs: dict[str, FieldSpec] = {}
        self.repeated: dict[str, RepeatedRowsWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)
        layout.addLayout(
            section_heading(
                "Más datos del caso",
                "La ficha se divide por uso. Todos los campos quedan disponibles para modelos Word.",
            )
        )
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self._build_general_tab()
        self._build_interview_tab()
        self._build_raeo_tab()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar datos")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh_dynamic_information()

    def _scroll_tab(self) -> tuple[QWidget, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 10, 8)
        content_layout.setSpacing(10)
        scroll.setWidget(content)
        return scroll, content_layout

    def _build_general_tab(self):
        tab, content = self._scroll_tab()
        system_card, system_layout = make_card("softCard")
        system_layout.addLayout(
            section_heading(
                "Datos generados por el sistema",
                "La carátula y el número de expediente se toman de los datos existentes.",
            )
        )
        self.system_summary = QLabel()
        self.system_summary.setWordWrap(True)
        system_layout.addWidget(self.system_summary)
        content.addWidget(system_card)
        self._add_sections(content, GENERAL_SECTIONS)
        self._add_repeated(content, GENERAL_REPEATED)
        self._add_custom_fields(content)
        content.addStretch()
        self.tabs.addTab(tab, "Datos generales")

    def _build_interview_tab(self):
        tab, content = self._scroll_tab()
        calculations, calculations_layout = make_card("softCard")
        calculations_layout.addLayout(
            section_heading(
                "Cálculos y alertas",
                "Se actualizan con lo cargado y no reemplazan la revisión profesional.",
            )
        )
        self.calculations_summary = QLabel()
        self.calculations_summary.setWordWrap(True)
        calculations_layout.addWidget(self.calculations_summary)
        self.suggestions_summary = QLabel()
        self.suggestions_summary.setObjectName("muted")
        self.suggestions_summary.setWordWrap(True)
        calculations_layout.addWidget(self.suggestions_summary)
        content.addWidget(calculations)
        self._add_sections(content, INTERVIEW_SECTIONS)
        self._add_repeated(content, INTERVIEW_REPEATED)
        content.addStretch()
        self.tabs.addTab(tab, "Entrevista inicial")

    def _build_raeo_tab(self):
        tab, content = self._scroll_tab()
        summary, summary_layout = make_card("softCard")
        summary_layout.addLayout(
            section_heading(
                "Datos reutilizados del expediente",
                "No se vuelven a cargar: se toman de Datos generales, la entrevista y el cuadro principal.",
            )
        )
        self.raeo_summary = QLabel()
        self.raeo_summary.setWordWrap(True)
        summary_layout.addWidget(self.raeo_summary)
        self.raeo_status = QLabel()
        self.raeo_status.setWordWrap(True)
        summary_layout.addWidget(self.raeo_status)
        content.addWidget(summary)
        self._add_sections(content, RAEO_SECTIONS)
        self._add_repeated(content, RAEO_REPEATED)
        content.addStretch()
        self.tabs.addTab(tab, "RAEO")

    def _add_sections(self, parent_layout: QVBoxLayout, sections):
        for section in sections:
            card, card_layout = make_card("softCard")
            card_layout.addLayout(section_heading(section.title, section.description))
            form = QFormLayout()
            form.setHorizontalSpacing(14)
            form.setVerticalSpacing(8)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for field in section.fields:
                label = self.template_field_label(field.label, template_variable_name(field.key))
                editor = self._make_field_editor(field)
                form.addRow(label, editor)
            card_layout.addLayout(form)
            parent_layout.addWidget(card)

    def _make_field_editor(self, field: FieldSpec) -> QWidget:
        value = field_initial_value(self._base_metadata, field)
        self._field_specs[field.key] = field
        if field.kind == "combo":
            editor = QComboBox()
            editor.setEditable(True)
            editor.addItem("")
            editor.addItems(field.choices)
            editor.setCurrentText(value)
            editor.currentTextChanged.connect(self.refresh_dynamic_information)
        elif field.kind == "textarea":
            editor = QPlainTextEdit(value)
            editor.setMaximumHeight(92)
            editor.setPlaceholderText(field.placeholder)
            editor.textChanged.connect(self.refresh_dynamic_information)
        else:
            editor = QLineEdit(value)
            editor.setPlaceholderText(field.placeholder)
            if field.kind == "money":
                editor.setPlaceholderText("Ej.: 850.000,00")
            elif field.kind == "integer":
                editor.setPlaceholderText("Número entero")
            editor.textChanged.connect(self.refresh_dynamic_information)
        editor.setToolTip(f"Variable para modelos: {{{{{template_variable_name(field.key)}}}}}")
        self.edits[field.key] = editor
        return editor

    def template_field_label(self, label_text: str, variable_name: str) -> QWidget:
        """Show each metadata field's Word code without making the form technical."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(label_text)
        label.setObjectName("muted")
        label.setWordWrap(True)
        code = f"{{{{{variable_name}}}}}"
        copy = icon_button("copy", f"Copiar {code}", lambda: None, color="#60736D")
        copy.clicked.connect(lambda: self.copy_template_code(code, copy))
        layout.addWidget(label)
        layout.addWidget(copy, 0, Qt.AlignmentFlag.AlignTop)
        return container

    @staticmethod
    def copy_template_code(code: str, button: QPushButton):
        QApplication.clipboard().setText(code)
        original = button.toolTip()
        button.setToolTip("Copiado")
        QTimer.singleShot(1200, lambda: button.setToolTip(original) if button else None)

    def _add_repeated(self, parent_layout: QVBoxLayout, specifications):
        for spec in specifications:
            editor = RepeatedRowsWidget(spec, self._base_metadata.get(spec.key, ""))
            editor.changed.connect(self.refresh_dynamic_information)
            self.repeated[spec.key] = editor
            parent_layout.addWidget(editor)

    def _add_custom_fields(self, parent_layout: QVBoxLayout):
        card, card_layout = make_card("softCard")
        card_layout.addLayout(
            section_heading(
                "Campos personalizados",
                "Usalos para datos propios del Estudio que todavía no estén contemplados.",
            )
        )
        self.custom_rows_layout = QVBoxLayout()
        self.custom_rows_layout.setSpacing(6)
        card_layout.addLayout(self.custom_rows_layout)
        known = set(CASE_FIELDS) | all_defined_keys()
        for section in GENERAL_SECTIONS + INTERVIEW_SECTIONS + RAEO_SECTIONS:
            for field in section.fields:
                known.update(field.aliases)
        for key, value in self._base_metadata.items():
            if key not in known:
                self.add_custom_row(key, value)
        add_custom = QPushButton("Agregar campo personalizado")
        decorate_button(add_custom, "plus")
        add_custom.clicked.connect(lambda: self.add_custom_row())
        card_layout.addWidget(add_custom, 0, Qt.AlignmentFlag.AlignLeft)
        parent_layout.addWidget(card)

    def add_custom_row(self, name: str = "", value: str = ""):
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("Nombre del dato")
        value_edit = QLineEdit(value)
        value_edit.setPlaceholderText("Valor")
        variable = icon_button("copy", "Copiar código del campo", lambda: None, color="#60736D")

        def refresh_variable(text: str):
            code = f"{{{{{template_variable_name(text)}}}}}" if text.strip() else "{{DATO}}"
            variable.setProperty("templateCode", code)
            variable.setToolTip(f"Copiar {code}")
            variable.setEnabled(bool(text.strip()))

        refresh_variable(name)
        name_edit.textChanged.connect(refresh_variable)
        variable.clicked.connect(
            lambda: self.copy_template_code(str(variable.property("templateCode")), variable)
        )
        remove = icon_button("trash", "Quitar este campo", lambda: self.remove_custom_row(row_widget))
        row.addWidget(name_edit, 2)
        row.addWidget(value_edit, 3)
        row.addWidget(variable)
        row.addWidget(remove)
        self.custom_rows_layout.addWidget(row_widget)
        self._custom_rows.append((row_widget, name_edit, value_edit))
        if not name:
            name_edit.setFocus()

    def remove_custom_row(self, widget: QWidget):
        self._custom_rows = [row for row in self._custom_rows if row[0] is not widget]
        widget.deleteLater()

    def _editor_value(self, editor: QWidget) -> str:
        if isinstance(editor, QPlainTextEdit):
            return editor.toPlainText().strip()
        if isinstance(editor, QComboBox):
            return editor.currentText().strip()
        if isinstance(editor, QLineEdit):
            return editor.text().strip()
        return ""

    def values(self) -> dict[str, str]:
        result = {
            key: str(self._base_metadata.get(key, "")).strip()
            for key in (SYSTEM_METADATA_KEYS | set(CASE_FIELDS))
            if str(self._base_metadata.get(key, "")).strip()
        }
        for field, editor in self.edits.items():
            value = self._editor_value(editor)
            if value:
                result[field] = value
            else:
                result.pop(field, None)
        for key, editor in self.repeated.items():
            value = editor.value()
            if value:
                result[key] = value
        for _, name_edit, value_edit in self._custom_rows:
            name = " ".join(name_edit.text().split()).strip()
            value = value_edit.text().strip()
            if name and value:
                result[name] = value
        return ensure_system_metadata(result, professional=self.professional)

    def refresh_dynamic_information(self, *args):
        if not hasattr(self, "system_summary"):
            return
        metadata = self.values()
        self._refresh_responsible_choices(metadata)
        caption = build_case_caption(metadata, self.case_name)
        case_number = metadata.get("CUIJ", "") or metadata.get("Número de expediente", "")
        self.system_summary.setText(
            f"<b>Carátula:</b> {caption or 'Sin datos suficientes'}<br>"
            f"<b>Número de expediente:</b> {case_number or 'Sin cargar'}<br>"
            f"<b>Identificación interna:</b> {metadata.get('Identificación interna del expediente', '')}<br>"
            f"<b>Registro creado:</b> {metadata.get('Fecha de creación del registro', '')} · "
            f"<b>Profesional creador:</b> {metadata.get('Profesional creador', 'Sin registrar')}"
        )
        computed = computed_values(metadata)
        calculation_rows = []
        labels = (
            ("EDAD_RAEO", "Edad sugerida para RAEO"),
            ("ANTIGUEDAD_LABORAL", "Antigüedad laboral"),
            ("DIAS_ACCIDENTE_DENUNCIA_ART", "Días entre accidente y denuncia ART"),
            ("DIAS_ACCIDENTE_ALTA_MEDICA", "Días entre accidente y alta"),
            ("DIAS_ALTA_REINGRESO", "Días entre alta y reingreso"),
            ("REMUNERACION_MENSUAL_ESTIMADA", "Remuneración mensual estimada"),
            ("DIFERENCIA_REMUNERACION_CONVENIO", "Diferencia con remuneración de convenio"),
        )
        for key, label in labels:
            value = computed.get(key, "")
            if value:
                prefix = "$ " if key.startswith(("REMUNERACION", "DIFERENCIA")) else ""
                calculation_rows.append(f"<b>{label}:</b> {prefix}{value}")
        self.calculations_summary.setText(
            "<br>".join(calculation_rows) if calculation_rows else "Cargá fechas y remuneraciones para ver cálculos automáticos."
        )
        suggestions = case_suggestions(metadata)
        self.suggestions_summary.setText(
            "<b>Sugerencias</b><br>• " + "<br>• ".join(suggestions)
            if suggestions
            else "Sin alertas con los datos actuales."
        )
        effective = raeo_effective_values(metadata)
        self.raeo_summary.setText(
            f"<b>Trabajador:</b> {effective['Actor'] or 'Sin cargar'} · "
            f"<b>Documento:</b> {effective['Documento'] or 'Sin cargar'} · "
            f"<b>Edad:</b> {effective['Edad'] or 'Sin calcular'}<br>"
            f"<b>Actividad:</b> {effective['Actividad o puesto'] or 'Sin cargar'} · "
            f"<b>Antigüedad:</b> {effective['Antigüedad'] or 'Sin calcular'}<br>"
            f"<b>Responsable principal:</b> {effective['Responsable principal'] or 'Sin cargar'}<br>"
            f"<b>Carátula:</b> {caption or 'Sin datos suficientes'}<br>"
            f"<b>Número de expediente:</b> {effective['CUIJ'] or 'Sin cargar'}"
        )
        missing = raeo_missing_fields(metadata)
        if missing:
            visible = ", ".join(missing[:7])
            extra = f" y {len(missing) - 7} más" if len(missing) > 7 else ""
            self.raeo_status.setObjectName("warning")
            self.raeo_status.setText(f"Faltan datos para emitir RAEO: {visible}{extra}.")
            self.tabs.setTabText(2, f"RAEO · {len(missing)} pendientes")
        else:
            self.raeo_status.setObjectName("caseBadge")
            self.raeo_status.setText("Datos necesarios para RAEO completos.")
            self.tabs.setTabText(2, "RAEO · completo")
        self.raeo_status.style().unpolish(self.raeo_status)
        self.raeo_status.style().polish(self.raeo_status)

    def _refresh_responsible_choices(self, metadata: dict[str, str]):
        editor = self.edits.get("Responsable principal RAEO")
        if not isinstance(editor, QComboBox):
            return
        current = editor.currentText().strip()
        options = []
        for value in (
            metadata.get("Empleador principal", ""),
            metadata.get("Demandado", ""),
        ):
            value = str(value).strip()
            if value and value not in options:
                options.append(value)
        for line in str(metadata.get("Responsables solidarios", "")).splitlines():
            value = re.split(r"\s*[|│]\s*", line, maxsplit=1)[0].strip()
            if value and value not in options:
                options.append(value)
        if current and current not in options:
            options.append(current)
        editor.blockSignals(True)
        try:
            editor.clear()
            editor.addItem("")
            editor.addItems(options)
            editor.setCurrentText(current)
        finally:
            editor.blockSignals(False)


class ModelPickerDialog(QDialog):
    def __init__(self, models: list[Path], parent=None):
        super().__init__(parent)
        self.models = models
        self.setWindowTitle("Crear escrito desde modelo")
        self.setMinimumSize(560, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(11)
        layout.addLayout(section_heading(
            "Elegí un modelo",
            "Buscá por nombre y definí el título del escrito en el mismo paso.",
        ))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar modelo…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_models)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setObjectName("modelList")
        self.list.setIconSize(QSize(22, 22))
        self.list.currentItemChanged.connect(self.model_changed)
        self.list.itemDoubleClicked.connect(lambda _: self.accept_if_valid())
        layout.addWidget(self.list, 1)
        layout.addWidget(QLabel("Nombre breve del escrito"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Ej.: APELACIÓN")
        layout.addWidget(self.title_edit)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Crear escrito")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.accept_if_valid)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.filter_models("")

    def filter_models(self, query: str):
        selected_path = self.selected_model
        self.list.clear()
        normalized = query.casefold().strip()
        for model in self.models:
            if normalized and normalized not in model.stem.casefold():
                continue
            item = QListWidgetItem(ui_icon("template", "#2563A7"), model.stem)
            item.setData(PATH_ROLE, str(model))
            item.setToolTip(str(model))
            self.list.addItem(item)
            if selected_path and model == selected_path:
                self.list.setCurrentItem(item)
        if self.list.count() and not self.list.currentItem():
            self.list.setCurrentRow(0)

    def model_changed(self, current: QListWidgetItem | None, previous=None):
        if current:
            self.title_edit.setText(Path(current.data(PATH_ROLE)).stem)
            self.title_edit.selectAll()
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(current is not None)

    def accept_if_valid(self):
        if self.selected_model and self.title.strip():
            self.accept()

    @property
    def selected_model(self) -> Path | None:
        item = self.list.currentItem()
        return Path(item.data(PATH_ROLE)) if item else None

    @property
    def title(self) -> str:
        return self.title_edit.text().strip()


class CompileNameDialog(QDialog):
    def __init__(self, case: Case, suggestion: str, identifier_missing: bool, parent=None):
        super().__init__(parent)
        self.case = case
        self.setWindowTitle("Nombre del PDF para firmar")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(11)
        layout.addLayout(section_heading(
            "Preparar archivo para firmar",
            "El nombre se conservará cuando lo arrastres a Xólido y facilita encontrarlo después.",
        ))
        if identifier_missing:
            warning = QLabel(
                "Este caso no tiene Actor ni Nombre corto. Revisá el primer componente para evitar confusiones."
            )
            warning.setObjectName("warning")
            warning.setWordWrap(True)
            layout.addWidget(warning)
        layout.addWidget(QLabel("Nombre del PDF"))
        self.name_edit = QLineEdit(suggestion)
        self.name_edit.selectAll()
        layout.addWidget(self.name_edit)
        hint = QLabel("Formato sugerido: ACTOR_2026-08-21_TÍTULO.pdf")
        hint.setObjectName("muted")
        layout.addWidget(hint)
        self.existing_options = QComboBox()
        self.existing_options.addItem("Reemplazar el PDF anterior (recomendado)", True)
        self.existing_options.addItem("Crear una nueva versión (_V2)", False)
        self.existing_options.setVisible(False)
        self.existing_label = QLabel("Ya existe un PDF con este nombre")
        self.existing_label.setObjectName("warning")
        self.existing_label.setVisible(False)
        layout.addWidget(self.existing_label)
        layout.addWidget(self.existing_options)
        self.name_edit.textChanged.connect(self.refresh_existing)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Compilar PDF")
        buttons.accepted.connect(self.accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh_existing()

    def refresh_existing(self):
        name = normalize_filename(self.name_edit.text().strip(), ".pdf")
        exists = bool(name) and (self.case.path / name).exists()
        self.existing_label.setVisible(exists)
        self.existing_options.setVisible(exists)

    def accept_if_valid(self):
        if self.file_name:
            self.accept()

    @property
    def file_name(self) -> str:
        return normalize_filename(self.name_edit.text().strip(), ".pdf") if self.name_edit.text().strip() else ""

    @property
    def replace_existing(self) -> bool:
        name = self.file_name
        return bool(name and (self.case.path / name).exists() and self.existing_options.currentData())


class CaseFilesList(QListWidget):
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


class CompilationList(QListWidget):
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
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
            self.window().handle_compilation_drop(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
            self.window().update_compilation_count()

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
            "Arrastrá documental desde Archivos del caso o desde afuera\nEl escrito nuevo se agrega al final",
        )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.window().remove_from_compilation()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.currentItem()
            if item:
                open_file(Path(item.data(PATH_ROLE)))
            event.accept()
            return
        super().keyPressEvent(event)


class CompileWorker(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self,
        case: Case,
        paths: list[Path],
        limit: int,
        output_name: str,
        replace_existing: bool = False,
    ):
        super().__init__()
        self.case = case
        self.paths = paths
        self.limit = limit
        self.output_name = output_name
        self.replace_existing = replace_existing
        self.cancel_event = Event()

    def cancel(self):
        self.cancel_event.set()

    @pyqtSlot()
    def run(self):
        try:
            result = compile_documents(
                self.case,
                self.paths,
                self.limit,
                self.output_name,
                self.progress.emit,
                self.cancel_event.is_set,
                self.replace_existing,
            )
            self.finished.emit(result)
        except CompilationCancelled:
            self.cancelled.emit()
        except Exception as error:
            self.failed.emit(str(error))


class CedulaExtractionWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, pdf: Path):
        super().__init__()
        self.pdf = pdf

    @pyqtSlot()
    def run(self):
        try:
            self.finished.emit(extract_cedula_text(self.pdf))
        except Exception as error:
            self.failed.emit(str(error))


class SignerDropDialog(QDialog):
    def __init__(self, pdf: Path, parent=None):
        super().__init__(parent)
        self.pdf = pdf
        self.setWindowTitle("Enviar a Xólido")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        title = QLabel("Xólido está listo")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        note = QLabel(
            "Arrastrá el archivo de abajo y soltalo en el cuadro de documentos de Xólido. "
            "Se usa la sesión que ya estaba abierta."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        self.file_item = CaseFilesList()
        self.file_item.setFixedHeight(64)
        item = QListWidgetItem(f"PDF  ·  {pdf.name}")
        item.setData(PATH_ROLE, str(pdf))
        item.setToolTip(str(pdf))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
        self.file_item.addItem(item)
        layout.addWidget(self.file_item)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class CertificatePickerDialog(QDialog):
    def __init__(self, certificates: list[SigningCertificate], parent=None):
        super().__init__(parent)
        self.certificates = certificates
        self.setWindowTitle("Elegir certificado de firma")
        self.setMinimumSize(580, 390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        layout.addLayout(
            section_heading(
                "Certificado para esta sesión",
                "El certificado elegido se reutilizará hasta cerrar la sesión de firma o salir del Gestor.",
            )
        )
        self.list = QListWidget()
        self.list.setObjectName("modelList")
        for index, certificate in enumerate(certificates):
            item = QListWidgetItem(ui_icon("signature", "#2B7564"), certificate.summary)
            item.setData(PATH_ROLE, index)
            item.setToolTip(f"Emisor: {certificate.issuer}\nToken: {certificate.token_label}")
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        layout.addWidget(self.list, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Usar certificado")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def selected_certificate(self) -> SigningCertificate | None:
        item = self.list.currentItem()
        return self.certificates[int(item.data(PATH_ROLE))] if item else None


class TokenPinDialog(QDialog):
    def __init__(self, certificate: SigningCertificate, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Iniciar sesión de firma")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(11)
        layout.addLayout(
            section_heading(
                "Desbloquear el token",
                "El PIN se usa una sola vez y no se guarda. La sesión permanece abierta mientras el Gestor siga abierto.",
            )
        )
        certificate_label = QLabel(certificate.summary)
        certificate_label.setObjectName("caseBadge")
        certificate_label.setWordWrap(True)
        layout.addWidget(certificate_label)
        layout.addWidget(QLabel("PIN del token"))
        self.pin_edit = QLineEdit()
        self.pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_edit.setPlaceholderText("Ingresá el PIN")
        self.pin_edit.returnPressed.connect(self.accept_if_valid)
        layout.addWidget(self.pin_edit)
        note = QLabel(
            "Por seguridad, cerrá manualmente la sesión desde el menú Firmar si te alejás del equipo."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Iniciar sesión")
        buttons.accepted.connect(self.accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.pin_edit.setFocus()

    def accept_if_valid(self):
        if self.pin_edit.text():
            self.accept()

    def take_pin(self) -> str:
        value = self.pin_edit.text()
        self.pin_edit.clear()
        return value


class SignPdfDialog(QDialog):
    def __init__(self, source: Path, certificate: SigningCertificate, parent=None):
        super().__init__(parent)
        self.source = source
        self.setWindowTitle("Firmar PDF")
        self.setMinimumWidth(590)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        layout.addLayout(
            section_heading(
                "Confirmar firma digital",
                "Se conservará el PDF original y se creará un nuevo archivo firmado en la misma carpeta.",
            )
        )
        source_label = QLabel(f"<b>Archivo:</b> {source.name}<br><b>Certificado:</b> {certificate.summary}")
        source_label.setWordWrap(True)
        layout.addWidget(source_label)
        layout.addWidget(QLabel("Nombre del archivo firmado"))
        self.name_edit = QLineEdit(signed_output_path(source).name)
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel("Motivo de la firma"))
        self.reason_edit = QLineEdit("Presentación judicial")
        layout.addWidget(self.reason_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Firmar ahora")
        buttons.accepted.connect(self.accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept_if_valid(self):
        if self.name_edit.text().strip():
            self.accept()

    @property
    def output(self) -> Path:
        return self.source.parent / normalize_filename(self.name_edit.text(), ".pdf")

    @property
    def reason(self) -> str:
        return self.reason_edit.text().strip()


class SisfeLoginDialog(QDialog):
    """Embedded manual login whose cookies live only for this process."""

    def __init__(self, session: ManualSisfeSession, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Iniciar sesión SISFE")
        self.setMinimumSize(980, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        note = QLabel(
            "Completá el acceso de Matriculados y el CAPTCHA aquí. Las cookies se usan sólo "
            "durante esta ejecución y no se guardan en el equipo."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        self.validation_status = QLabel("Completá Matriculados y CAPTCHA; luego validá la sesión.")
        self.validation_status.setObjectName("muted")
        self.validation_status.setWordWrap(True)
        layout.addWidget(self.validation_status)
        self.profile = QWebEngineProfile(self)
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
        )
        self.profile.cookieStore().cookieAdded.connect(self.capture_cookie)
        self._sync_timer: QTimer | None = None
        self.ready_for_sync = False
        self.browser = QWebEngineView()
        self.browser.setPage(QWebEnginePage(self.profile, self.browser))
        layout.addWidget(self.browser, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.use_session_button = buttons.addButton("Validar sesión", QDialogButtonBox.ButtonRole.AcceptRole)
        self.use_session_button.clicked.connect(self.accept_manual_session)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.session.mark_portal_opened()
        self._validate_after_load = False
        self.browser.setUrl(QUrl("https://sisfe.justiciasantafe.gov.ar/"))
        self.browser.loadFinished.connect(self.portal_loaded)

    def portal_loaded(self, ok: bool):
        path = self.browser.url().path().rstrip("/")
        self.ready_for_sync = bool(ok and path == "/buscar-expediente")
        if self._validate_after_load:
            self._validate_after_load = False
            if self.ready_for_sync:
                self.validate_loaded_session()
            else:
                self.validation_status.setText("No pudimos abrir el área de expedientes de SISFE. Reintentá.")
                self.use_session_button.setEnabled(True)

    def capture_cookie(self, cookie):
        name = bytes(cookie.name()).decode("utf-8", "ignore")
        value = bytes(cookie.value()).decode("utf-8", "ignore")
        self.session.attach_runtime_cookie(name, value, cookie.domain(), cookie.path())

    def accept_manual_session(self):
        # SISFE authorizes its internal endpoints from this application route.
        self.ready_for_sync = False
        self._validate_after_load = True
        self.use_session_button.setEnabled(False)
        self.validation_status.setText("Abriendo el área de expedientes y validando la sesión…")
        self.browser.setUrl(QUrl("https://sisfe.justiciasantafe.gov.ar/buscar-expediente"))

    def validate_loaded_session(self):
        self.browser.page().runJavaScript(browser_validation_script())
        timer = QTimer(self)
        timer.setInterval(250)
        elapsed = {"milliseconds": 0}
        self._sync_timer = timer

        def poll():
            elapsed["milliseconds"] += 250
            self.browser.page().runJavaScript(
                "window.__gestorSisfeValidation === null ? null : "
                "JSON.stringify(window.__gestorSisfeValidation)",
                lambda value: finish(value) if value else None,
            )
            if elapsed["milliseconds"] >= 15000:
                timer.stop()
                self._sync_timer = None
                self.validation_status.setText("SISFE demoró en validar. Esperá y presioná Validar sesión otra vez.")
                self.use_session_button.setEnabled(True)

        def finish(value):
            if not value or not timer.isActive():
                return
            timer.stop()
            self._sync_timer = None
            try:
                result = json.loads(str(value))
            except (TypeError, ValueError):
                result = {"ok": False, "error": "SISFE devolvió una validación inválida."}
            if not isinstance(result, dict):
                result = {"ok": False, "error": "SISFE devolvió una validación inválida."}
            if result.get("ok"):
                self.session.confirm_manual_login()
                self.ready_for_sync = True
                self.accept()
                return
            detail = result.get("status") or result.get("error") or "sin detalle"
            self.validation_status.setText(
                f"SISFE todavía no autorizó la sesión ({detail}). Esperá o completá el CAPTCHA y reintentá."
            )
            self.use_session_button.setEnabled(True)

        timer.timeout.connect(poll)
        timer.start()

    def request_snapshot(self, cuij: str, completed):
        """Query SISFE from its own browser context and return a plain snapshot."""
        if not self.ready_for_sync:
            completed(None, RuntimeError("SISFE todavía está preparando el área de expedientes."))
            return
        script = browser_sync_script(cuij)
        self.browser.page().runJavaScript(script)
        elapsed = {"milliseconds": 0}
        timer = QTimer(self)
        timer.setInterval(250)
        self._sync_timer = timer

        def poll():
            elapsed["milliseconds"] += 250
            self.browser.page().runJavaScript(
                "window.__gestorSisfeResult === null ? null : "
                "JSON.stringify(window.__gestorSisfeResult)",
                lambda value: finish(value) if value else None,
            )
            if elapsed["milliseconds"] >= 60000:
                timer.stop()
                self._sync_timer = None
                completed(None, RuntimeError("SISFE demoró demasiado en responder."))

        def finish(value):
            if not value or not timer.isActive():
                return
            timer.stop()
            self._sync_timer = None
            try:
                payload = json.loads(str(value))
                completed(snapshot_from_browser_payload(payload), None)
            except Exception as error:
                completed(None, error)

        timer.timeout.connect(poll)
        timer.start()

    def request_movement_detail(self, cuij: str, movement_id: str, completed):
        self._request_json_result(
            browser_movement_detail_script(cuij, movement_id),
            "__gestorSisfeMovement",
            45000,
            completed,
        )

    def _request_json_result(self, script: str, result_name: str, timeout_ms: int, completed):
        if self._sync_timer and self._sync_timer.isActive():
            completed(None, RuntimeError("SISFE todavía está procesando otra consulta."))
            return
        self.browser.page().runJavaScript(script)
        timer = QTimer(self)
        timer.setInterval(250)
        elapsed = {"milliseconds": 0}
        self._sync_timer = timer

        def poll():
            elapsed["milliseconds"] += 250
            expression = f"window.{result_name} === null ? null : JSON.stringify(window.{result_name})"
            self.browser.page().runJavaScript(
                expression,
                lambda value: finish(value) if value else None,
            )
            if elapsed["milliseconds"] >= timeout_ms:
                timer.stop()
                self._sync_timer = None
                completed(None, RuntimeError("SISFE demoró demasiado en responder."))

        def finish(value):
            if not value or not timer.isActive():
                return
            timer.stop()
            self._sync_timer = None
            try:
                payload = json.loads(str(value))
            except (TypeError, ValueError) as error:
                completed(None, RuntimeError("SISFE devolvió una respuesta inválida."))
                return
            if not isinstance(payload, dict):
                completed(None, RuntimeError("SISFE devolvió una respuesta inválida."))
                return
            if not payload.get("ok"):
                completed(None, RuntimeError(str(payload.get("error") or "SISFE no pudo completar la consulta.")))
                return
            completed(payload, None)

        timer.timeout.connect(poll)
        timer.start()


class SisfeCaseBrowserDialog(QDialog):
    """Official SISFE view that saves user-initiated downloads into one case."""

    def __init__(self, profile: QWebEngineProfile, remote_case_id: str, case: Case, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.case = case
        self._downloads: dict[int, Path] = {}
        self.setWindowTitle("Expediente en SISFE")
        self.setMinimumSize(1050, 760)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Vista oficial de SISFE. Descargá con los iconos del portal; los archivos se guardarán "
            "automáticamente en Documentos SISFE de este expediente."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.download_status = QLabel("Sin descargas en curso")
        self.download_status.setObjectName("muted")
        layout.addWidget(self.download_status)
        self.browser = QWebEngineView()
        self.browser.setPage(QWebEnginePage(profile, self.browser))
        self.browser.setUrl(
            QUrl(f"https://sisfe.justiciasantafe.gov.ar/detalle-expediente/{remote_case_id}")
        )
        layout.addWidget(self.browser, 1)
        self.profile.downloadRequested.connect(self.save_official_download)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save_official_download(self, download: QWebEngineDownloadRequest):
        directory = self.case.path / "Documentos SISFE"
        directory.mkdir(parents=True, exist_ok=True)
        filename = normalize_filename(download.suggestedFileName() or "Documento SISFE.pdf")
        target = unique_path(directory / filename)
        self._downloads[id(download)] = target
        self.download_status.setText(f"Descargando {target.name}…")
        download.setDownloadDirectory(str(target.parent))
        download.setDownloadFileName(target.name)
        download.stateChanged.connect(
            lambda state, request=download: self.finish_official_download(request, state)
        )
        download.accept()

    def finish_official_download(self, download: QWebEngineDownloadRequest, state):
        terminal_states = {
            QWebEngineDownloadRequest.DownloadState.DownloadCompleted,
            QWebEngineDownloadRequest.DownloadState.DownloadCancelled,
            QWebEngineDownloadRequest.DownloadState.DownloadInterrupted,
        }
        if state not in terminal_states:
            return
        target = self._downloads.pop(id(download), None)
        if state == QWebEngineDownloadRequest.DownloadState.DownloadCancelled:
            self.download_status.setText("Descarga cancelada")
            return
        if state == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
            detail = download.interruptReasonString() or "SISFE interrumpió la descarga"
            self.download_status.setText("No se pudo completar la descarga")
            QMessageBox.warning(self, "Descarga SISFE interrumpida", detail)
            return
        if not target or not target.is_file():
            self.download_status.setText("SISFE no generó el archivo esperado")
            return
        try:
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            duplicate = False
            with StudyDatabase(study_database_path(self.case.path.parent)) as database:
                expediente = database.import_case(self.case)
                existing = database.find_document_by_sha256(expediente.id, digest)
                existing_path = self.case.path / existing.relative_path if existing else None
                duplicate = bool(existing_path and existing_path.is_file())
                if not duplicate:
                    database.add_document(
                        expediente.id,
                        target.relative_to(self.case.path),
                        sha256=digest,
                        source="sisfe",
                    )
            if duplicate:
                move_to_recycle_bin([target])
                self.download_status.setText("El documento ya estaba guardado; no se creó otra copia")
            else:
                self.download_status.setText(f"Guardado: {target.name}")
            parent = self.parent()
            if isinstance(parent, MainWindow):
                parent.reload_case_files()
                message = (
                    "SISFE: el documento ya estaba guardado"
                    if duplicate
                    else f"SISFE: archivo guardado en {target.parent.name}"
                )
                parent.statusBar().showMessage(message, 6000)
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Documento descargado", f"El archivo se descargó, pero no pudimos registrarlo: {error}")

    def closeEvent(self, event):
        try:
            self.profile.downloadRequested.disconnect(self.save_official_download)
        except TypeError:
            pass
        super().closeEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, store: SettingsStore | None = None):
        super().__init__()
        self.store = store or SettingsStore()
        self.sisfe_session = ManualSisfeSession()
        self.sisfe_sync = SisfeSyncCoordinator(self.sisfe_session)
        self.base_template = ensure_default_writing_template(self.store.base_template)
        self.case: Case | None = None
        self.current_writing: Path | None = None
        self.last_compiled: Path | None = None
        self.last_signed: Path | None = None
        self.digital_signer = DigitalSignatureSession()
        self.case_directory: Path | None = None
        self._loading_files = False
        self._loading_quick = False
        self._loading_metadata = False
        self._metadata_editing = False
        self._metadata_dirty = False
        self._loaded_metadata: dict[str, str] = {}
        self._metadata_snapshot: dict[str, str] = {}
        self._compile_thread: QThread | None = None
        self._cedula_thread: QThread | None = None
        self._compile_worker: CompileWorker | None = None
        self._progress_dialog: QProgressDialog | None = None
        self._compile_cancelling = False
        self._close_after_compile = False
        self._signer_dialog: SignerDropDialog | None = None
        self._sisfe_login_dialog: SisfeLoginDialog | None = None
        self._sisfe_case_dialog: SisfeCaseBrowserDialog | None = None
        self.setWindowTitle("Gestor de documental")
        self.setMinimumSize(1120, 700)
        self.resize(1450, 880)
        self._build()
        self._install_shortcuts()
        self.reload_professionals()
        self.reload_cases()

    def _build(self):
        root = QWidget()
        root.setObjectName("appRoot")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QFrame()
        top.setObjectName("topBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(24, 12, 24, 12)
        brand_stack = QVBoxLayout()
        brand_stack.setSpacing(0)
        brand = QLabel("Gestor de documental")
        brand.setObjectName("brand")
        sub = QLabel("Casos, archivos y presentaciones en un mismo flujo")
        sub.setObjectName("brandSub")
        brand_stack.addWidget(brand)
        brand_stack.addWidget(sub)
        top_layout.addLayout(brand_stack)
        top_layout.addStretch()
        professional_stack = QVBoxLayout()
        professional_stack.setSpacing(2)
        professional_label = QLabel("PROFESIONAL")
        professional_label.setObjectName("professionalLabel")
        self.professional_combo = QComboBox()
        self.professional_combo.setObjectName("professional")
        self.professional_combo.currentTextChanged.connect(self.professional_changed)
        professional_stack.addWidget(professional_label)
        professional_stack.addWidget(self.professional_combo)
        top_layout.addLayout(professional_stack)
        add_professional = icon_button(
            "user-plus",
            "Agregar profesional",
            self.add_professional,
            bordered=True,
            color="#173F37",
        )
        top_layout.addWidget(add_professional, 0, Qt.AlignmentFlag.AlignBottom)
        outer.addWidget(top)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(270)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 18, 16, 16)
        side_layout.setSpacing(10)
        study_label = QLabel("UBICACIONES DEL ESTUDIO")
        study_label.setObjectName("eyebrow")
        side_layout.addWidget(study_label)
        self.study_name = QLabel("Sin carpeta definida")
        self.study_name.setObjectName("sectionTitle")
        self.study_name.setWordWrap(True)
        side_layout.addWidget(self.study_name)
        self.study_path = QLabel("Elegí dónde están las carpetas de tus casos")
        self.study_path.setObjectName("muted")
        self.study_path.setWordWrap(True)
        side_layout.addWidget(self.study_path)
        choose_study = QPushButton("Agregar ubicación")
        decorate_button(choose_study, "location-plus")
        choose_study.setToolTip("Agregar una carpeta local, de red o sincronizada")
        choose_study.clicked.connect(self.choose_study_root)
        side_layout.addWidget(choose_study)
        side_layout.addSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar caso, parte, expediente…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.reload_cases)
        side_layout.addWidget(self.search)
        new_case = QPushButton("Nuevo caso")
        new_case.setObjectName("primary")
        decorate_button(new_case, "folder-plus", "#FFFFFF")
        new_case.clicked.connect(self.new_case)
        side_layout.addWidget(new_case)
        self.case_tree = QTreeWidget()
        self.case_tree.setObjectName("caseTree")
        self.case_tree.setHeaderHidden(True)
        self.case_tree.setIndentation(18)
        tree_palette = self.case_tree.palette()
        tree_palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 0, 0, 0))
        tree_palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#164D41"))
        self.case_tree.setPalette(tree_palette)
        self.case_tree.itemSelectionChanged.connect(self.case_tree_changed)
        self.case_tree.itemDoubleClicked.connect(self.open_tree_case)
        self.case_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.case_tree.customContextMenuRequested.connect(self.show_case_menu)
        side_layout.addWidget(self.case_tree, 2)

        quick_header = QHBoxLayout()
        self.quick_label = QLabel("ACCESO RÁPIDO")
        self.quick_label.setObjectName("eyebrow")
        quick_header.addWidget(self.quick_label)
        quick_header.addStretch()
        self.quick_count = QLabel("0")
        self.quick_count.setObjectName("muted")
        quick_header.addWidget(self.quick_count)
        side_layout.addLayout(quick_header)
        quick_note = QLabel("Biblioteca siempre disponible para adjuntar o reutilizar")
        quick_note.setObjectName("muted")
        quick_note.setWordWrap(True)
        side_layout.addWidget(quick_note)
        self.quick_access = QuickAccessList()
        self.quick_access.setMinimumHeight(130)
        self.quick_access.setMaximumHeight(210)
        self.quick_access.itemDoubleClicked.connect(lambda _: self.open_selected_quick_file())
        self.quick_access.itemChanged.connect(self.finish_quick_rename)
        self.quick_access.customContextMenuRequested.connect(self.show_quick_menu)
        side_layout.addWidget(self.quick_access, 1)
        quick_actions = QHBoxLayout()
        quick_add = QPushButton("Agregar")
        decorate_button(quick_add, "paperclip")
        quick_add.clicked.connect(self.pick_quick_files)
        quick_folder = icon_button(
            "folder-open",
            "Abrir carpeta de Acceso rápido",
            self.open_quick_folder,
            bordered=True,
        )
        quick_actions.addWidget(quick_add)
        quick_actions.addWidget(quick_folder)
        side_layout.addLayout(quick_actions)
        models_button = QPushButton("Modelos de escritos")
        models_button.setObjectName("quiet")
        decorate_button(models_button, "template")
        models_button.clicked.connect(self.open_models_folder)
        side_layout.addWidget(models_button)
        body.addWidget(sidebar)

        workspace_wrap = QWidget()
        workspace_outer = QVBoxLayout(workspace_wrap)
        workspace_outer.setContentsMargins(20, 10, 20, 12)
        workspace_outer.setSpacing(8)

        case_header = QHBoxLayout()
        current_label = QLabel("CASO ACTUAL")
        current_label.setObjectName("eyebrow")
        case_header.addWidget(current_label)
        self.case_title = QLabel("Elegí un caso")
        self.case_title.setObjectName("caseTitle")
        case_header.addWidget(self.case_title)
        self.case_badge = QLabel()
        self.case_badge.setObjectName("caseBadge")
        self.case_badge.hide()
        case_header.addWidget(self.case_badge)
        case_header.addStretch()
        self.open_case_button = QPushButton("Abrir carpeta")
        decorate_button(self.open_case_button, "folder-open")
        self.open_case_button.clicked.connect(self.open_case_folder)
        case_header.addWidget(self.open_case_button)
        self.open_case_button.hide()
        workspace_outer.addLayout(case_header)

        self.workspace = QWidget()
        workspace_layout = QHBoxLayout(self.workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(12)

        information_column = QSplitter(Qt.Orientation.Vertical)
        information_column.setChildrenCollapsible(False)

        metadata_card, metadata_layout = make_card()
        metadata_layout.addLayout(section_heading("Datos del caso", "Se guardan como metadatos de esta carpeta"))
        fields_widget = QWidget()
        fields_grid = QGridLayout(fields_widget)
        fields_grid.setContentsMargins(0, 4, 0, 0)
        fields_grid.setHorizontalSpacing(10)
        fields_grid.setVerticalSpacing(4)
        self.metadata_edits: dict[str, QLineEdit] = {}
        for index, field in enumerate(VISIBLE_CASE_FIELDS):
            group = index // 4
            row = group * 2
            column = index % 4
            display_name = CASE_FIELD_LABELS.get(field, field)
            label = QLabel(display_name)
            label.setObjectName("muted")
            edit = QLineEdit()
            edit.setPlaceholderText(display_name)
            edit.setReadOnly(True)
            edit.textChanged.connect(self.metadata_changed)
            self.metadata_edits[field] = edit
            fields_grid.addWidget(label, row, column)
            fields_grid.addWidget(edit, row + 1, column)
        for column in range(4):
            fields_grid.setColumnStretch(column, 1)
        metadata_layout.addWidget(fields_widget)
        metadata_actions = QHBoxLayout()
        metadata_actions.setSpacing(7)
        self.edit_metadata_button = QPushButton("Editar datos")
        decorate_button(self.edit_metadata_button, "edit")
        self.edit_metadata_button.clicked.connect(self.begin_metadata_edit)
        self.more_metadata_button = QPushButton("Más datos")
        decorate_button(self.more_metadata_button, "plus")
        self.more_metadata_button.clicked.connect(self.open_extended_metadata)
        self.save_metadata_button = QPushButton("Guardar")
        self.save_metadata_button.setObjectName("green")
        decorate_button(self.save_metadata_button, "check", "#FFFFFF")
        self.save_metadata_button.clicked.connect(self.commit_metadata)
        self.save_metadata_button.hide()
        self.cancel_metadata_button = QPushButton("Cancelar")
        self.cancel_metadata_button.clicked.connect(self.cancel_metadata_edit)
        self.cancel_metadata_button.hide()
        metadata_actions.addWidget(self.edit_metadata_button)
        metadata_actions.addWidget(self.more_metadata_button)
        metadata_actions.addStretch()
        metadata_actions.addWidget(self.cancel_metadata_button)
        metadata_actions.addWidget(self.save_metadata_button)
        metadata_layout.addLayout(metadata_actions)
        information_column.addWidget(metadata_card)

        novedades_card, novedades_layout = make_card()
        novedades_header = QHBoxLayout()
        novedades_header.addLayout(
            section_heading("Novedades", "Movimientos recibidos por SISFE y otras fuentes")
        )
        novedades_header.addStretch()
        self.novedades_count = QLabel("Sin novedades")
        self.novedades_count.setObjectName("muted")
        novedades_header.addWidget(self.novedades_count)
        novedades_layout.addLayout(novedades_header)
        self.novedades_list = QListWidget()
        self.novedades_list.setObjectName("novedadesList")
        self.novedades_list.setFixedHeight(82)
        self.novedades_list.itemSelectionChanged.connect(self.update_novedad_actions)
        self.novedades_list.itemDoubleClicked.connect(lambda _: self.show_selected_novedad())
        novedades_layout.addWidget(self.novedades_list)
        novedades_actions = QHBoxLayout()
        self.sisfe_status = QLabel("SISFE sin iniciar")
        self.sisfe_status.setObjectName("muted")
        self.sisfe_status.setToolTip("Estado de la sesión y de la última consulta a SISFE")
        novedades_actions.addWidget(self.sisfe_status, 1)
        self.sisfe_connect_button = QPushButton("Abrir SISFE")
        decorate_button(self.sisfe_connect_button, "external")
        self.sisfe_connect_button.clicked.connect(self.open_sisfe_session)
        novedades_actions.addWidget(self.sisfe_connect_button)
        self.sisfe_sync_button = QPushButton("Sincronizar")
        self.sisfe_sync_button.setObjectName("green")
        decorate_button(self.sisfe_sync_button, "refresh", "#FFFFFF")
        self.sisfe_sync_button.clicked.connect(self.sync_sisfe)
        novedades_actions.addWidget(self.sisfe_sync_button)
        self.novedad_detail_button = icon_button(
            "external",
            "Ver detalle de la novedad seleccionada",
            self.show_selected_novedad,
            bordered=True,
        )
        self.novedad_detail_button.setEnabled(False)
        novedades_actions.addWidget(self.novedad_detail_button)
        novedades_layout.addLayout(novedades_actions)
        information_column.addWidget(novedades_card)

        files_card, files_layout = make_card()
        files_header = QHBoxLayout()
        files_header.addLayout(section_heading("Archivos del caso", "Archivos y carpetas · arrastrá hacia adentro o afuera"))
        files_header.addStretch()
        self.files_location = QLabel("Inicio")
        self.files_location.setObjectName("muted")
        files_header.addWidget(self.files_location)
        self.files_count = QLabel("0 archivos")
        self.files_count.setObjectName("muted")
        files_header.addWidget(self.files_count)
        files_layout.addLayout(files_header)
        self.case_files = CaseFilesList()
        self.case_files.itemDoubleClicked.connect(lambda _: self.open_selected_file())
        self.case_files.itemChanged.connect(self.finish_file_rename)
        self.case_files.customContextMenuRequested.connect(self.show_file_menu)
        files_layout.addWidget(self.case_files, 1)
        files_actions = QHBoxLayout()
        self.files_back = icon_button(
            "arrow-left",
            "Volver a la carpeta anterior",
            self.go_up_case_folder,
            bordered=True,
        )
        add_files = QPushButton("Agregar archivos")
        decorate_button(add_files, "paperclip")
        add_files.clicked.connect(self.pick_case_files)
        add_folder = QPushButton("Agregar carpeta")
        decorate_button(add_folder, "folder-plus")
        add_folder.clicked.connect(self.pick_case_folder)
        open_selected = icon_button(
            "external",
            "Abrir archivo o carpeta seleccionada",
            self.open_selected_file,
            bordered=True,
        )
        open_case_root = icon_button(
            "folder-open",
            "Abrir la carpeta principal del caso",
            self.open_case_folder,
            bordered=True,
        )
        add_to_compile = QPushButton("A compilación")
        add_to_compile.setObjectName("green")
        decorate_button(add_to_compile, "arrow-right", "#FFFFFF")
        add_to_compile.setToolTip("Agregar la selección a la compilación")
        add_to_compile.clicked.connect(self.add_selected_to_compilation)
        self.prepare_documents_button = QPushButton("Preparar documental")
        decorate_button(self.prepare_documents_button, "layers")
        self.prepare_documents_button.clicked.connect(self.open_preparation_dialog)
        files_actions.addWidget(self.files_back)
        files_actions.addWidget(add_files)
        files_actions.addWidget(add_folder)
        files_actions.addWidget(open_selected)
        files_actions.addWidget(open_case_root)
        files_actions.addStretch()
        files_actions.addWidget(add_to_compile)
        files_actions.addWidget(self.prepare_documents_button)
        files_layout.addLayout(files_actions)
        preparation_card, preparation_layout = make_card()
        prep_header = QHBoxLayout()
        prep_header.addLayout(section_heading("Documental a adjuntarse", "Ordená de arriba hacia abajo"))
        prep_header.addStretch()
        self.compilation_count = QLabel("0 elementos")
        self.compilation_count.setObjectName("muted")
        prep_header.addWidget(self.compilation_count)
        preparation_layout.addLayout(prep_header)

        writing_bar = QFrame()
        writing_bar.setObjectName("softCard")
        writing_bar.setMaximumHeight(64)
        writing_layout = QHBoxLayout(writing_bar)
        writing_layout.setContentsMargins(10, 6, 10, 6)
        writing_stack = QVBoxLayout()
        writing_stack.setSpacing(1)
        writing_label = QLabel("ESCRITO EN ELABORACIÓN")
        writing_label.setObjectName("eyebrow")
        self.writing_name = QLabel("Todavía no elegiste un escrito")
        self.writing_name.setWordWrap(True)
        writing_stack.addWidget(writing_label)
        writing_stack.addWidget(self.writing_name)
        writing_layout.addLayout(writing_stack, 1)
        self.writing_button = QPushButton("+ Escrito")
        self.writing_button.setObjectName("primary")
        decorate_button(self.writing_button, "file-plus", "#FFFFFF")
        self.writing_menu = QMenu(self)
        self.writing_menu.addAction("Escrito nuevo", self.new_blank_writing)
        self.writing_menu.addAction("Modificar modelo base en Word", self.open_base_template)
        self.writing_menu.addAction("Ver campos automáticos…", self.show_template_variables)
        self.writing_menu.addAction("Abrir guía de modelos", self.open_template_guide)
        self.writing_menu.addAction("Desde modelo…", self.new_writing_from_model)
        self.writing_menu.addSeparator()
        self.writing_menu.addAction("Agregar modelo…", self.add_writing_model)
        self.writing_menu.addAction("Abrir modelos", self.open_models_folder)
        self.writing_button.setMenu(self.writing_menu)
        writing_layout.addWidget(self.writing_button)
        preparation_layout.addWidget(writing_bar)

        self.compilation = CompilationList()
        preparation_layout.addWidget(self.compilation, 1)
        prep_actions = QHBoxLayout()
        remove = icon_button("trash", "Quitar de la compilación", self.remove_from_compilation)
        clear = icon_button("clear", "Vaciar la compilación", self.clear_compilation)
        move_up = icon_button("arrow-up", "Subir en el orden", lambda: self.move_compilation_item(-1))
        move_down = icon_button("arrow-down", "Bajar en el orden", lambda: self.move_compilation_item(1))
        prep_actions.addWidget(remove)
        prep_actions.addWidget(clear)
        prep_actions.addWidget(move_up)
        prep_actions.addWidget(move_down)
        prep_actions.addStretch()
        preparation_layout.addLayout(prep_actions)

        self.work_tabs = QTabWidget()
        self.work_tabs.setDocumentMode(True)
        self.files_tab_index = self.work_tabs.addTab(files_card, ui_icon("folder-open", "#2B7564"), "Archivos")
        self.compilation_tab_index = self.work_tabs.addTab(
            preparation_card,
            ui_icon("layers", "#2B7564"),
            "Compilación · 0",
        )
        information_column.addWidget(self.work_tabs)
        information_column.setSizes([155, 140, 620])
        workspace_layout.addWidget(information_column, 7)

        actions_card, actions_layout = make_card("actionCard")
        actions_card.setFixedWidth(235)
        actions_title = QLabel("Preparar presentación")
        actions_title.setObjectName("actionTitle")
        actions_layout.addWidget(actions_title)
        actions_note = QLabel("Se crea un único PDF dentro de la carpeta del caso.")
        actions_note.setObjectName("actionMuted")
        actions_note.setWordWrap(True)
        actions_layout.addWidget(actions_note)
        actions_layout.addSpacing(8)
        limit_label = QLabel("LÍMITE DEL ARCHIVO")
        limit_label.setObjectName("professionalLabel")
        actions_layout.addWidget(limit_label)
        self.limit_combo = QComboBox()
        for label, value in PRESENTATION_PROFILES.items():
            self.limit_combo.addItem(label, value)
        self.limit_combo.setCurrentIndex(self.limit_combo.findText(DEFAULT_PROFILE))
        actions_layout.addWidget(self.limit_combo)
        output_label = QLabel("NOMBRE AUTOMÁTICO")
        output_label.setObjectName("professionalLabel")
        actions_layout.addWidget(output_label)
        self.output_preview = QLabel("Se definirá al compilar")
        self.output_preview.setObjectName("actionMuted")
        self.output_preview.setWordWrap(True)
        actions_layout.addWidget(self.output_preview)
        # Conservado oculto por compatibilidad con integraciones anteriores. El
        # nombre visible se confirma recién al compilar.
        self.output_name = QLineEdit()
        self.output_name.hide()
        actions_layout.addSpacing(8)
        self.compile_button = QPushButton("Compilar PDF")
        self.compile_button.setObjectName("onDark")
        decorate_button(self.compile_button, "layers", "#173F37")
        self.compile_button.clicked.connect(self.compile_pdf)
        actions_layout.addWidget(self.compile_button)
        self.sign_button = QPushButton("Firmar")
        self.sign_button.setObjectName("onDark")
        decorate_button(self.sign_button, "signature", "#173F37")
        self.sign_button.clicked.connect(self.show_sign_menu)
        actions_layout.addWidget(self.sign_button)
        actions_layout.addStretch()
        last_label = QLabel("ÚLTIMO RESULTADO")
        last_label.setObjectName("professionalLabel")
        actions_layout.addWidget(last_label)
        self.last_output = QLabel("Aún no compilaste")
        self.last_output.setObjectName("actionMuted")
        self.last_output.setWordWrap(True)
        actions_layout.addWidget(self.last_output)
        workspace_layout.addWidget(actions_card)

        workspace_outer.addWidget(self.workspace, 1)
        body.addWidget(workspace_wrap, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Listo")

    def _install_shortcuts(self):
        self.new_case_shortcut = QShortcut(QKeySequence("Ctrl+Shift+N"), self)
        self.new_case_shortcut.activated.connect(self.new_case)
        self.new_writing_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        self.new_writing_shortcut.activated.connect(self.writing_button.showMenu)
        self.add_file_shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        self.add_file_shortcut.activated.connect(self.pick_case_files)
        self.compile_shortcut = QShortcut(QKeySequence("Ctrl+P"), self)
        self.compile_shortcut.activated.connect(self.compile_pdf)
        self.rename_shortcut = QShortcut(QKeySequence("F2"), self)
        self.rename_shortcut.activated.connect(self.rename_selected_file)

    def open_preparation_dialog(self):
        self.work_tabs.setCurrentIndex(self.compilation_tab_index)
        self.compilation.setFocus()

    def reload_professionals(self):
        self.professional_combo.blockSignals(True)
        self.professional_combo.clear()
        self.professional_combo.addItems(self.store.settings.professionals)
        index = self.professional_combo.findText(self.store.settings.current_professional)
        self.professional_combo.setCurrentIndex(max(0, index))
        self.professional_combo.blockSignals(False)

    def professional_changed(self, name: str):
        if name:
            self.store.set_professional(name)

    def add_professional(self):
        name, accepted = QInputDialog.getText(
            self,
            "Agregar profesional",
            "Nombre que aparecerá en modelos y presentaciones:",
        )
        if accepted and name.strip():
            self.store.add_professional(name)
            self.reload_professionals()

    def configure_mev_profile(self):
        professional = self.professional_combo.currentText().strip()
        if not professional:
            return
        profile = self.store.settings.mev_profiles.get(professional, {})
        user, accepted = QInputDialog.getText(self, "Acceso MEV", "Usuario MEV:", text=profile.get("user", ""))
        if not accepted:
            return
        department, accepted = QInputDialog.getText(self, "Acceso MEV", "Departamento judicial preferido:", text=profile.get("department", ""))
        if accepted:
            self.store.set_mev_profile(professional, user, department)
            self.statusBar().showMessage("Preferencias MEV guardadas. La contraseña no se almacena.", 5000)

    def choose_study_root(self):
        initial = str(self.store.settings.study_root or Path.home())
        folder = QFileDialog.getExistingDirectory(
            self,
            "Agregá una ubicación del Estudio",
            initial,
        )
        if folder:
            self.store.add_study_root(Path(folder))
            self.case = None
            self.reload_cases()

    def reload_cases(self, select_path: Path | None = None):
        roots = self.store.settings.study_roots
        active_root = self.store.settings.study_root
        self.case_tree.blockSignals(True)
        self.case_tree.clear()
        if len(roots) == 1:
            self.study_name.setText(roots[0].name or "Estudio")
            self.study_path.setText(str(roots[0]))
        elif roots:
            self.study_name.setText(f"{len(roots)} ubicaciones")
            active_name = active_root.name if active_root else "ninguna"
            self.study_path.setText(f"Activa: {active_name}")
        else:
            self.study_name.setText("Sin ubicaciones")
            self.study_path.setText("Agregá la carpeta local, compartida o sincronizada")

        query = self.search.text() if hasattr(self, "search") else ""
        selected_item = None
        active_item = None
        for root_path in roots:
            root_item = QTreeWidgetItem([root_path.name or str(root_path)])
            root_item.setIcon(0, ui_icon("building", "#2774A6"))
            root_item.setData(0, ROOT_ROLE, str(root_path))
            root_item.setToolTip(0, str(root_path))
            font = root_item.font(0)
            font.setBold(True)
            root_item.setFont(0, font)
            self.case_tree.addTopLevelItem(root_item)
            if root_path == active_root:
                active_item = root_item

            if root_path.is_dir():
                for case in list_cases(root_path):
                    if not case_matches(case, query):
                        continue
                    item = QTreeWidgetItem([case.name])
                    item.setIcon(0, ui_icon("folder", "#D0952D"))
                    item.setData(0, PATH_ROLE, str(case.path))
                    item.setToolTip(0, str(case.path))
                    root_item.addChild(item)
                    if select_path and case.path == select_path:
                        selected_item = item
                    elif self.case and case.path == self.case.path:
                        selected_item = item
            else:
                unavailable = QTreeWidgetItem(["Ubicación no disponible"])
                unavailable.setDisabled(True)
                unavailable.setIcon(
                    0,
                    ui_icon("warning", "#B36A24"),
                )
                root_item.addChild(unavailable)
            root_item.setExpanded(True)

        if selected_item:
            self.case_tree.setCurrentItem(selected_item)
        elif active_item:
            self.case_tree.setCurrentItem(active_item)
        self.case_tree.blockSignals(False)
        self.reload_quick_access()
        if selected_item:
            self.set_case(Case(Path(selected_item.data(0, PATH_ROLE))))
        elif not self.case or not self.case.path.is_dir():
            self.set_case(None)

    def case_tree_changed(self):
        item = self.case_tree.currentItem()
        path = item.data(0, PATH_ROLE) if item else None
        root = item.data(0, ROOT_ROLE) if item else None
        selected_path = Path(path) if path else None
        if (
            self.case
            and selected_path != self.case.path
            and not self.confirm_pending_metadata_change()
        ):
            self.restore_case_tree_selection()
            return
        if path:
            case = Case(selected_path)
            self.store.set_active_study_root(case.path.parent)
            self.update_study_summary()
            self.reload_quick_access()
            self.set_case(case)
        elif root:
            self.activate_study_root(Path(root))

    def open_tree_case(self, item: QTreeWidgetItem):
        path = item.data(0, PATH_ROLE)
        root = item.data(0, ROOT_ROLE)
        target = Path(path or root) if path or root else None
        if target and target.is_dir():
            open_file(target)

    def show_case_menu(self, point):
        item = self.case_tree.itemAt(point)
        path = item.data(0, PATH_ROLE) if item else None
        root = item.data(0, ROOT_ROLE) if item else None
        if not path and not root:
            return
        self.case_tree.setCurrentItem(item)
        menu = QMenu(self)
        if path:
            menu.addAction("Abrir carpeta", lambda: open_file(Path(path)))
            menu.addAction("Renombrar caso…", lambda: self.rename_case_folder(Case(Path(path))))
        else:
            root_path = Path(root)
            open_action = menu.addAction("Abrir ubicación", lambda: open_file(root_path))
            open_action.setEnabled(root_path.is_dir())
            menu.addAction("Usar esta ubicación", lambda: self.activate_study_root(root_path))
            menu.addAction("Nuevo caso aquí…", lambda: self.new_case_in_root(root_path))
            menu.addSeparator()
            menu.addAction(
                "Quitar del Gestor…",
                lambda: self.remove_study_root(root_path),
            )
        menu.exec(self.case_tree.mapToGlobal(point))

    def update_study_summary(self):
        roots = self.store.settings.study_roots
        active = self.store.settings.study_root
        if len(roots) == 1:
            self.study_name.setText(roots[0].name or "Estudio")
            self.study_path.setText(str(roots[0]))
        elif roots:
            self.study_name.setText(f"{len(roots)} ubicaciones")
            self.study_path.setText(f"Activa: {active.name if active else 'ninguna'}")
        else:
            self.study_name.setText("Sin ubicaciones")
            self.study_path.setText("Agregá la carpeta local, compartida o sincronizada")

    def activate_study_root(self, root: Path):
        self.store.set_active_study_root(root)
        if self.case and self.case.path.parent != root:
            self.set_case(None)
        self.update_study_summary()
        self.reload_quick_access()
        self.statusBar().showMessage(f"Ubicación activa: {root.name}", 3500)

    def remove_study_root(self, root: Path):
        answer = QMessageBox.question(
            self,
            "Quitar ubicación del Gestor",
            f"¿Querés dejar de mostrar {root.name}?\n\n"
            "No se borrará la carpeta ni ninguno de sus casos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self.case and self.case.path.parent == root:
            self.set_case(None)
        self.store.remove_study_root(root)
        self.reload_cases()

    def rename_case_folder(self, case: Case):
        name, accepted = QInputDialog.getText(
            self,
            "Renombrar caso",
            "Nuevo nombre de la carpeta:",
            text=case.name,
        )
        if not accepted or not name.strip() or name.strip() == case.name:
            return
        try:
            was_current = self.case is not None and self.case.path == case.path
            renamed = rename_case(case, name)
            if was_current:
                self.case = renamed
            self.reload_cases(renamed.path)
            self.statusBar().showMessage(f"Caso renombrado: {renamed.name}", 4500)
        except Exception as error:
            QMessageBox.warning(self, "No pudimos renombrar el caso", str(error))

    def set_case(self, case: Case | None):
        self.case = case
        self.case_directory = case.path if case else None
        self.current_writing = None
        self.last_compiled = None
        self.compilation.clear()
        self.last_output.setText("Aún no compilaste")
        self.workspace.setEnabled(case is not None)
        self.open_case_button.setEnabled(case is not None)
        self.sisfe_sync_button.setEnabled(case is not None)
        if not case:
            self.case_title.setText("Elegí un caso")
            self.load_metadata({})
            self.case_badge.hide()
            self.reload_case_files()
            self.update_writing_label()
            self.update_compilation_count()
            self.update_output_preview()
            self.reload_novedades()
            return
        try:
            # El registro sólo vincula la carpeta existente con SQLite y
            # conserva los archivos y el JSON del gestor como están.
            register_case_as_expediente(case)
        except (OSError, RuntimeError, sqlite3.Error) as error:
            # Una ubicación de sólo lectura no debe impedir el uso del gestor
            # documental que ya funciona sobre sus carpetas.
            self.statusBar().showMessage(
                f"No se pudo vincular el expediente: {error}", 7000
            )
        self.case_title.setText(case.name)
        self.load_metadata(read_case_metadata(case))
        self.reload_novedades()
        self.reload_case_files()
        self.update_writing_label()
        self.update_compilation_count()
        self.update_case_badge()
        self.update_output_preview()

    def open_sisfe_session(self):
        dialog = SisfeLoginDialog(self.sisfe_session, self)
        if dialog.exec() and self.sisfe_session.active:
            self._sisfe_login_dialog = dialog
            self.sisfe_status.setText("Preparando el área de expedientes SISFE…")
        else:
            self.sisfe_status.setText("Sesión SISFE sin confirmar")

    def sync_sisfe(self):
        if not self.require_case():
            return
        if not self.sisfe_session.active or not self._sisfe_login_dialog:
            QMessageBox.information(
                self, "Sesión SISFE", "Iniciá y confirmá la sesión manual de SISFE primero."
            )
            return
        if not self._sisfe_login_dialog.ready_for_sync:
            QMessageBox.information(
                self,
                "Sesión SISFE",
                "SISFE todavía está abriendo el área de expedientes. Esperá unos segundos y reintentá.",
            )
            return
        cuij = read_case_metadata(self.case).get("CUIJ", "")
        if not cuij.strip():
            QMessageBox.information(self, "Sincronización SISFE", "El caso necesita CUIJ para sincronizar.")
            return
        self.sisfe_sync_button.setEnabled(False)
        self.sisfe_status.setText("Consultando novedades SISFE…")

        def completed(snapshot, error):
            self.sisfe_sync_button.setEnabled(True)
            if error:
                self.sisfe_status.setText("No se pudo sincronizar")
                QMessageBox.warning(self, "No pudimos sincronizar SISFE", str(error))
                return
            try:
                result = self.sisfe_sync.importer.import_snapshot(
                    self.case, snapshot, self.case.path / "Documentos SISFE"
                )
            except Exception as import_error:
                self.sisfe_status.setText("No se pudo importar")
                QMessageBox.warning(self, "No pudimos importar SISFE", str(import_error))
                return
            self.reload_novedades()
            self.reload_case_files()
            self.sisfe_status.setText("Sesión manual lista para sincronizar")
            self.statusBar().showMessage(
                f"SISFE sincronizado: {result.movements_registered} novedades nuevas", 5000
            )

        self._sisfe_login_dialog.request_snapshot(cuij, completed)

    def reload_novedades(self):
        self.novedades_list.clear()
        self.update_novedad_actions()
        if not self.case:
            self.novedades_count.setText("Sin novedades")
            return
        try:
            movements = recent_case_novedades(self.case)
        except (OSError, RuntimeError, sqlite3.Error) as error:
            self.novedades_count.setText("No disponibles")
            self.novedades_list.addItem(f"No pudimos cargar las novedades: {error}")
            return
        for movement in movements:
            stamp = movement.occurred_at.strftime("%d/%m/%Y %H:%M") if movement.occurred_at else "Sin fecha"
            item = QListWidgetItem(ui_icon("bell", "#2B7564"), f"{movement.title}\n{stamp} · {movement.source.upper()}")
            item.setToolTip(movement.external_id or movement.source)
            item.setData(
                MOVEMENT_ROLE,
                {
                    "external_id": movement.external_id,
                    "title": movement.title,
                    "source": movement.source,
                    "occurred_at": movement.occurred_at.isoformat() if movement.occurred_at else "",
                },
            )
            self.novedades_list.addItem(item)
        count = len(movements)
        self.novedades_count.setText(
            "Sin novedades" if not count else f"{count} novedad{'es' if count != 1 else ''}"
        )

    def update_novedad_actions(self):
        if hasattr(self, "novedad_detail_button"):
            self.novedad_detail_button.setEnabled(self.novedades_list.currentItem() is not None)

    def selected_novedad_data(self) -> dict | None:
        item = self.novedades_list.currentItem()
        data = item.data(MOVEMENT_ROLE) if item else None
        return data if isinstance(data, dict) else None

    def show_selected_novedad(self):
        movement = self.selected_novedad_data()
        if not movement:
            return
        if movement.get("source") != "sisfe" or not movement.get("external_id"):
            QMessageBox.information(
                self,
                "Detalle de la novedad",
                f"{movement.get('title', 'Movimiento')}\n\nEsta novedad no proviene de SISFE.",
            )
            return
        if not self._sisfe_login_dialog or not self.sisfe_session.active:
            QMessageBox.information(
                self,
                "Sesión SISFE",
                "Iniciá la sesión SISFE para consultar el detalle y sus documentos.",
            )
            return
        cuij = read_case_metadata(self.case).get("CUIJ", "") if self.case else ""
        self.novedad_detail_button.setEnabled(False)
        self.sisfe_status.setText("Consultando detalle SISFE…")

        def completed(detail, error):
            self.update_novedad_actions()
            self.sisfe_status.setText("Sesión manual lista para sincronizar")
            if error:
                QMessageBox.warning(self, "No pudimos consultar la novedad", str(error))
                return
            stamp = _format_sisfe_date(detail.get("occurred_at"))
            observation = detail.get("observation") or "Sin observaciones adicionales."
            attachments = []
            if detail.get("has_primary_document"):
                attachments.append("documento principal")
            if detail.get("has_additional_documents"):
                attachments.append("adjuntos adicionales")
            if detail.get("has_related_organizations"):
                attachments.append("organismos relacionados")
            box = QMessageBox(self)
            box.setWindowTitle("Detalle de la novedad SISFE")
            box.setIcon(QMessageBox.Icon.Information)
            box.setText(str(detail.get("title") or movement.get("title") or "Movimiento SISFE"))
            box.setInformativeText(
                f"Fecha: {stamp}\n"
                f"Contenido: {observation}\n"
                f"Disponible: {', '.join(attachments) if attachments else 'sin adjuntos'}"
            )
            open_button = box.addButton(
                "Abrir expediente en SISFE",
                QMessageBox.ButtonRole.ActionRole,
            )
            box.addButton(QMessageBox.StandardButton.Close)
            box.exec()
            if box.clickedButton() is open_button:
                self.open_sisfe_case(str(detail.get("remote_case_id") or ""))

        self._sisfe_login_dialog.request_movement_detail(
            cuij,
            str(movement["external_id"]),
            completed,
        )

    def open_sisfe_case(self, remote_case_id: str):
        if not remote_case_id or not self._sisfe_login_dialog or not self.case:
            return
        self._sisfe_case_dialog = SisfeCaseBrowserDialog(
            self._sisfe_login_dialog.profile,
            remote_case_id,
            self.case,
            self,
        )
        self._sisfe_case_dialog.show()
        self._sisfe_case_dialog.raise_()
        self._sisfe_case_dialog.activateWindow()

    def require_study(self) -> bool:
        if self.store.settings.study_root:
            return True
        QMessageBox.information(
            self,
            "Agregá una ubicación del Estudio",
            "Primero elegí una carpeta local, de red o sincronizada que contenga casos.",
        )
        return False

    def require_case(self) -> bool:
        if self.case:
            return True
        QMessageBox.information(self, "Elegí un caso", "Seleccioná o creá un caso para continuar.")
        return False

    def new_case(self):
        if not self.require_study():
            return
        self.new_case_in_root(self.store.settings.study_root)

    def new_case_in_root(self, root: Path):
        if not root.is_dir():
            QMessageBox.warning(
                self,
                "Ubicación no disponible",
                "Conectá o sincronizá esta ubicación antes de crear el caso.",
            )
            return
        name, accepted = QInputDialog.getText(
            self,
            "Nuevo caso",
            f"Nombre de la carpeta del caso en {root.name}:",
        )
        if not accepted or not name.strip():
            return
        try:
            self.store.set_active_study_root(root)
            case = create_case(root, name)
            self.reload_cases(case.path)
            self.begin_metadata_edit()
            self.statusBar().showMessage(f"Caso creado: {case.name}", 5000)
        except Exception as error:
            QMessageBox.critical(self, "No pudimos crear el caso", str(error))

    def open_case_folder(self):
        if self.require_case():
            open_file(self.case.path)

    def quick_library(self, create: bool = False) -> Path | None:
        root = self.store.settings.study_root
        if not root or not root.is_dir():
            return None
        return study_library_path(root, create)

    def reload_quick_access(self, select_path: Path | None = None):
        self._loading_quick = True
        self.quick_access.blockSignals(True)
        self.quick_access.clear()
        try:
            library = self.quick_library(create=True)
            self.quick_access.setEnabled(library is not None)
            active = self.store.settings.study_root
            self.quick_label.setText(
                f"ACCESO RÁPIDO · {active.name.upper()}"
                if active
                else "ACCESO RÁPIDO"
            )
            if library:
                self.quick_access.setToolTip(str(library))
                for path in Case(library).files():
                    item = QListWidgetItem(path.name)
                    item.setIcon(self.icon_for_path(path))
                    item.setData(PATH_ROLE, str(path))
                    item.setToolTip(f"{path}\n{human_size(path.stat().st_size)}")
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsDragEnabled)
                    self.quick_access.addItem(item)
                    if select_path and path == select_path:
                        self.quick_access.setCurrentItem(item)
        except OSError as error:
            self.quick_access.setEnabled(False)
            self.quick_access.setToolTip(str(error))
        finally:
            self.quick_access.blockSignals(False)
            self._loading_quick = False
        self.quick_count.setText(str(self.quick_access.count()))

    def selected_quick_paths(self) -> list[Path]:
        return [Path(item.data(PATH_ROLE)) for item in self.quick_access.selectedItems()]

    def pick_quick_files(self):
        files = QFileDialog.getOpenFileNames(self, "Agregar a Acceso rápido")[0]
        self.import_quick_access_paths([Path(path) for path in files])

    def import_quick_access_paths(self, paths: list[Path]) -> list[Path]:
        library = self.quick_library(create=True)
        if not library:
            QMessageBox.information(
                self,
                "Elegí una ubicación del Estudio",
                "Primero activá la ubicación que tendrá este Acceso rápido.",
            )
            return []
        imported = []
        target_case = Case(library)
        for source in paths:
            if not source.is_file():
                continue
            try:
                if source.parent.resolve() == library.resolve():
                    target = source
                else:
                    dialog = ImportFileDialog(source, self)
                    dialog.setWindowTitle("Agregar a Acceso rápido")
                    if not dialog.exec():
                        continue
                    target = import_file(
                        target_case,
                        source,
                        dialog.normalized_name,
                        dialog.convert_to_pdf,
                    )
                imported.append(target)
            except Exception as error:
                QMessageBox.critical(self, "No pudimos agregar el archivo", str(error))
        if imported:
            self.reload_quick_access(imported[-1])
            self.statusBar().showMessage("Acceso rápido actualizado", 4000)
        return imported

    def open_selected_quick_file(self):
        paths = self.selected_quick_paths()
        if paths:
            open_file(paths[0])

    def open_quick_folder(self):
        library = self.quick_library(create=True)
        if library:
            open_file(library)
        else:
            self.require_study()

    def finish_quick_rename(self, item: QListWidgetItem):
        if self._loading_quick:
            return
        source = Path(item.data(PATH_ROLE))
        if item.text() == source.name:
            return
        try:
            renamed = rename_case_file(source, item.text())
            self.reload_quick_access(renamed)
        except Exception as error:
            self._loading_quick = True
            item.setText(source.name)
            self._loading_quick = False
            QMessageBox.warning(self, "No pudimos renombrar", str(error))

    def show_quick_menu(self, point):
        item = self.quick_access.itemAt(point)
        if not item:
            return
        self.quick_access.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction("Abrir", self.open_selected_quick_file)
        menu.addAction("Renombrar", lambda: self.quick_access.editItem(item))
        if self.case:
            menu.addAction("Copiar al caso actual…", lambda: self.import_paths(self.selected_quick_paths()))
        menu.addSeparator()
        menu.addAction("Enviar a la Papelera", self.remove_selected_quick_files)
        menu.exec(self.quick_access.mapToGlobal(point))

    def remove_selected_quick_files(self):
        paths = self.selected_quick_paths()
        if not paths:
            return
        label = paths[0].name if len(paths) == 1 else f"{len(paths)} archivos"
        answer = QMessageBox.question(
            self,
            "Quitar de Acceso rápido",
            f"¿Querés enviar {label} a la Papelera de Windows?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            move_to_recycle_bin(paths)
            self.reload_quick_access()
        except Exception as error:
            QMessageBox.warning(self, "No pudimos quitar los archivos", str(error))

    def load_metadata(self, metadata: dict[str, str]):
        self._loading_metadata = True
        try:
            for field, edit in self.metadata_edits.items():
                edit.setText(metadata.get(field, ""))
        finally:
            self._loading_metadata = False
        self._loaded_metadata = dict(metadata)
        self._metadata_snapshot = self.basic_metadata_values()
        self._metadata_dirty = False
        self.set_metadata_editing(False)
        self.update_more_metadata_count()

    def basic_metadata_values(self) -> dict[str, str]:
        return {
            field: edit.text().strip()
            for field, edit in self.metadata_edits.items()
            if edit.text().strip()
        }

    def set_metadata_editing(self, editing: bool):
        self._metadata_editing = bool(editing and self.case)
        for edit in self.metadata_edits.values():
            edit.setReadOnly(not self._metadata_editing)
        self.edit_metadata_button.setVisible(not self._metadata_editing)
        self.more_metadata_button.setVisible(not self._metadata_editing)
        self.save_metadata_button.setVisible(self._metadata_editing)
        self.cancel_metadata_button.setVisible(self._metadata_editing)

    def begin_metadata_edit(self):
        if not self.case:
            return
        self._metadata_snapshot = self.basic_metadata_values()
        self._metadata_dirty = False
        self.set_metadata_editing(True)
        self.metadata_edits["Actor"].setFocus()
        self.metadata_edits["Actor"].selectAll()

    def metadata_changed(self):
        if self._loading_metadata or not self._metadata_editing:
            return
        self._metadata_dirty = self.basic_metadata_values() != self._metadata_snapshot
        self.save_metadata_button.setText("Guardar cambios" if self._metadata_dirty else "Guardar")

    def commit_metadata(self) -> bool:
        if self._loading_metadata or not self.case:
            return False
        metadata = dict(self._loaded_metadata)
        for field in VISIBLE_CASE_FIELDS:
            value = self.metadata_edits[field].text().strip()
            if value:
                metadata[field] = value
            else:
                metadata.pop(field, None)
        try:
            save_case_metadata(self.case, metadata)
            self._loaded_metadata = read_case_metadata(self.case)
            self._metadata_snapshot = self.basic_metadata_values()
            self._metadata_dirty = False
            self.set_metadata_editing(False)
            self.update_more_metadata_count()
            self.update_case_badge()
            self.update_output_preview()
            self.statusBar().showMessage("Datos del caso guardados", 2500)
            return True
        except Exception as error:
            QMessageBox.warning(
                self,
                "No pudimos guardar los datos del caso",
                f"Los archivos del caso no fueron modificados.\n\nDetalle: {error}",
            )
            return False

    def save_metadata(self):
        """Compatibilidad con llamadas anteriores; ahora el guardado es explícito."""
        return self.commit_metadata()

    def cancel_metadata_edit(self):
        if not self.case:
            return
        self.load_metadata(self._loaded_metadata)
        self.statusBar().showMessage("Cambios descartados", 2200)

    def confirm_pending_metadata_change(self) -> bool:
        if not self._metadata_editing:
            return True
        if not self._metadata_dirty:
            self.cancel_metadata_edit()
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Hay datos sin guardar")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("Cambiaste datos del caso actual.")
        box.setInformativeText("¿Querés guardarlos antes de continuar?")
        save_button = box.addButton("Guardar", QMessageBox.ButtonRole.AcceptRole)
        discard_button = box.addButton("Descartar", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton("Seguir editando", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_button:
            return self.commit_metadata()
        if clicked is discard_button:
            self.cancel_metadata_edit()
            return True
        if clicked is cancel_button:
            return False
        return False

    def restore_case_tree_selection(self):
        if not self.case:
            return
        self.case_tree.blockSignals(True)
        try:
            for root_index in range(self.case_tree.topLevelItemCount()):
                root = self.case_tree.topLevelItem(root_index)
                for child_index in range(root.childCount()):
                    child = root.child(child_index)
                    if child.data(0, PATH_ROLE) == str(self.case.path):
                        self.case_tree.setCurrentItem(child)
                        return
        finally:
            self.case_tree.blockSignals(False)

    def open_extended_metadata(self):
        if not self.case:
            return
        metadata = dict(self._loaded_metadata)
        metadata.update(self.basic_metadata_values())
        dialog = ExtendedMetadataDialog(
            metadata,
            self,
            case_name=self.case.name,
            professional=self.professional_combo.currentText(),
        )
        if not dialog.exec():
            return
        payload = self.basic_metadata_values()
        payload.update(dialog.values())
        try:
            save_case_metadata(self.case, payload)
            self.load_metadata(read_case_metadata(self.case))
            self.update_case_badge()
            self.update_output_preview()
            self.statusBar().showMessage("Datos ampliados guardados", 3000)
        except Exception as error:
            QMessageBox.warning(self, "No pudimos guardar los datos", str(error))

    def update_more_metadata_count(self):
        if not hasattr(self, "more_metadata_button"):
            return
        count = sum(
            1
            for key, value in self._loaded_metadata.items()
            if key not in CASE_FIELDS and str(value).strip()
        )
        self.more_metadata_button.setText(f"Más datos · {count}" if count else "Más datos")

    def update_case_badge(self):
        if not self.case:
            self.case_badge.hide()
            return
        has_data = any(str(value).strip() for value in self._loaded_metadata.values())
        self.case_badge.setText(
            f"{self.case.path.parent.name.upper()} · DATOS CARGADOS"
            if has_data
            else f"{self.case.path.parent.name.upper()} · SIN DATOS"
        )
        self.case_badge.setProperty("pending", not has_data)
        self.case_badge.style().unpolish(self.case_badge)
        self.case_badge.style().polish(self.case_badge)
        self.case_badge.show()

    def update_output_preview(self):
        if not hasattr(self, "output_preview"):
            return
        if not self.case:
            self.output_preview.setText("Se definirá al compilar")
            return
        suggestion = suggested_presentation_name(self.case, self.current_writing)
        self.output_preview.setText(f"Se propondrá al compilar:\n{suggestion}")

    def reload_case_files(self, select_path: Path | None = None):
        self._loading_files = True
        self.case_files.blockSignals(True)
        self.case_files.clear()
        if self.case:
            document_categories: dict[Path, str] = {}
            try:
                with StudyDatabase(study_database_path(self.case.path.parent)) as database:
                    expediente = database.find_expediente_by_folder(self.case.path)
                    if expediente:
                        document_categories = {
                            (self.case.path / document.relative_path).resolve(): document.category
                            for document in database.list_documents(expediente.id)
                        }
            except (OSError, RuntimeError, sqlite3.Error):
                # La carpeta sigue siendo la fuente principal; una etiqueta no
                # debe impedir mostrar sus archivos.
                document_categories = {}
            current = self.case_directory or self.case.path
            if not current.is_dir() or not self.path_is_inside_case(current):
                current = self.case.path
                self.case_directory = current
            entries = sorted(
                (
                    path for path in current.iterdir()
                    if not path.name.startswith(".")
                ),
                key=lambda path: (0 if path.is_dir() else 1, path.name.casefold()),
            )
            for path in entries:
                category = document_categories.get(path.resolve(), "otro")
                label = self.case_file_label(path, category)
                item = QListWidgetItem(label)
                item.setIcon(self.icon_for_path(path))
                item.setData(PATH_ROLE, str(path))
                if path.is_dir():
                    item.setToolTip(f"Carpeta\n{path}")
                else:
                    item.setToolTip(
                        f"{self.case_file_description(path)}\n{path}\n"
                        f"{human_size(path.stat().st_size)}"
                        + (
                            f"\nClasificación: {self.document_category_label(category)}"
                            if category != "otro"
                            else ""
                        )
                    )
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
                self.case_files.addItem(item)
                if select_path and path == select_path:
                    self.case_files.setCurrentItem(item)
            relative = current.relative_to(self.case.path)
            self.files_location.setText(
                "Inicio" if not relative.parts else "  ›  ".join(relative.parts)
            )
            self.files_location.setToolTip(str(current))
            self.files_back.setEnabled(current != self.case.path)
        else:
            self.files_location.setText("Inicio")
            self.files_location.setToolTip("")
            self.files_back.setEnabled(False)
        self.case_files.blockSignals(False)
        self._loading_files = False
        count = self.case_files.count()
        self.files_count.setText(f"{count} elemento" if count == 1 else f"{count} elementos")

    def icon_for_path(self, path: Path) -> QIcon:
        if path.is_dir():
            return ui_icon("folder", "#D0952D")
        name, color = file_icon_name(path.suffix)
        return ui_icon(name, color)

    def case_file_description(self, path: Path) -> str:
        if path.is_dir():
            return "Carpeta"
        stem = path.stem.upper()
        if path.suffix.casefold() in {".doc", ".docx", ".dot", ".dotx"}:
            return "Documento editable en Word"
        if path.suffix.casefold() == ".pdf":
            if "FIRMADO" in stem or "SIGNED" in stem:
                return "PDF firmado"
            if re.search(r"_\d{4}-\d{2}-\d{2}_", path.stem):
                return "PDF final para firmar o presentar"
            return "Documento PDF"
        return "Archivo del caso"

    @staticmethod
    def document_category_label(category: str) -> str:
        return {
            "judicial": "JUDICIAL",
            "parte": "ESCRITO DE PARTE",
            "cedula": "CÉDULA",
            "audiencia": "AUDIENCIA",
        }.get(category, "OTRO")

    def case_file_label(self, path: Path, category: str = "otro") -> str:
        if path.is_dir():
            return path.name
        description = self.case_file_description(path)
        labels = {
            "Documento editable en Word": "EDITABLE",
            "PDF final para firmar o presentar": "PARA FIRMAR",
            "PDF firmado": "FIRMADO",
        }
        tags = []
        if labels.get(description):
            tags.append(labels[description])
        if category != "otro":
            tags.append(self.document_category_label(category))
        return f"{path.name}    · {' · '.join(tags)}" if tags else path.name

    def go_up_case_folder(self):
        if not self.case or not self.case_directory:
            return
        if self.case_directory != self.case.path:
            self.case_directory = self.case_directory.parent
            self.reload_case_files()

    def pick_case_files(self):
        if not self.require_case():
            return
        files = QFileDialog.getOpenFileNames(self, "Agregar archivos al caso")[0]
        self.import_paths([Path(path) for path in files])

    def pick_case_folder(self):
        if not self.require_case():
            return
        folder = QFileDialog.getExistingDirectory(self, "Agregar carpeta al caso")
        if folder:
            self.import_paths([Path(folder)])

    def import_paths(self, paths: list[Path], add_to_compilation: bool = False) -> list[Path]:
        if not self.require_case():
            return []
        imported = []
        for source in paths:
            try:
                if self.path_is_inside_case(source):
                    target = source
                elif source.is_dir():
                    name, accepted = QInputDialog.getText(
                        self,
                        "Agregar carpeta al caso",
                        "Nombre de la carpeta dentro del caso:",
                        text=source.name,
                    )
                    if not accepted or not name.strip():
                        continue
                    destination = self.case_directory or self.case.path
                    target = import_directory(Case(destination), source, name)
                elif source.is_file():
                    dialog = ImportFileDialog(source, self)
                    if not dialog.exec():
                        continue
                    destination = self.case_directory or self.case.path
                    target = import_file(
                        Case(destination),
                        source,
                        dialog.normalized_name,
                        dialog.convert_to_pdf,
                    )
                else:
                    continue
                imported.append(target)
                if add_to_compilation:
                    self.add_paths_to_compilation([target])
            except Exception as error:
                QMessageBox.critical(self, "No pudimos agregar el archivo", str(error))
        if imported:
            self.case_directory = imported[-1].parent if imported[-1].is_file() else imported[-1].parent
            self.reload_case_files(imported[-1])
            self.statusBar().showMessage(
                f"{len(imported)} elemento agregado" if len(imported) == 1 else f"{len(imported)} elementos agregados",
                4500,
            )
        return imported

    def path_is_inside_case(self, path: Path) -> bool:
        if not self.case:
            return False
        try:
            path.resolve().relative_to(self.case.path.resolve())
            return True
        except (OSError, ValueError):
            return False

    def start_file_rename(self, item: QListWidgetItem):
        self.rename_selected_file()

    def rename_selected_file(self):
        item = self.case_files.currentItem()
        if not item:
            return
        source = Path(item.data(PATH_ROLE))
        name, accepted = QInputDialog.getText(
            self,
            "Renombrar carpeta" if source.is_dir() else "Renombrar archivo",
            "Nuevo nombre:",
            text=source.name,
        )
        if not accepted or not name.strip() or name.strip() == source.name:
            return
        try:
            renamed = rename_case_entry(source, name)
            self.replace_path_everywhere(source, renamed)
            self.reload_case_files(renamed)
            self.statusBar().showMessage(f"Renombrado: {renamed.name}", 3500)
        except Exception as error:
            QMessageBox.warning(self, "No pudimos renombrar", str(error))

    def finish_file_rename(self, item: QListWidgetItem):
        # Kept for compatibility with older saved UI state. Renaming is now a
        # dialog so a nested path is never mistaken for a file name.
        return

    def replace_path_everywhere(self, previous: Path, current: Path):
        def moved(path: Path | None) -> Path | None:
            if path is None:
                return None
            try:
                relative = path.resolve().relative_to(previous.resolve())
                return current / relative
            except (OSError, ValueError):
                return path

        self.current_writing = moved(self.current_writing)
        self.last_compiled = moved(self.last_compiled)
        for index in range(self.compilation.count()):
            item = self.compilation.item(index)
            old_path = Path(item.data(PATH_ROLE))
            new_path = moved(old_path)
            if new_path != old_path:
                item.setData(PATH_ROLE, str(new_path))
                kind = item.data(TYPE_ROLE)
                item.setText(self.compilation_text(new_path, kind))
        self.update_writing_label()

    def selected_case_paths(self) -> list[Path]:
        return [Path(item.data(PATH_ROLE)) for item in self.case_files.selectedItems()]

    def open_selected_file(self):
        paths = self.selected_case_paths()
        if paths:
            if paths[0].is_dir():
                self.case_directory = paths[0]
                self.reload_case_files()
            else:
                open_file(paths[0])

    def show_file_menu(self, point):
        item = self.case_files.itemAt(point)
        menu = QMenu(self)
        if item:
            menu.addAction("Abrir", self.open_selected_file)
            menu.addAction("Renombrar…", self.rename_selected_file)
            path = Path(item.data(PATH_ROLE))
            if path.is_dir():
                menu.addAction("Abrir en el Explorador", lambda: open_file(path))
            menu.addAction(
                "Agregar contenido a compilación" if path.is_dir() else "Agregar a compilación",
                self.add_selected_to_compilation,
            )
            if path.is_file() and path.suffix.lower() in {".doc", ".docx", ".odt", ".rtf"}:
                menu.addAction("Usar como escrito", lambda: self.set_current_writing(path))
            if path.is_file() and path.suffix.lower() == ".pdf":
                menu.addAction("Generar cédula…", lambda: self.generate_cedula_from_pdf(path))
                classify = menu.addMenu("Clasificar documento")
                for category, label in (
                    ("judicial", "Judicial · decreto o proveído"),
                    ("parte", "Escrito de parte"),
                    ("cedula", "Cédula"),
                    ("audiencia", "Audiencia"),
                    ("otro", "Otro documento"),
                ):
                    classify.addAction(label, lambda checked=False, value=category: self.set_document_category(path, value))
            menu.addSeparator()
            menu.addAction("Enviar a la Papelera", self.remove_selected_case_files)
        menu.exec(self.case_files.mapToGlobal(point))

    def set_document_category(self, path: Path, category: str):
        if not self.case:
            return
        try:
            with StudyDatabase(study_database_path(self.case.path.parent)) as database:
                expediente = database.import_case(self.case)
                database.add_document(expediente.id, path.relative_to(self.case.path), source="local")
                database.set_document_category(expediente.id, path.relative_to(self.case.path), category)
            self.reload_case_files(path)
            self.statusBar().showMessage(f"Documento clasificado: {category}", 3000)
        except (OSError, ValueError, sqlite3.Error) as error:
            QMessageBox.warning(self, "No pudimos clasificar el documento", str(error))

    def generate_cedula_from_pdf(self, pdf: Path):
        if not self.case or self._cedula_thread is not None:
            return
        models = [
            path for path in list_models(self.store.models_dir)
            if "cedula" in path.stem.casefold() or "cédula" in path.stem.casefold()
        ]
        if not models:
            QMessageBox.information(
                self,
                "Modelos de cédula",
                "Agregá primero un modelo Word cuyo nombre incluya “Cédula”.",
            )
            return
        names = [model.name for model in models]
        selected, accepted = QInputDialog.getItem(
            self, "Generar cédula", "Modelo Word de cédula:", names, 0, False
        )
        if not accepted:
            return
        template = models[names.index(selected)]
        case = self.case
        self.statusBar().showMessage("Extrayendo el texto del decreto…")
        thread = QThread(self)
        worker = CedulaExtractionWorker(pdf)
        worker.moveToThread(thread)
        self._cedula_thread = thread
        thread.started.connect(worker.run)

        def cleanup():
            self._cedula_thread = None
            worker.deleteLater()
            thread.deleteLater()

        def completed(extracted):
            try:
                writing = create_writing(
                    case,
                    f"Cédula - {pdf.stem}",
                    template,
                    self.professional_combo.currentText(),
                    {"TEXTO_PROVEIDO": extracted.text},
                )
            except Exception as error:
                QMessageBox.warning(self, "No pudimos generar la cédula", str(error))
            else:
                self.reload_case_files(writing)
                self.set_current_writing(writing)
                open_file(writing)
                review = " Revisá los firmantes." if not extracted.signers_detected else ""
                self.statusBar().showMessage(f"Cédula creada desde {pdf.name}.{review}", 7000)
            thread.quit()

        worker.finished.connect(completed)
        worker.failed.connect(lambda message: (QMessageBox.warning(self, "No pudimos extraer el decreto", message), thread.quit()))
        thread.finished.connect(cleanup)
        thread.start()

    def remove_selected_case_files(self):
        paths = self.selected_case_paths()
        if not paths:
            return
        # If both a folder and one of its children are selected, recycle only
        # the folder. This prevents a second operation on a path already moved.
        top_level: list[Path] = []
        for path in sorted(paths, key=lambda value: len(value.parts)):
            if any(
                self.path_is_within(path, selected)
                for selected in top_level
            ):
                continue
            top_level.append(path)
        paths = top_level
        label = paths[0].name if len(paths) == 1 else f"{len(paths)} elementos"
        answer = QMessageBox.question(
            self,
            "Quitar archivos del caso",
            f"¿Querés enviar {label} a la Papelera de Windows?\n\nPodrás recuperarlos desde la Papelera.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            move_to_recycle_bin(paths)
            def was_removed(candidate: Path | None) -> bool:
                if candidate is None:
                    return False
                for removed in paths:
                    try:
                        candidate.resolve().relative_to(removed.resolve())
                        return True
                    except (OSError, ValueError):
                        continue
                return False

            if was_removed(self.current_writing):
                self.current_writing = None
            if was_removed(self.last_compiled):
                self.last_compiled = None
                self.last_output.setText("Aún no compilaste")
            for index in range(self.compilation.count() - 1, -1, -1):
                path = Path(self.compilation.item(index).data(PATH_ROLE))
                if was_removed(path):
                    self.compilation.takeItem(index)
            self.reload_case_files()
            self.update_writing_label()
            self.update_compilation_count()
            self.statusBar().showMessage("Elemento enviado a la Papelera" if len(paths) == 1 else "Elementos enviados a la Papelera", 4500)
        except Exception as error:
            QMessageBox.warning(self, "No pudimos quitar los archivos", str(error))

    @staticmethod
    def path_is_within(path: Path, parent: Path) -> bool:
        try:
            path.resolve().relative_to(parent.resolve())
            return True
        except (OSError, ValueError):
            return False

    def add_selected_to_compilation(self):
        before = self.compilation.count()
        self.add_paths_to_compilation(self.selected_case_paths())
        if self.compilation.count() > before:
            self.open_preparation_dialog()

    def compilable_files(self, paths: list[Path]) -> list[Path]:
        result: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            candidates = [path] if path.is_file() else (
                sorted(path.rglob("*"), key=lambda item: item.as_posix().casefold())
                if path.is_dir()
                else []
            )
            for candidate in candidates:
                if not candidate.is_file() or candidate.suffix.lower() not in PDF_EXTENSIONS:
                    continue
                resolved = candidate.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    result.append(candidate)
        return result

    def add_paths_to_compilation(self, paths: list[Path]):
        for path in self.compilable_files(paths):
            kind = "writing" if path == self.current_writing else "document"
            self.add_compilation_path(path, kind)

    def compilation_text(self, path: Path, kind: str) -> str:
        prefix = "ESCRITO" if kind == "writing" else "DOC"
        return f"{prefix}  ·  {path.name}"

    def add_compilation_path(self, path: Path, kind: str = "document"):
        for index in range(self.compilation.count()):
            existing = self.compilation.item(index)
            if Path(existing.data(PATH_ROLE)) == path:
                if kind == "writing":
                    existing.setData(TYPE_ROLE, "writing")
                    existing.setText(self.compilation_text(path, "writing"))
                    item = self.compilation.takeItem(index)
                    self.compilation.addItem(item)
                self.update_compilation_count()
                return
        item = QListWidgetItem(self.compilation_text(path, kind))
        item.setData(PATH_ROLE, str(path))
        item.setData(TYPE_ROLE, kind)
        item.setToolTip(str(path))
        item.setIcon(self.icon_for_path(path))
        self.compilation.addItem(item)
        self.update_compilation_count()

    def handle_compilation_drop(self, paths: list[Path]):
        if not self.require_case():
            return
        inside = []
        outside = []
        for path in paths:
            is_inside = self.path_is_inside_case(path)
            (inside if is_inside else outside).append(path)
        self.add_paths_to_compilation(inside)
        if outside:
            self.import_paths(outside, add_to_compilation=True)

    def remove_from_compilation(self):
        for item in self.compilation.selectedItems():
            self.compilation.takeItem(self.compilation.row(item))
        self.update_compilation_count()

    def move_compilation_item(self, direction: int):
        item = self.compilation.currentItem()
        if not item:
            return
        current = self.compilation.row(item)
        target = max(0, min(self.compilation.count() - 1, current + direction))
        if target == current:
            return
        item = self.compilation.takeItem(current)
        self.compilation.insertItem(target, item)
        self.compilation.setCurrentItem(item)

    def clear_compilation(self):
        self.compilation.clear()
        self.update_compilation_count()

    def update_compilation_count(self):
        count = self.compilation.count()
        self.compilation_count.setText(
            f"{count} elemento" if count == 1 else f"{count} elementos"
        )
        if hasattr(self, "work_tabs"):
            self.work_tabs.setTabText(self.compilation_tab_index, f"Compilación · {count}")

    def compilation_paths(self) -> list[Path]:
        return [
            Path(self.compilation.item(index).data(PATH_ROLE))
            for index in range(self.compilation.count())
        ]

    def new_blank_writing(self):
        if not self.require_case():
            return
        title, accepted = QInputDialog.getText(
            self,
            "Escrito nuevo",
            "Nombre breve para el archivo:",
            text="Escrito",
        )
        if accepted and title.strip():
            self.create_and_open_writing(title, self.base_template)

    def new_writing_from_model(self):
        if not self.require_case():
            return
        models = [
            path
            for path in list_models(self.store.models_dir)
            if path.resolve() != self.base_template.resolve()
        ]
        if not models:
            QMessageBox.information(
                self,
                "Todavía no hay modelos",
                "Usá “Agregar modelo…” para guardar documentos Word reutilizables.",
            )
            return
        dialog = ModelPickerDialog(models, self)
        if dialog.exec() and dialog.selected_model and dialog.title:
            self.create_and_open_writing(dialog.title, dialog.selected_model)

    def create_and_open_writing(self, title: str, template: Path | None = None):
        try:
            path = create_writing(
                self.case,
                title,
                template,
                self.professional_combo.currentText(),
            )
            self.set_current_writing(path)
            self.case_directory = path.parent
            self.reload_case_files(path)
            open_file(path)
            self.statusBar().showMessage(f"Escrito creado: {path.name}", 5000)
        except Exception as error:
            QMessageBox.critical(self, "No pudimos crear el escrito", str(error))

    def set_current_writing(self, path: Path):
        self.current_writing = path
        for index in range(self.compilation.count() - 1, -1, -1):
            item = self.compilation.item(index)
            if item.data(TYPE_ROLE) == "writing":
                item.setData(TYPE_ROLE, "document")
                old_path = Path(item.data(PATH_ROLE))
                item.setText(self.compilation_text(old_path, "document"))
        self.add_compilation_path(path, "writing")
        self.update_writing_label()
        self.update_output_preview()

    def update_writing_label(self):
        if self.current_writing and self.current_writing.exists():
            self.writing_name.setText(self.current_writing.name)
            self.writing_name.setToolTip(str(self.current_writing))
        else:
            self.writing_name.setText("Todavía no elegiste un escrito")
            self.writing_name.setToolTip("")

    def add_writing_model(self):
        source = QFileDialog.getOpenFileName(
            self,
            "Agregar modelo Word",
            "",
            "Documentos Word (*.docx)",
        )[0]
        if not source:
            return
        try:
            target = add_model(self.store.models_dir, Path(source))
            self.statusBar().showMessage(f"Modelo agregado: {target.name}", 4500)
        except Exception as error:
            QMessageBox.critical(self, "No pudimos agregar el modelo", str(error))

    def open_models_folder(self):
        self.store.models_dir.mkdir(parents=True, exist_ok=True)
        open_file(self.store.models_dir)

    def open_base_template(self):
        try:
            self.base_template = ensure_default_writing_template(self.store.base_template)
            open_file(self.base_template)
            self.statusBar().showMessage(
                "Modelo base abierto. Los próximos escritos nuevos usarán estos cambios.",
                6000,
            )
        except Exception as error:
            QMessageBox.critical(self, "No pudimos abrir el modelo base", str(error))

    def show_template_variables(self):
        QMessageBox.information(
            self,
            "Campos automáticos de los modelos",
            "Escribí estos campos directamente en el lugar del Word donde "
            "querés que aparezca cada dato:\n\n"
            "{{PROFESIONAL}}  Campo Abogado, en mayúsculas y sin Dr./Dra.\n"
            "{{CARATULA}}  ACTOR C/ DEMANDADO S/ CAUSA\n"
            "{{NUMERO_EXPEDIENTE}}  Número de expediente o CUIJ\n"
            "{{CUIJ_COMPLETO}}  (CUIJ N° …), si fue cargado\n"
            "{{ACTOR}}  {{DEMANDADO}}  {{CAUSA}}  {{CUIJ}}\n"
            "{{RADICACION}}  {{ABOGADO}}  {{CONTRAPARTE}}\n"
            "{{NOMBRE_CORTO}}  Identificador breve usado en archivos PDF\n"
            "{{JURISDICCION}}  {{FUERO}}  {{JUZGADO}}  {{SECRETARIA}}\n"
            "{{EDAD_RAEO}}  {{ANTIGUEDAD_LABORAL}}  Cálculos de la ficha ampliada\n"
            "{{TITULO}}  Nombre del escrito\n"
            "{{FECHA}}  Fecha numérica actual\n"
            "{{FECHA_EXTENSA}}  Ej.: 13 de agosto de 2026\n\n"
            "Ejemplo para un modelo de apelación:\n"
            "{{PROFESIONAL}}, abogado de la parte actora, en autos "
            "“{{CARATULA}}”{{CUIJ_COMPLETO}}, ante V.S. digo:\n\n"
            "Guardá el Word y agregalo desde + Escrito → Agregar modelo. "
            "Luego usalo desde + Escrito → Desde modelo.\n\n"
            "En “Más datos” podés ver variables adicionales y crear campos propios.\n\n"
            "Al crear el escrito, se reemplazan con los datos del caso. "
            "Si un dato está vacío, el campo queda vacío.",
        )

    def open_template_guide(self):
        guide = Path(__file__).resolve().parent.parent / "docs" / "MODELOS_WORD.md"
        if guide.is_file():
            open_file(guide)
        else:
            self.show_template_variables()

    def compile_pdf(self):
        if self._compile_thread is not None:
            return
        if not self.require_case():
            return
        paths = self.compilation_paths()
        if not paths:
            self.open_preparation_dialog()
            QMessageBox.information(
                self,
                "Faltan archivos",
                "Agregá la documental y el escrito en la pestaña Compilación.",
            )
            return
        if not self.confirm_pending_metadata_change():
            return
        name_choice = self.prompt_compilation_name()
        if not name_choice:
            return
        output_name, replace_existing = name_choice
        limit = int(self.limit_combo.currentData())
        self._progress_dialog = QProgressDialog(
            "Preparando los archivos…",
            "Cancelar",
            0,
            0,
            self,
        )
        self._progress_dialog.setWindowTitle("Compilando PDF")
        self._progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._progress_dialog.setMinimumDuration(0)
        self._progress_dialog.setAutoClose(False)
        self._progress_dialog.setAutoReset(False)
        self._progress_dialog.canceled.connect(self.cancel_compilation)
        self._progress_dialog.show()
        self.compile_button.setEnabled(False)
        self.compile_button.setText("Compilando…")

        thread = QThread(self)
        worker = CompileWorker(
            self.case,
            paths,
            limit,
            output_name,
            replace_existing,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._compile_progress)
        worker.finished.connect(self._compile_finished)
        worker.failed.connect(self._compile_failed)
        worker.cancelled.connect(self._compile_cancelled)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.cancelled.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._compile_cleanup)
        self._compile_thread = thread
        self._compile_worker = worker
        self._compile_cancelling = False
        thread.start()

    def prompt_compilation_name(self) -> tuple[str, bool] | None:
        if not self.case:
            return None
        metadata = read_case_metadata(self.case)
        suggestion = self.output_name.text().strip() or suggested_presentation_name(
            self.case,
            self.current_writing,
        )
        identifier_missing = not (
            metadata.get("Nombre corto para archivos", "").strip()
            or metadata.get("Actor", "").strip()
        )
        dialog = CompileNameDialog(self.case, suggestion, identifier_missing, self)
        if not dialog.exec():
            return None
        self.output_name.clear()
        return dialog.file_name, dialog.replace_existing

    def cancel_compilation(self):
        if self._compile_worker is None or self._compile_cancelling:
            return
        self._compile_cancelling = True
        self._compile_worker.cancel()
        self.compile_button.setText("Cancelando…")
        self.statusBar().showMessage("Deteniendo la compilación…")
        if self._progress_dialog:
            self._progress_dialog.setLabelText("Deteniendo la compilación…")
            self._progress_dialog.setCancelButton(None)

    def _compile_progress(self, message: str):
        self.statusBar().showMessage(message)
        if self._progress_dialog:
            self._progress_dialog.setLabelText(message)

    def _compile_finished(self, result):
        self._close_compile_progress()
        if self._close_after_compile:
            return
        self.last_compiled = result.output
        self.last_output.setText(f"{result.output.name}\n{human_size(result.output.stat().st_size)}")
        self.case_directory = result.output.parent
        self.work_tabs.setCurrentIndex(self.files_tab_index)
        self.reload_case_files(result.output)
        self.update_output_preview()
        if result.exceeds_limit:
            answer = QMessageBox.question(
                self,
                "El PDF supera el límite",
                f"El archivo pesa {human_size(result.output.stat().st_size)} y el límite elegido es "
                f"{human_size(result.limit)}.\n\n¿Querés dividirlo en partes ahora?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                try:
                    parts = split_pdf(result.output, result.limit, self.case.path, result.output.stem)
                    self.case_directory = self.case.path
                    self.reload_case_files(parts[-1] if parts else result.output)
                    QMessageBox.information(
                        self,
                        "PDF compilado y dividido",
                        f"Se guardó el PDF completo y {len(parts)} partes en la carpeta del caso.",
                    )
                except Exception as error:
                    QMessageBox.critical(self, "No pudimos dividir el PDF", str(error))
            else:
                QMessageBox.information(
                    self,
                    "PDF compilado",
                    "Se conservó el archivo único aunque supera el límite elegido.",
                )
        else:
            note = " y fue comprimido" if result.compressed else ""
            QMessageBox.information(
                self,
                "PDF listo",
                f"{result.output.name}{note}.\n\nTamaño final: {human_size(result.output.stat().st_size)}",
            )
        self.statusBar().showMessage("Compilación terminada", 5000)

    def _compile_failed(self, message: str):
        self._close_compile_progress()
        if not self._close_after_compile:
            QMessageBox.critical(self, "No pudimos compilar", message)

    def _compile_cancelled(self):
        self._close_compile_progress()
        if not self._close_after_compile:
            self.statusBar().showMessage("Compilación cancelada", 5000)

    def _close_compile_progress(self):
        self.compile_button.setEnabled(True)
        self.compile_button.setText("Compilar PDF")
        if self._progress_dialog:
            self._progress_dialog.blockSignals(True)
            self._progress_dialog.close()
            self._progress_dialog.deleteLater()
            self._progress_dialog = None

    def _compile_cleanup(self):
        self._compile_thread = None
        self._compile_worker = None
        self._compile_cancelling = False
        if self._close_after_compile:
            self._close_after_compile = False
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        if self._compile_thread is not None and self._compile_thread.isRunning():
            if self._compile_cancelling:
                event.ignore()
                return
            answer = QMessageBox.question(
                self,
                "Compilación en curso",
                "La compilación continúa en segundo plano.\n\n"
                "¿Querés cancelarla y cerrar el programa?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._close_after_compile = True
                self.cancel_compilation()
            event.ignore()
            return
        if not self.confirm_pending_metadata_change():
            event.ignore()
            return
        self.digital_signer.close()
        super().closeEvent(event)

    def current_pdf_for_signing(self) -> Path | None:
        for path in self.selected_case_paths():
            if path.is_file() and path.suffix.casefold() == ".pdf":
                return path
        if self.last_compiled and self.last_compiled.exists():
            return self.last_compiled
        return None

    def show_sign_menu(self):
        pdf = self.current_pdf_for_signing()
        menu = QMenu(self)
        certificate = self.digital_signer.certificate
        internal_label = (
            f"Firmar dentro del Gestor · sesión abierta"
            if self.digital_signer.active
            else "Firmar dentro del Gestor…"
        )
        internal_action = menu.addAction(ui_icon("signature", "#2B7564"), internal_label)
        internal_action.setEnabled(pdf is not None)
        if pdf:
            internal_action.triggered.connect(lambda: self.sign_with_token(pdf))
        if certificate:
            internal_action.setToolTip(certificate.summary)
            menu.addAction("Cerrar sesión de firma", self.close_digital_signature_session)
        menu.addSeparator()
        open_action = menu.addAction("Abrir PDF para firmar")
        open_action.setEnabled(pdf is not None)
        if pdf:
            open_action.triggered.connect(lambda: open_file(pdf))
        signer = self.store.settings.signer_path
        if signer:
            verb = "Preparar para Xólido" if "xolido" in signer.stem.casefold() else f"Preparar para {signer.stem}"
            send_action = menu.addAction(verb)
            send_action.setEnabled(pdf is not None)
            if pdf:
                send_action.triggered.connect(lambda: self.send_to_signer(signer, pdf))
        menu.addAction("Configurar aplicación de firma…", self.configure_signer)
        if self.case:
            menu.addAction("Abrir carpeta del caso", lambda: open_file(self.case.path))
        menu.exec(self.sign_button.mapToGlobal(self.sign_button.rect().bottomLeft()))

    def choose_signing_certificate(self) -> SigningCertificate | None:
        certificates = select_current_certificates(discover_signing_certificates())
        if not certificates:
            raise SigningUnavailable(
                "El token está conectado, pero no contiene un certificado vigente para firmar."
            )
        if len(certificates) == 1:
            return certificates[0]
        dialog = CertificatePickerDialog(certificates, self)
        return dialog.selected_certificate if dialog.exec() else None

    def sign_with_token(self, pdf: Path):
        try:
            certificate = self.digital_signer.certificate or self.choose_signing_certificate()
            if not certificate:
                return
            confirmation = SignPdfDialog(pdf, certificate, self)
            if not confirmation.exec():
                return
            target = confirmation.output
            reason = confirmation.reason
            if target.exists():
                QMessageBox.warning(
                    self,
                    "Ya existe el archivo firmado",
                    "Elegí otro nombre. El Gestor no reemplaza una firma existente.",
                )
                return
            if not self.digital_signer.active:
                pin_dialog = TokenPinDialog(certificate, self)
                if not pin_dialog.exec():
                    return
                pin = pin_dialog.take_pin()
                try:
                    self.digital_signer.open(certificate, pin)
                finally:
                    pin = ""
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                signed = self.digital_signer.sign_pdf(
                    pdf,
                    target,
                    reason=reason,
                    location="Argentina",
                )
            finally:
                QApplication.restoreOverrideCursor()
            self.last_signed = signed
            self.case_directory = signed.parent
            self.reload_case_files(signed)
            size = signed.stat().st_size
            self.last_output.setText(f"{signed.name}\nFIRMADO · {human_size(size)}")
            limit = int(self.limit_combo.currentData())
            if size > limit:
                QMessageBox.warning(
                    self,
                    "Firma realizada, pero supera el límite",
                    f"El PDF quedó firmado correctamente, pero pesa {human_size(size)} y el límite "
                    f"seleccionado es {human_size(limit)}.\n\n"
                    "No lo comprimas ni lo modifiques después de firmarlo. Volvé a compilar con más margen y firmá otra copia.",
                )
            else:
                QMessageBox.information(
                    self,
                    "PDF firmado",
                    f"Se creó {signed.name}.\n\nTamaño final: {human_size(size)}\n"
                    "La sesión del token seguirá abierta para los próximos documentos.",
                )
            self.statusBar().showMessage("Firma digital terminada · sesión abierta", 6000)
        except (SigningUnavailable, SigningError, FileExistsError) as error:
            QMessageBox.critical(
                self,
                "No pudimos firmar dentro del Gestor",
                f"{error}\n\nPodés continuar con Xólido desde este mismo menú.",
            )
        except Exception as error:
            self.digital_signer.close()
            QMessageBox.critical(
                self,
                "No pudimos firmar dentro del Gestor",
                f"Ocurrió un problema inesperado.\n\nDetalle: {error}",
            )

    def close_digital_signature_session(self):
        self.digital_signer.close()
        self.statusBar().showMessage("Sesión de firma cerrada", 3500)

    def configure_signer(self):
        path = QFileDialog.getOpenFileName(
            self,
            "Elegí Xólido u otra aplicación de firma",
            "",
            "Aplicaciones (*.exe);;Todos los archivos (*.*)",
        )[0]
        if path:
            self.store.set_signer(Path(path))
            self.statusBar().showMessage(f"Firmador configurado: {Path(path).stem}", 4500)

    def send_to_signer(self, signer: Path, pdf: Path):
        try:
            focus_or_launch_signer(signer)
            self._signer_dialog = SignerDropDialog(pdf, self)
            self._signer_dialog.show()
            self._signer_dialog.raise_()
            self._signer_dialog.activateWindow()
        except Exception as error:
            QMessageBox.critical(self, "No pudimos abrir el firmador", str(error))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Gestor de documental")
    app.setApplicationDisplayName("Gestor de documental")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    app.setWindowIcon(ui_icon("layers", "#D45B36", 32))
    window = MainWindow()
    window.show()
    return app.exec()
