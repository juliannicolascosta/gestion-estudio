"""Puente transitorio entre las carpetas del gestor y el modelo relacional."""

from __future__ import annotations

from .domain import Expediente
from .models import Case
from .study_database import StudyDatabase, study_database_path


def register_case_as_expediente(case: Case) -> Expediente:
    """Register a selected case folder without changing its files or metadata."""
    with StudyDatabase(study_database_path(case.path.parent)) as database:
        return database.import_case(case)
