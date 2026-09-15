"""Coordinación inyectable entre una sesión manual y la importación local SISFE."""

from __future__ import annotations

from pathlib import Path

from .models import Case
from .sisfe_import import SisfeCaseSnapshot, SisfeImportResult, SisfeImportService
from .sisfe_session import ManualSisfeSession


class SisfeSessionRequired(RuntimeError):
    pass


class SisfePortalService:
    """Single application boundary for authenticated SISFE operations.

    Qt obtains snapshots inside the official browser context.  This service
    deliberately owns their import so the UI never reaches into an importer
    and alternate HTTP transports cannot be selected accidentally.
    """

    def __init__(
        self,
        session: ManualSisfeSession,
        importer: SisfeImportService | None = None,
    ):
        self.session = session
        self.importer = importer or SisfeImportService()

    def require_active_session(self):
        if not self.session.active:
            raise SisfeSessionRequired("Iniciá y confirmá la sesión manual de SISFE primero.")

    def import_snapshot(
        self,
        case: Case,
        snapshot: SisfeCaseSnapshot,
        document_directory: Path,
    ) -> SisfeImportResult:
        self.require_active_session()
        return self.importer.import_snapshot(case, snapshot, document_directory)
