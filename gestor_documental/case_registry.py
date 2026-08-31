"""Puente transitorio entre las carpetas del gestor y el modelo relacional."""

from __future__ import annotations

from .domain import Expediente, Movimiento
from .models import Case
from .study_database import StudyDatabase, study_database_path


def register_case_as_expediente(case: Case) -> Expediente:
    """Register a selected case folder without changing its files or metadata."""
    with StudyDatabase(study_database_path(case.path.parent)) as database:
        return database.import_case(case)


def recent_case_novedades(case: Case, limit: int = 20) -> list[Movimiento]:
    """Read the selected expediente's latest movements for its integrated inbox."""
    with StudyDatabase(study_database_path(case.path.parent)) as database:
        expediente = database.find_expediente_by_folder(case.path)
        return database.list_recent_movements(expediente.id, limit) if expediente else []
