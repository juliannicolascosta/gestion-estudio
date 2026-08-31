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


class SisfeSyncCoordinator:
    """Run only with an active manual session and an explicit data provider."""

    def __init__(
        self,
        session: ManualSisfeSession,
        snapshot_provider: Callable[[Case], SisfeCaseSnapshot] | None = None,
        importer: SisfeImportService | None = None,
    ):
        self.session = session
        self.snapshot_provider = snapshot_provider
        self.importer = importer or SisfeImportService()

    def synchronize(self, case: Case, document_directory: Path) -> SisfeImportResult:
        if not self.session.active:
            raise SisfeSessionRequired("Iniciá y confirmá la sesión manual de SISFE primero.")
        if not self.snapshot_provider:
            raise SisfeSnapshotProviderMissing(
                "Esta compilación aún no tiene un transporte SISFE configurado."
            )
        return self.importer.import_snapshot(case, self.snapshot_provider(case), document_directory)
