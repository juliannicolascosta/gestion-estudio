from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import Case
from .services import read_case_metadata
from .study_database import StudyDatabase, study_database_path


DEFAULT_ACTIVITY_SETTINGS: dict[str, object] = {
    "yellow_days": 45,
    "red_days": 90,
    "green_color": "#2B7A55",
    "yellow_color": "#D0952D",
    "red_color": "#C9493C",
    "archived_color": "#7B8581",
    "show_archived": True,
    "show_recent": True,
}


@dataclass(frozen=True)
class CaseActivity:
    status: str
    latest_at: datetime
    inactive_days: int
    archived: bool = False


def normalized_activity_settings(raw: dict[str, object] | None) -> dict[str, object]:
    settings = dict(DEFAULT_ACTIVITY_SETTINGS)
    if isinstance(raw, dict):
        settings.update({key: value for key, value in raw.items() if key in settings})
    yellow = max(1, int(settings["yellow_days"]))
    red = max(yellow + 1, int(settings["red_days"]))
    settings["yellow_days"] = yellow
    settings["red_days"] = red
    return settings


def is_case_archived(case: Case) -> bool:
    return read_case_metadata(case).get("Archivado", "").strip().casefold() in {
        "1", "si", "sí", "true", "yes",
    }


def latest_case_activity(
    case: Case,
    movement_at: datetime | None = None,
    *,
    query_database: bool = True,
) -> datetime:
    timestamps: list[datetime] = []
    if case.path.is_dir():
        for path in case.path.rglob("*"):
            if path.is_file():
                try:
                    timestamps.append(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))
                except OSError:
                    continue
        if not timestamps:
            try:
                timestamps.append(datetime.fromtimestamp(case.path.stat().st_mtime, timezone.utc))
            except OSError:
                pass

    if movement_at:
        if movement_at.tzinfo is None:
            movement_at = movement_at.replace(tzinfo=timezone.utc)
        timestamps.append(movement_at.astimezone(timezone.utc))
    elif query_database and (database_path := study_database_path(case.path.parent)).is_file():
        try:
            with StudyDatabase(database_path) as database:
                expediente = database.find_expediente_by_folder(case.path)
                if expediente:
                    movements = database.list_recent_movements(expediente.id, 1)
                    if movements and movements[0].occurred_at:
                        movement_at = movements[0].occurred_at
                        if movement_at.tzinfo is None:
                            movement_at = movement_at.replace(tzinfo=timezone.utc)
                        timestamps.append(movement_at.astimezone(timezone.utc))
        except (OSError, ValueError):
            pass
    return max(timestamps, default=datetime.now(timezone.utc))


def case_activity(
    case: Case,
    settings: dict[str, object] | None = None,
    *,
    now: datetime | None = None,
    movement_at: datetime | None = None,
    query_database: bool = True,
) -> CaseActivity:
    policy = normalized_activity_settings(settings)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    latest = latest_case_activity(case, movement_at, query_database=query_database)
    inactive_days = max(0, (current.astimezone(timezone.utc) - latest).days)
    archived = is_case_archived(case)
    if archived:
        status = "archived"
    elif inactive_days >= int(policy["red_days"]):
        status = "red"
    elif inactive_days >= int(policy["yellow_days"]):
        status = "yellow"
    else:
        status = "green"
    return CaseActivity(status, latest, inactive_days, archived)


def case_activities(
    cases: list[Case],
    settings: dict[str, object] | None = None,
    *,
    now: datetime | None = None,
) -> dict[Path, CaseActivity]:
    """Calculate a directory with one shared database connection."""
    movement_dates: dict[Path, datetime] = {}
    if cases:
        database_path = study_database_path(cases[0].path.parent)
        if database_path.is_file():
            try:
                with StudyDatabase(database_path) as database:
                    for case in cases:
                        expediente = database.find_expediente_by_folder(case.path)
                        if not expediente:
                            continue
                        movements = database.list_recent_movements(expediente.id, 1)
                        if movements and movements[0].occurred_at:
                            movement_dates[case.path] = movements[0].occurred_at
            except (OSError, ValueError):
                pass
    return {
        case.path: case_activity(
            case,
            settings,
            now=now,
            movement_at=movement_dates.get(case.path),
            query_database=False,
        )
        for case in cases
    }


def set_case_archived(case: Case, archived: bool) -> None:
    metadata = read_case_metadata(case)
    if archived:
        metadata["Archivado"] = "Sí"
    else:
        metadata.pop("Archivado", None)
    from .services import save_case_metadata

    save_case_metadata(case, metadata)
