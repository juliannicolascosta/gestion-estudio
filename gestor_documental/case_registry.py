"""Puente transitorio entre las carpetas del gestor y el modelo relacional."""

from __future__ import annotations

from .domain import Expediente, Movimiento
from .models import Case
from .study_database import StudyDatabase, study_database_path
from .services import read_case_metadata, save_case_metadata


def register_case_as_expediente(case: Case) -> Expediente:
    """Register a selected case folder without changing its files or metadata."""
    with StudyDatabase(study_database_path(case.path.parent)) as database:
        return database.import_case(case)


def recent_case_novedades(case: Case, limit: int | None = None) -> list[Movimiento]:
    """Read the expediente movements; by default the inbox shows them all."""
    with StudyDatabase(study_database_path(case.path.parent)) as database:
        expediente = database.find_expediente_by_folder(case.path)
        return database.list_recent_movements(expediente.id, limit) if expediente else []


def unread_case_novedades(case: Case) -> tuple[str, ...]:
    """Return persisted unread movement ids, migrating the former counter once."""
    metadata = read_case_metadata(case)
    raw_legacy = metadata.get("Novedades SISFE sin ver", "")
    try:
        legacy_count = max(0, int(raw_legacy or 0))
    except (TypeError, ValueError):
        legacy_count = 0
    with StudyDatabase(study_database_path(case.path.parent)) as database:
        expediente = database.find_expediente_by_folder(case.path)
        if not expediente:
            return ()
        if legacy_count:
            database.migrate_legacy_unread_count(expediente.id, legacy_count)
        unread = database.unread_movement_ids(expediente.id)
    if raw_legacy:
        metadata.pop("Novedades SISFE sin ver", None)
        save_case_metadata(case, metadata)
    return unread


def mark_case_novedades_read(
    case: Case,
    movement_ids: tuple[str, ...] | None = None,
) -> int:
    """Mark the persisted unread state without modifying SISFE movements."""
    with StudyDatabase(study_database_path(case.path.parent)) as database:
        expediente = database.find_expediente_by_folder(case.path)
        changed = database.mark_movements_read(expediente.id, movement_ids) if expediente else 0
    metadata = read_case_metadata(case)
    if metadata.pop("Novedades SISFE sin ver", None) is not None:
        save_case_metadata(case, metadata)
    return changed
