"""Qt surfaces for the manual SISFE session and official downloads.

The browser remains the owner of authentication and CAPTCHA.  This module only
drives controls rendered by SISFE and registers downloads after Qt receives
them; it never exports session tokens or replays document endpoints.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import (
    QWebEngineDownloadRequest,
    QWebEnginePage,
    QWebEngineProfile,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from ..models import Case
from ..services import normalize_filename, unique_path
from ..sisfe_browser import (
    browser_click_official_additional_attachment_script,
    browser_click_official_movement_attachment_script,
    browser_movement_detail_script,
    browser_prepare_official_movement_page_script,
    browser_sync_script,
    browser_validation_script,
    snapshot_from_browser_payload,
)
from ..sisfe_session import ManualSisfeSession
from ..sisfe_downloads import SisfeDownloadRegistry


SISFE_ORIGIN = "https://sisfe.justiciasantafe.gov.ar"


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
        self._sync_timer: QTimer | None = None
        self.ready_for_sync = False
        self.browser = QWebEngineView()
        self.browser.setPage(QWebEnginePage(self.profile, self.browser))
        layout.addWidget(self.browser, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.use_session_button = buttons.addButton(
            "Validar sesión", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.use_session_button.clicked.connect(self.accept_manual_session)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.session.mark_portal_opened()
        self._validate_after_load = False
        self.browser.loadFinished.connect(self.portal_loaded)
        self.browser.setUrl(QUrl(f"{SISFE_ORIGIN}/"))

    def portal_loaded(self, ok: bool):
        path = self.browser.url().path().rstrip("/")
        self.ready_for_sync = bool(ok and path == "/buscar-expediente")
        if self._validate_after_load:
            self._validate_after_load = False
            if self.ready_for_sync:
                self.validate_loaded_session()
            else:
                self.validation_status.setText(
                    "No pudimos abrir el área de expedientes de SISFE. Reintentá."
                )
                self.use_session_button.setEnabled(True)

    def accept_manual_session(self):
        self.ready_for_sync = False
        self._validate_after_load = True
        self.use_session_button.setEnabled(False)
        self.validation_status.setText("Abriendo el área de expedientes y validando la sesión…")
        self.browser.setUrl(QUrl(f"{SISFE_ORIGIN}/buscar-expediente"))

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
                self.validation_status.setText(
                    "SISFE demoró en validar. Esperá y presioná Validar sesión otra vez."
                )
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
                f"SISFE todavía no autorizó la sesión ({detail}). "
                "Esperá o completá el CAPTCHA y reintentá."
            )
            self.use_session_button.setEnabled(True)

        timer.timeout.connect(poll)
        timer.start()

    def request_snapshot(self, cuij: str, completed):
        """Query SISFE from its own browser context and return a plain snapshot."""
        if not self.ready_for_sync:
            completed(None, RuntimeError("SISFE todavía está preparando el área de expedientes."))
            return
        if self._sync_timer and self._sync_timer.isActive():
            completed(None, RuntimeError("SISFE todavía está procesando otra consulta."))
            return
        self.browser.page().runJavaScript(browser_sync_script(cuij))
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
            expression = (
                f"window.{result_name} === null ? null : JSON.stringify(window.{result_name})"
            )
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
            except (TypeError, ValueError):
                completed(None, RuntimeError("SISFE devolvió una respuesta inválida."))
                return
            if not isinstance(payload, dict):
                completed(None, RuntimeError("SISFE devolvió una respuesta inválida."))
                return
            if not payload.get("ok"):
                completed(
                    None,
                    RuntimeError(
                        str(payload.get("error") or "SISFE no pudo completar la consulta.")
                    ),
                )
                return
            completed(payload, None)

        timer.timeout.connect(poll)
        timer.start()


class SisfeCaseBrowserDialog(QDialog):
    """Official SISFE case view with optional control-driven downloading."""

    documentSaved = pyqtSignal(str, bool)
    automationFinished = pyqtSignal(bool, str)

    _ACTION_TIMEOUT_MS = 25000
    _DOWNLOAD_TIMEOUT_MS = 60000

    def __init__(
        self,
        profile: QWebEngineProfile,
        remote_case_id: str,
        case: Case,
        parent=None,
        *,
        movement_detail: dict | None = None,
        auto_download: bool = False,
    ):
        super().__init__(parent)
        self.profile = profile
        self.case = case
        self.remote_case_id = str(remote_case_id)
        self.movement_detail = dict(movement_detail or {})
        self._downloads: dict[int, tuple[Path, str, str]] = {}
        self._automatic = bool(auto_download and self.movement_detail)
        self._automation_stage = "seed" if self._automatic else "manual"
        self._automation_elapsed = 0
        self._script_running = False
        self._additional_index = 0
        self._current_role = ""
        self._finish_emitted = False
        self._download_registry = SisfeDownloadRegistry()

        self.setWindowTitle("Expediente en SISFE")
        self.setMinimumSize(1050, 760)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Vista oficial de SISFE. El Gestor usa los mismos clips del portal y guarda los "
            "archivos en Documentos SISFE. Si el portal no responde, podés usar esos clips manualmente."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        initial_status = (
            "Preparando la descarga oficial…" if self._automatic else "Sin descargas en curso"
        )
        self.download_status = QLabel(initial_status)
        self.download_status.setObjectName("muted")
        self.download_status.setWordWrap(True)
        layout.addWidget(self.download_status)
        self.browser = QWebEngineView()
        self.browser.setPage(QWebEnginePage(profile, self.browser))
        self.browser.loadFinished.connect(self._page_loaded)
        layout.addWidget(self.browser, 1)
        self.profile.downloadRequested.connect(self.save_official_download)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._automation_timer = QTimer(self)
        self._automation_timer.setInterval(500)
        self._automation_timer.timeout.connect(self._automation_tick)
        if self._automatic:
            self._automation_timer.start()
        self.browser.setUrl(QUrl(self._detail_url))

    @property
    def _detail_url(self) -> str:
        return f"{SISFE_ORIGIN}/detalle-expediente/{self.remote_case_id}"

    def _page_loaded(self, ok: bool):
        if not self._automatic:
            return
        if not ok:
            self._automation_failed("SISFE no pudo abrir la pantalla del expediente.")
            return
        if self._automation_stage == "seed":
            script = browser_prepare_official_movement_page_script(
                self.remote_case_id,
                int(self.movement_detail.get("page_number") or 1),
            )

            def prepared(_result):
                if not self._automatic:
                    return
                self._set_automation_stage("detail", "Buscando el movimiento en SISFE…")
                self.browser.reload()

            self.browser.page().runJavaScript(script, prepared)
            return
        if self._automation_stage == "detail":
            if not self.browser.url().path().startswith("/detalle-expediente/"):
                self._automation_failed(
                    "SISFE salió del expediente. Revisá la sesión y usá los controles oficiales."
                )
                return
            if self.movement_detail.get("has_primary_document"):
                self._set_automation_stage("click_primary", "Solicitando el documento principal…")
            elif self.movement_detail.get("has_additional_documents"):
                self._set_automation_stage("open_additional", "Abriendo los adjuntos oficiales…")
            else:
                self._automation_done("Este movimiento no tiene documentos descargables.")

    def _set_automation_stage(self, stage: str, status: str = ""):
        self._automation_stage = stage
        self._automation_elapsed = 0
        self._script_running = False
        if status:
            self.download_status.setText(status)

    def _automation_tick(self):
        if not self._automatic:
            self._automation_timer.stop()
            return
        self._automation_elapsed += self._automation_timer.interval()
        stage = self._automation_stage
        if stage in {"seed", "detail"}:
            if self._automation_elapsed >= self._ACTION_TIMEOUT_MS:
                self._automation_failed("SISFE demoró demasiado en mostrar el expediente.")
            return
        if stage == "click_primary":
            self._click_movement_attachment("primary")
        elif stage == "open_additional":
            self._click_movement_attachment("additional")
        elif stage == "click_additional":
            self._click_additional_attachment()
        elif stage in {"wait_primary", "wait_additional"}:
            if self._automation_elapsed >= self._DOWNLOAD_TIMEOUT_MS:
                self._automation_failed(
                    "SISFE no inició la descarga. Podés reintentar con el clip visible en el portal."
                )

    def _click_movement_attachment(self, role: str):
        if self._script_running:
            return
        if self._automation_elapsed >= self._ACTION_TIMEOUT_MS:
            self._automation_failed(
                "No encontramos el control oficial del documento. Podés usar el clip manualmente."
            )
            return
        self._current_role = role
        script = browser_click_official_movement_attachment_script(
            str(self.movement_detail.get("title") or ""),
            int(self.movement_detail.get("row_number") or 0),
            role,
        )
        self._run_action_script(
            script,
            lambda result, requested_role=role: self._movement_attachment_clicked(
                requested_role,
                result,
            ),
        )

    def _movement_attachment_clicked(self, requested_role: str, result):
        if not isinstance(result, dict) or not result.get("ok"):
            return
        expected_stage = "click_primary" if requested_role == "primary" else "open_additional"
        if self._automation_stage != expected_stage:
            return
        if requested_role == "primary":
            self._set_automation_stage("wait_primary", "SISFE está generando el documento principal…")
        else:
            self._set_automation_stage("click_additional", "Buscando adjuntos adicionales…")

    def _click_additional_attachment(self):
        if self._script_running:
            return
        if self._automation_elapsed >= self._ACTION_TIMEOUT_MS:
            self._automation_failed(
                "No encontramos la lista oficial de adjuntos. Podés usar los clips manualmente."
            )
            return
        self._current_role = "additional"
        script = browser_click_official_additional_attachment_script(self._additional_index)
        self._run_action_script(script, self._additional_attachment_clicked)

    def _additional_attachment_clicked(self, result):
        if not isinstance(result, dict) or not result.get("ok"):
            return
        if self._automation_stage != "click_additional":
            return
        if result.get("complete"):
            self._automation_done("Descarga de documentos SISFE completada.")
            return
        self._set_automation_stage(
            "wait_additional",
            f"SISFE está generando el adjunto {self._additional_index + 1}…",
        )

    def _run_action_script(self, script: str, completed):
        self._script_running = True

        def finish(result):
            self._script_running = False
            if self._automatic:
                completed(result)

        self.browser.page().runJavaScript(script, finish)

    def _automation_done(self, message: str):
        self._automatic = False
        self._automation_stage = "done"
        self._automation_timer.stop()
        self.download_status.setText(message)
        self._emit_automation_finished(True, message)

    def _automation_failed(self, message: str):
        self._automatic = False
        self._automation_stage = "manual"
        self._automation_timer.stop()
        self.download_status.setText(f"{message} La vista oficial quedó abierta.")
        self._emit_automation_finished(False, message)

    def _emit_automation_finished(self, success: bool, message: str):
        if self._finish_emitted:
            return
        self._finish_emitted = True
        self.automationFinished.emit(success, message)

    def save_official_download(self, download: QWebEngineDownloadRequest):
        directory = self.case.path / "Documentos SISFE"
        directory.mkdir(parents=True, exist_ok=True)
        filename = self._download_filename(download.suggestedFileName())
        target = unique_path(directory / filename)
        movement_id = str(self.movement_detail.get("movement_id") or "")
        role = self._current_role if movement_id else ""
        if self._automatic and role == "primary":
            self._set_automation_stage("wait_primary", "SISFE está generando el documento principal…")
        elif self._automatic and role == "additional" and self._automation_stage == "click_additional":
            self._set_automation_stage(
                "wait_additional",
                f"SISFE está generando el adjunto {self._additional_index + 1}…",
            )
        self._downloads[id(download)] = (target, movement_id, role)
        self.download_status.setText(f"Descargando {target.name}…")
        download.setDownloadDirectory(str(target.parent))
        download.setDownloadFileName(target.name)
        download.stateChanged.connect(
            lambda state, request=download: self.finish_official_download(request, state)
        )
        download.accept()

    def _download_filename(self, suggested: str) -> str:
        suggested = suggested or "Documento SISFE.pdf"
        if suggested.casefold() not in {"documento.pdf", "download.pdf"}:
            return normalize_filename(suggested, ".pdf")
        title = str(self.movement_detail.get("title") or "Documento SISFE")
        occurred_at = str(self.movement_detail.get("occurred_at") or "")[:10]
        prefix = f"{occurred_at} - " if occurred_at else ""
        suffix = " - Adjunto" if self._current_role == "additional" else ""
        return normalize_filename(f"{prefix}{title}{suffix}.pdf", ".pdf")

    def finish_official_download(self, download: QWebEngineDownloadRequest, state):
        terminal_states = {
            QWebEngineDownloadRequest.DownloadState.DownloadCompleted,
            QWebEngineDownloadRequest.DownloadState.DownloadCancelled,
            QWebEngineDownloadRequest.DownloadState.DownloadInterrupted,
        }
        if state not in terminal_states:
            return
        context = self._downloads.pop(id(download), None)
        if state == QWebEngineDownloadRequest.DownloadState.DownloadCancelled:
            self._automation_failed("La descarga fue cancelada.")
            return
        if state == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
            detail = download.interruptReasonString() or "SISFE interrumpió la descarga"
            self._automation_failed("No se pudo completar la descarga.")
            if self.isVisible():
                QMessageBox.warning(self, "Descarga SISFE interrumpida", detail)
            return
        if not context:
            self._automation_failed("No pudimos identificar el archivo descargado.")
            return
        target, movement_id, role = context
        if not target.is_file():
            self._automation_failed("SISFE no generó el archivo esperado.")
            return
        try:
            registered = self._download_registry.register(
                self.case,
                target,
                movement_external_id=movement_id,
                role=role,
            )
            if registered.duplicate:
                self.download_status.setText("El documento ya estaba guardado; no se creó otra copia.")
            else:
                self.download_status.setText(f"Guardado: {registered.path.name}")
            self.documentSaved.emit(str(registered.path), registered.duplicate)
            self._continue_after_download(role)
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
            self._automation_failed("El archivo se descargó, pero no pudimos registrarlo.")
            if self.isVisible():
                QMessageBox.warning(
                    self,
                    "Documento descargado",
                    f"El archivo se descargó, pero no pudimos registrarlo: {error}",
                )

    def _continue_after_download(self, role: str):
        if not self._automatic:
            return
        if role == "primary" and self.movement_detail.get("has_additional_documents"):
            self._set_automation_stage("open_additional", "Abriendo los adjuntos oficiales…")
        elif role == "additional":
            self._additional_index += 1
            self._set_automation_stage("click_additional", "Buscando el siguiente adjunto…")
        else:
            self._automation_done("Descarga del documento SISFE completada.")

    def closeEvent(self, event):
        self._automation_timer.stop()
        try:
            self.profile.downloadRequested.disconnect(self.save_official_download)
        except TypeError:
            pass
        super().closeEvent(event)
