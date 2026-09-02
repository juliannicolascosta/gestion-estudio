"""Coordinación inyectable entre una sesión manual y la importación local SISFE."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .models import Case
from .sisfe_import import SisfeCaseSnapshot, SisfeImportResult, SisfeImportService
from .sisfe_session import ManualSisfeSession


class SisfeSessionRequired(RuntimeError):
    pass


class SisfeSnapshotProviderMissing(RuntimeError):
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


class SisfeSyncCoordinator(SisfePortalService):
    """Compatibility adapter for injected, non-UI snapshot providers."""

    def __init__(
        self,
        session: ManualSisfeSession,
        snapshot_provider: Callable[[Case], SisfeCaseSnapshot] | None = None,
        importer: SisfeImportService | None = None,
    ):
        super().__init__(session, importer)
        self.snapshot_provider = snapshot_provider

    def synchronize(self, case: Case, document_directory: Path) -> SisfeImportResult:
        self.require_active_session()
        if not self.snapshot_provider:
            raise SisfeSnapshotProviderMissing(
                "Esta compilación aún no tiene un transporte SISFE configurado."
            )
        return self.import_snapshot(case, self.snapshot_provider(case), document_directory)
