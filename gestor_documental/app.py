from __future__ import annotations

import sys
import re
import sqlite3
import shutil
import unicodedata
import json
from datetime import date, datetime
from pathlib import Path

from PyQt6.QtCore import (
    QFileSystemWatcher,
    QMimeData,
    QObject,
    QSize,
    QStringListModel,
    QThread,
    QTimer,
    Qt,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPalette, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
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
    QProgressBar,
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
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from . import __version__
from .background_workers import (
    CedulaExtractionWorker,
    CompileWorker,
    SisfeSnapshotImportWorker,
    StudyBackupWorker,
)
from .case_spreadsheet_import import ImportRow, import_rows
from .long_tasks import BatchTaskWorker, LongTask, TaskDetail, TaskState
from .case_documents import rename_document_entry
from .activity_center import build_case_activity
from .ui.document_recovery import DocumentRecoveryWorker
from .models import (
    ADVANCED_FIELD_VARIABLES,
    CASE_FIELDS,
    CASE_FIELD_LABELS,
    DEFAULT_PROFILE,
    NO_LIMIT,
    NO_LIMIT_PROFILE,
    PRESENTATION_LIMITS,
    PRESENTATION_PROFILES,
    PROFILE_FOR_LIMIT,
    VISIBLE_CASE_FIELDS,
    Case,
)
from .case_data import (
    CASE_TYPE_FIELD,
    CASE_TYPE_LRT,
    CASE_TYPE_SUCCESSION,
    CASE_TYPES,
    COMMON_GENERAL_SECTIONS,
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
    case_type_from_metadata,
    canonical_case_type,
    case_suggestions,
    computed_values,
    ensure_system_metadata,
    field_initial_value,
    process_sections,
    repeated_for_case_type,
    raeo_effective_values,
    raeo_missing_fields,
    sections_for_case_type,
)
from .case_registry import (
    mark_case_novedades_read,
    recent_case_novedades,
    register_case_as_expediente,
    unread_case_novedades,
)
from .movement_interpretation import interpret_movement
from .case_activity import (
    case_activities,
    normalized_activity_settings,
    set_case_archived,
)
from .compilation_draft import (
    CompilationDraft,
    DraftItem,
    load_compilation_history,
    load_compilation_draft,
    record_compilation_history,
    save_compilation_draft as persist_compilation_draft,
)
from .sisfe_session import ManualSisfeSession
from .sisfe_browser import classify_sisfe_movement
from .sisfe_sync import SisfePortalService
from .icons import (
    badged_icon,
    file_icon_name,
    foro_application_icon,
    foro_mark,
    movement_icon,
    ui_icon,
)
from .signing import (
    DigitalSignatureSession,
    SigningCertificate,
    SigningError,
    SigningUnavailable,
    VisibleSignature,
    discover_signing_certificates,
    select_current_certificates,
    signed_output_path,
    visible_signature_box,
)
from .services import (
    SettingsStore,
    IMAGE_EXTENSIONS,
    PDF_EXTENSIONS,
    add_model,
    can_convert_to_pdf,
    case_matches,
    copy_external_case,
    create_case,
    create_writing,
    ensure_default_writing_template,
    external_case_summary,
    find_unresolved_placeholders,
    find_recent_signer_output,
    focus_or_launch_signer,
    human_size,
    import_file,
    import_directory,
    list_cases,
    list_models,
    move_to_recycle_bin,
    normalize_filename,
    normalize_naming_pattern,
    open_file,
    read_case_metadata,
    rank_models_for_document,
    rename_case,
    rename_case_entry,
    rename_case_file,
    safe_name,
    save_case_metadata,
    suggested_presentation_name,
    template_variable_name,
    to_pdf,
    split_pdf,
    study_library_path,
    unique_path,
)
from .study_backup import (
    BackupResult,
    RestoreResult,
    StudyBackupError,
    inspect_study_backup,
)
from .study_database import StudyDatabase, study_database_path
from .ui.compilation import CompilationHistoryDialog, CompilationList
from .ui.case_files import (
    DATE_COLUMN_WIDTH,
    SIZE_COLUMN_WIDTH,
    CaseFilesList,
    QuickAccessList,
)
from .ui.case_import import ExternalCaseImportDialog
from .ui.case_spreadsheet_import import CaseSpreadsheetImportDialog
from .ui.operation_status import OperationState, OperationStatusIndicator
from .ui.roles import (
    ACTIVITY_ROLE,
    MODIFIED_ROLE,
    MOVEMENT_ROLE,
    PATH_ROLE,
    PENDING_DUE_ROLE,
    ROOT_ROLE,
    SIZE_ROLE,
    TYPE_ROLE,
)
from .ui.settings_dialogs import (
    ActivitySettingsDialog,
    ApplicationSettingsDialog,
    NamingPatternDialog,
    ProfessionalProfileDialog,
    RadicacionesDialog,
    SisfeAccessDialog,
)
from .ui.sisfe import SisfeCaseBrowserDialog, SisfeLoginDialog


ADD_PROFESSIONAL_LABEL = "Añadir nuevo profesional…"

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


def _timeline_date_label(value: datetime | None) -> str:
    if value is None:
        return "SIN FECHA"
    months = ("ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC")
    return f"{value.day:02d} {months[value.month - 1]} {value.year}"


def _comparable_text(value: str) -> str:
    """Clave estable para no duplicar valores por mayúsculas, acentos o espacios."""
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _interpretation_summary(text: str) -> str:
    rows = []
    for result in interpret_movement(text):
        extracted = (
            result.extracted_at.strftime("%d/%m/%Y %H:%M").removesuffix(" 00:00")
            if result.extracted_at
            else "fecha sin confirmar"
        )
        warning = f" · {result.warning}" if result.warning else ""
        rows.append(f"{result.kind}: {extracted}{warning}")
    return "\n".join(rows)

APP_STYLE = """
QMainWindow, QWidget#appRoot { background: #F1EEE4; color: #2A332B; }
QWidget { font-family: "Segoe UI Variable Text", "Segoe UI"; font-size: 13px; }
QToolTip { background: #3A4735; color: #F9F4E9; border: 0; padding: 6px 8px; }
QFrame#topBar { background: #2B5748; border: 0; }
QLabel#brand { color: #F9F4E9; font-size: 19px; font-weight: 700; letter-spacing: 2px; }
QLabel#brandVersion { color: #A6BEB0; font-size: 10px; font-weight: 600; padding-bottom: 3px; }
QLabel#professionalLabel { color: #7C8B7E; font-size: 10px; font-weight: 700; letter-spacing: .6px; }
QFrame#sidebar { background: #F7F3E9; border-right: 1px solid #E2DDCC; }
QFrame#card, QFrame#caseHeader, QFrame#actionCard { background: #FFFFFF; border: 1px solid #E3DED0; border-radius: 10px; }
QFrame#softCard { background: #F4F1E5; border: 1px solid #E3DED0; border-radius: 8px; }
QLabel#eyebrow { color: #7C8B7E; font-size: 10px; font-weight: 700; letter-spacing: .8px; }
QLabel#fieldLabel { color: #8A9789; font-size: 9px; font-weight: 700; letter-spacing: .8px; }
QLabel#sectionTitle { color: #2A332B; font-size: 15px; font-weight: 700; }
QLabel#caseTitle { color: #2B5748; font-size: 19px; font-weight: 700; }
QLabel#muted { color: #7C8B7E; font-size: 11px; }
QLabel#actionTitle { color: #2A332B; font-size: 14px; font-weight: 700; }
QLabel#actionMuted { color: #7C8B7E; font-size: 11px; }
QLabel#caseBadge { background: #EDF1E7; color: #3A4735; border-radius: 6px; padding: 3px 8px; font-size: 10px; font-weight: 700; }
QLabel#caseBadge[pending="true"] { background: #F6EEDC; color: #8A5B12; }
QLabel#warning { background: #F6EEDC; color: #7B5316; border-radius: 8px; padding: 8px 10px; }
QLineEdit, QComboBox { background: #FFFFFF; border: 1px solid #D5D0C0; border-radius: 6px; padding: 7px 9px; min-height: 17px; }
QLineEdit:focus, QComboBox:focus { border: 1px solid #698D05; }
QLineEdit:read-only { background: #FBF9F3; color: #3A4735; border-color: #EAE5D8; }
QLineEdit#metaValue { background: transparent; border: 0; border-bottom: 1px solid #EDE8DB; border-radius: 0; padding: 2px 0 3px 0; color: #2A332B; font-weight: 600; }
QLineEdit#metaValue:focus { border-bottom: 1px solid #698D05; }
QComboBox#professional { background: #23483C; color: #F9F4E9; border: 1px solid #3F6455; min-width: 180px; padding: 6px 9px; }
QComboBox#professional::drop-down { border: 0; width: 18px; }
QComboBox#professional QAbstractItemView { background: #FFFFFF; color: #2A332B; border: 1px solid #D5D0C0; selection-background-color: #E5EEE8; selection-color: #1F4034; outline: 0; }
QPushButton { background: #FFFFFF; color: #2A332B; border: 1px solid #D5D0C0; border-radius: 6px; padding: 8px 12px; font-weight: 600; }
QPushButton:hover { background: #FBF9F3; border-color: #B6AF9A; }
QPushButton:disabled { color: #A6AFA4; border-color: #E6E1D3; }
QPushButton#primary { background: #2B5748; color: #F9F4E9; border-color: #2B5748; padding: 9px 14px; }
QPushButton#primary:hover { background: #23483C; border-color: #23483C; }
QPushButton#primary:disabled { background: #B7C4BB; border-color: #B7C4BB; color: #F1EEE4; }
QPushButton#green { background: #618765; color: #FFFFFF; border-color: #618765; }
QPushButton#green:hover { background: #527356; border-color: #527356; }
QPushButton#onDark { background: #2B5748; color: #F9F4E9; border-color: #2B5748; padding: 9px 14px; }
QPushButton#onDark:hover { background: #23483C; border-color: #23483C; }
QPushButton#quiet { background: transparent; border: 0; color: #5D6B5E; padding: 6px 8px; text-align: left; }
QPushButton#quiet:hover { background: #EDEAE0; color: #2A332B; }
QPushButton#iconOnly { min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; padding: 0; border-radius: 6px; }
QPushButton#iconQuiet { min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; padding: 0; border: 0; background: transparent; }
QPushButton#iconQuiet:hover { background: #EDEAE0; }
QPushButton#topIcon { min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; padding: 0; border: 0; background: transparent; }
QPushButton#topIcon:hover { background: #3A6455; }
QPushButton#limit { padding: 6px 2px; color: #3A4735; font-weight: 600; }
QPushButton#limit:checked { background: #2B5748; color: #F9F4E9; border-color: #2B5748; }
QPushButton#columnHeaderButton { background: transparent; border: 0; border-bottom: 1px solid #EDE8DB; border-radius: 0; color: #7C8B7E; font-size: 10px; font-weight: 700; padding: 4px 2px; text-align: left; }
QPushButton#columnHeaderButton:hover { color: #2B5748; background: #F7F5EC; }
QTreeWidget, QListWidget { background: transparent; border: 0; outline: 0; }
QTreeWidget#caseTree { show-decoration-selected: 0; }
QTreeView::branch:selected, QTreeWidget::branch:selected { background: transparent; border: 0; }
QTreeWidget::item, QListWidget::item { border-radius: 6px; padding: 6px 6px; margin: 1px 0; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #EFEDE3; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #E2EBDC; color: #1F4034; }
QListWidget#modelList { background: #FBF9F3; border: 1px solid #E3DED0; border-radius: 8px; padding: 5px; }
QListWidget#modelList::item { background: #FFFFFF; border: 1px solid transparent; padding: 11px; margin: 2px; }
QListWidget#modelList::item:hover { background: #F2F5EE; color: #2B5748; border-color: #D8E2D2; }
QListWidget#modelList::item:selected { background: #2B5748; color: #F9F4E9; border-color: #23483C; }
QListWidget#modelList::item:selected:hover { background: #23483C; color: #F9F4E9; border-color: #1B3A30; }
QListWidget#novedadesList { border: 0; background: #FFFFFF; padding: 2px 10px 8px 4px; }
QListWidget#novedadesList::item { padding: 13px 10px 14px 8px; margin: 0; border: 0; border-bottom: 1px solid #E7EAE7; }
QListWidget#novedadesList::item:hover { background: #F8FAF8; }
QListWidget#novedadesList::item:selected { background: #EEF5F1; color: #183D32; }
QProgressBar#taskProgress { max-height: 5px; min-height: 5px; border: 0; border-radius: 2px; background: #E3DED0; }
QProgressBar#taskProgress::chunk { background: #698D05; border-radius: 2px; }
QSplitter::handle { background: #E4DFD0; width: 6px; height: 6px; }
QSplitter::handle:hover { background: #698D05; }
QScrollArea { border: 0; background: transparent; }
QTabWidget::pane { border: 0; background: transparent; top: -1px; }
QTabBar::tab { background: transparent; color: #6C7A6D; border: 0; border-bottom: 2px solid transparent; border-radius: 0; padding: 8px 12px; margin: 0 8px 6px 0; font-weight: 600; }
QTabBar::tab:hover { color: #2B5748; }
QTabBar::tab:selected { color: #2B5748; border-bottom: 2px solid #698D05; }
QPlainTextEdit { background: #FFFFFF; border: 1px solid #D5D0C0; border-radius: 6px; padding: 8px 10px; }
QPlainTextEdit:focus { border: 1px solid #698D05; }
QMenu { background: white; border: 1px solid #E3DED0; padding: 4px; }
QMenu::item { padding: 7px 24px 7px 10px; border-radius: 5px; }
QMenu::item:selected { background: #E2EBDC; color: #1F4034; }
QStatusBar { background: #FBF9F3; color: #6C7A6D; border-top: 1px solid #E3DED0; }
QStatusBar::item { border: 0; }
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


def decorate_button(button: QPushButton, icon_name: str, color: str = "#2B5748") -> QPushButton:
    button.setIcon(ui_icon(icon_name, color))
    button.setIconSize(QSize(19, 19))
    return button


def icon_button(
    icon_name: str,
    tooltip: str,
    slot,
    *,
    bordered: bool = False,
    color: str = "#2B5748",
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
        self.convert.setChecked(False)
        layout.addWidget(self.convert)
        self.image_mode_label = QLabel("Tratamiento de la imagen")
        self.image_mode = QComboBox()
        self.image_mode.addItem("Mantener color", "color")
        self.image_mode.addItem("Escala de grises · archivo más liviano", "grayscale")
        self.image_mode.addItem("Blanco y negro · máximo ahorro", "black_white")
        is_image = source.suffix.casefold() in IMAGE_EXTENSIONS
        self.image_mode_label.setVisible(False)
        self.image_mode.setVisible(False)
        if is_image:
            self.convert.toggled.connect(self.image_mode_label.setVisible)
            self.convert.toggled.connect(self.image_mode.setVisible)
        layout.addWidget(self.image_mode_label)
        layout.addWidget(self.image_mode)
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

    @property
    def selected_image_mode(self) -> str:
        return str(self.image_mode.currentData() or "color")


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
    documentRequested = pyqtSignal(str, object)

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
        self._active_case_type = case_type_from_metadata(self._base_metadata)
        self._base_metadata[CASE_TYPE_FIELD] = self._active_case_type
        self.setWindowTitle("Datos ampliados del caso")
        self.setMinimumSize(820, 720)
        self.resize(940, 790)
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        self._custom_rows: list[tuple[QWidget, QLineEdit, QLineEdit]] = []
        self.edits: dict[str, QWidget] = {}
        self._field_specs: dict[str, FieldSpec] = {}
        self.repeated: dict[str, RepeatedRowsWidget] = {}
        self._type_field_keys: set[str] = set()
        self._type_repeated_keys: set[str] = set()

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
        self._build_case_type_tab()
        self._build_process_tab()
        self._build_raeo_tab()

        generated_actions = QHBoxLayout()
        generated_label = QLabel("GENERAR DESDE LA ENTREVISTA")
        generated_label.setObjectName("eyebrow")
        generated_actions.addWidget(generated_label)
        generated_actions.addWidget(
            icon_button(
                "template",
                "Ver metadatos disponibles para modelos Word",
                self.open_template_variables,
                bordered=True,
            )
        )
        generated_actions.addStretch()
        self.interview_document_buttons: dict[str, QPushButton] = {}
        for action, label in (
            ("ficha", "Ficha inicial"),
            ("pacto", "Pacto de cuota litis"),
            ("poder", "Poder"),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda checked=False, value=action: self.documentRequested.emit(value, self.values())
            )
            self.interview_document_buttons[action] = button
            generated_actions.addWidget(button)
        layout.addLayout(generated_actions)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar datos")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh_dynamic_information()
        first_edit = next(
            (edit for edit in self.edits.values() if isinstance(edit, QLineEdit)),
            None,
        )
        if first_edit:
            QTimer.singleShot(0, first_edit.setFocus)

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
        self._add_date_variables(content)
        self._add_sections(content, COMMON_GENERAL_SECTIONS)
        self._add_custom_fields(content)
        content.addStretch()
        self.tabs.addTab(tab, "Datos generales")

    def _build_case_type_tab(self):
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
        self.case_type_dynamic = QVBoxLayout()
        self.case_type_dynamic.setSpacing(10)
        content.addLayout(self.case_type_dynamic)
        content.addStretch()
        self.case_type_tab_index = self.tabs.addTab(tab, "Datos del caso")
        self._rebuild_case_type_fields()

    def _build_process_tab(self):
        tab, content = self._scroll_tab()
        reference, reference_layout = make_card("softCard")
        reference_layout.addLayout(
            section_heading(
                "Datos ya cargados",
                "Se reutilizan automáticamente y no se vuelven a editar en esta pestaña.",
            )
        )
        self.process_summary = QLabel()
        self.process_summary.setWordWrap(True)
        reference_layout.addWidget(self.process_summary)
        content.addWidget(reference)
        self._add_sections(content, process_sections())
        content.addStretch()
        self.tabs.addTab(tab, "Datos procesales")

    def _add_date_variables(self, parent_layout: QVBoxLayout):
        today = date.today()
        months = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
        weekdays = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
        values = (
            ("FECHA", today.strftime("%d/%m/%Y")),
            ("DIA", str(today.day)),
            ("DIA_SEMANA", weekdays[today.weekday()]),
            ("MES", months[today.month - 1]),
            ("ANIO", str(today.year)),
        )
        card, card_layout = make_card("softCard")
        card_layout.addLayout(section_heading("Fechas para modelos", "Copiá el dato o su variable para usarlo en un escrito."))
        row = QHBoxLayout()
        for key, value in values:
            button = QPushButton(f"{value}\n{{{{{key}}}}}")
            button.setToolTip(f"Copiar {{{{{key}}}}}")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda checked=False, code=f"{{{{{key}}}}}": QApplication.clipboard().setText(code))
            row.addWidget(button)
        card_layout.addLayout(row)
        parent_layout.addWidget(card)

    def open_template_variables(self):
        entries = {
            "TITULO": "Título breve del escrito",
            "CARATULA": "Carátula generada del expediente",
            "ACTOR": "Parte actora",
            "DEMANDADO": "Demandado principal",
            "CAUSA": "Objeto o causa",
            "CUIJ": "Número de expediente",
            "ABOGADO": "Profesional interviniente",
            "FECHA": "Fecha de generación",
            "FECHA_EXTENSA": "Fecha de generación en letras",
            "ABOGADO_DE_LA_CONTRAPARTE": "Abogado informado para la contraparte",
            "ABOGADO_CONTRAPARTE": "Abogado informado para la contraparte",
        }
        for key in set(CASE_FIELDS) | all_defined_keys():
            variable = ADVANCED_FIELD_VARIABLES.get(key, template_variable_name(key))
            entries.setdefault(variable, key)
            entries.setdefault(template_variable_name(key), key)
        MetadataPlaceholderDialog(entries, self).exec()

    def _store_case_type_draft(self):
        for key in self._type_field_keys:
            editor = self.edits.get(key)
            if editor is not None:
                value = self._editor_value(editor)
                if value:
                    self._base_metadata[key] = value
                else:
                    self._base_metadata.pop(key, None)
        for key in self._type_repeated_keys:
            editor = self.repeated.get(key)
            if editor is not None:
                value = editor.value()
                if value:
                    self._base_metadata[key] = value
                else:
                    self._base_metadata.pop(key, None)

    def _rebuild_case_type_fields(self):
        while self.case_type_dynamic.count():
            item = self.case_type_dynamic.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for key in self._type_field_keys:
            self.edits.pop(key, None)
            self._field_specs.pop(key, None)
        for key in self._type_repeated_keys:
            self.repeated.pop(key, None)
        before_fields = set(self.edits)
        before_repeated = set(self.repeated)
        self._add_sections(self.case_type_dynamic, sections_for_case_type(self._active_case_type))
        self._add_repeated(self.case_type_dynamic, repeated_for_case_type(self._active_case_type))
        self._type_field_keys = set(self.edits) - before_fields
        self._type_repeated_keys = set(self.repeated) - before_repeated
        self.tabs.setTabText(self.case_type_tab_index, f"Datos del caso · {self._active_case_type}")
        if hasattr(self, "raeo_tab_index"):
            self.tabs.setTabVisible(self.raeo_tab_index, self._active_case_type == CASE_TYPE_LRT)

    def _case_type_changed(self, text: str):
        if text not in CASE_TYPES or text == self._active_case_type:
            return
        self._store_case_type_draft()
        self._active_case_type = text
        self._base_metadata[CASE_TYPE_FIELD] = text
        self._base_metadata["Tipo de proceso"] = text
        self._rebuild_case_type_fields()
        self.refresh_dynamic_information()

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
        self.raeo_tab_index = self.tabs.addTab(tab, "RAEO")
        self.tabs.setTabVisible(self.raeo_tab_index, self._active_case_type == CASE_TYPE_LRT)

    def _add_sections(self, parent_layout: QVBoxLayout, sections):
        for section in sections:
            card, card_layout = make_card("softCard")
            card_layout.addLayout(section_heading(section.title, section.description))
            form = QFormLayout()
            form.setHorizontalSpacing(14)
            form.setVerticalSpacing(8)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for field in section.fields:
                # Algunos datos (por ejemplo ARCA/ANSES) son comunes y también
                # forman parte de fichas históricas LRT. Se muestran una sola vez:
                # sobrescribir el editor dejaría una referencia Qt ya eliminada
                # al cambiar de tipo de caso.
                if field.key in self.edits:
                    continue
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
            editor.setEditable(field.key != CASE_TYPE_FIELD)
            editor.addItem("")
            editor.addItems(field.choices)
            editor.setCurrentText(value)
            if field.key == CASE_TYPE_FIELD:
                editor.currentTextChanged.connect(self._case_type_changed)
            else:
                editor.currentTextChanged.connect(self.refresh_dynamic_information)
        elif field.kind == "textarea":
            editor = QPlainTextEdit(value)
            editor.setMaximumHeight(92)
            editor.setPlaceholderText(field.placeholder)
            editor.textChanged.connect(self.refresh_dynamic_information)
        else:
            editor = QLineEdit(value)
            editor.setPlaceholderText(field.placeholder)
            if field.key in {"Nombre completo", "Clave fiscal (ARCA)", "Clave de Seguridad Social (ANSES)"}:
                editor.setClearButtonEnabled(True)
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
        copy.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
        variable.setFocusPolicy(Qt.FocusPolicy.NoFocus)

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
            key: str(value).strip()
            for key, value in self._base_metadata.items()
            if str(value).strip()
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
        result[CASE_TYPE_FIELD] = self._active_case_type
        result["Tipo de proceso"] = self._active_case_type
        full_name = result.get("Nombre completo", "").strip()
        if full_name:
            result["Actor"] = full_name
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
            f"<b>Nombre natural:</b> {metadata.get('Nombre y apellido', '') or 'Sin cargar'} · "
            f"<b>Apellido y nombres:</b> {metadata.get('Apellido y nombres', '') or 'Sin cargar'}<br>"
            f"<b>Número de expediente:</b> {case_number or 'Sin cargar'}<br>"
            f"<b>Identificación interna:</b> {metadata.get('Identificación interna del expediente', '')}<br>"
            f"<b>Registro creado:</b> {metadata.get('Fecha de creación del registro', '')} · "
            f"<b>Profesional creador:</b> {metadata.get('Profesional creador', 'Sin registrar')}"
        )
        if hasattr(self, "process_summary"):
            self.process_summary.setText(
                f"<b>Actor:</b> {metadata.get('Actor', '') or 'Sin cargar'}<br>"
                f"<b>Demandado:</b> {metadata.get('Demandado', '') or 'Sin cargar'}<br>"
                f"<b>Causa:</b> {metadata.get('Causa', '') or 'Sin cargar'}<br>"
                f"<b>Número de expediente:</b> {case_number or 'Sin cargar'}"
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
            self.tabs.setTabText(self.raeo_tab_index, f"RAEO · {len(missing)} pendientes")
        else:
            self.raeo_status.setObjectName("caseBadge")
            self.raeo_status.setText("Datos necesarios para RAEO completos.")
            self.tabs.setTabText(self.raeo_tab_index, "RAEO · completo")
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
    def __init__(
        self,
        models: list[Path],
        parent=None,
        *,
        model_provider=None,
        add_model_callback=None,
        selection_only: bool = False,
        window_title: str | None = None,
        heading: str | None = None,
        subtitle: str | None = None,
    ):
        super().__init__(parent)
        self.models = models
        self.model_provider = model_provider
        self.add_model_callback = add_model_callback
        self.selection_only = selection_only
        self.setWindowTitle(window_title or "Crear escrito desde modelo")
        self.setMinimumSize(560, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(11)
        layout.addLayout(section_heading(
            heading or "Elegí un modelo",
            subtitle or "Buscá por nombre y definí el título del escrito en el mismo paso.",
        ))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar modelo…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_models)
        search_row = QHBoxLayout()
        search_row.addWidget(self.search, 1)
        if self.model_provider:
            refresh = QPushButton("Actualizar")
            refresh.clicked.connect(self.refresh_models)
            search_row.addWidget(refresh)
        if self.add_model_callback:
            add = QPushButton("Agregar modelo…")
            add.clicked.connect(self.add_model_from_dialog)
            search_row.addWidget(add)
        layout.addLayout(search_row)
        self.list = QListWidget()
        self.list.setObjectName("modelList")
        self.list.setIconSize(QSize(22, 22))
        self.list.currentItemChanged.connect(self.model_changed)
        self.list.itemDoubleClicked.connect(lambda _: self.accept_if_valid())
        layout.addWidget(self.list, 1)
        self.title_edit: QLineEdit | None = None
        if not self.selection_only:
            layout.addWidget(QLabel("Nombre breve del escrito"))
            self.title_edit = QLineEdit()
            self.title_edit.setPlaceholderText("Ej.: APELACIÓN")
            layout.addWidget(self.title_edit)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Elegir modelo" if self.selection_only else "Crear escrito"
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        clear_button = self.buttons.addButton("Limpiar", QDialogButtonBox.ButtonRole.ResetRole)
        clear_button.clicked.connect(self.clear_selection)
        self.buttons.accepted.connect(self.accept_if_valid)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.filter_models("")
        self.search.setFocus()

    def refresh_models(self, selected: Path | None = None):
        if self.model_provider:
            self.models = list(self.model_provider())
        self.filter_models(self.search.text())
        if selected:
            for index in range(self.list.count()):
                item = self.list.item(index)
                if Path(item.data(PATH_ROLE)) == selected:
                    self.list.setCurrentItem(item)
                    break

    def add_model_from_dialog(self):
        if not self.add_model_callback:
            return
        selected = self.add_model_callback()
        self.refresh_models(selected)

    def clear_selection(self):
        self.search.clear()
        self.list.clearSelection()
        self.list.setCurrentItem(None)
        if self.title_edit:
            self.title_edit.clear()
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

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
        if current and self.title_edit:
            self.title_edit.setText(Path(current.data(PATH_ROLE)).stem)
            self.title_edit.selectAll()
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(current is not None)

    def accept_if_valid(self):
        if self.selected_model and (self.selection_only or self.title.strip()):
            self.accept()

    @property
    def selected_model(self) -> Path | None:
        item = self.list.currentItem()
        return Path(item.data(PATH_ROLE)) if item else None

    @property
    def title(self) -> str:
        return self.title_edit.text().strip() if self.title_edit else ""


class MetadataPlaceholderDialog(QDialog):
    """Compact, searchable catalogue of placeholders recognised by Word models."""

    def __init__(self, entries: dict[str, str], parent=None):
        super().__init__(parent)
        self.entries = dict(sorted(entries.items()))
        self.setWindowTitle("Metadatos disponibles para Word")
        self.setMinimumSize(560, 500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        layout.addLayout(section_heading(
            "Variables para modelos Word",
            "Doble clic para copiar. Los datos se completan desde el caso y “Más datos”.",
        ))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar variable o descripción…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_entries)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setObjectName("modelList")
        self.list.itemDoubleClicked.connect(self.copy_current)
        layout.addWidget(self.list, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.filter_entries("")

    def filter_entries(self, query: str):
        self.list.clear()
        needle = query.casefold().strip()
        for code, description in self.entries.items():
            text = f"{{{{{code}}}}} — {description}"
            if needle and needle not in text.casefold():
                continue
            item = QListWidgetItem(ui_icon("template", "#2563A7"), text)
            item.setData(Qt.ItemDataRole.UserRole, f"{{{{{code}}}}}")
            item.setToolTip("Doble clic para copiar")
            self.list.addItem(item)

    def copy_current(self):
        item = self.list.currentItem()
        if item:
            QApplication.clipboard().setText(str(item.data(Qt.ItemDataRole.UserRole)))


class HeirPickerDialog(QDialog):
    def __init__(self, rows: list[list[str]], parent=None):
        super().__init__(parent)
        self.rows = rows
        self.setWindowTitle("Elegir poderdantes")
        self.setMinimumSize(560, 420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.addLayout(section_heading(
            "¿Para quién se genera el poder?",
            "Podés seleccionar uno o varios herederos.",
        ))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for index, row in enumerate(rows):
            detail = " · ".join(value for value in row[1:] if value)
            item = QListWidgetItem(f"{row[0]}{f' · {detail}' if detail else ''}")
            item.setData(PATH_ROLE, index)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        layout.addWidget(self.list, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continuar")
        buttons.accepted.connect(self.accept_if_selected)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept_if_selected(self):
        if self.list.selectedItems():
            self.accept()

    @property
    def selected_rows(self) -> list[list[str]]:
        indexes = sorted(int(item.data(PATH_ROLE)) for item in self.list.selectedItems())
        return [self.rows[index] for index in indexes]


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


class StudyActivityDialog(QDialog):
    def __init__(self, entries: list[tuple[Case, object]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Actividad del Estudio")
        self.resize(820, 620)
        layout = QVBoxLayout(self)
        title = QLabel("Actividad de todos los expedientes")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        note = QLabel("Ordenada por urgencia. Doble clic para abrir el expediente.")
        note.setObjectName("muted")
        layout.addWidget(note)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        layout.addWidget(self.list, 1)
        for case, activity in entries:
            item = QListWidgetItem(
                ui_icon("bell", "#B42318" if activity.priority <= 1 else "#2B7564"),
                f"{case.name}\n{activity.kind.upper()} · {activity.title}\n{activity.detail}",
            )
            item.setData(
                ACTIVITY_ROLE,
                {
                    "case_path": str(case.path),
                    "target": activity.target,
                    "title": activity.title,
                    "external_id": activity.external_id,
                    "source": activity.source,
                    "task_id": activity.task_id,
                    "file_path": activity.file_path,
                },
            )
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Open).setText("Abrir expediente")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Open).setEnabled(bool(entries))
        layout.addWidget(buttons)

    def selected_data(self) -> dict | None:
        item = self.list.currentItem()
        data = item.data(ACTIVITY_ROLE) if item else None
        return data if isinstance(data, dict) else None


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
        self.setMinimumSize(650, 720)
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
        self.visible_check = QCheckBox("Mostrar la firma en el documento")
        self.visible_check.setChecked(False)
        layout.addWidget(self.visible_check)
        options = QHBoxLayout()
        options.addWidget(QLabel("Página"))
        self.page_combo = QComboBox()
        self.page_combo.addItem("Última página", -1)
        try:
            import pymupdf

            with pymupdf.open(source) as document:
                self.page_count = len(document)
        except Exception:
            self.page_count = 1
        for index in range(self.page_count):
            self.page_combo.addItem(f"Página {index + 1}", index)
        options.addWidget(self.page_combo, 1)
        options.addWidget(QLabel("Posición"))
        self.position_combo = QComboBox()
        for label, value in (
            ("Abajo a la derecha", "bottom_right"),
            ("Abajo a la izquierda", "bottom_left"),
            ("Centro a la derecha", "middle_right"),
            ("Centro a la izquierda", "middle_left"),
            ("Arriba a la derecha", "top_right"),
            ("Arriba a la izquierda", "top_left"),
        ):
            self.position_combo.addItem(label, value)
        options.addWidget(self.position_combo, 2)
        layout.addLayout(options)
        self.preview = QLabel("Vista previa no disponible")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(330)
        self.preview.setStyleSheet("background: #E8ECEA; border: 1px solid #CBD5D1; border-radius: 8px;")
        layout.addWidget(self.preview, 1)
        self.visible_check.toggled.connect(self.refresh_signature_preview)
        self.page_combo.currentIndexChanged.connect(self.refresh_signature_preview)
        self.position_combo.currentIndexChanged.connect(self.refresh_signature_preview)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Firmar ahora")
        buttons.accepted.connect(self.accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh_signature_preview()

    def accept_if_valid(self):
        if self.name_edit.text().strip():
            self.accept()

    @property
    def output(self) -> Path:
        return self.source.parent / normalize_filename(self.name_edit.text(), ".pdf")

    @property
    def reason(self) -> str:
        return self.reason_edit.text().strip()

    @property
    def visible_signature(self) -> VisibleSignature:
        return VisibleSignature(
            enabled=self.visible_check.isChecked(),
            page=int(self.page_combo.currentData()),
            position=str(self.position_combo.currentData()),
        )

    def refresh_signature_preview(self, *args):
        try:
            import pymupdf

            page_index = int(self.page_combo.currentData())
            if page_index < 0:
                page_index = self.page_count - 1
            with pymupdf.open(self.source) as document:
                page = document[page_index]
                pix = page.get_pixmap(matrix=pymupdf.Matrix(0.72, 0.72), alpha=False)
                preview = QPixmap()
                preview.loadFromData(pix.tobytes("png"))
                if self.visible_check.isChecked():
                    x1, y1, x2, y2 = visible_signature_box(
                        page.rect.width,
                        page.rect.height,
                        str(self.position_combo.currentData()),
                    )
                    scale_x = preview.width() / page.rect.width
                    scale_y = preview.height() / page.rect.height
                    painter = QPainter(preview)
                    pen = painter.pen()
                    pen.setColor(QColor("#2B7564"))
                    pen.setWidth(3)
                    painter.setPen(pen)
                    painter.setBrush(QColor(43, 117, 100, 35))
                    painter.drawRect(
                        int(x1 * scale_x),
                        int((page.rect.height - y2) * scale_y),
                        int((x2 - x1) * scale_x),
                        int((y2 - y1) * scale_y),
                    )
                    painter.end()
                self.preview.setPixmap(
                    preview.scaled(
                        540,
                        330,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        except Exception:
            self.preview.setText("No pudimos generar la vista previa de esta página.")


class MainWindow(QMainWindow):
    sisfe_snapshot_import_requested = pyqtSignal(object, object)

    def __init__(self, store: SettingsStore | None = None):
        super().__init__()
        self.store = store or SettingsStore()
        self.sisfe_session = ManualSisfeSession()
        self.sisfe_portal = SisfePortalService(self.sisfe_session)
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
        self._loading_compilation = False
        self._loading_pending = False
        self._metadata_editing = False
        self._metadata_dirty = False
        self._loaded_metadata: dict[str, str] = {}
        self._metadata_snapshot: dict[str, str] = {}
        self._compile_thread: QThread | None = None
        self._cedula_thread: QThread | None = None
        self._recovery_thread = None
        self._study_backup_thread: QThread | None = None
        self._study_backup_worker: StudyBackupWorker | None = None
        self._study_backup_progress: QProgressDialog | None = None
        self._compile_worker: CompileWorker | None = None
        self._progress_dialog: QProgressDialog | None = None
        self._compile_cancelling = False
        self._close_after_compile = False
        self._signer_dialog: SignerDropDialog | None = None
        self._external_sign_source: Path | None = None
        self._external_sign_started_at = 0.0
        self._external_sign_candidate: tuple[Path, int] | None = None
        self._sisfe_login_dialog: SisfeLoginDialog | None = None
        self._sisfe_case_dialog: SisfeCaseBrowserDialog | None = None
        self._sisfe_download_request: tuple[str, dict] | None = None
        self._sisfe_download_queue: list[tuple[str, dict]] = []
        self._sisfe_download_failures: dict[tuple[str, str], tuple[str, dict]] = {}
        self._sisfe_download_states: dict[tuple[str, str], tuple[str, str]] = {}
        self._sisfe_download_active = False
        self._cut_paths: list[Path] = []
        self._restoring_layout = True
        self._long_task: LongTask | None = None
        self._long_task_kind = ""
        self._long_task_thread: QThread | None = None
        self._long_task_worker: BatchTaskWorker | None = None
        self._task_result_message: QMessageBox | None = None
        self._close_after_long_task = False
        self._long_task_omitted = 0
        self._sync_all_cases: list[Case] = []
        self._sync_all_index = 0
        self._sync_unit_active = False
        self._visible_unread_case: Case | None = None
        self._visible_unread_movement_ids: tuple[str, ...] = ()
        self._visible_workspace_sizes = [780, 440]
        self._layout_save_timer = QTimer(self)
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.setInterval(350)
        self._layout_save_timer.timeout.connect(self.save_layout_state)
        self._file_refresh_timer = QTimer(self)
        self._file_refresh_timer.setSingleShot(True)
        self._file_refresh_timer.setInterval(300)
        self._file_refresh_timer.timeout.connect(self.reload_case_files)
        self._file_watcher = QFileSystemWatcher(self)
        self._file_watcher.directoryChanged.connect(self.schedule_case_files_refresh)
        self._signer_output_timer = QTimer(self)
        self._signer_output_timer.setInterval(1500)
        self._signer_output_timer.timeout.connect(self.check_external_signer_output)
        self.setWindowTitle("FORO")
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
        outer.addWidget(self._build_top_bar())

        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.body_splitter.setObjectName("bodySplitter")
        self.body_splitter.setChildrenCollapsible(False)
        self.body_splitter.setHandleWidth(6)
        self.body_splitter.addWidget(self._build_sidebar())
        self.body_splitter.addWidget(self._build_workspace())
        self.body_splitter.setStretchFactor(0, 0)
        self.body_splitter.setStretchFactor(1, 1)
        self.body_splitter.setSizes([250, 1200])
        outer.addWidget(self.body_splitter, 1)

        self.setCentralWidget(root)
        self._build_status_bar()
        self.restore_layout()
        for splitter in (
            self.body_splitter,
            self.workspace_splitter,
            self.presentation_column,
        ):
            splitter.splitterMoved.connect(self.schedule_layout_save)
        self._restoring_layout = False

    # ------------------------------------------------------------------
    # Barra superior: identidad, profesional activo y opciones
    # ------------------------------------------------------------------
    def _build_top_bar(self) -> QFrame:
        top = QFrame()
        top.setObjectName("topBar")
        layout = QHBoxLayout(top)
        layout.setContentsMargins(18, 9, 12, 9)
        layout.setSpacing(9)

        mark = QLabel()
        mark.setObjectName("brandMark")
        mark.setPixmap(foro_mark(24).pixmap(QSize(24, 24)))
        mark.setFixedSize(24, 24)
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)

        brand = QLabel("FORO")
        brand.setObjectName("brand")
        layout.addWidget(brand, 0, Qt.AlignmentFlag.AlignVCenter)

        version = QLabel(f"v{__version__}")
        version.setObjectName("brandVersion")
        version.setToolTip("Versión instalada de FORO")
        layout.addWidget(version, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addStretch()

        self.professional_combo = QComboBox()
        self.professional_combo.setObjectName("professional")
        self.professional_combo.setToolTip(
            "Profesional activo. Define ubicaciones, perfil y accesos a los portales."
        )
        self.professional_combo.activated.connect(
            lambda _index: self.professional_changed(self.professional_combo.currentText())
        )
        layout.addWidget(self.professional_combo, 0, Qt.AlignmentFlag.AlignVCenter)

        self.professional_settings_button = icon_button(
            "settings",
            "Opciones del profesional y del sistema",
            lambda: None,
            color="#F9F4E9",
        )
        self.professional_settings_button.setObjectName("topIcon")
        professional_menu = QMenu(self.professional_settings_button)
        professional_menu.addAction("Configuración", self.configure_application)
        professional_menu.addAction("Crear copia de seguridad del Estudio", self.create_active_study_backup)
        professional_menu.addAction("Restaurar copia de seguridad del Estudio", self.restore_study_from_backup)
        professional_menu.addAction("Importar casos", self.import_cases_from_spreadsheet)
        professional_menu.addAction("Sincronizar todos los expedientes", self.sync_all_expedientes)
        self.professional_settings_button.setMenu(professional_menu)
        layout.addWidget(self.professional_settings_button, 0, Qt.AlignmentFlag.AlignVCenter)
        return top

    # ------------------------------------------------------------------
    # Panel lateral: búsqueda universal, Nuevo caso, ubicaciones y casos
    # ------------------------------------------------------------------
    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(215)
        sidebar.setMaximumWidth(460)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(13, 13, 13, 11)
        layout.setSpacing(9)

        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Buscar caso, parte, expediente…")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(
            ui_icon("search", "#7C8B7E"), QLineEdit.ActionPosition.LeadingPosition
        )
        self.search.setToolTip(
            "Busca en todos los casos: nombre, actor, demandado, carátula, "
            "expediente, causa y radicación."
        )
        self.search.textChanged.connect(self.reload_cases)
        layout.addWidget(self.search)

        new_case = QPushButton("Nuevo caso")
        new_case.setObjectName("primary")
        decorate_button(new_case, "folder-plus", "#F9F4E9")
        new_case.setToolTip("Crear un caso en la ubicación activa (Ctrl+Shift+N)")
        new_case.clicked.connect(self.new_case)
        layout.addWidget(new_case)

        locations_header = QHBoxLayout()
        locations_header.setSpacing(2)
        locations_label = QLabel("CASOS")
        locations_label.setObjectName("eyebrow")
        locations_header.addWidget(locations_label)
        locations_header.addStretch()
        self.add_location_button = icon_button(
            "plus",
            "Agregar una ubicación del Estudio (carpeta local, de red o sincronizada)",
            self.choose_study_root,
        )
        locations_header.addWidget(self.add_location_button)
        layout.addLayout(locations_header)

        # El resumen del Estudio se conserva como fuente de los tooltips del
        # árbol: la ruta física no compite con la información jurídica.
        self.study_name = QLabel("Sin ubicaciones", sidebar)
        self.study_name.setObjectName("sectionTitle")
        self.study_name.setVisible(False)
        self.study_path = QLabel("", sidebar)
        self.study_path.setObjectName("muted")
        self.study_path.setVisible(False)

        self.case_tree = QTreeWidget()
        self.case_tree.setObjectName("caseTree")
        self.case_tree.setHeaderHidden(True)
        self.case_tree.setIndentation(16)
        tree_palette = self.case_tree.palette()
        tree_palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 0, 0, 0))
        tree_palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#1F4034"))
        self.case_tree.setPalette(tree_palette)
        self.case_tree.itemSelectionChanged.connect(self.case_tree_changed)
        self.case_tree.itemDoubleClicked.connect(self.open_tree_case)
        self.case_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.case_tree.customContextMenuRequested.connect(self.show_case_menu)
        layout.addWidget(self.case_tree, 1)

        self.models_button = QPushButton("Modelos")
        self.models_button.setObjectName("quiet")
        decorate_button(self.models_button, "template")
        self.models_button.setToolTip("Modelos de escritos del Estudio")
        self.models_button.clicked.connect(self.open_models_folder)
        layout.addWidget(self.models_button)

        self.frequent_documents_button = QPushButton("Documentos frecuentes")
        self.frequent_documents_button.setObjectName("quiet")
        decorate_button(self.frequent_documents_button, "books")
        self.frequent_documents_button.setToolTip(
            "Matrícula, ARCA, CBU y archivos recurrentes, listos para arrastrar"
        )
        self.frequent_documents_button.clicked.connect(self.toggle_quick_access)
        layout.addWidget(self.frequent_documents_button)

        self._build_frequent_documents_panel()
        return sidebar

    def _build_frequent_documents_panel(self):
        """Panel pequeño y flotante; reemplaza a la antigua Biblioteca fija."""
        self.quick_panel = QDialog(self)
        self.quick_panel.setWindowTitle("Documentos frecuentes")
        self.quick_panel.setWindowFlag(Qt.WindowType.Tool, True)
        self.quick_panel.resize(380, 440)
        panel_layout = QVBoxLayout(self.quick_panel)
        panel_layout.setContentsMargins(14, 12, 14, 12)
        panel_layout.setSpacing(8)

        header = QHBoxLayout()
        self.quick_label = QLabel("DOCUMENTOS FRECUENTES")
        self.quick_label.setObjectName("eyebrow")
        header.addWidget(self.quick_label)
        header.addStretch()
        self.quick_count = QLabel("0")
        self.quick_count.setObjectName("muted")
        header.addWidget(self.quick_count)
        panel_layout.addLayout(header)

        self.quick_note = QLabel(
            "Arrastrá estos archivos a un caso, a la presentación, a un correo o a WhatsApp."
        )
        self.quick_note.setObjectName("muted")
        self.quick_note.setWordWrap(True)
        panel_layout.addWidget(self.quick_note)

        self.quick_access = QuickAccessList()
        self.quick_access.itemDoubleClicked.connect(lambda _: self.open_selected_quick_file())
        self.quick_access.itemChanged.connect(self.finish_quick_rename)
        self.quick_access.customContextMenuRequested.connect(self.show_quick_menu)
        panel_layout.addWidget(self.quick_access, 1)

        self.quick_actions_widget = QWidget()
        quick_actions = QHBoxLayout(self.quick_actions_widget)
        quick_actions.setContentsMargins(0, 0, 0, 0)
        quick_add = QPushButton("Agregar")
        decorate_button(quick_add, "paperclip")
        quick_add.clicked.connect(self.pick_quick_files)
        quick_folder = icon_button(
            "folder-open",
            "Abrir la carpeta de Documentos frecuentes",
            self.open_quick_folder,
            bordered=True,
        )
        quick_actions.addWidget(quick_add)
        quick_actions.addStretch()
        quick_actions.addWidget(quick_folder)
        panel_layout.addWidget(self.quick_actions_widget)

    # ------------------------------------------------------------------
    # Zona de trabajo
    # ------------------------------------------------------------------
    def _build_workspace(self) -> QWidget:
        wrap = QWidget()
        wrap_layout = QVBoxLayout(wrap)
        wrap_layout.setContentsMargins(16, 12, 16, 10)
        wrap_layout.setSpacing(0)

        self.workspace = QWidget()
        workspace_layout = QVBoxLayout(self.workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(10)
        workspace_layout.addWidget(self._build_case_header())

        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setObjectName("workspaceSplitter")
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setHandleWidth(6)

        self.work_tabs = QTabWidget()
        self.work_tabs.setDocumentMode(True)
        self.files_tab_index = self.work_tabs.addTab(
            self._build_files_tab(), ui_icon("folder-open", "#2B5748"), "Archivos"
        )
        self.portal_tab_index = self.work_tabs.addTab(
            self._build_expediente_tab(), ui_icon("file-text", "#2B5748"), "Expediente · 0"
        )
        self._pending_page = self._build_pending_tab()
        self.pending_tab_index = -1
        # Se conserva la lógica interna para accesos globales y compatibilidad,
        # pero Actividad ya no ocupa una pestaña del caso.
        self._activity_page = self._build_activity_tab()
        self.activity_tab_index = -1
        self.work_tabs.currentChanged.connect(self.case_tab_changed)
        self.workspace_splitter.addWidget(self.work_tabs)
        self.workspace_splitter.addWidget(self._build_presentation_panel())
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 0)
        self.workspace_splitter.setSizes(self._visible_workspace_sizes)
        workspace_layout.addWidget(self.workspace_splitter, 1)

        wrap_layout.addWidget(self.workspace, 1)
        return wrap

    # ------------------------------------------------------------------
    # Encabezado del caso abierto: carátula y cinco datos
    # ------------------------------------------------------------------
    def _build_case_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("caseHeader")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 14, 12)
        layout.setSpacing(9)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.case_title = QLabel("Elegí un caso")
        self.case_title.setObjectName("caseTitle")
        self.case_title.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        title_row.addWidget(self.case_title, 1)

        self.case_badge = QLabel()
        self.case_badge.setObjectName("caseBadge")
        self.case_badge.hide()
        title_row.addWidget(self.case_badge)

        self.client_cases_button = QPushButton()
        self.client_cases_button.setObjectName("quiet")
        decorate_button(self.client_cases_button, "person")
        self.client_cases_button.setToolTip("Ver otros casos de este cliente")
        self.client_cases_button.clicked.connect(self.show_client_cases)
        self.client_cases_button.hide()
        title_row.addWidget(self.client_cases_button)

        self.open_case_button = icon_button(
            "folder-open",
            "Abrir la carpeta del caso en el Explorador",
            self.open_case_folder,
        )
        self.open_case_button.hide()
        title_row.addWidget(self.open_case_button)

        self.edit_metadata_button = icon_button(
            "edit",
            "Editar los datos visibles del caso",
            self.begin_metadata_edit,
            bordered=True,
        )
        self.cancel_metadata_button = QPushButton("Cancelar")
        self.cancel_metadata_button.clicked.connect(self.cancel_metadata_edit)
        self.cancel_metadata_button.hide()
        title_row.addWidget(self.cancel_metadata_button)

        self.save_metadata_button = QPushButton("Guardar")
        self.save_metadata_button.setObjectName("green")
        decorate_button(self.save_metadata_button, "check", "#FFFFFF")
        self.save_metadata_button.clicked.connect(self.commit_metadata)
        self.save_metadata_button.hide()
        title_row.addWidget(self.save_metadata_button)

        self.more_metadata_button = QPushButton("Datos del caso")
        decorate_button(self.more_metadata_button, "file-text")
        self.more_metadata_button.setToolTip(
            "Ficha estructural del caso: alimenta búsquedas y generación de escritos"
        )
        self.more_metadata_button.clicked.connect(self.open_extended_metadata)
        title_row.addWidget(self.more_metadata_button)

        layout.addLayout(title_row)

        fields_widget = QWidget()
        fields_grid = QGridLayout(fields_widget)
        fields_grid.setContentsMargins(0, 0, 0, 0)
        fields_grid.setHorizontalSpacing(18)
        fields_grid.setVerticalSpacing(2)
        self.metadata_edits: dict[str, QLineEdit] = {}
        stretch_by_field = {
            "Actor": 3,
            "Demandado": 3,
            "Causa": 3,
            "CUIJ": 2,
            "Radicación": 3,
        }
        previous_edit: QLineEdit | None = None
        for column, field in enumerate(VISIBLE_CASE_FIELDS):
            display_name = CASE_FIELD_LABELS.get(field, field)
            label = QLabel(display_name.upper())
            label.setObjectName("fieldLabel")
            edit = QLineEdit()
            edit.setObjectName("metaValue")
            edit.setPlaceholderText(display_name)
            edit.setReadOnly(True)
            edit.textChanged.connect(self.metadata_changed)
            self.metadata_edits[field] = edit
            fields_grid.addWidget(label, 0, column)
            fields_grid.addWidget(edit, 1, column)
            fields_grid.setColumnStretch(column, stretch_by_field.get(field, 2))
            if previous_edit is not None:
                QWidget.setTabOrder(previous_edit, edit)
            previous_edit = edit
        fields_grid.addWidget(
            self.edit_metadata_button,
            1,
            len(VISIBLE_CASE_FIELDS),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        layout.addWidget(fields_widget)

        # Radicación: texto libre que además se autocompleta con los valores
        # que el propio Estudio viene usando.
        self.radicacion_completer = QCompleter([], self)
        self.radicacion_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.radicacion_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.radicacion_completer.setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion
        )
        self.metadata_edits["Radicación"].setCompleter(self.radicacion_completer)
        return card

    # ------------------------------------------------------------------
    # Pestaña Archivos: lógica de Explorador
    # ------------------------------------------------------------------
    def _build_files_tab(self) -> QFrame:
        card, layout = make_card()
        header = QHBoxLayout()
        header.setSpacing(8)
        self.files_search = QLineEdit()
        self.files_search.setPlaceholderText("Buscar archivos en este caso…")
        self.files_search.setClearButtonEnabled(True)
        self.files_search.addAction(
            ui_icon("search", "#7C8B7E"), QLineEdit.ActionPosition.LeadingPosition
        )
        self.files_search.textChanged.connect(lambda _: self.reload_case_files())
        header.addWidget(self.files_search, 1)
        self.files_location = QLabel("Inicio")
        self.files_location.setObjectName("muted")
        header.addWidget(self.files_location)
        self.files_count = QLabel("0 elementos")
        self.files_count.setObjectName("muted")
        header.addWidget(self.files_count)
        sort_button = icon_button("sort", "Ordenar archivos", lambda: None, bordered=True)
        sort_menu = QMenu(sort_button)
        for label, value in (
            ("Nombre A → Z", "name_asc"), ("Nombre Z → A", "name_desc"),
            ("Más recientes", "modified_desc"), ("Más antiguos", "modified_asc"),
            ("Tipo A → Z", "type_asc"), ("Tipo Z → A", "type_desc"),
        ):
            sort_menu.addAction(
                label,
                lambda _checked=False, key=value: self.files_sort_combo.setCurrentIndex(
                    self.files_sort_combo.findData(key)
                ),
            )
        sort_button.setMenu(sort_menu)
        header.addWidget(sort_button)
        layout.addLayout(header)

        # El orden se gobierna desde los encabezados de columna; el combo se
        # conserva oculto porque es el estado que persiste la distribución.
        self.files_sort_combo = QComboBox()
        self.files_sort_combo.setToolTip("Cambia solamente el orden visual de esta lista")
        for label, value in (
            ("Nombre · A → Z", "name_asc"),
            ("Nombre · Z → A", "name_desc"),
            ("Fecha · reciente", "modified_desc"),
            ("Fecha · antigua", "modified_asc"),
            ("Tamaño · mayor", "size_desc"),
            ("Tamaño · menor", "size_asc"),
            ("Tipo · A → Z", "type_asc"),
            ("Tipo · Z → A", "type_desc"),
        ):
            self.files_sort_combo.addItem(label, value)
        self.files_sort_combo.currentIndexChanged.connect(self.change_files_sort)
        self.files_sort_combo.hide()
        layout.addWidget(self.files_sort_combo)

        columns = QWidget()
        columns_layout = QHBoxLayout(columns)
        columns_layout.setContentsMargins(34, 0, 8, 0)
        columns_layout.setSpacing(0)
        self.files_column_buttons: dict[str, QPushButton] = {}
        for key, text, width in (
            ("name", "Nombre", 0),
            ("modified", "Fecha de modificación", DATE_COLUMN_WIDTH),
            ("size", "Tamaño", SIZE_COLUMN_WIDTH),
        ):
            button = QPushButton(text)
            button.setObjectName("columnHeaderButton")
            button.setToolTip(f"Ordenar por {text.lower()}")
            button.setAccessibleName(f"Ordenar por {text.lower()}")
            if width:
                button.setFixedWidth(width)
                columns_layout.addWidget(button, 0)
            else:
                columns_layout.addWidget(button, 1)
            button.clicked.connect(
                lambda _checked=False, column=key: self.sort_case_files_by(column)
            )
            self.files_column_buttons[key] = button
        layout.addWidget(columns)

        self.case_files = CaseFilesList()
        self.case_files.itemDoubleClicked.connect(lambda _: self.open_selected_file())
        self.case_files.itemChanged.connect(self.finish_file_rename)
        self.case_files.customContextMenuRequested.connect(self.show_file_menu)
        layout.addWidget(self.case_files, 1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.files_back = icon_button(
            "arrow-left",
            "Volver a la carpeta anterior",
            self.go_up_case_folder,
            bordered=True,
        )
        add_files = QPushButton("Agregar archivo")
        decorate_button(add_files, "paperclip")
        add_files.setToolTip("Copiar archivos a la carpeta del caso (Ctrl+O)")
        add_files.clicked.connect(self.pick_case_files)
        self.add_to_presentation_button = QPushButton("Agregar a presentación")
        self.add_to_presentation_button.setObjectName("green")
        decorate_button(self.add_to_presentation_button, "arrow-right", "#FFFFFF")
        self.add_to_presentation_button.setToolTip(
            "Llevar la selección al panel Presentación"
        )
        self.add_to_presentation_button.clicked.connect(self.add_selected_to_compilation)
        actions.addWidget(self.files_back)
        actions.addWidget(add_files)
        actions.addStretch()
        actions.addWidget(self.add_to_presentation_button)
        layout.addLayout(actions)
        return card

    # ------------------------------------------------------------------
    # Pestaña Expediente: movimientos judiciales
    # ------------------------------------------------------------------
    def _build_expediente_tab(self) -> QFrame:
        card, layout = make_card()
        header = QHBoxLayout()
        header.addLayout(
            section_heading("Expediente", "Movimientos del portal, en orden cronológico")
        )
        header.addStretch()
        self.novedades_count = QLabel("Sin movimientos")
        self.novedades_count.setObjectName("muted")
        header.addWidget(self.novedades_count)
        layout.addLayout(header)

        self.portal_case_status = QLabel("UBICACIÓN ACTUAL · Sin información")
        self.portal_case_status.setObjectName("caseBadge")
        self.portal_case_status.setWordWrap(True)
        layout.addWidget(self.portal_case_status)

        self.novedades_list = QListWidget()
        self.novedades_list.setObjectName("novedadesList")
        self.novedades_list.setMinimumHeight(200)
        self.novedades_list.setWordWrap(True)
        self.novedades_list.setIconSize(QSize(24, 24))
        self.novedades_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.novedades_list.itemSelectionChanged.connect(self.update_novedad_actions)
        self.novedades_list.itemDoubleClicked.connect(lambda _: self.open_selected_novedad())
        self.novedades_list.customContextMenuRequested.connect(self.show_novedad_menu)
        layout.addWidget(self.novedades_list, 1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.sisfe_sync_button = QPushButton("Sincronizar este expediente")
        self.sisfe_sync_button.setText("")
        self.sisfe_sync_button.setIcon(ui_icon("refresh", "#2B7564"))
        self.sisfe_sync_button.setToolTip("Sincronizar expediente")
        self.sisfe_sync_button.setAccessibleName("Sincronizar expediente")
        self.sisfe_sync_button.clicked.connect(self.sync_sisfe)
        actions.addWidget(self.sisfe_sync_button)
        self.download_pending_button = icon_button(
            "download", "Descargar PDFs pendientes", self.download_pending_pdfs, bordered=True
        )
        actions.addWidget(self.download_pending_button)
        actions.addStretch()
        self.sisfe_retry_button = icon_button(
            "refresh", "Reintentar la última descarga SISFE", self.retry_sisfe_download,
            bordered=True,
        )
        self.sisfe_retry_button.setVisible(False)
        actions.addWidget(self.sisfe_retry_button)
        self.sisfe_show_download_button = icon_button(
            "external", "Abrir SISFE para resolver la descarga", self.show_sisfe_download,
            bordered=True,
        )
        self.sisfe_show_download_button.setVisible(False)
        actions.addWidget(self.sisfe_show_download_button)
        layout.addLayout(actions)
        return card

    # ------------------------------------------------------------------
    # Pestaña Actividad (sin rediseño en esta etapa)
    # ------------------------------------------------------------------
    def _build_activity_tab(self) -> QFrame:
        card, layout = make_card()
        header = QHBoxLayout()
        header.addLayout(
            section_heading(
                "Actividad del expediente",
                "Lo que requiere atención, reunido desde Portal y Pendientes",
            )
        )
        header.addStretch()
        self.activity_count = QLabel("Sin acciones")
        self.activity_count.setObjectName("muted")
        header.addWidget(self.activity_count)
        self.show_completed_tasks = QCheckBox("Ver completadas")
        self.show_completed_tasks.toggled.connect(self.reload_activity)
        header.addWidget(self.show_completed_tasks)
        layout.addLayout(header)
        self.activity_list = QListWidget()
        self.activity_list.setObjectName("activityList")
        self.activity_list.itemSelectionChanged.connect(self.update_activity_actions)
        self.activity_list.itemDoubleClicked.connect(lambda _: self.open_selected_activity())
        layout.addWidget(self.activity_list, 1)
        actions = QHBoxLayout()
        hint = QLabel(
            "Doble clic para ir al movimiento o documento pendiente que originó la acción."
        )
        hint.setObjectName("muted")
        actions.addWidget(hint, 1)
        new_activity_task = QPushButton("Nueva tarea")
        decorate_button(new_activity_task, "plus")
        new_activity_task.clicked.connect(self.create_manual_activity_task)
        actions.addWidget(new_activity_task)
        self.edit_activity_task_button = QPushButton("Editar tarea")
        decorate_button(self.edit_activity_task_button, "edit")
        self.edit_activity_task_button.clicked.connect(self.edit_manual_activity_task)
        self.edit_activity_task_button.setEnabled(False)
        actions.addWidget(self.edit_activity_task_button)
        self.confirm_activity_button = QPushButton("Confirmar como tarea")
        self.confirm_activity_button.setObjectName("green")
        decorate_button(self.confirm_activity_button, "check", "#FFFFFF")
        self.confirm_activity_button.clicked.connect(self.confirm_selected_activity)
        self.confirm_activity_button.setEnabled(False)
        actions.addWidget(self.confirm_activity_button)
        layout.addLayout(actions)
        return card

    # ------------------------------------------------------------------
    # Pestaña Pendientes (fuera de alcance en esta revisión)
    # ------------------------------------------------------------------
    def _build_pending_tab(self) -> QFrame:
        card, layout = make_card()
        header = QHBoxLayout()
        header.addLayout(
            section_heading(
                "Documentación pendiente",
                "Checklist de lo solicitado al cliente y todavía no recibido",
            )
        )
        header.addStretch()
        self.pending_documents_count = QLabel("Sin pendientes")
        self.pending_documents_count.setObjectName("muted")
        header.addWidget(self.pending_documents_count)
        layout.addLayout(header)
        self.pending_documents_list = QListWidget()
        self.pending_documents_list.setObjectName("pendingDocumentsList")
        self.pending_documents_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.pending_documents_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.pending_documents_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.pending_documents_list.model().rowsMoved.connect(
            lambda: QTimer.singleShot(0, self.persist_pending_document_order)
        )
        self.pending_documents_list.itemSelectionChanged.connect(
            self.update_pending_document_actions
        )
        self.pending_documents_list.itemChanged.connect(self.pending_document_changed)
        layout.addWidget(self.pending_documents_list, 1)
        actions = QHBoxLayout()
        pending_add = QPushButton("Agregar pendiente")
        decorate_button(pending_add, "plus")
        pending_add.clicked.connect(self.add_pending_document)
        self.pending_rename_button = icon_button("edit", "Renombrar pendiente", self.rename_pending_document)
        self.pending_due_button = icon_button(
            "bell", "Definir fecha objetivo y recordatorio", self.set_pending_document_due_date
        )
        self.pending_delete_button = icon_button("trash", "Borrar pendientes seleccionados", self.delete_pending_documents)
        self.pending_clear_button = icon_button("clear", "Vaciar la lista de pendientes", self.clear_pending_documents)
        self.pending_up_button = icon_button("arrow-up", "Subir en el orden", lambda: self.move_pending_document(-1))
        self.pending_down_button = icon_button("arrow-down", "Bajar en el orden", lambda: self.move_pending_document(1))
        self.pending_received_button = QPushButton("Marcar como recibido")
        self.pending_received_button.setObjectName("green")
        decorate_button(self.pending_received_button, "check", "#FFFFFF")
        self.pending_received_button.clicked.connect(self.complete_pending_documents)
        self.pending_received_button.setEnabled(False)
        actions.addWidget(pending_add)
        actions.addWidget(self.pending_rename_button)
        actions.addWidget(self.pending_due_button)
        actions.addWidget(self.pending_delete_button)
        actions.addWidget(self.pending_clear_button)
        actions.addWidget(self.pending_up_button)
        actions.addWidget(self.pending_down_button)
        actions.addStretch()
        actions.addWidget(self.pending_received_button)
        layout.addLayout(actions)
        return card

    # ------------------------------------------------------------------
    # Panel Presentación
    # ------------------------------------------------------------------
    def _build_presentation_panel(self) -> QSplitter:
        preparation_card, preparation_layout = make_card()
        header = QHBoxLayout()
        title = QLabel("Presentación")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()
        self.compilation_count = QLabel("0 elementos")
        self.compilation_count.setObjectName("muted")
        header.addWidget(self.compilation_count)
        add_presentation = icon_button(
            "plus", "Agregar archivos a la presentación", self.pick_presentation_files,
            bordered=True,
        )
        header.addWidget(add_presentation)
        self.compilation_toggle_button = icon_button(
            "arrow-right", "Ocultar el panel Presentación", self.toggle_compilation_panel,
            bordered=True,
        )
        header.addWidget(self.compilation_toggle_button)
        preparation_layout.addLayout(header)

        writing_row = QHBoxLayout()
        writing_row.setSpacing(5)
        self.writing_button = QPushButton("Nuevo escrito")
        self.writing_button.setObjectName("primary")
        decorate_button(self.writing_button, "file-plus", "#F9F4E9")
        self.writing_button.setToolTip("Elegir un modelo y crear el escrito del caso (Ctrl+N)")
        self.writing_button.clicked.connect(self.new_writing_from_model)
        writing_row.addWidget(self.writing_button, 1)
        preparation_layout.addLayout(writing_row)

        self.writing_name = QLabel("Todavía no elegiste un escrito")
        self.writing_name.setObjectName("muted")
        self.writing_name.setWordWrap(True)
        preparation_layout.addWidget(self.writing_name)

        files_label = QLabel("ARCHIVOS EN LA PRESENTACIÓN")
        files_label.setObjectName("eyebrow")
        preparation_layout.addWidget(files_label)

        self.compilation = CompilationList()
        self.compilation.filesDropped.connect(self.handle_compilation_drop)
        self.compilation.dropRejected.connect(self.notify_unsupported_file_drop)
        self.compilation.removeRequested.connect(self.remove_from_compilation)
        self.compilation.openRequested.connect(open_file)
        self.compilation.orderChanged.connect(self.update_compilation_count)
        preparation_layout.addWidget(self.compilation, 1)

        prep_actions = QHBoxLayout()
        prep_actions.setSpacing(5)
        remove = icon_button("trash", "Quitar de la presentación", self.remove_from_compilation)
        clear = icon_button("clear", "Vaciar la presentación sin borrar archivos", self.clear_compilation)
        history = icon_button("history", "Recuperar una presentación anterior", self.open_compilation_history)
        move_up = icon_button("arrow-up", "Subir en el orden", lambda: self.move_compilation_item(-1))
        move_down = icon_button("arrow-down", "Bajar en el orden", lambda: self.move_compilation_item(1))
        prep_actions.addWidget(remove)
        prep_actions.addWidget(clear)
        prep_actions.addWidget(history)
        prep_actions.addStretch()
        prep_actions.addWidget(move_up)
        prep_actions.addWidget(move_down)
        preparation_layout.addLayout(prep_actions)

        actions_card, actions_layout = make_card("actionCard")
        limit_label = QLabel("LÍMITE DE TAMAÑO FINAL")
        limit_label.setObjectName("eyebrow")
        actions_layout.addWidget(limit_label)

        # El combo es el modelo de datos del límite y conserva el borrador
        # portable; la elección visible son los cuatro botones del panel.
        self.limit_combo = QComboBox()
        for label, value in PRESENTATION_PROFILES.items():
            self.limit_combo.addItem(label, value)
        self.limit_combo.setCurrentIndex(self.limit_combo.findText(DEFAULT_PROFILE))
        self.limit_combo.currentTextChanged.connect(self.compilation_profile_changed)
        self.limit_combo.hide()
        actions_layout.addWidget(self.limit_combo)

        limits_row = QHBoxLayout()
        limits_row.setSpacing(5)
        self.limit_buttons: dict[int, QPushButton] = {}
        for text, value in PRESENTATION_LIMITS:
            button = QPushButton(text)
            button.setObjectName("limit")
            button.setCheckable(True)
            button.setToolTip(
                f"Comprimir la presentación hasta {text}. "
                "Volvé a tocarlo para compilar sin compresión."
            )
            button.clicked.connect(
                lambda _checked=False, limit=value: self.choose_presentation_limit(limit)
            )
            limits_row.addWidget(button)
            self.limit_buttons[value] = button
        actions_layout.addLayout(limits_row)

        self.limit_hint = QLabel("Sin límite elegido: se compila al tamaño natural.")
        self.limit_hint.setObjectName("actionMuted")
        self.limit_hint.setWordWrap(True)
        actions_layout.addWidget(self.limit_hint)

        # Conservado oculto por compatibilidad con integraciones anteriores.
        self.output_preview = QLabel("Se definirá al compilar")
        self.output_preview.setObjectName("actionMuted")
        self.output_preview.setWordWrap(True)
        self.output_preview.hide()
        actions_layout.addWidget(self.output_preview)
        self.output_name = QLineEdit()
        self.output_name.hide()

        actions_layout.addSpacing(4)
        self.compile_button = QPushButton("Compilar PDF")
        self.compile_button.setObjectName("primary")
        decorate_button(self.compile_button, "layers", "#F9F4E9")
        self.compile_button.setToolTip("Unir la presentación en un único PDF (Ctrl+P)")
        self.compile_button.clicked.connect(self.compile_pdf)
        actions_layout.addWidget(self.compile_button)

        sign_row = QHBoxLayout()
        sign_row.setSpacing(5)
        self.sign_button = QPushButton("Firmar")
        decorate_button(self.sign_button, "signature")
        self.sign_button.setToolTip("Firmar el PDF seleccionado o el último compilado")
        self.sign_button.clicked.connect(self.sign_current_pdf)
        sign_row.addWidget(self.sign_button, 1)
        self.sign_options_button = QPushButton()
        self.sign_options_button.setMaximumWidth(38)
        self.sign_options_button.setIcon(ui_icon("arrow-down", "#2B5748"))
        self.sign_options_button.setToolTip("Otras opciones de firma")
        self.sign_options_button.setAccessibleName("Otras opciones de firma")
        self.sign_options_button.clicked.connect(self.show_sign_menu)
        sign_row.addWidget(self.sign_options_button)
        actions_layout.addLayout(sign_row)

        last_label = QLabel("ÚLTIMO RESULTADO")
        last_label.setObjectName("eyebrow")
        actions_layout.addWidget(last_label)
        self.last_output = QLabel("Aún no compilaste")
        self.last_output.setObjectName("actionMuted")
        self.last_output.setWordWrap(True)
        actions_layout.addWidget(self.last_output)

        self.compilation_card = preparation_card
        self.presentation_column = QSplitter(Qt.Orientation.Vertical)
        self.presentation_column.setObjectName("presentationColumn")
        self.presentation_column.setChildrenCollapsible(False)
        self.presentation_column.setHandleWidth(6)
        self.presentation_column.setMinimumWidth(250)
        self.presentation_column.setMaximumWidth(560)
        self.presentation_column.addWidget(self.compilation_card)
        self.presentation_column.addWidget(actions_card)
        self.presentation_column.setSizes([520, 300])
        return self.presentation_column

    # ------------------------------------------------------------------
    # Barra inferior de estado
    # ------------------------------------------------------------------
    def _build_status_bar(self):
        bar = QStatusBar()
        bar.setSizeGripEnabled(False)
        self.case_sync_label = OperationStatusIndicator("", compact=False)
        self.case_sync_label.hide()
        bar.addWidget(self.case_sync_label)

        middle = QWidget()
        middle.setObjectName("statusMiddle")
        middle_layout = QHBoxLayout(middle)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.addStretch(1)
        self.status_activity = QWidget()
        activity_layout = QHBoxLayout(self.status_activity)
        activity_layout.setContentsMargins(12, 0, 12, 0)
        activity_layout.setSpacing(8)
        self.status_center = QLabel("")
        self.status_center.setObjectName("muted")
        self.task_progress = QProgressBar()
        self.task_progress.setObjectName("taskProgress")
        self.task_progress.setFixedWidth(170)
        self.task_progress.setTextVisible(False)
        self.task_stop_button = icon_button(
            "stop", "Detener sincronización", self.stop_long_task, color="#6C7A6D"
        )
        activity_layout.addWidget(self.status_center)
        activity_layout.addWidget(self.task_progress)
        activity_layout.addWidget(self.task_stop_button)
        self.status_activity.hide()
        middle_layout.addWidget(self.status_activity)
        middle_layout.addStretch(1)
        bar.addWidget(middle, 1)

        self.status_right = QWidget()
        self.status_right.setObjectName("statusRight")
        right_layout = QHBoxLayout(self.status_right)
        right_layout.setContentsMargins(8, 0, 6, 0)
        right_layout.setSpacing(8)
        self.sync_all_button = QPushButton("Sincronizar todos")
        decorate_button(self.sync_all_button, "refresh")
        self.sync_all_button.setToolTip("Sincronizar todos los expedientes")
        self.sync_all_button.clicked.connect(self.sync_all_expedientes)
        self.sync_all_button.setObjectName("statusAction")
        right_layout.addWidget(self.sync_all_button)
        self.sisfe_indicator = OperationStatusIndicator("SISFE sin confirmar", compact=True)
        self.sisfe_status = self.sisfe_indicator
        self.sisfe_indicator.setToolTip(
            "SISFE sin confirmar. Abrí y confirmá la sesión del profesional."
        )
        self.sisfe_indicator.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sisfe_indicator.mousePressEvent = lambda _event: self.open_sisfe_session()
        right_layout.addWidget(self.sisfe_indicator)
        bar.addPermanentWidget(self.status_right)
        self.setStatusBar(bar)
        self.statusBar().showMessage("Listo")

    def _install_shortcuts(self):
        self.new_case_shortcut = QShortcut(QKeySequence("Ctrl+Shift+N"), self)
        self.new_case_shortcut.activated.connect(self.new_case)
        self.new_writing_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        self.new_writing_shortcut.activated.connect(self.new_writing_from_model)
        self.add_file_shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        self.add_file_shortcut.activated.connect(self.pick_case_files)
        self.compile_shortcut = QShortcut(QKeySequence("Ctrl+P"), self)
        self.compile_shortcut.activated.connect(self.compile_pdf)
        self.rename_shortcut = QShortcut(QKeySequence("F2"), self)
        self.rename_shortcut.activated.connect(self.rename_selected_file)

    @staticmethod
    def _valid_layout_sizes(value: object, count: int, fallback: list[int]) -> list[int]:
        if not isinstance(value, list) or len(value) != count:
            return list(fallback)
        try:
            sizes = [max(0, int(size)) for size in value]
        except (TypeError, ValueError):
            return list(fallback)
        return sizes if sum(sizes) > 0 else list(fallback)

    def sidebar_widths(self) -> dict[str, int]:
        raw = self.store.settings.layout_state.get("sidebar_by_professional", {})
        if not isinstance(raw, dict):
            return {}
        widths = {}
        for name, value in raw.items():
            try:
                widths[str(name)] = int(value)
            except (TypeError, ValueError):
                continue
        return widths

    def restore_layout(self):
        state = self.store.settings.layout_state
        body_sizes = self._valid_layout_sizes(state.get("body"), 2, [250, 1200])
        stored_width = self.sidebar_widths().get(self.store.settings.current_professional)
        if stored_width:
            total = sum(body_sizes) or 1450
            body_sizes = [stored_width, max(total - stored_width, 600)]
        workspace_sizes = self._valid_layout_sizes(
            state.get("workspace"), 2, self._visible_workspace_sizes
        )
        presentation_sizes = self._valid_layout_sizes(
            state.get("presentation"), 2, [520, 300]
        )
        self._visible_workspace_sizes = workspace_sizes
        self.body_splitter.setSizes(body_sizes)
        self.presentation_column.setSizes(presentation_sizes)
        visible = state.get("compilation_visible", True)
        self.set_compilation_panel_visible(visible if isinstance(visible, bool) else True)
        self.restore_files_sort()
        self.restore_presentation_limit()

    def schedule_layout_save(self, *_args):
        if not self._restoring_layout:
            self._layout_save_timer.start()

    def save_layout_state(self):
        if self._restoring_layout:
            return
        workspace_sizes = self.workspace_splitter.sizes()
        if not self.presentation_column.isHidden() and len(workspace_sizes) == 2 and workspace_sizes[1] > 0:
            self._visible_workspace_sizes = workspace_sizes
        body_sizes = self.body_splitter.sizes()
        sidebar_widths = self.sidebar_widths()
        professional = self.store.settings.current_professional
        if professional and body_sizes and body_sizes[0] > 0:
            sidebar_widths[professional] = int(body_sizes[0])
        self.store.set_layout_state(
            {
                **self.store.settings.layout_state,
                "body": body_sizes,
                "workspace": self._visible_workspace_sizes,
                "presentation": self.presentation_column.sizes(),
                "compilation_visible": not self.presentation_column.isHidden(),
                "files_sort": self.files_sort_combo.currentData(),
                "sidebar_by_professional": sidebar_widths,
            }
        )

    def change_files_sort(self, _index: int):
        """Actualiza sólo la vista: nunca mueve, renombra ni toca archivos."""
        self.update_files_column_headers()
        if not self._restoring_layout:
            self.save_layout_state()
        if hasattr(self, "case_files"):
            self.reload_case_files()

    def sort_case_files_by(self, column: str):
        """Orden por encabezado, como en el Explorador: alterna asc/desc."""
        current = self.files_sort_combo.currentData() or "name_asc"
        if current.startswith(column):
            target = f"{column}_desc" if current.endswith("_asc") else f"{column}_asc"
        else:
            target = "name_asc" if column == "name" else f"{column}_desc"
        index = self.files_sort_combo.findData(target)
        if index >= 0:
            self.files_sort_combo.setCurrentIndex(index)
        self.update_files_column_headers()

    def update_files_column_headers(self):
        if not hasattr(self, "files_column_buttons"):
            return
        current = str(self.files_sort_combo.currentData() or "name_asc")
        labels = {
            "name": "Nombre",
            "modified": "Fecha de modificación",
            "size": "Tamaño",
        }
        for key, button in self.files_column_buttons.items():
            if current.startswith(key):
                arrow = " ↑" if current.endswith("_asc") else " ↓"
                button.setText(f"{labels[key]}{arrow}")
            else:
                button.setText(labels[key])

    def restore_files_sort(self):
        sort_key = self.store.settings.layout_state.get("files_sort", "name_asc")
        index = self.files_sort_combo.findData(sort_key)
        self.files_sort_combo.blockSignals(True)
        self.files_sort_combo.setCurrentIndex(index if index >= 0 else 0)
        self.files_sort_combo.blockSignals(False)
        self.update_files_column_headers()

    def set_compilation_panel_visible(self, visible: bool):
        if not visible and not self.presentation_column.isHidden():
            sizes = self.workspace_splitter.sizes()
            if len(sizes) == 2 and sizes[1] > 0:
                self._visible_workspace_sizes = sizes
        self.presentation_column.setVisible(visible)
        self.compilation_toggle_button.setIcon(
            ui_icon("arrow-right" if visible else "arrow-left")
        )
        tooltip = "Ocultar panel Presentación" if visible else "Mostrar panel Presentación"
        self.compilation_toggle_button.setToolTip(tooltip)
        self.compilation_toggle_button.setAccessibleName(tooltip)
        if visible:
            self.workspace_splitter.setSizes(self._visible_workspace_sizes)
        self.schedule_layout_save()

    def toggle_compilation_panel(self):
        self.set_compilation_panel_visible(self.presentation_column.isHidden())

    def reset_layout(self):
        self._visible_workspace_sizes = [780, 440]
        self.body_splitter.setSizes([250, 1200])
        self.workspace_splitter.setSizes(self._visible_workspace_sizes)
        self.presentation_column.setSizes([520, 300])
        self.set_compilation_panel_visible(True)
        self.save_layout_state()
        self.statusBar().showMessage("Distribución restablecida", 4000)

    def open_preparation_dialog(self):
        if self.presentation_column.isHidden():
            self.set_compilation_panel_visible(True)
        self.compilation.setFocus()

    def toggle_quick_access(self):
        """Muestra u oculta el panel flotante de Documentos frecuentes."""
        if self.quick_panel.isVisible():
            self.quick_panel.hide()
            return
        self.reload_quick_access()
        self.quick_panel.show()
        self.quick_panel.raise_()
        self.quick_panel.activateWindow()

    def application_settings_summary(self) -> dict[str, object]:
        professional = self.professional_combo.currentText().strip()
        if professional == ADD_PROFESSIONAL_LABEL:
            professional = ""
        profile = self.store.settings.professional_profiles.get(professional, {})
        signer = self.store.settings.signer_path
        signer_output = self.store.settings.signer_output_dir
        return {
            "professional": professional,
            "professionals": list(self.store.settings.professionals),
            "profile_fields": sum(bool(str(value).strip()) for value in profile.values()),
            "models_count": len(list_models(self.store.models_dir)),
            "models_path": self.store.models_dir,
            "signer": signer.name if signer else "",
            "signer_output": signer_output if signer_output else "",
            "naming_pattern": self.store.settings.naming_pattern,
        }

    def configure_application(self):
        dialog = ApplicationSettingsDialog(self.application_settings_summary(), self)
        actions = {
            "add_professional": self.add_professional,
            "edit_professional": self.edit_current_professional,
            "configure_mev": self.configure_mev_profile,
            "configure_sisfe": self.configure_sisfe_profile,
            "configure_case_activity": self.configure_case_activity,
            "configure_radicaciones": self.configure_radicaciones,
            "add_model": self.add_writing_model,
            "open_models": self.open_models_folder,
            "open_base_template": self.open_base_template,
            "show_template_variables": self.show_template_variables,
            "configure_naming": self.configure_naming_pattern,
            "configure_signer": self.configure_signer,
            "configure_signer_output": self.configure_signer_output,
            "choose_certificate": self.preview_signing_certificate,
        }

        def run_action(name: str):
            action = actions.get(name)
            if action is not None:
                action()
                dialog.refresh_summary(self.application_settings_summary())

        dialog.actionRequested.connect(run_action)
        dialog.exec()

    def configure_naming_pattern(self):
        dialog = NamingPatternDialog(self.store.settings.naming_pattern, self)
        if not dialog.exec():
            return
        try:
            self.store.set_naming_pattern(normalize_naming_pattern(dialog.value()))
            self.update_output_preview()
            self.statusBar().showMessage("Regla de nombres actualizada", 3500)
        except ValueError as error:
            QMessageBox.warning(self, "Regla de nombres inválida", str(error))

    def reload_professionals(self):
        self.professional_combo.blockSignals(True)
        self.professional_combo.clear()
        self.professional_combo.addItems(self.store.settings.professionals)
        self.professional_combo.addItem(ADD_PROFESSIONAL_LABEL)
        index = self.professional_combo.findText(self.store.settings.current_professional)
        self.professional_combo.setCurrentIndex(
            index if index >= 0 else self.professional_combo.count() - 1
        )
        self.professional_combo.blockSignals(False)

    def professional_changed(self, name: str):
        if name == ADD_PROFESSIONAL_LABEL:
            self.add_professional()
            return
        if name:
            self.store.set_professional(name)
            if not self._restoring_layout:
                # Cada profesional conserva su ancho de panel y su último límite.
                self._restoring_layout = True
                try:
                    stored_width = self.sidebar_widths().get(name)
                    if stored_width:
                        sizes = self.body_splitter.sizes()
                        total = sum(sizes) or 1450
                        self.body_splitter.setSizes(
                            [stored_width, max(total - stored_width, 600)]
                        )
                    self.restore_presentation_limit()
                finally:
                    self._restoring_layout = False

    def add_professional(self):
        dialog = ProfessionalProfileDialog(parent=self)
        if dialog.exec():
            try:
                self.store.save_professional_profile(None, dialog.values())
            except ValueError as error:
                QMessageBox.warning(self, "No pudimos guardar el perfil", str(error))
        self.reload_professionals()

    def edit_current_professional(self):
        name = self.professional_combo.currentText().strip()
        if not name or name == ADD_PROFESSIONAL_LABEL:
            return
        profile = dict(self.store.settings.professional_profiles.get(name, {}))
        profile.setdefault("name", name)
        dialog = ProfessionalProfileDialog(profile, self)
        if not dialog.exec():
            return
        try:
            self.store.save_professional_profile(name, dialog.values())
            self.reload_professionals()
            self.statusBar().showMessage("Perfil profesional actualizado", 3500)
        except ValueError as error:
            QMessageBox.warning(self, "No pudimos guardar el perfil", str(error))

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

    def configure_sisfe_profile(self):
        professional = self.professional_combo.currentText().strip()
        if not professional:
            return
        dialog = SisfeAccessDialog(self.store.settings.sisfe_profiles.get(professional, {}), self)
        if dialog.exec():
            values = dialog.values()
            self.store.set_sisfe_profile(
                professional,
                values["circumscription"], values["college"],
                values["license"], values["password"],
            )
            self.statusBar().showMessage("Acceso SISFE guardado para este profesional", 4500)

    def preview_signing_certificate(self):
        certificate = self.choose_signing_certificate()
        if certificate:
            self.statusBar().showMessage(
                f"Certificado disponible: {certificate.summary}", 5000
            )

    def cases_by_radicacion(self) -> dict[str, list[Case]]:
        grouped: dict[str, list[Case]] = {}
        for root in self.store.settings.study_roots:
            if not root.is_dir():
                continue
            for case in list_cases(root):
                value = str(read_case_metadata(case).get("Radicación", "")).strip()
                if value:
                    grouped.setdefault(value, []).append(case)
        return grouped

    def configure_radicaciones(self):
        grouped = self.cases_by_radicacion()
        if not grouped:
            QMessageBox.information(
                self, "Radicaciones", "Todavía no hay radicaciones cargadas en los casos."
            )
            return
        dialog = RadicacionesDialog(
            {name: len(cases) for name, cases in grouped.items()}, self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        current = dialog.selected_name
        box = QMessageBox(self)
        box.setWindowTitle("Administrar radicación")
        box.setText(f"{current}\n\nUsada en {len(grouped[current])} caso(s).")
        rename_button = box.addButton("Renombrar", QMessageBox.ButtonRole.AcceptRole)
        delete_button = box.addButton("Eliminar", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is delete_button:
            QMessageBox.information(
                self, "Radicación en uso",
                "No puede eliminarse mientras esté vinculada a casos. Renombrala o quitá el dato desde cada caso.",
            )
            return
        if box.clickedButton() is not rename_button:
            return
        replacement, accepted = QInputDialog.getText(
            self, "Renombrar radicación", "Nuevo nombre:", text=current
        )
        replacement = " ".join(replacement.split()).strip()
        if not accepted or not replacement or replacement == current:
            return
        if QMessageBox.question(
            self, "Aplicar a los casos",
            f"¿Aplicar «{replacement}» a los {len(grouped[current])} caso(s) vinculados?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            for case in grouped[current]:
                metadata = read_case_metadata(case)
                metadata["Radicación"] = replacement
                save_case_metadata(case, metadata)
        except OSError as error:
            QMessageBox.warning(self, "No pudimos actualizar", str(error))
            return
        self.reload_cases(self.case.path if self.case else None)
        self.statusBar().showMessage("Radicación actualizada en todos los casos vinculados", 5000)

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

    def create_active_study_backup(self):
        root = self.store.settings.study_root
        if root is None or not root.is_dir():
            QMessageBox.information(
                self,
                "Falta la ubicación",
                "Seleccioná una Ubicación del Estudio disponible antes de crear el respaldo.",
            )
            return
        if self._study_backup_thread is not None:
            self.statusBar().showMessage("Ya hay una operación de respaldo en curso.", 5000)
            return
        default_name = f"FORO-Backup-{date.today().isoformat()}.foro-backup"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Crear copia de seguridad del Estudio",
            str(root.parent / default_name),
            "Copia de seguridad de FORO (*.foro-backup)",
        )
        if filename:
            target = Path(filename)
            if not target.name.casefold().endswith(".foro-backup"):
                target = target.with_name(target.name + ".foro-backup")
            self._start_study_backup_operation("backup", root, target)

    def restore_study_from_backup(self):
        if self._study_backup_thread is not None:
            self.statusBar().showMessage("Ya hay una operación de respaldo en curso.", 5000)
            return
        initial = self.store.settings.study_root
        backup_name, _ = QFileDialog.getOpenFileName(
            self,
            "Restaurar copia de seguridad del Estudio",
            str(initial.parent if initial else Path.home()),
            "Copia de seguridad de FORO (*.foro-backup);;Copias anteriores (*.zip)",
        )
        if not backup_name:
            return
        try:
            summary = inspect_study_backup(Path(backup_name))
        except StudyBackupError as error:
            QMessageBox.warning(self, "Copia no válida", str(error))
            return

        created = summary.created_at[:10] if summary.created_at else "Sin información"
        choice = QMessageBox(self)
        choice.setWindowTitle("Confirmar restauración")
        choice.setIcon(QMessageBox.Icon.Warning)
        choice.setText("FORO Backup")
        choice.setInformativeText(
            f"Fecha: {created}\nVersión FORO: {summary.foro_version or 'anterior'}\n"
            f"Casos: {summary.case_count}\nArchivos: {summary.file_count}\n"
            f"Tamaño: {human_size(summary.total_bytes)}\n\n"
            "Antes de restaurar se creará automáticamente una copia del estado actual. "
            "El archivo contiene documentación sensible: guardalo en un lugar seguro."
        )
        current_button = choice.addButton("Restaurar en la ubicación actual", QMessageBox.ButtonRole.AcceptRole)
        new_button = choice.addButton("Restaurar en otra ubicación", QMessageBox.ButtonRole.ActionRole)
        choice.addButton(QMessageBox.StandardButton.Cancel)
        choice.exec()
        clicked = choice.clickedButton()
        if clicked is not current_button and clicked is not new_button:
            return

        if clicked == current_button:
            if initial is None or not initial.is_dir():
                QMessageBox.warning(self, "Falta la ubicación", "No hay una ubicación actual disponible para reemplazar.")
                return
            target = initial
            replace_existing = True
        else:
            destination = QFileDialog.getExistingDirectory(
                self,
                "Elegí o creá una carpeta vacía para restaurar",
                str(initial.parent if initial else Path.home()),
            )
            if not destination:
                return
            target = Path(destination)
            if any(target.iterdir()):
                QMessageBox.warning(
                    self,
                    "La carpeta no está vacía",
                    "Para proteger tus archivos, elegí una carpeta nueva o vacía.",
                )
                return
            replace_existing = False

        stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        safety = (initial.parent if initial else target.parent) / f"FORO-Antes-de-restaurar-{stamp}.foro-backup"
        self._start_study_backup_operation(
            "restore", Path(backup_name), target,
            current_study_root=initial,
            safety_backup_path=safety,
            replace_existing=replace_existing,
        )

    def _start_study_backup_operation(
        self,
        operation: str,
        source: Path,
        destination: Path,
        *,
        current_study_root: Path | None = None,
        safety_backup_path: Path | None = None,
        replace_existing: bool = False,
    ):
        thread = QThread(self)
        worker = StudyBackupWorker(
            operation,
            source,
            destination,
            app_dir=self.store.app_dir,
            current_study_root=current_study_root,
            safety_backup_path=safety_backup_path,
            replace_existing=replace_existing,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._update_study_backup_progress)
        worker.completed.connect(self._study_backup_completed)
        worker.failed.connect(self._study_backup_failed)
        worker.cancelled.connect(self._study_backup_cancelled)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._study_backup_cleanup)
        self._study_backup_thread = thread
        self._study_backup_worker = worker
        title = "Creando copia de seguridad" if operation == "backup" else "Restaurando copia de seguridad"
        progress = QProgressDialog(title + "…", "Detener", 0, 0, self)
        progress.setWindowTitle(title)
        progress.setWindowModality(
            Qt.WindowModality.NonModal
            if operation == "backup"
            else Qt.WindowModality.ApplicationModal
        )
        # Sólo modifica un threading.Event: la conexión directa permite detener
        # el trabajo aunque el event loop del hilo esté ocupado copiando.
        progress.canceled.connect(
            worker.cancel,
            Qt.ConnectionType.DirectConnection,
        )
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.show()
        self._study_backup_progress = progress
        thread.start()

    def _update_study_backup_progress(self, current: int, total: int, relative: str):
        progress = self._study_backup_progress
        if progress is None:
            return
        progress.setMaximum(max(1, total))
        progress.setValue(current)
        if relative == "Verificando copia":
            label = relative
        elif relative.startswith("study/"):
            label = "Copiando documentos"
        elif relative.startswith("models/"):
            label = "Copiando modelos"
        elif relative.startswith("settings/"):
            label = "Preparando configuración"
        else:
            label = "Verificando y restaurando"
        progress.setLabelText(label)

    def _study_backup_completed(self, result: object):
        if isinstance(result, BackupResult):
            QMessageBox.information(
                self,
                "Copia creada correctamente",
                f"{datetime.now().strftime('%d/%m/%Y · %H:%M')}\n"
                f"{result.case_count} casos\n{result.file_count} archivos\n"
                f"{human_size(result.total_bytes)}\n\nArchivo: {result.path}\n\n"
                "Esta copia contiene documentación sensible. Guardala en un lugar seguro.",
            )
        elif isinstance(result, RestoreResult):
            self.store = SettingsStore(self.store.app_dir)
            self.store.add_study_root(result.root)
            self.reload_professionals()
            self.case = None
            self.reload_cases()
            QMessageBox.information(
                self,
                "Estudio restaurado correctamente",
                f"{result.case_count} casos\n{result.file_count} archivos\n"
                f"{human_size(result.total_bytes)}\n\n"
                f"Copia previa: {result.safety_backup or 'No fue necesaria'}",
            )

    def _study_backup_failed(self, message: str):
        QMessageBox.warning(self, "No pudimos completar la operación", message)

    def _study_backup_cancelled(self):
        self.statusBar().showMessage("Operación cancelada sin modificar el Estudio.", 5000)

    def _study_backup_cleanup(self):
        if self._study_backup_progress is not None:
            self._study_backup_progress.close()
            self._study_backup_progress.deleteLater()
        self._study_backup_progress = None
        self._study_backup_thread = None
        self._study_backup_worker = None

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
        radicaciones: dict[str, str] = {}
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
                cases = list_cases(root_path)
                policy = normalized_activity_settings(self.store.settings.activity_settings)
                activities = case_activities(cases, policy)
                visible_cases = []
                for case in cases:
                    if not case_matches(case, query):
                        continue
                    activity = activities[case.path]
                    if activity.archived and not policy["show_archived"]:
                        continue
                    if activity.status == "green" and not policy["show_recent"]:
                        continue
                    metadata = read_case_metadata(case)
                    radicacion = str(metadata.get("Radicación", "")).strip()
                    if radicacion:
                        # La uniformidad nace del uso real del Estudio: se
                        # evitan duplicados por mayúsculas, acentos o espacios.
                        radicaciones.setdefault(
                            _comparable_text(radicacion), radicacion
                        )
                    client_label, client_key = self.case_client_identity(metadata)
                    visible_cases.append((case, activity, client_label, client_key, metadata))

                grouped: dict[str, list[tuple[Case, object, str, str, dict[str, str]]]] = {}
                for entry in visible_cases:
                    if entry[3]:
                        grouped.setdefault(entry[3], []).append(entry)
                client_parents: dict[str, QTreeWidgetItem] = {}
                for client_key, entries in grouped.items():
                    if len(entries) < 2:
                        continue
                    label = entries[0][2]
                    parent = QTreeWidgetItem([f"{label} — {len(entries)} casos"])
                    parent.setIcon(0, ui_icon("person", "#2774A6"))
                    parent.setToolTip(0, "Cliente con varios casos. Las carpetas y documentos siguen separados.")
                    font = parent.font(0)
                    font.setBold(True)
                    parent.setFont(0, font)
                    root_item.addChild(parent)
                    parent.setExpanded(True)
                    client_parents[client_key] = parent
                for case, activity, _client_label, client_key, metadata in visible_cases:
                    item = QTreeWidgetItem([case.name])
                    color_key = {
                        "green": "green_color",
                        "yellow": "yellow_color",
                        "red": "red_color",
                        "archived": "archived_color",
                    }[activity.status]
                    try:
                        unseen = len(unread_case_novedades(case))
                    except (OSError, RuntimeError, sqlite3.Error):
                        unseen = 0
                    item.setIcon(0, badged_icon("folder", str(policy[color_key]), unseen))
                    item.setData(0, PATH_ROLE, str(case.path))
                    state_label = {
                        "green": "Actividad normal",
                        "yellow": "Requiere atención",
                        "red": "Inactivo",
                        "archived": "Archivado",
                    }[activity.status]
                    item.setToolTip(
                        0,
                        f"{state_label} · última actividad: "
                        f"{activity.latest_at.astimezone().strftime('%d/%m/%Y')} "
                        f"({activity.inactive_days} días)\n{case.path}",
                    )
                    client_parents.get(client_key, root_item).addChild(item)
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
        if hasattr(self, "radicacion_completer"):
            self.radicacion_completer.setModel(
                QStringListModel(sorted(radicaciones.values()), self)
            )
        self.reload_quick_access()
        if selected_item:
            self.set_case(Case(Path(selected_item.data(0, PATH_ROLE))))
        elif not self.case or not self.case.path.is_dir():
            self.set_case(None)

    @staticmethod
    def case_client_identity(metadata: dict[str, str]) -> tuple[str, str]:
        """Return a conservative visual grouping key; it never changes a case."""
        label = (metadata.get("Nombre completo") or metadata.get("Actor") or "").strip()
        if not label:
            label = ", ".join(
                part for part in (
                    metadata.get("Apellido del actor", "").strip(),
                    metadata.get("Nombres del actor", "").strip(),
                ) if part
            )
        for field in ("CUIL del actor", "DNI del actor", "DNI/CUIT actor"):
            digits = re.sub(r"\D", "", metadata.get(field, ""))
            if digits:
                return label or "Cliente sin nombre", f"id:{digits}"
        normalized = re.sub(r"\s+", " ", label.casefold()).strip()
        return label or "", f"name:{normalized}" if normalized else ""

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
            target_case = Case(Path(path))
            archived = read_case_metadata(target_case).get("Archivado", "").casefold() in {
                "1", "si", "sí", "true", "yes",
            }
            menu.addAction(
                "Reactivar caso" if archived else "Archivar caso",
                lambda: self.toggle_case_archived(target_case, not archived),
            )
        else:
            root_path = Path(root)
            open_action = menu.addAction("Abrir ubicación", lambda: open_file(root_path))
            open_action.setEnabled(root_path.is_dir())
            menu.addAction("Usar esta ubicación", lambda: self.activate_study_root(root_path))
            menu.addAction("Nuevo caso aquí…", lambda: self.new_case_in_root(root_path))
            incorporate = menu.addAction(
                "Incorporar carpeta como caso…",
                lambda: self.import_external_case(root_path),
            )
            incorporate.setEnabled(root_path.is_dir())
            menu.addSeparator()
            menu.addAction(
                "Quitar del Gestor…",
                lambda: self.remove_study_root(root_path),
            )
        menu.addSeparator()
        menu.addAction(
            "Marcar todas las novedades como leídas",
            self.mark_all_sisfe_news_read,
        )
        menu.exec(self.case_tree.mapToGlobal(point))

    def mark_all_sisfe_news_read(self):
        changed = 0
        for root in self.store.settings.study_roots:
            if not root.is_dir():
                continue
            for case in list_cases(root):
                try:
                    changed += mark_case_novedades_read(case)
                except (OSError, RuntimeError, sqlite3.Error):
                    continue
        self._visible_unread_case = None
        self._visible_unread_movement_ids = ()
        if self.case:
            self.reload_novedades()
        self.reload_cases(self.case.path if self.case else None)
        self.statusBar().showMessage(
            "Todas las novedades quedaron marcadas como leídas"
            if changed
            else "No había novedades sin leer",
            4000,
        )

    def toggle_case_archived(self, case: Case, archived: bool):
        try:
            set_case_archived(case, archived)
            policy = normalized_activity_settings(self.store.settings.activity_settings)
            if archived and not policy["show_archived"] and self.case == case:
                self.set_case(None)
            self.reload_cases(case.path if not archived else None)
            self.statusBar().showMessage(
                "Caso archivado" if archived else "Caso reactivado",
                3500,
            )
        except Exception as error:
            QMessageBox.warning(self, "No pudimos actualizar el caso", str(error))

    def configure_case_activity(self):
        dialog = ActivitySettingsDialog(self.store.settings.activity_settings, self)
        if dialog.exec():
            self.store.set_activity_settings(dialog.values())
            selected = self.case.path if self.case else None
            self.reload_cases(selected)
            self.statusBar().showMessage("Semáforo de casos actualizado", 3500)

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
            previous_path = case.path
            renamed = rename_case(case, name)
            database_warning = ""
            try:
                with StudyDatabase(study_database_path(renamed.path.parent)) as database:
                    database.relocate_case(previous_path, renamed)
            except (OSError, RuntimeError, sqlite3.Error) as database_error:
                database_warning = str(database_error)
            if was_current:
                self.case = renamed
                self.replace_path_everywhere(previous_path, renamed.path)
            self.reload_cases(renamed.path)
            message = (
                f"Caso renombrado; no se pudo actualizar el índice: {database_warning}"
                if database_warning
                else f"Caso renombrado: {renamed.name}"
            )
            self.statusBar().showMessage(message, 7000 if database_warning else 4500)
        except Exception as error:
            QMessageBox.warning(self, "No pudimos renombrar el caso", str(error))

    def set_case(self, case: Case | None):
        if self.case and (case is None or self.case.path != case.path):
            self.finish_unread_view_cycle(refresh=False)
        self.save_compilation_draft()
        self._loading_compilation = True
        self.case = case
        self.case_directory = case.path if case else None
        self.current_writing = None
        self.last_compiled = None
        self.last_signed = None
        self.compilation.clear()
        self.last_output.setText("Aún no compilaste")
        self.workspace.setEnabled(case is not None)
        self.open_case_button.setEnabled(case is not None)
        self.sisfe_sync_button.setEnabled(case is not None)
        if not case:
            self.restore_presentation_limit()
            self.case_title.setText("Elegí un caso")
            self.case_title.setToolTip("")
            self.update_case_sync_label()
            self.load_metadata({})
            self.case_badge.hide()
            self.client_cases_button.hide()
            self.reload_case_files()
            self.update_writing_label()
            self.update_compilation_count()
            self.update_output_preview()
            self.reload_novedades()
            self.reload_pending_documents()
            self._loading_compilation = False
            return
        self.restore_compilation_draft(load_compilation_draft(case))
        self.sync_case_projection()
        self.case_title.setText(self.case_caption(case))
        self.case_title.setToolTip(case.name)
        self.update_case_sync_label()
        self.refresh_client_cases_button()
        self.load_metadata(read_case_metadata(case))
        self.reload_novedades()
        self.reload_pending_documents()
        self.reload_case_files()
        self.update_writing_label()
        self.update_compilation_count()
        self.update_case_badge()
        self.update_output_preview()
        self._loading_compilation = False

    def client_cases_for_current_case(self) -> list[object]:
        if not self.case:
            return []
        try:
            with StudyDatabase(study_database_path(self.case.path.parent)) as database:
                expediente = database.find_expediente_by_folder(self.case.path)
                if not expediente:
                    return []
                row = database.connection.execute(
                    "SELECT client_id FROM expedientes WHERE id = ?", (expediente.id,)
                ).fetchone()
                indexed = database.list_client_cases(row["client_id"]) if row and row["client_id"] else []
        except (OSError, RuntimeError, sqlite3.Error):
            indexed = []
        if len(indexed) > 1:
            return indexed
        # Casos aún no abiertos no están necesariamente indexados. Se leen
        # para mostrar el vínculo, sin crear ni modificar carpeta alguna.
        _label, identity = self.case_client_identity(read_case_metadata(self.case))
        if not identity:
            return indexed
        return [
            candidate for candidate in list_cases(self.case.path.parent)
            if self.case_client_identity(read_case_metadata(candidate))[1] == identity
        ]

    def refresh_client_cases_button(self):
        cases = self.client_cases_for_current_case()
        if len(cases) > 1:
            self.client_cases_button.setText(f"{len(cases)} casos del cliente")
            self.client_cases_button.show()
        else:
            self.client_cases_button.hide()

    def show_client_cases(self):
        cases = self.client_cases_for_current_case()
        if len(cases) < 2:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Casos del cliente")
        dialog.setMinimumWidth(520)
        layout = QVBoxLayout(dialog)
        layout.addLayout(section_heading(
            "Casos del cliente", "Cada expediente conserva su propia carpeta, documental y estado.",
        ))
        listing = QListWidget()
        for case in cases:
            title = case.title if hasattr(case, "title") else case.name
            folder_path = case.folder_path if hasattr(case, "folder_path") else case.path
            detail = " · ".join(
                part for part in (
                    getattr(case, "case_number", ""), getattr(case, "tribunal", ""),
                ) if part
            )
            item = QListWidgetItem(ui_icon("folder", "#2774A6"), title)
            item.setData(PATH_ROLE, str(folder_path))
            item.setToolTip(detail or str(folder_path))
            listing.addItem(item)
        layout.addWidget(listing)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        def open_case(item):
            path = Path(item.data(PATH_ROLE))
            if path.is_dir():
                dialog.accept()
                self.reload_cases(path)

        listing.itemDoubleClicked.connect(open_case)
        listing.setCurrentRow(0)
        listing.setFocus()
        dialog.exec()

    def restore_compilation_draft(self, draft: CompilationDraft):
        self.current_writing = draft.current_writing
        self.last_compiled = draft.last_compiled
        self.last_signed = draft.last_signed
        profile_index = self.limit_combo.findText(draft.profile)
        self.limit_combo.setCurrentIndex(
            profile_index if profile_index >= 0 else self.limit_combo.findText(DEFAULT_PROFILE)
        )
        for draft_item in draft.items:
            self.add_compilation_path(draft_item.path, draft_item.kind)
        self.update_last_output_label()

    def save_compilation_draft(self):
        if not self.case or self._loading_compilation:
            return
        items = tuple(
            DraftItem(
                Path(self.compilation.item(index).data(PATH_ROLE)),
                str(self.compilation.item(index).data(TYPE_ROLE) or "document"),
            )
            for index in range(self.compilation.count())
        )
        try:
            persist_compilation_draft(
                self.case,
                items,
                current_writing=self.current_writing,
                last_compiled=self.last_compiled,
                last_signed=self.last_signed,
                profile=self.limit_combo.currentText(),
            )
        except (OSError, ValueError) as error:
            self.statusBar().showMessage(
                f"No se pudo guardar el borrador de compilación: {error}", 7000
            )

    def update_last_output_label(self):
        output = self.last_signed or self.last_compiled
        if not output or not output.is_file():
            self.last_output.setText("Aún no compilaste")
            return
        signed = "FIRMADO · " if output == self.last_signed else ""
        try:
            size = human_size(output.stat().st_size)
        except OSError:
            size = "tamaño no disponible"
        self.last_output.setText(f"{output.name}\n{signed}{size}")

    def compilation_profile_changed(self, _profile: str):
        self.update_limit_buttons()
        self.remember_presentation_limit()
        self.save_compilation_draft()

    def selected_presentation_limit(self) -> int:
        try:
            return int(self.limit_combo.currentData())
        except (TypeError, ValueError):
            return NO_LIMIT

    def set_presentation_limit(self, limit: int):
        profile = PROFILE_FOR_LIMIT.get(limit, NO_LIMIT_PROFILE)
        index = self.limit_combo.findText(profile)
        if index >= 0:
            self.limit_combo.setCurrentIndex(index)
        self.update_limit_buttons()

    def choose_presentation_limit(self, limit: int):
        """Volver a tocar el límite elegido lo desactiva: sin compresión."""
        if self.selected_presentation_limit() == limit:
            self.set_presentation_limit(NO_LIMIT)
        else:
            self.set_presentation_limit(limit)

    def update_limit_buttons(self):
        if not hasattr(self, "limit_buttons"):
            return
        current = self.selected_presentation_limit()
        for value, button in self.limit_buttons.items():
            button.setChecked(value == current)
        if hasattr(self, "limit_hint"):
            self.limit_hint.setText(
                "Sin límite elegido: se compila al tamaño natural."
                if current == NO_LIMIT
                else f"Se comprime sólo si supera {PROFILE_FOR_LIMIT[current].split('· ')[-1]}."
            )

    def presentation_limits_by_professional(self) -> dict[str, int]:
        raw = self.store.settings.layout_state.get("presentation_limits", {})
        if not isinstance(raw, dict):
            return {}
        limits = {}
        for name, value in raw.items():
            try:
                limits[str(name)] = int(value)
            except (TypeError, ValueError):
                continue
        return limits

    def remember_presentation_limit(self):
        if self._restoring_layout or self._loading_compilation:
            return
        professional = self.store.settings.current_professional
        if not professional:
            return
        limits = self.presentation_limits_by_professional()
        limits[professional] = self.selected_presentation_limit()
        self.store.set_layout_state(
            {**self.store.settings.layout_state, "presentation_limits": limits}
        )

    def restore_presentation_limit(self):
        professional = self.store.settings.current_professional
        stored = self.presentation_limits_by_professional().get(professional)
        if stored is not None and stored in PROFILE_FOR_LIMIT:
            self.set_presentation_limit(stored)
        else:
            self.update_limit_buttons()

    def sync_case_projection(self):
        """Refresh SQLite without making it a prerequisite for file work."""
        if not self.case:
            return
        try:
            register_case_as_expediente(self.case)
        except (OSError, RuntimeError, sqlite3.Error) as error:
            # A read-only or temporarily disconnected location must not block
            # the established document workflow.
            self.statusBar().showMessage(
                f"No se pudo actualizar el índice del expediente: {error}", 7000
            )

    def open_sisfe_session(self):
        professional = self.professional_combo.currentText().strip()
        credentials = self.store.settings.sisfe_profiles.get(professional, {})
        if (
            self._sisfe_login_dialog is not None
            and self._sisfe_login_dialog.ready_for_sync
            and self.sisfe_session.active
        ):
            self.update_sisfe_indicator(OperationState.SUCCESS, "Sesión SISFE activa")
            self.statusBar().showMessage("Se reutilizó la sesión SISFE vigente.", 4000)
            return
        if self._sisfe_login_dialog is None:
            self._sisfe_login_dialog = SisfeLoginDialog(
                self.sisfe_session,
                self,
                credentials=credentials,
                profile_dir=self.store.app_dir / "SISFE" / "BrowserProfile",
            )
        else:
            self._sisfe_login_dialog.credentials = dict(credentials)
            self._sisfe_login_dialog.prepare_for_open()
        dialog = self._sisfe_login_dialog
        if dialog.exec() and self.sisfe_session.active:
            self.update_sisfe_indicator(
                OperationState.SUCCESS,
                "Sesión SISFE activa",
            )
        else:
            self.update_sisfe_indicator(OperationState.ERROR, "SISFE desconectado")

    def sync_sisfe(self):
        if self.long_task_active():
            self.warn_long_task_active()
            return
        if not self.require_case():
            return
        case = self.case
        configured_portal = read_case_metadata(self.case).get("Portal jurídico asociado", "").strip()
        if configured_portal and configured_portal != "SISFE":
            QMessageBox.information(
                self,
                "Portal jurídico del caso",
                f"Este caso está asociado a {configured_portal}. Por ahora la sincronización automática sólo está disponible para SISFE.",
            )
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
        self.update_sisfe_indicator(OperationState.RUNNING, "Consultando novedades SISFE…")
        self.update_case_sync_label("Sincronizando…")

        def completed(snapshot, error):
            self.sisfe_sync_button.setEnabled(True)
            if error:
                self.update_sisfe_indicator(OperationState.ERROR, "No se pudo sincronizar")
                self.update_case_sync_label()
                QMessageBox.warning(self, "No pudimos sincronizar SISFE", str(error))
                return
            try:
                result = self.sisfe_portal.import_snapshot(
                    case, snapshot, case.path / "Documentos SISFE"
                )
            except Exception as import_error:
                self.update_sisfe_indicator(OperationState.ERROR, "No se pudo importar")
                self.update_case_sync_label()
                QMessageBox.warning(self, "No pudimos importar SISFE", str(import_error))
                return
            self.record_case_sync(case)
            self.record_unseen_sisfe(case, result.movements_registered)
            if self.case == case:
                self.reload_novedades()
                self.reload_case_files()
            self.update_sisfe_indicator(
                OperationState.SUCCESS,
                "Sesión SISFE activa",
            )
            self.statusBar().showMessage(
                f"SISFE sincronizado: {result.movements_registered} novedades nuevas", 5000
            )

        self._sisfe_login_dialog.request_snapshot(
            cuij, completed, self.known_sisfe_movement_ids(case)
        )

    @staticmethod
    def known_sisfe_movement_ids(case: Case) -> tuple[str, ...]:
        try:
            with StudyDatabase(study_database_path(case.path.parent)) as database:
                expediente = database.find_expediente_by_folder(case.path)
                if not expediente:
                    return ()
                return tuple(
                    movement.external_id
                    for movement in database.list_recent_movements(expediente.id, None)
                    if movement.source == "sisfe" and movement.external_id
                )
        except (OSError, RuntimeError, sqlite3.Error):
            return ()

    def record_unseen_sisfe(self, case: Case, count: int, *, reload_tree: bool = True):
        # La importación ya marca cada fila nueva en SQLite. Este método sólo
        # actualiza la proyección visual; no mantiene un segundo contador.
        if isinstance(count, int) and count > 0 and reload_tree:
            self.reload_cases(self.case.path if self.case else None)

    def case_tab_changed(self, index: int):
        if index == self.portal_tab_index and self.case:
            self.reload_novedades()
            return
        self.finish_unread_view_cycle()

    def finish_unread_view_cycle(self, *, refresh: bool = True):
        case = self._visible_unread_case
        movement_ids = self._visible_unread_movement_ids
        if not case or not movement_ids:
            return
        self._visible_unread_case = None
        self._visible_unread_movement_ids = ()
        try:
            mark_case_novedades_read(case, movement_ids)
        except (OSError, RuntimeError, sqlite3.Error):
            return
        if refresh and self.case == case:
            self.reload_novedades()
        if refresh:
            self.reload_cases(self.case.path if self.case else None)

    # ------------------------------------------------------------------
    # Estado del caso y de los portales
    # ------------------------------------------------------------------
    @staticmethod
    def case_caption(case: Case) -> str:
        """Carátula del caso; si todavía no hay datos, el nombre de la carpeta."""
        caption = build_case_caption(read_case_metadata(case), fallback="")
        return caption or case.name

    def update_sisfe_indicator(self, state: OperationState, message: str):
        """Un único estado técnico, replicado en la barra inferior."""
        if state is OperationState.SUCCESS:
            visible_state, visible_text = OperationState.SUCCESS, "SISFE conectado"
        elif state is OperationState.ERROR:
            visible_state, visible_text = OperationState.ERROR, "SISFE desconectado"
        elif state is OperationState.RUNNING and self.sisfe_session.active:
            visible_state, visible_text = OperationState.SUCCESS, "SISFE conectado"
        else:
            visible_state, visible_text = OperationState.IDLE, "SISFE sin confirmar"
        if hasattr(self, "sisfe_status"):
            self.sisfe_status.set_state(visible_state, visible_text)
            self.sisfe_status.setToolTip(message)
        if hasattr(self, "sisfe_indicator"):
            self.sisfe_indicator.set_state(visible_state, visible_text)
            self.sisfe_indicator.setToolTip(message)

    def record_case_sync(self, case: Case):
        moment = datetime.now()
        try:
            self.store.set_case_sync_state(case.path, moment.isoformat(timespec="seconds"))
        except OSError:
            return
        if self.case and self.case.path == case.path:
            self.update_case_sync_label()

    def update_case_sync_label(self, text: str | None = None):
        if not hasattr(self, "case_sync_label"):
            return
        if text is not None:
            self.case_sync_label.set_state(OperationState.RUNNING, text)
            self.case_sync_label.setToolTip(text)
            return
        if not self.case:
            self.case_sync_label.set_state(OperationState.IDLE, "")
            self.case_sync_label.setToolTip("")
            return
        stored = self.store.settings.case_sync_state.get(str(self.case.path), "")
        try:
            moment = datetime.fromisoformat(stored) if stored else None
        except ValueError:
            moment = None
        if not moment:
            self.case_sync_label.set_state(OperationState.IDLE, "Expediente sin sincronizar")
            self.case_sync_label.setToolTip(
                "Este expediente todavía no se sincronizó con el portal."
            )
            return
        same_day = moment.date() == datetime.now().date()
        self.case_sync_label.set_state(
            OperationState.SUCCESS,
            f"Expediente sincronizado · {moment.strftime('%H:%M')}"
            if same_day
            else f"Expediente sincronizado · {moment.strftime('%d/%m %H:%M')}"
        )
        self.case_sync_label.setToolTip(
            f"Última sincronización del expediente: {moment.strftime('%d/%m/%Y %H:%M')}"
        )

    def open_selected_novedad(self):
        """Doble clic: si el movimiento tiene PDF descargado, se abre."""
        movement = self.selected_novedad_data() or {}
        cedulas = [Path(path) for path in movement.get("cedula_documents", [])]
        for cedula in cedulas:
            if cedula.is_file():
                open_file(cedula)
                return
        documents = [Path(path) for path in movement.get("local_documents", [])]
        for document in documents:
            if document.is_file():
                open_file(document)
                return
        self.show_selected_novedad()

    def expedientes_with_identifier(self) -> list[Case]:
        cases: list[Case] = []
        for root in self.store.settings.study_roots:
            if not root.is_dir():
                continue
            for candidate in list_cases(root):
                if str(read_case_metadata(candidate).get("CUIJ", "")).strip():
                    cases.append(candidate)
        return cases

    def long_task_active(self) -> bool:
        return bool(
            (self._long_task is not None and self._long_task.active)
            or (self._long_task_thread is not None and self._long_task_thread.isRunning())
        )

    def warn_long_task_active(self):
        QMessageBox.information(
            self,
            "Proceso en curso",
            "Hay un proceso en curso. Esperá a que termine o detenelo.",
        )

    def begin_long_task(self, task: LongTask, kind: str):
        self._long_task = task
        self._long_task_kind = kind
        task.state_changed.connect(self._long_task_state_changed)
        task.progress_changed.connect(self._long_task_progress_changed)
        task.finished.connect(self._long_task_finished)
        self.task_progress.setRange(0, task.total)
        self.task_progress.setValue(0)
        self.status_center.setText(f"{task.name} 0 de {task.total}")
        self.task_stop_button.setEnabled(True)
        self.status_activity.show()
        self.sync_all_button.setEnabled(False)

    def _long_task_progress_changed(self, current: int, total: int, name: str):
        self.task_progress.setRange(0, total)
        self.task_progress.setValue(current)
        self.status_center.setText(f"{name} {current} de {total}")

    def _long_task_state_changed(self, state: TaskState):
        if state is TaskState.RUNNING:
            if (
                self._long_task_kind == "sync"
                and self._sync_all_index
                and not self._sync_unit_active
            ):
                QTimer.singleShot(0, self._sync_next_expediente)
        elif state is TaskState.CANCELLING:
            self.status_center.setText("Deteniendo de forma segura…")
            self.task_stop_button.setEnabled(False)

    def stop_long_task(self):
        task = self._long_task
        if task is None or not task.active:
            return
        task.cancel()
        if self._long_task_kind == "sync":
            QTimer.singleShot(0, self._sync_next_expediente)

    @staticmethod
    def _task_details_text(details: tuple[TaskDetail, ...]) -> str:
        return "\n".join(
            f"{detail.item}: {detail.message or detail.result}"
            for detail in details
        )

    def _long_task_finished(self, summary: dict):
        kind = self._long_task_kind
        details = summary["details"]
        state = summary["state"]
        self.status_activity.hide()
        thread = self._long_task_thread
        if kind == "sync" and thread is not None and thread.isRunning():
            thread.quit()
        self.sync_all_button.setEnabled(thread is None or not thread.isRunning())
        if kind == "sync":
            self.update_sisfe_indicator(
                OperationState.ERROR if state is TaskState.ERROR else OperationState.SUCCESS,
                "SISFE desconectado" if state is TaskState.ERROR else "Sesión SISFE activa",
            )
            selected = self.case.path if self.case else None
            self.reload_cases(selected)
            if self.case:
                self.reload_novedades()
                self.reload_case_files()
            changed = sum(detail.result == "ok" for detail in details)
            unchanged = sum(detail.result == "sin_cambios" for detail in details)
            errors = sum(detail.result == "error" for detail in details)
            title = (
                "Sincronización completada"
                if state is TaskState.COMPLETED
                else "Sincronización detenida"
                if state is TaskState.CANCELLED
                else "Sincronización interrumpida"
            )
            text = (
                f"{summary['current']} de {summary['total']} expedientes procesados\n"
                f"{changed} con novedades\n{unchanged} sin cambios\n{errors} con errores"
            )
        else:
            imported = sum(detail.result == "ok" for detail in details)
            errors = sum(detail.result == "error" for detail in details)
            title = (
                "Importación finalizada"
                if state is TaskState.COMPLETED
                else "Importación detenida"
                if state is TaskState.CANCELLED
                else "Importación interrumpida"
            )
            text = (
                f"{imported} importados\n"
                f"{self._long_task_omitted} omitidos\n"
                f"{summary['total'] - summary['current']} sin procesar\n{errors} con error"
            )
            selected = next(
                (
                    detail.payload.case.path
                    for detail in reversed(details)
                    if detail.result == "ok" and detail.payload is not None
                ),
                self.case.path if self.case else None,
            )
            self.reload_cases(selected)
        if summary.get("error"):
            text += f"\n\n{summary['error']}"
        message = QMessageBox(self)
        message.setWindowTitle(title)
        message.setText(text)
        detail_text = self._task_details_text(details)
        if detail_text:
            message.setDetailedText(detail_text)
        closing = self._close_after_long_task
        if not closing:
            self._task_result_message = message
            message.finished.connect(
                lambda _result: setattr(self, "_task_result_message", None)
            )
        self._long_task = None
        self._long_task_kind = ""
        self._sync_all_cases = []
        self._sync_all_index = 0
        self._sync_unit_active = False
        self._long_task_omitted = 0
        if not closing:
            message.show()
        if self._close_after_long_task and (
            self._long_task_thread is None or not self._long_task_thread.isRunning()
        ):
            self._close_after_long_task = False
            QTimer.singleShot(0, self.close)

    def sync_all_expedientes(self):
        """Acción global, separada de la sincronización del expediente abierto."""
        if self.long_task_active():
            self.warn_long_task_active()
            return
        if not self.require_study():
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
        cases = self.expedientes_with_identifier()
        if not cases:
            QMessageBox.information(
                self,
                "Sincronizar todos",
                "Ningún caso tiene número de expediente cargado todavía.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Sincronizar todos los expedientes",
            f"Se consultarán {len(cases)} expedientes, uno por vez. ¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._sisfe_login_dialog.prepare_background_sync()
        self._sync_all_cases = list(cases)
        self._sync_all_index = 0
        task = LongTask("Sincronizando expedientes", len(cases))
        self.begin_long_task(task, "sync")
        thread = QThread(self)
        worker = SisfeSnapshotImportWorker(self.sisfe_portal)
        worker.moveToThread(thread)
        self.sisfe_snapshot_import_requested.connect(worker.process)
        worker.completed.connect(self._sync_snapshot_imported)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._long_task_thread_finished)
        self._long_task_thread = thread
        self._long_task_worker = worker
        task.start()
        thread.start()
        self.update_sisfe_indicator(
            OperationState.RUNNING, f"Sincronizando {len(cases)} expedientes…"
        )
        self._sync_next_expediente()

    def _sync_next_expediente(self):
        task = self._long_task
        if task is None or self._long_task_kind != "sync":
            return
        if self._sync_unit_active:
            return
        if task.state is TaskState.CANCELLING:
            task.cancelled()
            return
        if task.state is TaskState.PAUSED:
            return
        if not self.sisfe_session.active or not self._sisfe_login_dialog:
            task.fail("La sesión SISFE dejó de estar activa.")
            return
        if not self._sisfe_login_dialog.ready_for_sync:
            task.fail("SISFE dejó de estar disponible para consultas.")
            return
        if self._sync_all_index >= len(self._sync_all_cases):
            task.complete()
            return
        case = self._sync_all_cases[self._sync_all_index]
        self._sync_all_index += 1
        self._sync_unit_active = True
        cuij = str(read_case_metadata(case).get("CUIJ", "")).strip()

        def completed(snapshot, error):
            current_task = self._long_task
            if current_task is not task:
                return
            if not error:
                self.sisfe_snapshot_import_requested.emit(case, snapshot)
                return
            else:
                self._sync_unit_active = False
                error_text = str(error)
                if (
                    not self.sisfe_session.active
                    or any(
                        marker in error_text.casefold()
                        for marker in ("sesión", "login", "autoriz")
                    )
                ):
                    task.fail(error_text)
                    return
                task.complete_unit(case.name, "error", error_text)
            QTimer.singleShot(0, self._sync_next_expediente)

        self._sisfe_login_dialog.request_snapshot(
            cuij, completed, self.known_sisfe_movement_ids(case)
        )

    def _sync_snapshot_imported(self, case: Case, result, error: str):
        task = self._long_task
        if task is None or self._long_task_kind != "sync":
            return
        self._sync_unit_active = False
        if error:
            task.complete_unit(case.name, "error", error)
        else:
            self.record_case_sync(case)
            self.record_unseen_sisfe(
                case, result.movements_registered, reload_tree=False
            )
            message = (
                f"{result.movements_registered} novedades · "
                f"{result.documents_registered} PDF"
            )
            task.complete_unit(
                case.name,
                "ok" if result.movements_registered else "sin_cambios",
                message,
                result,
            )
        QTimer.singleShot(0, self._sync_next_expediente)

    def case_activity_items(self, case: Case, *, show_completed: bool = False):
        metadata = read_case_metadata(case)
        pending = [
            " ".join(line.split())
            for line in str(metadata.get("Documentación pendiente", "")).splitlines()
            if line.strip()
        ]
        received = [
            " ".join(line.split())
            for line in str(metadata.get("Documentación recibida", "")).splitlines()
            if line.strip()
        ]
        pending_due_dates = self.pending_document_due_dates(metadata)
        task_statuses: dict[str, str] = {}
        case_tasks = []
        with StudyDatabase(study_database_path(case.path.parent)) as database:
            expediente = database.find_expediente_by_folder(case.path)
            if expediente:
                case_tasks = database.list_tasks(expediente.id)
                task_statuses = {
                    task.suggested_by: task.status for task in case_tasks if task.suggested_by
                }
        available_paths = [
            path.relative_to(case.path).as_posix()
            for path in case.path.rglob("*")
            if path.is_file()
            and not any(part.startswith(".") for part in path.relative_to(case.path).parts)
        ]
        return build_case_activity(
            recent_case_novedades(case),
            pending,
            received,
            task_statuses,
            available_document_paths=available_paths,
            tasks=case_tasks,
            show_completed=show_completed,
            pending_due_dates=pending_due_dates,
        )

    def study_activity_entries(self) -> list[tuple[Case, object]]:
        entries = []
        for root in self.store.settings.study_roots:
            if not root.is_dir():
                continue
            for case in list_cases(root):
                try:
                    entries.extend((case, item) for item in self.case_activity_items(case))
                except (OSError, RuntimeError, sqlite3.Error):
                    continue
        entries.sort(
            key=lambda entry: (
                entry[1].priority,
                entry[1].due_at.date() if entry[1].due_at else date.max,
                entry[0].name.casefold(),
            )
        )
        return entries

    def open_study_activity(self):
        entries = self.study_activity_entries()
        if not entries:
            QMessageBox.information(self, "Actividad del Estudio", "No hay acciones activas en los expedientes.")
            return
        dialog = StudyActivityDialog(entries, self)
        if not dialog.exec():
            return
        selected = dialog.selected_data()
        if not selected:
            return
        self.reload_cases(Path(selected["case_path"]))
        target = selected.get("target")
        self.work_tabs.setCurrentIndex(
            self.portal_tab_index if target == "portal"
            else self.files_tab_index if target == "files"
            else self.files_tab_index
        )

    def reload_activity(self):
        if not hasattr(self, "activity_list"):
            return
        self.activity_list.clear()
        if not self.case:
            self.activity_count.setText("Sin acciones")
            return
        try:
            items = self.case_activity_items(
                self.case, show_completed=self.show_completed_tasks.isChecked()
            )
        except (OSError, RuntimeError, sqlite3.Error) as error:
            self.activity_count.setText("No disponible")
            self.activity_list.addItem(f"No pudimos reunir la actividad: {error}")
            return
        colors = {0: "#B42318", 1: "#B36A24", 2: "#8A5B12", 3: "#2B7564"}
        icons = {
            "Audiencia": "bell",
            "Traslado": "arrow-right",
            "Vencimiento": "check",
            "Documentación": "file",
            "Posible recepción": "check",
            "Tarea": "check",
        }
        for activity in items:
            item = QListWidgetItem(
                ui_icon(icons.get(activity.kind, "bell"), colors.get(activity.priority, "#2B7564")),
                f"{activity.kind.upper()} · {activity.title}\n{activity.detail}",
            )
            item.setData(
                ACTIVITY_ROLE,
                {
                    "target": activity.target,
                    "title": activity.title,
                    "external_id": activity.external_id,
                    "source": activity.source,
                    "kind": activity.kind,
                    "due_at": activity.due_at.isoformat() if activity.due_at else "",
                    "task_key": activity.task_key,
                    "confirmed": activity.confirmed,
                    "file_path": activity.file_path,
                    "task_id": activity.task_id,
                    "completed": activity.completed,
                    "urgency": activity.urgency,
                    "reminder": activity.reminder,
                },
            )
            item.setToolTip(
                "Recordatorio confirmado por el profesional · doble clic para abrir el origen"
                if activity.reminder
                else (
                    "Tarea ya confirmada · doble clic para abrir el origen"
                    if activity.confirmed
                    else "Doble clic para abrir el origen"
                )
            )
            if activity.priority <= 1:
                font = QFont(item.font())
                font.setBold(True)
                item.setFont(font)
            if activity.completed:
                item.setForeground(QColor("#7A8984"))
            self.activity_list.addItem(item)
        active_count = sum(not activity.completed for activity in items)
        completed_count = len(items) - active_count
        urgent_count = sum(
            activity.urgency in {"Vencida", "Hoy", "Próxima"} and not activity.completed
            for activity in items
        )
        self.activity_count.setText(
            "Sin acciones"
            if not items
            else f"{active_count} activas"
            + (f" · {urgent_count} urgentes" if urgent_count else "")
            + (f" · {completed_count} completadas" if completed_count else "")
        )
        self.update_activity_actions()

    def update_activity_actions(self):
        if not hasattr(self, "confirm_activity_button"):
            return
        selected = self.activity_list.currentItem()
        data = selected.data(ACTIVITY_ROLE) if selected else None
        is_receipt = isinstance(data, dict) and data.get("target") == "files"
        is_task = isinstance(data, dict) and data.get("target") == "task"
        enabled = is_receipt or is_task or (
            isinstance(data, dict)
            and data.get("target") == "portal"
            and bool(data.get("task_key"))
            and not bool(data.get("completed"))
        )
        self.confirm_activity_button.setEnabled(enabled)
        self.edit_activity_task_button.setEnabled(is_task)
        self.confirm_activity_button.setText(
            "Marcar recibido"
            if is_receipt
            else (
                "Marcar completada"
                if is_task or (enabled and data.get("confirmed"))
                else "Confirmar como tarea"
            )
        )

    def confirm_selected_activity(self):
        selected = self.activity_list.currentItem()
        data = selected.data(ACTIVITY_ROLE) if selected else None
        if not self.case or not isinstance(data, dict):
            return
        if data.get("target") == "files":
            self.confirm_activity_receipt(str(data.get("title", "")))
            return
        if data.get("target") == "task":
            self.complete_manual_activity_task(str(data.get("task_id", "")))
            return
        if not data.get("task_key"):
            return
        due_at = datetime.fromisoformat(data["due_at"]) if data.get("due_at") else None
        due_text = due_at.strftime("%d/%m/%Y %H:%M") if due_at else "sin fecha cierta"
        completing = bool(data.get("confirmed"))
        if QMessageBox.question(
            self,
            "Completar tarea" if completing else "Confirmar tarea",
            f"{data.get('kind')}: {data.get('title')}\n\nFecha: {due_text}\n\n"
            + (
                "¿Querés marcar esta tarea como completada?"
                if completing
                else "¿Querés confirmarla como tarea del expediente?"
            ),
        ) != QMessageBox.StandardButton.Yes:
            return
        professional = self.professional_combo.currentText().strip()
        if not professional or professional == ADD_PROFESSIONAL_LABEL:
            QMessageBox.information(self, "Falta el profesional", "Seleccioná el profesional responsable.")
            return
        try:
            with StudyDatabase(study_database_path(self.case.path.parent)) as database:
                expediente = database.find_expediente_by_folder(self.case.path)
                if not expediente:
                    raise RuntimeError("No encontramos el expediente en la base operativa.")
                if completing:
                    database.complete_activity_task(
                        expediente.id, str(data["task_key"]), professional
                    )
                else:
                    database.confirm_activity_task(
                        expediente.id,
                        f"{data.get('kind')}: {data.get('title')}",
                        professional,
                        due_at=due_at,
                        task_key=str(data["task_key"]),
                    )
            self.reload_activity()
            self.statusBar().showMessage(
                "Tarea completada" if completing else "Tarea confirmada para este expediente",
                4500,
            )
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
            QMessageBox.warning(self, "No pudimos confirmar la tarea", str(error))

    def confirm_activity_receipt(self, description: str):
        values, received = self._pending_values_and_received()
        matching = next((value for value in values if value.casefold() == description.casefold()), "")
        if not matching:
            return
        if QMessageBox.question(
            self,
            "Confirmar recepción",
            f"¿Querés marcar como recibido?\n\n{matching}",
        ) != QMessageBox.StandardButton.Yes:
            return
        received.add(matching)
        self.save_pending_documents(values, received)
        self.statusBar().showMessage(f"Documentación recibida: {matching}", 4500)

    def create_manual_activity_task(self):
        if not self.require_case():
            return
        title, accepted = QInputDialog.getText(self, "Nueva tarea", "Tarea del expediente:")
        title = " ".join(title.split()).strip()
        if not accepted or not title:
            return
        raw_date, accepted = QInputDialog.getText(
            self, "Nueva tarea", "Fecha objetivo opcional (dd/mm/aaaa o dd/mm/aaaa hh:mm):"
        )
        if not accepted:
            return
        due_at = None
        if raw_date.strip():
            for pattern in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
                try:
                    due_at = datetime.strptime(raw_date.strip(), pattern)
                    break
                except ValueError:
                    continue
            if due_at is None:
                QMessageBox.information(self, "Fecha inválida", "Usá el formato dd/mm/aaaa o dd/mm/aaaa hh:mm.")
                return
        professional = self.professional_combo.currentText().strip()
        if not professional or professional == ADD_PROFESSIONAL_LABEL:
            QMessageBox.information(self, "Falta el profesional", "Seleccioná el profesional responsable.")
            return
        try:
            with StudyDatabase(study_database_path(self.case.path.parent)) as database:
                expediente = database.find_expediente_by_folder(self.case.path)
                if not expediente:
                    raise RuntimeError("No encontramos el expediente en la base operativa.")
                database.create_manual_task(
                    expediente.id, title, professional, due_at=due_at
                )
            self.reload_activity()
            self.statusBar().showMessage("Tarea agregada al expediente", 4500)
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
            QMessageBox.warning(self, "No pudimos crear la tarea", str(error))

    def complete_manual_activity_task(self, task_id: str):
        if not self.case or not task_id:
            return
        if QMessageBox.question(self, "Completar tarea", "¿Querés marcar esta tarea como completada?") != QMessageBox.StandardButton.Yes:
            return
        professional = self.professional_combo.currentText().strip()
        try:
            with StudyDatabase(study_database_path(self.case.path.parent)) as database:
                database.complete_task(task_id, professional)
            self.reload_activity()
            self.statusBar().showMessage("Tarea completada", 4500)
        except (OSError, RuntimeError, ValueError, KeyError, sqlite3.Error) as error:
            QMessageBox.warning(self, "No pudimos completar la tarea", str(error))

    def edit_manual_activity_task(self):
        selected = self.activity_list.currentItem()
        data = selected.data(ACTIVITY_ROLE) if selected else None
        if not self.case or not isinstance(data, dict) or data.get("target") != "task":
            return
        title, accepted = QInputDialog.getText(
            self, "Editar tarea", "Descripción:", text=str(data.get("title", ""))
        )
        title = " ".join(title.split()).strip()
        if not accepted or not title:
            return
        current_due = ""
        if data.get("due_at"):
            current_due = datetime.fromisoformat(data["due_at"]).strftime("%d/%m/%Y %H:%M")
        raw_date, accepted = QInputDialog.getText(
            self,
            "Editar tarea",
            "Fecha objetivo opcional (dd/mm/aaaa o dd/mm/aaaa hh:mm):",
            text=current_due,
        )
        if not accepted:
            return
        due_at = None
        if raw_date.strip():
            for pattern in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
                try:
                    due_at = datetime.strptime(raw_date.strip(), pattern)
                    break
                except ValueError:
                    continue
            if due_at is None:
                QMessageBox.information(self, "Fecha inválida", "Usá el formato dd/mm/aaaa o dd/mm/aaaa hh:mm.")
                return
        professional = self.professional_combo.currentText().strip()
        try:
            with StudyDatabase(study_database_path(self.case.path.parent)) as database:
                database.update_manual_task(
                    str(data.get("task_id", "")), title, professional, due_at=due_at
                )
            self.reload_activity()
            self.statusBar().showMessage("Tarea actualizada", 4500)
        except (OSError, RuntimeError, ValueError, KeyError, sqlite3.Error) as error:
            QMessageBox.warning(self, "No pudimos editar la tarea", str(error))

    def open_selected_activity(self):
        selected = self.activity_list.currentItem()
        data = selected.data(ACTIVITY_ROLE) if selected else None
        if not isinstance(data, dict):
            return
        if data.get("target") == "pending":
            self.work_tabs.setCurrentIndex(self.files_tab_index)
            expected = str(data.get("title", "")).casefold()
            for index in range(self.pending_documents_list.count()):
                item = self.pending_documents_list.item(index)
                if item.text().casefold() == expected:
                    self.pending_documents_list.setCurrentItem(item)
                    self.pending_documents_list.scrollToItem(item)
                    break
            return
        if data.get("target") == "files":
            relative = Path(str(data.get("file_path", "")))
            candidate = self.case.path / relative if self.case else None
            if candidate and candidate.is_file() and self.path_is_inside_case(candidate):
                self.case_directory = candidate.parent
                self.reload_case_files(candidate)
                self.work_tabs.setCurrentIndex(self.files_tab_index)
            return
        self.work_tabs.setCurrentIndex(self.portal_tab_index)
        external_id = str(data.get("external_id", ""))
        source = str(data.get("source", ""))
        title = str(data.get("title", ""))
        for index in range(self.novedades_list.count()):
            item = self.novedades_list.item(index)
            movement = item.data(MOVEMENT_ROLE)
            if not isinstance(movement, dict):
                continue
            same_identity = external_id and movement.get("external_id") == external_id
            same_fallback = (
                not external_id
                and movement.get("source") == source
                and movement.get("title") == title
            )
            if same_identity or same_fallback:
                self.novedades_list.setCurrentItem(item)
                self.novedades_list.scrollToItem(item)
                break

    def reload_novedades(self):
        self.novedades_list.clear()
        self.update_novedad_actions()
        if not self.case:
            self.novedades_count.setText("Sin novedades")
            self.portal_case_status.setText("UBICACIÓN ACTUAL · Sin información")
            if hasattr(self, "work_tabs"):
                self.work_tabs.setTabText(self.portal_tab_index, "Expediente · 0")
            self.reload_activity()
            return
        try:
            movements = recent_case_novedades(self.case)
            unread_ids = set(unread_case_novedades(self.case))
            metadata = read_case_metadata(self.case)
            status = str(metadata.get("Ubicación actual SISFE", "")).strip()
            raw_synced_at = str(metadata.get("Última sincronización SISFE", "")).strip()
            synced_at = _format_sisfe_date(raw_synced_at) if raw_synced_at else ""
            status_text = status or "Sin información"
            self.portal_case_status.setText(f"UBICACIÓN ACTUAL · {status_text}")
            self.portal_case_status.setToolTip(
                f"Última sincronización: {synced_at}" if synced_at else "Todavía no sincronizado"
            )
        except (OSError, RuntimeError, sqlite3.Error) as error:
            self.novedades_count.setText("No disponibles")
            self.novedades_list.addItem(f"No pudimos cargar las novedades: {error}")
            if hasattr(self, "work_tabs"):
                self.work_tabs.setTabText(self.portal_tab_index, "Portal jurídico")
            self.reload_activity()
            return
        if self.work_tabs.currentIndex() == self.portal_tab_index and unread_ids:
            self._visible_unread_case = self.case
            self._visible_unread_movement_ids = tuple(unread_ids)
        previous_date = object()
        for movement in movements:
            movement_date = movement.occurred_at.date() if movement.occurred_at else None
            date_heading = ""
            if movement_date != previous_date:
                date_heading = _timeline_date_label(movement.occurred_at) + "\n"
                previous_date = movement_date
            interpretation = _interpretation_summary(movement.title)
            local_documents = self.movement_local_documents(movement.external_id, movement.source)
            cedula_documents = [
                path for path in local_documents if "CEDULA" in _comparable_text(path.stem).upper()
            ]
            document_line = "\nPDF disponible localmente" if local_documents else ""
            download_key = self.sisfe_download_key(self.case, movement.external_id)
            download_state, download_message = self._sisfe_download_states.get(
                download_key, ("", "")
            )
            if local_documents and download_state == "completed":
                self._sisfe_download_states.pop(download_key, None)
                download_state = ""
            state_line = {
                "queued": "\nEN COLA · descarga SISFE pendiente",
                "running": "\nDESCARGANDO · SISFE en segundo plano",
                "failed": "\nERROR · clic derecho para reintentar",
            }.get(download_state, "")
            kind = classify_sisfe_movement(movement.title, movement.movement_kind or "otro")
            judicial = kind in {"judicial", "cedula"}
            available = bool(movement.document_available)
            icon_color = (
                "#2B7A55" if local_documents
                else "#C9493C" if available
                else "#768681"
            )
            is_unread = movement.id in unread_ids
            details = [movement.title]
            if movement.observation.strip():
                details.append(movement.observation.strip())
            secondary = []
            if movement.presenter.strip():
                secondary.append(movement.presenter.strip())
            if movement.cargo_number.strip():
                secondary.append(f"CARGO {movement.cargo_number.strip()}")
            if secondary:
                details.append("   ·   ".join(secondary))
            if cedula_documents:
                details.append("✉ Cédula asociada")
            icon_name = (
                "notification" if kind == "cedula"
                else "judicial" if judicial
                else "party-filing" if kind == "parte"
                else "file"
            )
            item = QListWidgetItem(
                movement_icon(icon_name, icon_color, is_unread),
                date_heading + "\n".join(details) + f"{document_line}{state_line}",
            )
            line_count = len(details) + bool(date_heading) + bool(document_line) + bool(state_line)
            item.setSizeHint(QSize(0, max(66, 24 + line_count * 20)))
            if "CARGO A VERIFICAR" in f"{movement.title} {interpretation}".upper():
                item.setForeground(QColor("#B42318"))
                font = QFont(item.font())
                font.setBold(True)
                item.setFont(font)
            tooltip = f"Texto de origen: {movement.title}"
            if interpretation:
                tooltip += f"\n\n{interpretation}"
            if download_message:
                tooltip += f"\n\nDescarga SISFE: {download_message}"
            item.setToolTip(tooltip)
            item.setData(
                MOVEMENT_ROLE,
                {
                    "external_id": movement.external_id,
                    "title": movement.title,
                    "source": movement.source,
                    "occurred_at": movement.occurred_at.isoformat() if movement.occurred_at else "",
                    "interpretation": interpretation,
                    "local_documents": [str(path) for path in local_documents],
                    "cedula_documents": [str(path) for path in cedula_documents],
                    "download_state": download_state,
                    "judicial": judicial,
                    "movement_kind": kind,
                    "document_available": available,
                    "observation": movement.observation,
                    "presenter": movement.presenter,
                    "cargo_number": movement.cargo_number,
                    "is_unread": is_unread,
                },
            )
            self.novedades_list.addItem(item)
        count = len(movements)
        self.novedades_count.setText(
            "Sin novedades" if not count else f"{count} novedad{'es' if count != 1 else ''}"
        )
        if hasattr(self, "work_tabs"):
            self.work_tabs.setTabText(self.portal_tab_index, f"Expediente · {count}")
        self.reload_activity()

    def reload_pending_documents(self):
        if not hasattr(self, "pending_documents_list"):
            return
        self._loading_pending = True
        self.pending_documents_list.clear()
        values = []
        received = set()
        due_dates = {}
        if self.case:
            metadata = read_case_metadata(self.case)
            raw = str(metadata.get("Documentación pendiente", ""))
            values = [" ".join(line.split()) for line in raw.splitlines() if line.strip()]
            received = {
                " ".join(line.split())
                for line in str(metadata.get("Documentación recibida", "")).splitlines()
                if line.strip()
            }
            due_dates = self.pending_document_due_dates(metadata)
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
                    item.toolTip()
                    + f" · recordatorio para el {due_at.strftime('%d/%m/%Y')}"
                )
            self.pending_documents_list.addItem(item)
        self._loading_pending = False
        pending_count = sum(value not in received for value in values)
        received_count = len(values) - pending_count
        self.pending_documents_count.setText(
            "Sin documentos solicitados"
            if not values
            else f"{pending_count} pendientes · {received_count} recibidos"
        )
        if hasattr(self, "work_tabs"):
            if self.pending_tab_index >= 0:
                self.work_tabs.setTabText(
                    self.pending_tab_index,
                    f"Pendientes · {pending_count}",
                )
        self.update_pending_document_actions()
        self.reload_activity()

    def update_pending_document_actions(self):
        if hasattr(self, "pending_received_button"):
            selected = self.pending_documents_list.selectedItems()
            enabled = bool(selected) and self.case is not None
            self.pending_received_button.setEnabled(enabled)
            self.pending_rename_button.setEnabled(len(selected) == 1 and self.case is not None)
            self.pending_due_button.setEnabled(len(selected) == 1 and self.case is not None)
            self.pending_delete_button.setEnabled(enabled)
            self.pending_clear_button.setEnabled(self.pending_documents_list.count() > 0 and self.case is not None)
            current = self.pending_documents_list.currentRow()
            self.pending_up_button.setEnabled(enabled and current > 0)
            self.pending_down_button.setEnabled(enabled and current < self.pending_documents_list.count() - 1)

    def add_pending_document(self):
        if not self.require_case():
            return
        description, accepted = QInputDialog.getText(
            self,
            "Documentación pendiente",
            "Documento solicitado al cliente:",
        )
        normalized = " ".join(description.split()).strip()
        if not accepted or not normalized:
            return
        current = [
            self.pending_documents_list.item(index).text()
            for index in range(self.pending_documents_list.count())
        ]
        if normalized.casefold() in {value.casefold() for value in current}:
            QMessageBox.information(
                self,
                "Documentación pendiente",
                "Ese documento ya figura como pendiente.",
            )
            return
        current.append(normalized)
        self.save_pending_documents(current)
        self.work_tabs.setCurrentIndex(self.files_tab_index)

    def complete_pending_documents(self):
        selected = self.pending_documents_list.selectedItems()
        if not selected or not self.case:
            return
        received = {item.text() for item in selected}
        metadata = read_case_metadata(self.case)
        stored_received = {
            " ".join(line.split())
            for line in str(metadata.get("Documentación recibida", "")).splitlines()
            if line.strip()
        }
        stored_received.update(received)
        values = [
            self.pending_documents_list.item(index).text()
            for index in range(self.pending_documents_list.count())
        ]
        self.save_pending_documents(values, stored_received)
        label = next(iter(received)) if len(received) == 1 else f"{len(received)} documentos"
        self.statusBar().showMessage(f"Documentación recibida: {label}", 4500)

    def _pending_values_and_received(self) -> tuple[list[str], set[str]]:
        values = []
        received = set()
        for index in range(self.pending_documents_list.count()):
            item = self.pending_documents_list.item(index)
            values.append(item.text())
            if item.checkState() == Qt.CheckState.Checked:
                received.add(item.text())
        return values, received

    def rename_pending_document(self):
        selected = self.pending_documents_list.selectedItems()
        if len(selected) != 1 or not self.case:
            return
        item = selected[0]
        description, accepted = QInputDialog.getText(self, "Renombrar pendiente", "Nuevo nombre:", text=item.text())
        normalized = " ".join(description.split()).strip()
        if not accepted or not normalized or normalized == item.text():
            return
        values, received = self._pending_values_and_received()
        if normalized.casefold() in {value.casefold() for value in values if value != item.text()}:
            QMessageBox.information(self, "Documentación pendiente", "Ese documento ya figura en la lista.")
            return
        old = item.text()
        metadata = read_case_metadata(self.case)
        due_dates = self.pending_document_due_dates(metadata)
        values[values.index(old)] = normalized
        if old in received:
            received.remove(old)
            received.add(normalized)
        due = due_dates.pop(old.casefold(), None)
        if due:
            due_dates[normalized.casefold()] = due
        self.save_pending_documents(values, received, due_dates)

    @staticmethod
    def pending_document_due_dates(metadata: dict[str, str]) -> dict[str, datetime]:
        try:
            raw = json.loads(str(metadata.get("Fechas de documentación pendiente", "{}")))
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

    def set_pending_document_due_date(self):
        selected = self.pending_documents_list.selectedItems()
        if len(selected) != 1 or not self.case:
            return
        item = selected[0]
        current = str(item.data(PENDING_DUE_ROLE) or "")
        initial = datetime.fromisoformat(current).strftime("%d/%m/%Y") if current else ""
        raw, accepted = QInputDialog.getText(
            self,
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
                QMessageBox.information(self, "Fecha inválida", "Usá el formato dd/mm/aaaa.")
                return
        values, received = self._pending_values_and_received()
        due_dates = self.pending_document_due_dates(read_case_metadata(self.case))
        if due_at:
            due_dates[item.text().casefold()] = due_at
        else:
            due_dates.pop(item.text().casefold(), None)
        self.save_pending_documents(values, received, due_dates)

    def delete_pending_documents(self):
        selected = self.pending_documents_list.selectedItems()
        if not selected or not self.case:
            return
        if QMessageBox.question(self, "Borrar pendientes", "¿Querés borrar los pendientes seleccionados?") != QMessageBox.StandardButton.Yes:
            return
        removed = {item.text() for item in selected}
        values, received = self._pending_values_and_received()
        self.save_pending_documents([value for value in values if value not in removed], received - removed)

    def clear_pending_documents(self):
        if not self.case or not self.pending_documents_list.count():
            return
        if QMessageBox.question(self, "Vaciar pendientes", "¿Querés vaciar toda la lista de documentación?") == QMessageBox.StandardButton.Yes:
            self.save_pending_documents([], set())

    def move_pending_document(self, offset: int):
        row = self.pending_documents_list.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= self.pending_documents_list.count():
            return
        self._loading_pending = True
        item = self.pending_documents_list.takeItem(row)
        self.pending_documents_list.insertItem(target, item)
        self.pending_documents_list.setCurrentRow(target)
        self._loading_pending = False
        self.persist_pending_document_order()

    def persist_pending_document_order(self):
        if self._loading_pending or not self.case:
            return
        values, received = self._pending_values_and_received()
        self.save_pending_documents(values, received)

    def pending_document_changed(self, _item: QListWidgetItem):
        if self._loading_pending or not self.case:
            return
        values, received = self._pending_values_and_received()
        self.save_pending_documents(values, received)

    def save_pending_documents(
        self,
        values: list[str],
        received: set[str] | None = None,
        due_dates: dict[str, datetime] | None = None,
    ):
        if not self.case:
            return
        metadata = read_case_metadata(self.case)
        if values:
            metadata["Documentación pendiente"] = "\n".join(values)
        else:
            metadata.pop("Documentación pendiente", None)
        if received is not None:
            ordered_received = [value for value in values if value in received]
            if ordered_received:
                metadata["Documentación recibida"] = "\n".join(ordered_received)
            else:
                metadata.pop("Documentación recibida", None)
        stored_dates = due_dates if due_dates is not None else self.pending_document_due_dates(metadata)
        allowed = {value.casefold() for value in values}
        stored_dates = {key.casefold(): value for key, value in stored_dates.items() if key.casefold() in allowed}
        if stored_dates:
            metadata["Fechas de documentación pendiente"] = json.dumps(
                {key: value.isoformat() for key, value in stored_dates.items()},
                ensure_ascii=False,
                sort_keys=True,
            )
        else:
            metadata.pop("Fechas de documentación pendiente", None)
        try:
            save_case_metadata(self.case, metadata)
            self._loaded_metadata = read_case_metadata(self.case)
            self.sync_case_projection()
            self.update_more_metadata_count()
            self.update_case_badge()
            self.reload_pending_documents()
        except Exception as error:
            QMessageBox.warning(
                self,
                "No pudimos actualizar la documentación pendiente",
                str(error),
            )

    def update_novedad_actions(self):
        if hasattr(self, "novedad_detail_button"):
            self.novedad_detail_button.setEnabled(self.novedades_list.currentItem() is not None)

    def selected_novedad_data(self) -> dict | None:
        item = self.novedades_list.currentItem()
        data = item.data(MOVEMENT_ROLE) if item else None
        return data if isinstance(data, dict) else None

    def movement_local_documents(self, external_id: str, source: str) -> list[Path]:
        """Obtiene asociaciones existentes, sin crear ni modificar archivos."""
        if not self.case or not external_id:
            return []
        try:
            with StudyDatabase(study_database_path(self.case.path.parent)) as database:
                expediente = database.find_expediente_by_folder(self.case.path)
                movement = (
                    database.find_movement_by_external_id(
                        expediente.id, external_id, source=source
                    )
                    if expediente else None
                )
                documents = database.list_movement_documents(movement.id) if movement else []
        except (OSError, RuntimeError, sqlite3.Error):
            return []
        case_root = self.case.path.resolve()
        paths: list[Path] = []
        for document in documents:
            path = (case_root / document.relative_path).resolve()
            if path.is_file() and case_root in path.parents:
                paths.append(path)
        return paths

    def show_novedad_menu(self, point):
        item = self.novedades_list.itemAt(point)
        if not item:
            return
        self.novedades_list.setCurrentItem(item)
        movement = self.selected_novedad_data()
        if not movement:
            return
        menu = QMenu(self)
        local_documents = [Path(path) for path in movement.get("local_documents", [])]
        cedula_documents = [Path(path) for path in movement.get("cedula_documents", [])]
        download_state = str(movement.get("download_state") or "")
        if local_documents:
            if len(local_documents) == 1:
                menu.addAction("Abrir documento", lambda: open_file(local_documents[0]))
            else:
                open_menu = menu.addMenu("Abrir documento")
                for path in local_documents:
                    open_menu.addAction(path.name, lambda checked=False, value=path: open_file(value))
            if cedula_documents:
                menu.addAction("Abrir cédula asociada", lambda: open_file(cedula_documents[0]))
            if movement.get("judicial") and local_documents[0].suffix.lower() == ".pdf":
                menu.addAction(
                    "Generar cédula",
                    lambda: self.generate_cedula_from_pdf(
                        local_documents[0],
                        context=dict(
                            self.capture_sisfe_context(),
                            movement_external_id=movement.get("external_id", ""),
                            movement_source=movement.get("source", ""),
                        ),
                    ),
                )
        if movement.get("source") == "sisfe" and movement.get("external_id"):
            if local_documents:
                action = menu.addAction("Descargar documento")
                action.setEnabled(False)
                action.setToolTip("Ya está disponible localmente; no se crea una copia.")
            elif download_state == "failed":
                key = self.sisfe_download_key(self.case, str(movement["external_id"]))
                menu.addAction(
                    "Reintentar descarga",
                    lambda checked=False, value=key: self.retry_sisfe_movement(value),
                )
            elif download_state in {"queued", "running"}:
                action = menu.addAction(
                    "Descarga en curso" if download_state == "running" else "Descarga en cola"
                )
                action.setEnabled(False)
            else:
                menu.addAction("Descargar documento", self.download_selected_novedad_document)
                if movement.get("judicial"):
                    menu.addAction("Generar cédula", self.generate_cedula_from_selected_novedad)
        menu.addSeparator()
        menu.addAction("Ver detalle", self.show_selected_novedad)
        menu.exec(self.novedades_list.mapToGlobal(point))

    @staticmethod
    def is_judicial_movement(title: str) -> bool:
        normalized = _comparable_text(title).upper()
        return any(
            term in normalized
            for term in (
                "DECRETO", "PROVIDENCIA", "PROVEIDO", "AUTO ", "RESOLUCION",
                "SENTENCIA", "AUDIENCIA", "DESPACHO", "NOTIFICACION",
            )
        )

    def download_selected_novedad_document(self):
        self._request_selected_movement_detail(
            lambda remote_case_id, detail, _movement: self.start_sisfe_download(remote_case_id, detail)
        )

    def generate_cedula_from_selected_novedad(self):
        """Descarga el PDF conocido por SISFE y continúa con la cédula."""
        def continue_after_detail(remote_case_id, detail, movement):
            if not (detail.get("has_primary_document") or detail.get("has_additional_documents")):
                QMessageBox.information(
                    self, "Sin documento", "Este movimiento no tiene documentos descargables en SISFE."
                )
                return
            detail["_generate_cedula"] = True
            detail.setdefault("_gestor_context", {}).update(
                movement_external_id=movement.get("external_id", ""),
                movement_source=movement.get("source", "sisfe"),
            )
            self.start_sisfe_download(remote_case_id, detail)

        self._request_selected_movement_detail(continue_after_detail)

    def _request_selected_movement_detail(self, completed):
        context = self.capture_sisfe_context()
        movement = self.selected_novedad_data()
        if not movement or movement.get("source") != "sisfe" or not movement.get("external_id"):
            return
        if not self._sisfe_login_dialog or not self.sisfe_session.active or not self.case:
            QMessageBox.information(self, "Sesión SISFE", "Iniciá la sesión SISFE para consultar el documento.")
            return
        cuij = read_case_metadata(self.case).get("CUIJ", "")
        if not cuij.strip():
            QMessageBox.information(self, "Sin número de expediente", "El caso necesita número de expediente para consultar SISFE.")
            return
        self.update_sisfe_indicator(OperationState.RUNNING, "Consultando documento SISFE…")

        def detail_ready(detail, error):
            if error:
                self.update_sisfe_indicator(OperationState.ERROR, "No se pudo consultar el documento")
                QMessageBox.warning(self, "No pudimos consultar SISFE", str(error))
                return
            self.update_sisfe_indicator(OperationState.SUCCESS, "Documento SISFE encontrado")
            detail = dict(detail, _gestor_context=context)
            completed(str(detail.get("remote_case_id") or ""), detail, movement)

        self._sisfe_login_dialog.request_movement_detail(cuij, str(movement["external_id"]), detail_ready)

    def show_selected_novedad(self):
        context = self.capture_sisfe_context()
        movement = self.selected_novedad_data()
        if not movement:
            return
        if movement.get("source") != "sisfe" or not movement.get("external_id"):
            interpretation = movement.get("interpretation") or "Sin detecciones automáticas."
            QMessageBox.information(
                self,
                "Detalle de la novedad",
                f"{movement.get('title', 'Movimiento')}\n\nInterpretación:\n{interpretation}\n\n"
                "Esta novedad no proviene de SISFE.",
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
        self.update_sisfe_indicator(OperationState.RUNNING, "Consultando detalle SISFE…")

        def completed(detail, error):
            self.update_novedad_actions()
            if error:
                self.update_sisfe_indicator(
                    OperationState.ERROR,
                    "No se pudo consultar la novedad",
                )
                QMessageBox.warning(self, "No pudimos consultar la novedad", str(error))
                return
            self.update_sisfe_indicator(
                OperationState.SUCCESS,
                "Sesión manual lista para sincronizar",
            )
            stamp = _format_sisfe_date(detail.get("occurred_at"))
            observation = detail.get("observation") or "Sin observaciones adicionales."
            interpretation = _interpretation_summary(
                f"{detail.get('title') or movement.get('title') or ''} {observation}"
            ) or "Sin detecciones automáticas."
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
                f"Interpretación: {interpretation}\n"
                f"Disponible: {', '.join(attachments) if attachments else 'sin adjuntos'}"
            )
            open_button = box.addButton(
                "Abrir expediente en SISFE",
                QMessageBox.ButtonRole.ActionRole,
            )
            download_button = None
            if detail.get("has_primary_document") or detail.get("has_additional_documents"):
                download_button = box.addButton(
                    "Descargar documentos",
                    QMessageBox.ButtonRole.ActionRole,
                )
            box.addButton(QMessageBox.StandardButton.Close)
            box.exec()
            remote_case_id = str(detail.get("remote_case_id") or "")
            detail = dict(detail, _gestor_context=context)
            if download_button and box.clickedButton() is download_button:
                self.start_sisfe_download(remote_case_id, detail)
            elif box.clickedButton() is open_button:
                self.open_sisfe_case(remote_case_id, movement_detail=detail)

        self._sisfe_login_dialog.request_movement_detail(
            cuij,
            str(movement["external_id"]),
            completed,
        )

    def open_sisfe_case(
        self,
        remote_case_id: str,
        *,
        movement_detail: dict | None = None,
        auto_download: bool = False,
    ):
        if self._sisfe_download_active:
            self.show_sisfe_download()
            return
        case = (movement_detail or {}).get("_gestor_context", {}).get("case", self.case)
        if not remote_case_id or not self._sisfe_login_dialog or not case:
            return
        if self._sisfe_case_dialog is not None:
            self._sisfe_case_dialog.close()
            self._sisfe_case_dialog.deleteLater()
        self._sisfe_case_dialog = SisfeCaseBrowserDialog(
            self._sisfe_login_dialog.profile,
            remote_case_id,
            case,
            self,
            movement_detail=movement_detail,
            auto_download=auto_download,
        )
        self._sisfe_case_dialog.documentSaved.connect(self.sisfe_document_saved)
        self._sisfe_case_dialog.show()
        self._sisfe_case_dialog.raise_()
        self._sisfe_case_dialog.activateWindow()

    def capture_sisfe_context(self) -> dict:
        return {
            "case": self.case,
            "professional": self.professional_combo.currentText(),
            "profile_values": dict(self.professional_template_values()),
        }

    @staticmethod
    def sisfe_download_key(case: Case | None, movement_id: str) -> tuple[str, str]:
        case_path = str(case.path.resolve()) if case else ""
        return case_path, str(movement_id or "")

    def sisfe_request_key(self, request: tuple[str, dict] | None) -> tuple[str, str]:
        if not request:
            return "", ""
        _remote_case_id, detail = request
        context = detail.get("_gestor_context", {})
        return self.sisfe_download_key(
            context.get("case"), str(detail.get("movement_id") or "")
        )

    def start_sisfe_download(self, remote_case_id: str, movement_detail: dict):
        movement_detail = dict(movement_detail)
        context = movement_detail.setdefault("_gestor_context", self.capture_sisfe_context())
        case = context["case"]
        if not remote_case_id or not self._sisfe_login_dialog or not case:
            return
        request = (remote_case_id, movement_detail)
        key = self.sisfe_request_key(request)
        known_requests = [self._sisfe_download_request, *self._sisfe_download_queue]
        if key != ("", "") and any(self.sisfe_request_key(known) == key for known in known_requests):
            self.statusBar().showMessage("Ese movimiento ya está en la cola de descargas.", 5000)
            return
        self._sisfe_download_failures.pop(key, None)
        if self._sisfe_download_active:
            self._sisfe_download_queue.append(request)
            self._sisfe_download_states[key] = (
                "queued",
                f"En espera · posición {len(self._sisfe_download_queue)}",
            )
            if self.case == case:
                self.reload_novedades()
            self.update_sisfe_indicator(
                OperationState.RUNNING,
                f"Descargando desde SISFE · {len(self._sisfe_download_queue)} en cola",
            )
            self.statusBar().showMessage("Movimiento agregado a la cola SISFE.", 5000)
            return
        self._begin_sisfe_download(request)

    def _begin_sisfe_download(self, request: tuple[str, dict]):
        remote_case_id, movement_detail = request
        context = movement_detail.get("_gestor_context", {})
        case = context.get("case")
        if not self._sisfe_login_dialog or not case:
            return
        if self._sisfe_case_dialog is not None:
            self._sisfe_case_dialog.close()
            self._sisfe_case_dialog.deleteLater()
        self._sisfe_download_request = request
        key = self.sisfe_request_key(request)
        self._sisfe_download_states[key] = ("running", "Descarga en segundo plano")
        self._sisfe_case_dialog = SisfeCaseBrowserDialog(
            self._sisfe_login_dialog.profile,
            remote_case_id,
            case,
            self,
            movement_detail=movement_detail,
            auto_download=True,
        )
        self._sisfe_case_dialog.documentSaved.connect(self.sisfe_document_saved)
        self._sisfe_case_dialog.automationFinished.connect(self.sisfe_download_finished)
        dialog = self._sisfe_case_dialog

        def dialog_closed(_result):
            if self._sisfe_download_active and self._sisfe_case_dialog is dialog:
                self.sisfe_download_finished(False, "Se cerró la ventana de descarga. Podés reintentar.")

        dialog.finished.connect(dialog_closed)
        self._sisfe_download_active = True
        self.sisfe_retry_button.setVisible(False)
        self.sisfe_show_download_button.setVisible(False)
        queue_suffix = (
            f" · {len(self._sisfe_download_queue)} en cola"
            if self._sisfe_download_queue else ""
        )
        self.update_sisfe_indicator(
            OperationState.RUNNING, f"Descargando desde SISFE…{queue_suffix}"
        )
        self.statusBar().showMessage("La descarga SISFE continúa en segundo plano", 5000)
        if self.case == case:
            self.reload_novedades()

    def sisfe_download_finished(self, success: bool, message: str):
        request = self._sisfe_download_request
        key = self.sisfe_request_key(request)
        case = request[1].get("_gestor_context", {}).get("case") if request else None
        self._sisfe_download_active = False
        self._sisfe_download_request = None
        if success:
            self._sisfe_download_states[key] = ("completed", message)
            self._sisfe_download_failures.pop(key, None)
            self.update_sisfe_indicator(OperationState.SUCCESS, "Descarga SISFE completada")
            self.statusBar().showMessage(f"SISFE: {message}", 6500)
            dialog = self._sisfe_case_dialog
            self._sisfe_case_dialog = None
            if dialog is not None:
                dialog.close()
                dialog.deleteLater()
            self.sisfe_retry_button.setVisible(False)
            self.sisfe_show_download_button.setVisible(False)
        else:
            self._sisfe_download_states[key] = ("failed", message)
            if request:
                self._sisfe_download_failures[key] = request
            self.update_sisfe_indicator(OperationState.ERROR, "No se pudo descargar desde SISFE")
            self.sisfe_status.setToolTip(message)
            self.sisfe_retry_button.setVisible(True)
            self.sisfe_show_download_button.setVisible(True)
            self.statusBar().showMessage(f"SISFE: {message}", 9000)
        if self.case == case:
            self.reload_novedades()
        if self._sisfe_download_queue:
            failed_dialog = self._sisfe_case_dialog
            self._sisfe_case_dialog = None
            if failed_dialog is not None:
                failed_dialog.close()
                failed_dialog.deleteLater()
            next_request = self._sisfe_download_queue.pop(0)
            QTimer.singleShot(0, lambda value=next_request: self._begin_sisfe_download(value))

    def retry_sisfe_download(self):
        if not self._sisfe_download_failures:
            return
        key = next(reversed(self._sisfe_download_failures))
        self.retry_sisfe_movement(key)

    def retry_sisfe_movement(self, key: tuple[str, str]):
        request = self._sisfe_download_failures.pop(key, None)
        if not request:
            return
        self.start_sisfe_download(*request)

    def show_sisfe_download(self):
        if self._sisfe_case_dialog is None:
            return
        self._sisfe_case_dialog.show()
        self._sisfe_case_dialog.raise_()
        self._sisfe_case_dialog.activateWindow()

    def sisfe_document_saved(self, path: str, duplicate: bool):
        request = self._sisfe_download_request
        context = request[1].get("_gestor_context", {}) if request else {}
        owner_case = context.get("case")
        if self.case == owner_case:
            self.reload_case_files()
            self.reload_novedades()
        if duplicate:
            message = "SISFE: el documento ya estaba guardado"
        else:
            message = f"SISFE: archivo guardado en {Path(path).parent.name}"
        self.statusBar().showMessage(message, 6000)
        saved_path = Path(path)
        generate_cedula = bool(request and request[1].pop("_generate_cedula", False))
        if generate_cedula and saved_path.suffix.lower() == ".pdf":
            QTimer.singleShot(0, lambda value=saved_path, owner=context: self.generate_cedula_from_pdf(value, context=owner))

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

    def import_cases_from_spreadsheet(self):
        if self.long_task_active():
            self.warn_long_task_active()
            return
        if not self.require_study():
            return
        root = self.store.settings.study_root
        if root is None or not root.is_dir():
            QMessageBox.warning(
                self,
                "Ubicación no disponible",
                "Conectá o sincronizá esta ubicación antes de importar casos.",
            )
            return
        professional = self.professional_combo.currentText().strip()
        if professional == ADD_PROFESSIONAL_LABEL:
            professional = ""
        dialog = CaseSpreadsheetImportDialog(root, professional, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        rows = [row for row in dialog.rows if row.selected]
        if not rows:
            return
        self._long_task_omitted = len(dialog.rows) - len(rows)
        task = LongTask("Importando casos", len(rows))
        self.begin_long_task(task, "import")

        def process(row: ImportRow):
            outcome = import_rows(root, [row], professional=professional)[0]
            if outcome.error:
                return "error", outcome.error, outcome
            return "ok", "Importado", outcome

        thread = QThread(self)
        worker = BatchTaskWorker(
            task,
            rows,
            process,
            lambda row: row.actor or f"Fila {row.source_row}",
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.stopped.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._long_task_thread_finished)
        self._long_task_thread = thread
        self._long_task_worker = worker
        task.start()
        thread.start()

    def _long_task_thread_finished(self):
        self._long_task_thread = None
        self._long_task_worker = None
        self.sync_all_button.setEnabled(True)
        if self._close_after_long_task and self._long_task is None:
            self._close_after_long_task = False
            QTimer.singleShot(0, self.close)

    def import_external_case(self, study_root: Path | None = None):
        if not self.require_study():
            return
        root = Path(study_root) if study_root else self.store.settings.study_root
        if root is None or not root.is_dir():
            QMessageBox.warning(
                self,
                "Ubicación no disponible",
                "Conectá o sincronizá esta ubicación antes de incorporar un caso.",
            )
            return
        source_name = QFileDialog.getExistingDirectory(
            self,
            "Elegí la carpeta externa del caso",
            str(root.parent),
        )
        if not source_name:
            return
        source = Path(source_name)
        try:
            file_count, total_bytes = external_case_summary(source)
            dialog = ExternalCaseImportDialog(
                source,
                root,
                file_count,
                total_bytes,
                self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            case = copy_external_case(root, source, dialog.case_name)
            self.reload_cases(case.path)
            self.set_case(case)
            self.statusBar().showMessage(
                f"Caso incorporado por copia: {case.name} · el origen no fue modificado",
                7000,
            )
        except Exception as error:
            QMessageBox.critical(self, "No pudimos incorporar la carpeta", str(error))

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
            self.set_case(case)
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
                f"DOCUMENTOS FRECUENTES · {active.name.upper()}"
                if active
                else "DOCUMENTOS FRECUENTES"
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
                        dialog.selected_image_mode,
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
            self.sync_case_projection()
            self._metadata_snapshot = self.basic_metadata_values()
            self._metadata_dirty = False
            self.set_metadata_editing(False)
            self.update_more_metadata_count()
            self.update_case_badge()
            self.update_output_preview()
            self.reload_pending_documents()
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

        def matching_descendant(parent: QTreeWidgetItem) -> QTreeWidgetItem | None:
            for index in range(parent.childCount()):
                child = parent.child(index)
                if child.data(0, PATH_ROLE) == str(self.case.path):
                    return child
                nested = matching_descendant(child)
                if nested:
                    return nested
            return None

        self.case_tree.blockSignals(True)
        try:
            for root_index in range(self.case_tree.topLevelItemCount()):
                root = self.case_tree.topLevelItem(root_index)
                item = matching_descendant(root)
                if item:
                    self.case_tree.setCurrentItem(item)
                    return
        finally:
            self.case_tree.blockSignals(False)

    def open_extended_metadata(self):
        if not self.case:
            return
        metadata = dict(self._loaded_metadata)
        metadata.update(self.basic_metadata_values())
        metadata = self.with_shared_client_defaults(metadata)
        dialog = ExtendedMetadataDialog(
            metadata,
            self,
            case_name=self.case.name,
            professional=self.professional_combo.currentText(),
        )
        dialog.documentRequested.connect(
            lambda action, values: self.generate_interview_document(action, values, dialog)
        )
        if not dialog.exec():
            return
        self.save_extended_metadata_values(dialog.values())

    def with_shared_client_defaults(self, metadata: dict[str, str]) -> dict[str, str]:
        """Prefill missing personal data already known for the same client.

        The values are offered only in the form. They are written to this case
        if the user explicitly saves it, and no sibling case file is modified.
        """
        if not self.case:
            return dict(metadata)
        try:
            with StudyDatabase(study_database_path(self.case.path.parent)) as database:
                client = database.find_client_by_case_folder(self.case.path)
        except (OSError, RuntimeError, sqlite3.Error):
            client = None
        result = dict(metadata)
        if not client:
            return result
        shared_values = {
            "Nombre completo": client.name,
            "DNI del actor": client.dni,
            "CUIL del actor": client.cuil,
            "Teléfono del actor": client.phone,
            "Correo electrónico del actor": client.email,
            "Domicilio real": client.address,
        }
        for key, value in shared_values.items():
            if value and not str(result.get(key, "")).strip():
                result[key] = value
        return result

    def save_extended_metadata_values(self, values: dict[str, str]) -> bool:
        if not self.case:
            return False
        payload = self.basic_metadata_values()
        payload.update(values)
        try:
            save_case_metadata(self.case, payload)
            self.load_metadata(read_case_metadata(self.case))
            self.sync_case_projection()
            self.update_case_badge()
            self.update_output_preview()
            self.reload_pending_documents()
            self.statusBar().showMessage("Datos ampliados guardados", 3000)
            return True
        except Exception as error:
            QMessageBox.warning(self, "No pudimos guardar los datos", str(error))
            return False

    def generate_interview_document(
        self,
        action: str,
        values: dict[str, str],
        parent: QWidget | None = None,
    ):
        if not self.case or not self.save_extended_metadata_values(values):
            return

        def available_models() -> list[Path]:
            models = [
                path
                for path in list_models(self.store.models_dir)
                if path.resolve() != self.base_template.resolve()
            ]
            return rank_models_for_document(models, action, values.get(CASE_TYPE_FIELD, ""))

        models = available_models()
        if not models:
            QMessageBox.information(
                parent or self,
                "Todavía no hay modelos",
                "Agregá un modelo Word para continuar. El catálogo se actualiza automáticamente.",
            )
            added = self.add_writing_model()
            if not added:
                return
            models = available_models()

        dialog = ModelPickerDialog(
            models,
            parent or self,
            model_provider=available_models,
            add_model_callback=self.add_writing_model,
        )
        labels = {
            "ficha": "Generar ficha inicial",
            "pacto": "Generar pacto de cuota litis",
            "poder": "Generar poder",
        }
        dialog.setWindowTitle(labels.get(action, "Generar documento"))
        if not dialog.exec() or not dialog.selected_model or not dialog.title:
            return

        extra_values: dict[str, str] = {}
        if action == "poder" and canonical_case_type(values.get(CASE_TYPE_FIELD, "")) == CASE_TYPE_SUCCESSION:
            heirs = []
            for raw_line in str(values.get("Herederos", "")).splitlines():
                row = [part.strip() for part in re.split(r"\s*[|│]\s*", raw_line)]
                if row and row[0]:
                    heirs.append((row + [""] * 5)[:5])
            if not heirs:
                QMessageBox.information(
                    parent or self,
                    "Faltan herederos",
                    "Cargá al menos un heredero en la ficha antes de generar el poder.",
                )
                return
            heir_dialog = HeirPickerDialog(heirs, parent or self)
            if not heir_dialog.exec():
                return
            selected = heir_dialog.selected_rows
            names = [row[0] for row in selected]
            first = selected[0]
            extra_values.update(
                {
                    "PODERDANTES": "; ".join(names),
                    "HEREDEROS_SELECCIONADOS": "\n".join(" | ".join(row) for row in selected),
                    "HEREDERO": "; ".join(names),
                    "NOMBRE_HEREDERO": first[0],
                    "DNI_HEREDERO": first[1],
                    "CUIT_HEREDERO": first[2],
                    "DOMICILIO_HEREDERO": first[3],
                    "CARACTER_HEREDERO": first[4],
                }
            )

        self.create_and_open_writing(dialog.title, dialog.selected_model, extra_values)

    def update_more_metadata_count(self):
        if not hasattr(self, "more_metadata_button"):
            return
        count = sum(
            1
            for key, value in self._loaded_metadata.items()
            if key not in CASE_FIELDS and key not in SYSTEM_METADATA_KEYS and str(value).strip()
        )
        self.more_metadata_button.setText(
            f"Datos del caso · {count}" if count else "Datos del caso"
        )

    def update_case_badge(self):
        if not self.case:
            self.case_badge.hide()
            return
        has_data = any(str(value).strip() for value in self._loaded_metadata.values())
        self.case_badge.setText(
            self.case.path.parent.name.upper()
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
        suggestion = suggested_presentation_name(
            self.case, self.current_writing, pattern=self.store.settings.naming_pattern
        )
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
            try:
                entries = [
                    path for path in current.iterdir()
                    if not path.name.startswith(".")
                ]
                query = (
                    self.files_search.text().strip().casefold()
                    if hasattr(self, "files_search")
                    else ""
                )
                if query:
                    entries = [
                        path for path in entries if query in path.name.casefold()
                    ]
                sort_key = self.files_sort_combo.currentData() or "name_asc"
                reverse = sort_key.endswith("_desc")
                if sort_key.startswith("modified"):
                    entries.sort(
                        key=lambda path: (path.stat().st_mtime, path.name.casefold()),
                        reverse=reverse,
                    )
                elif sort_key.startswith("size"):
                    entries.sort(
                        key=lambda path: (
                            path.stat().st_size if path.is_file() else -1,
                            path.name.casefold(),
                        ),
                        reverse=reverse,
                    )
                elif sort_key.startswith("type"):
                    entries.sort(
                        key=lambda path: (
                            "" if path.is_dir() else path.suffix.casefold(),
                            path.name.casefold(),
                        ),
                        reverse=reverse,
                    )
                else:
                    entries.sort(key=lambda path: path.name.casefold(), reverse=reverse)
                # Las carpetas quedan primero: es navegación visual, no una
                # operación sobre la estructura física del caso.
                entries.sort(key=lambda path: 0 if path.is_dir() else 1)
            except OSError:
                entries = []
            for path in entries:
                category = document_categories.get(path.resolve(), "otro")
                label = self.case_file_label(path, category)
                item = QListWidgetItem(label)
                item.setIcon(self.icon_for_path(path))
                item.setData(PATH_ROLE, str(path))
                try:
                    stats = path.stat()
                    item.setData(
                        MODIFIED_ROLE,
                        datetime.fromtimestamp(stats.st_mtime).strftime("%d/%m/%Y %H:%M"),
                    )
                    item.setData(
                        SIZE_ROLE, "—" if path.is_dir() else human_size(stats.st_size)
                    )
                except OSError:
                    item.setData(MODIFIED_ROLE, "")
                    item.setData(SIZE_ROLE, "")
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
        self.refresh_case_file_watcher()

    def refresh_case_file_watcher(self):
        watched = self._file_watcher.directories()
        if watched:
            self._file_watcher.removePaths(watched)
        current = self.case_directory if self.case else None
        if current and current.is_dir():
            self._file_watcher.addPath(str(current))

    def schedule_case_files_refresh(self, _path: str = ""):
        if self.case and not self._loading_files:
            self._file_refresh_timer.start()

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

    def pick_presentation_files(self):
        if not self.require_case():
            return
        files = QFileDialog.getOpenFileNames(
            self, "Agregar archivos a la presentación", str(self.case.path)
        )[0]
        if files:
            self.handle_compilation_drop([Path(path) for path in files])

    def pick_case_folder(self):
        if not self.require_case():
            return
        folder = QFileDialog.getExistingDirectory(self, "Agregar carpeta al caso")
        if folder:
            self.import_paths([Path(folder)])

    def import_paths(self, paths: list[Path], add_to_compilation: bool = False) -> list[Path]:
        if not self.require_case():
            return []
        try:
            case_root = self.case.path.resolve(strict=True)
            destination = (self.case_directory or self.case.path).resolve(strict=True)
            destination.relative_to(case_root)
            if not destination.is_dir():
                raise ValueError
        except (OSError, RuntimeError, ValueError):
            QMessageBox.critical(
                self,
                "No pudimos agregar el archivo",
                "La carpeta de destino no pertenece al caso actual.",
            )
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
                    if Path(name.strip()).name != name.strip() or ".." in Path(name.strip()).parts:
                        raise ValueError("El nombre de la carpeta no es seguro.")
                    target = import_directory(Case(destination), source, name)
                elif source.is_file():
                    dialog = ImportFileDialog(source, self)
                    if not dialog.exec():
                        continue
                    normalized_name = dialog.normalized_name.strip()
                    if (
                        not normalized_name
                        or Path(normalized_name).name != normalized_name
                        or ".." in Path(normalized_name).parts
                    ):
                        raise ValueError("El nombre del archivo no es seguro.")
                    target = import_file(
                        Case(destination),
                        source,
                        normalized_name,
                        dialog.convert_to_pdf,
                        dialog.selected_image_mode,
                    )
                else:
                    continue
                target.resolve(strict=True).relative_to(case_root)
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

    def notify_unsupported_file_drop(self):
        self.statusBar().showMessage(
            "Este elemento no puede arrastrarse directamente. "
            "Descargalo primero y luego agregalo a FORO.",
            7000,
        )

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
            renamed = rename_document_entry(self.case, source, name)
            self.replace_path_everywhere(source, renamed)
            self.reload_case_files(renamed)
            self.reload_novedades()
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
        self.last_signed = moved(self.last_signed)
        self.case_directory = moved(self.case_directory)
        for index in range(self.compilation.count()):
            item = self.compilation.item(index)
            old_path = Path(item.data(PATH_ROLE))
            new_path = moved(old_path)
            if new_path != old_path:
                item.setData(PATH_ROLE, str(new_path))
                kind = item.data(TYPE_ROLE)
                item.setText(self.compilation_text(new_path, kind))
        self.update_writing_label()
        self.save_compilation_draft()

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
            menu.addSeparator()
            menu.addAction("Cortar", self.cut_selected_case_files).setShortcut(QKeySequence.StandardKey.Cut)
            menu.addAction("Copiar", self.copy_selected_case_files).setShortcut(QKeySequence.StandardKey.Copy)
            path = Path(item.data(PATH_ROLE))
            if path.is_dir():
                menu.addAction("Abrir en el Explorador", lambda: open_file(path))
            menu.addAction(
                "Agregar contenido a Presentación" if path.is_dir() else "Agregar a Presentación",
                self.add_selected_to_compilation,
            )
            if path.is_file() and path.suffix.lower() in {".doc", ".docx", ".odt", ".rtf"}:
                menu.addAction("Usar como escrito", lambda: self.set_current_writing(path))
            if path.is_file() and can_convert_to_pdf(path):
                menu.addAction("Convertir a PDF", lambda: self.convert_to_pdf(path))
            if path.is_file() and path.suffix.lower() == ".pdf":
                menu.addAction("Generar cédula…", lambda: self.generate_cedula_from_pdf(path))
            menu.addSeparator()
            menu.addAction("Enviar a la Papelera", self.remove_selected_case_files)
        clipboard_paths = self.clipboard_file_paths()
        if clipboard_paths:
            if item:
                menu.addSeparator()
            menu.addAction("Pegar", self.paste_case_files).setShortcut(QKeySequence.StandardKey.Paste)
        menu.addSeparator()
        menu.addAction("Nueva carpeta…", self.create_case_subfolder)
        menu.addAction("Agregar carpeta existente…", self.pick_case_folder)
        menu.addAction("Recuperar vínculos de documentos", self.recover_case_document_links).setEnabled(self._recovery_thread is None)
        menu.exec(self.case_files.mapToGlobal(point))

    def recover_case_document_links(self):
        if not self.case or self._recovery_thread is not None:
            return
        case = self.case
        worker = DocumentRecoveryWorker(case, self)
        self._recovery_thread = worker
        self.statusBar().showMessage(f"Buscando documentos movidos en {case.name}…")

        def completed(result):
            if self.case == case:
                for previous, current in result.recovered:
                    self.replace_path_everywhere(previous, current)
                self.reload_case_files()
                self.reload_novedades()
            QMessageBox.information(
                self, "Recuperación de vínculos",
                f"{case.name}: {len(result.recovered)} vínculos recuperados.\n"
                f"{result.unresolved} sin resolver (sin huella previa, sin coincidencia única o archivo cambiado).\n"
                "Los archivos originales no se modificaron.",
            )

        def cleanup():
            self._recovery_thread = None
            worker.deleteLater()

        worker.recovered.connect(completed)
        worker.failed.connect(lambda message: QMessageBox.warning(self, "No pudimos recuperar los vínculos", message))
        worker.finished.connect(cleanup)
        worker.start()

    def clipboard_file_paths(self) -> list[Path]:
        mime = QApplication.clipboard().mimeData()
        if not mime or not mime.hasUrls():
            return []
        return [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]

    def copy_selected_case_files(self):
        paths = self.selected_case_paths()
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        QApplication.clipboard().setMimeData(mime)
        self._cut_paths = []
        self.statusBar().showMessage(
            f"{len(paths)} elemento{'s' if len(paths) != 1 else ''} listo para copiar",
            3500,
        )

    def cut_selected_case_files(self):
        paths = self.selected_case_paths()
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        QApplication.clipboard().setMimeData(mime)
        self._cut_paths = [path.resolve() for path in paths]
        self.statusBar().showMessage(
            f"{len(paths)} elemento{'s' if len(paths) != 1 else ''} listo para mover",
            3500,
        )

    def paste_case_files(self):
        if not self.require_case():
            return
        sources = [path for path in self.clipboard_file_paths() if path.exists()]
        if not sources:
            return
        destination = self.case_directory or self.case.path
        moved_sources = {path.resolve() for path in self._cut_paths}
        results = []
        try:
            for source in sources:
                source_resolved = source.resolve()
                move = source_resolved in moved_sources
                if move and source.parent.resolve() == destination.resolve():
                    results.append(source)
                    continue
                if source.is_dir():
                    try:
                        destination.resolve().relative_to(source_resolved)
                    except ValueError:
                        pass
                    else:
                        raise ValueError("No se puede pegar una carpeta dentro de sí misma.")
                target = unique_path(destination / source.name)
                if move:
                    shutil.move(str(source), str(target))
                    if self.path_is_inside_case(source):
                        self.replace_path_everywhere(source, target)
                elif source.is_dir():
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)
                results.append(target)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "No pudimos pegar los elementos", str(error))
        finally:
            self._cut_paths = []
        if results:
            self.reload_case_files(results[-1])
            self.statusBar().showMessage(
                f"{len(results)} elemento{'s' if len(results) != 1 else ''} pegado",
                4000,
            )

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

    def generate_cedula_from_pdf(self, pdf: Path, *, context: dict | None = None):
        context = context or self.capture_sisfe_context()
        case = context["case"]
        if not case or self._cedula_thread is not None:
            return
        if not pdf.resolve().is_relative_to(case.path.resolve()):
            QMessageBox.warning(self, "Documento de otro expediente", "El decreto no pertenece al expediente de esta operación.")
            return
        models = [
            path for path in list_models(self.store.models_dir)
            if "CEDULA" in template_variable_name(path.stem)
        ]
        if not models:
            QMessageBox.information(
                self,
                "Modelos de cédula",
                "Agregá primero un modelo Word cuyo nombre incluya “Cédula”.",
            )
            return
        picker = ModelPickerDialog(
            models,
            self,
            selection_only=True,
            window_title="Elegir modelo de cédula",
            heading="Elegí un modelo de cédula",
            subtitle="Buscá por nombre y elegí el modelo que se completará con el movimiento.",
        )
        if picker.exec() != QDialog.DialogCode.Accepted or not picker.selected_model:
            return
        template = picker.selected_model
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
                profile_values = dict(context["profile_values"])
                profile_values["TEXTO_PROVEIDO"] = extracted.text
                writing = create_writing(
                    case,
                    f"Cédula - {pdf.stem}",
                    template,
                    context["professional"],
                    profile_values,
                )
            except Exception as error:
                QMessageBox.warning(self, "No pudimos generar la cédula", str(error))
            else:
                if self.case == case:
                    self.reload_case_files(writing)
                    self.set_current_writing(writing)
                external_id = str(context.get("movement_external_id") or "")
                if external_id:
                    try:
                        with StudyDatabase(study_database_path(case.path.parent)) as database:
                            expediente = database.find_expediente_by_folder(case.path)
                            movement = database.find_movement_by_external_id(
                                expediente.id, external_id,
                                source=str(context.get("movement_source") or "sisfe"),
                            ) if expediente else None
                            if expediente and movement:
                                document = database.add_document(
                                    expediente.id,
                                    writing.relative_to(case.path),
                                    source="generated",
                                    category="cedula",
                                )
                                database.link_document_to_movement(
                                    movement.id, document.id, role="cedula"
                                )
                    except (OSError, ValueError, sqlite3.Error):
                        pass
                open_file(writing)
                self.warn_unresolved_placeholders(writing)
                review = " Revisá los firmantes." if not extracted.signers_detected else ""
                self.statusBar().showMessage(f"Cédula creada desde {pdf.name}.{review}", 7000)
            thread.quit()

        worker.finished.connect(completed)
        worker.failed.connect(lambda message: (QMessageBox.warning(self, "No pudimos extraer el decreto", message), thread.quit()))
        thread.finished.connect(cleanup)
        thread.start()

    def convert_to_pdf(self, source: Path):
        """Crea un PDF junto al original, sin reemplazarlo ni moverlo."""
        if not self.case:
            return
        try:
            converted = to_pdf(source, source.parent / ".gestor-conversion")
            target = unique_path(source.with_suffix(".pdf"))
            shutil.move(str(converted), target)
        except Exception as error:
            QMessageBox.warning(self, "No pudimos convertir a PDF", str(error))
            return
        finally:
            shutil.rmtree(source.parent / ".gestor-conversion", ignore_errors=True)
        self.reload_case_files(target)
        self.statusBar().showMessage(f"Convertido a PDF: {target.name}", 4000)

    def create_case_subfolder(self):
        if not self.require_case():
            return
        parent = self.case_directory or self.case.path
        name, accepted = QInputDialog.getText(self, "Nueva carpeta", "Nombre de la carpeta:")
        if not accepted or not name.strip():
            return
        try:
            target = unique_path(parent / safe_name(name.strip()))
            target.mkdir(parents=True)
        except Exception as error:
            QMessageBox.warning(self, "No pudimos crear la carpeta", str(error))
            return
        self.reload_case_files(target)

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
        return (
            f"{path.name}    · PRESENTACIÓN PRINCIPAL"
            if kind == "writing"
            else path.name
        )

    def download_pending_pdfs(self):
        if not self.case or not self._sisfe_login_dialog or not self.sisfe_session.active:
            QMessageBox.information(self, "Sesión SISFE", "Iniciá la sesión SISFE primero.")
            return
        pending = []
        for index in range(self.novedades_list.count()):
            data = self.novedades_list.item(index).data(MOVEMENT_ROLE)
            if (
                isinstance(data, dict)
                and data.get("source") == "sisfe"
                and data.get("external_id")
                and data.get("document_available")
                and not data.get("local_documents")
            ):
                pending.append(data)
        if not pending:
            self.statusBar().showMessage("No hay PDFs pendientes de descarga", 4000)
            return
        cuij = str(read_case_metadata(self.case).get("CUIJ", "")).strip()
        case = self.case
        total = len(pending)

        def next_pending():
            if not pending:
                self.statusBar().showMessage(
                    f"Se preparó la descarga de {total} PDF(s) pendiente(s)", 6000
                )
                return
            movement = pending.pop(0)
            self.statusBar().showMessage(
                f"Preparando PDFs pendientes… {total - len(pending)} de {total}"
            )

            def detail_ready(detail, error):
                if not error and detail:
                    context = self.capture_sisfe_context()
                    context["case"] = case
                    detail = dict(detail, _gestor_context=context)
                    self.start_sisfe_download(str(detail.get("remote_case_id") or ""), detail)
                QTimer.singleShot(0, next_pending)

            self._sisfe_login_dialog.request_movement_detail(
                cuij, str(movement["external_id"]), detail_ready
            )

        next_pending()

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
        self.update_compilation_count()

    def clear_compilation(self):
        """Close the working preparation without touching any case file."""
        self.compilation.clear()
        self.current_writing = None
        self.output_name.clear()
        self.update_writing_label()
        self.update_output_preview()
        self.update_compilation_count()
        self.statusBar().showMessage(
            "Preparación limpia; los archivos originales se conservaron.", 5000
        )

    def open_compilation_history(self):
        if not self.case:
            return
        entries = load_compilation_history(self.case)
        if not entries:
            QMessageBox.information(
                self,
                "Historial de compilaciones",
                "Todavía no hay compilaciones anteriores para este expediente.",
            )
            return
        dialog = CompilationHistoryDialog(entries, self)
        if not dialog.exec() or not dialog.selected_entry:
            return
        entry = dialog.selected_entry
        self._loading_compilation = True
        try:
            self.compilation.clear()
            self.current_writing = next(
                (item.path for item in entry.items if item.kind == "writing"), None
            )
            for item in entry.items:
                self.add_compilation_path(item.path, item.kind)
            profile_index = self.limit_combo.findText(entry.profile)
            if profile_index >= 0:
                self.limit_combo.setCurrentIndex(profile_index)
        finally:
            self._loading_compilation = False
        self.update_compilation_count()
        self.update_writing_label()
        self.set_compilation_panel_visible(True)
        self.statusBar().showMessage("Armado anterior recuperado", 4500)

    @staticmethod
    def compilation_pdf_pages(path: Path) -> int:
        if path.suffix.casefold() not in PDF_EXTENSIONS:
            return 0
        try:
            with path.open("rb") as stream:
                if stream.read(5) != b"%PDF-":
                    return 0
                stream.seek(0)
                return len(PdfReader(stream).pages)
        except (OSError, PdfReadError, ValueError):
            return 0

    def update_compilation_count(self):
        count = self.compilation.count()
        label = f"{count} elemento" if count == 1 else f"{count} elementos"
        total_size = 0
        pdf_pages = 0
        for path in self.compilation_paths():
            try:
                total_size += path.stat().st_size
            except OSError:
                pass
            pdf_pages += self.compilation_pdf_pages(path)
        if count:
            details = []
            if pdf_pages:
                details.append(
                    f"{pdf_pages} página PDF" if pdf_pages == 1 else f"{pdf_pages} páginas PDF"
                )
            details.append(human_size(total_size))
            label = f"{label} · {' · '.join(details)}"
        self.compilation_count.setText(label)
        self.save_compilation_draft()

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

    def create_and_open_writing(
        self,
        title: str,
        template: Path | None = None,
        extra_values: dict[str, str] | None = None,
    ):
        try:
            profile_values = self.professional_template_values()
            profile_values.update(extra_values or {})
            path = create_writing(
                self.case,
                title,
                template,
                self.professional_combo.currentText(),
                profile_values,
            )
            self.set_current_writing(path)
            self.case_directory = path.parent
            self.reload_case_files(path)
            open_file(path)
            self.warn_unresolved_placeholders(path)
            self.statusBar().showMessage(f"Escrito creado: {path.name}", 5000)
        except Exception as error:
            QMessageBox.critical(self, "No pudimos crear el escrito", str(error))

    def warn_unresolved_placeholders(self, path: Path):
        unresolved = find_unresolved_placeholders(path)
        if unresolved:
            preview = ", ".join(unresolved[:3])
            remaining = len(unresolved) - 3
            suffix = f" y {remaining} más" if remaining > 0 else ""
            self.statusBar().showMessage(
                f"Atención: quedaron variables sin completar ({preview}{suffix}).",
                10000,
            )

    def professional_template_values(self) -> dict[str, str]:
        name = self.professional_combo.currentText().strip()
        profile = self.store.settings.professional_profiles.get(name, {})
        variable_names = {
            "name": "PROFESIONAL_NOMBRE_COMPLETO",
            "dni": "PROFESIONAL_DNI",
            "cuit": "PROFESIONAL_CUIT",
            "address": "PROFESIONAL_DOMICILIO",
            "city": "PROFESIONAL_LOCALIDAD",
            "province": "PROFESIONAL_PROVINCIA",
            "phone": "PROFESIONAL_TELEFONO",
            "tax_status": "PROFESIONAL_CONDICION_FISCAL",
            "email": "PROFESIONAL_CORREO",
            "license_santa_fe": "PROFESIONAL_MATRICULA_SANTA_FE",
            "license_buenos_aires": "PROFESIONAL_MATRICULA_BUENOS_AIRES",
            "license_federal": "PROFESIONAL_MATRICULA_FEDERAL",
            "bank": "PROFESIONAL_BANCO",
            "account_type": "PROFESIONAL_TIPO_CUENTA",
            "account_number": "PROFESIONAL_NUMERO_CUENTA",
            "cbu": "PROFESIONAL_CBU",
        }
        return {
            variable: str(profile.get(key, "")).strip()
            for key, variable in variable_names.items()
        }

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
            return None
        try:
            target = add_model(self.store.models_dir, Path(source))
            self.statusBar().showMessage(f"Modelo agregado: {target.name}", 4500)
            return target
        except Exception as error:
            QMessageBox.critical(self, "No pudimos agregar el modelo", str(error))
            return None

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
            "{{PROFESIONAL_DNI}}  {{PROFESIONAL_CUIT}}  {{PROFESIONAL_CBU}}  Datos del perfil\n"
            "{{PROFESIONAL_MATRICULA_SANTA_FE}}  y matrículas de otras jurisdicciones\n"
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
                "Agregá la documental y el escrito en el panel Presentación.",
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
            pattern=self.store.settings.naming_pattern,
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
        self.last_signed = None
        history_items = tuple(
            DraftItem(
                Path(self.compilation.item(index).data(PATH_ROLE)),
                str(self.compilation.item(index).data(TYPE_ROLE) or "document"),
            )
            for index in range(self.compilation.count())
        )
        try:
            record_compilation_history(
                self.case,
                history_items,
                result.output,
                self.limit_combo.currentText(),
            )
        except (OSError, ValueError) as error:
            self.statusBar().showMessage(f"No se pudo actualizar el historial: {error}", 7000)
        # Una compilación exitosa cierra esta preparación. Sólo se descartan
        # referencias internas; los originales y el PDF resultante permanecen
        # en el expediente y el último resultado sigue disponible para firmar.
        self.clear_compilation()
        self.update_last_output_label()
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

    def confirm_stop_long_task_and_exit(self) -> bool:
        message = QMessageBox(self)
        message.setWindowTitle("Hay un proceso en curso")
        message.setText("Hay un proceso en curso.")
        message.setInformativeText(
            "Podés volver a FORO o detener el proceso de forma segura antes de salir."
        )
        message.addButton("Volver", QMessageBox.ButtonRole.RejectRole)
        stop = message.addButton("Detener y salir", QMessageBox.ButtonRole.DestructiveRole)
        message.exec()
        return message.clickedButton() is stop

    def closeEvent(self, event):
        if self.long_task_active():
            if self.confirm_stop_long_task_and_exit():
                self._close_after_long_task = True
                self.stop_long_task()
            event.ignore()
            return
        if self._study_backup_thread is not None:
            self.statusBar().showMessage(
                "Esperá a que termine el respaldo o la restauración antes de cerrar.", 7000
            )
            event.ignore()
            return
        if self._recovery_thread is not None:
            self.statusBar().showMessage("Esperá a que termine la recuperación de vínculos antes de cerrar.", 5000)
            event.ignore()
            return
        if self._cedula_thread is not None or self._sisfe_download_active:
            self.statusBar().showMessage("Esperá a que termine la extracción o descarga antes de cerrar.", 7000)
            event.ignore()
            return
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
        self._layout_save_timer.stop()
        self._file_refresh_timer.stop()
        self._signer_output_timer.stop()
        watched = self._file_watcher.directories()
        if watched:
            self._file_watcher.removePaths(watched)
        self.save_layout_state()
        self.save_compilation_draft()
        if self._sisfe_case_dialog is not None:
            self._sisfe_case_dialog.close()
        if self._sisfe_login_dialog is not None:
            self._sisfe_login_dialog.close()
        self.sisfe_session.close()
        self.digital_signer.close()
        super().closeEvent(event)

    def current_pdf_for_signing(self) -> Path | None:
        for path in self.selected_case_paths():
            if path.is_file() and path.suffix.casefold() == ".pdf":
                return path
        if self.last_compiled and self.last_compiled.exists():
            return self.last_compiled
        return None

    def sign_current_pdf(self):
        pdf = self.current_pdf_for_signing()
        if pdf is None:
            QMessageBox.information(
                self,
                "Falta el PDF",
                "Seleccioná un PDF del expediente o compilá la presentación primero.",
            )
            return
        self.sign_with_token(pdf)

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
        anchor = getattr(self, "sign_options_button", self.sign_button)
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

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
                    visible_signature=confirmation.visible_signature,
                )
            finally:
                QApplication.restoreOverrideCursor()
            self.last_signed = signed
            self.case_directory = signed.parent
            self.reload_case_files(signed)
            size = signed.stat().st_size
            self.last_output.setText(f"{signed.name}\nFIRMADO · {human_size(size)}")
            self.save_compilation_draft()
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

    def configure_signer_output(self):
        current = self.store.settings.signer_output_dir
        directory = QFileDialog.getExistingDirectory(
            self,
            "Carpeta donde el firmador guarda los PDF",
            str(current or ""),
        )
        if directory:
            self.store.set_signer_output_dir(Path(directory))
            self.statusBar().showMessage("Carpeta de archivos firmados configurada", 4500)

    def send_to_signer(self, signer: Path, pdf: Path):
        try:
            focus_or_launch_signer(signer)
            output_dir = self.store.settings.signer_output_dir
            if output_dir and output_dir.is_dir():
                self._external_sign_source = pdf.resolve()
                self._external_sign_started_at = datetime.now().timestamp()
                self._external_sign_candidate = None
                self._signer_output_timer.start()
                self.statusBar().showMessage(
                    "Esperando el PDF firmado para incorporarlo al expediente…", 6000
                )
            self._signer_dialog = SignerDropDialog(pdf, self)
            self._signer_dialog.show()
            self._signer_dialog.raise_()
            self._signer_dialog.activateWindow()
        except Exception as error:
            QMessageBox.critical(self, "No pudimos abrir el firmador", str(error))

    def check_external_signer_output(self):
        source = self._external_sign_source
        output_dir = self.store.settings.signer_output_dir
        if not source or not output_dir or not self.case:
            self._signer_output_timer.stop()
            return
        if datetime.now().timestamp() - self._external_sign_started_at > 600:
            self._signer_output_timer.stop()
            self.statusBar().showMessage("No se detectó un nuevo PDF firmado", 5000)
            return
        candidate = find_recent_signer_output(
            source, output_dir, self._external_sign_started_at
        )
        if candidate is None:
            return
        try:
            size = candidate.stat().st_size
        except OSError:
            return
        marker = (candidate, size)
        if size <= 0 or marker != self._external_sign_candidate:
            self._external_sign_candidate = marker
            return
        try:
            candidate.resolve().relative_to(self.case.path.resolve())
            recovered = candidate
        except ValueError:
            try:
                recovered = import_file(self.case, candidate, candidate.name)
            except (OSError, ValueError):
                return
        self._signer_output_timer.stop()
        self._external_sign_source = None
        self.last_signed = recovered
        self.case_directory = recovered.parent
        self.reload_case_files(recovered)
        self.last_output.setText(
            f"{recovered.name}\nRECUPERADO DEL FIRMADOR · {human_size(recovered.stat().st_size)}"
        )
        self.save_compilation_draft()
        if self._signer_dialog:
            self._signer_dialog.close()
        QMessageBox.information(
            self,
            "PDF recuperado",
            f"Se incorporó {recovered.name} al expediente.",
        )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FORO")
    app.setApplicationDisplayName("FORO")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    app.setWindowIcon(foro_application_icon(64))
    window = MainWindow()
    window.show()
    return app.exec()
