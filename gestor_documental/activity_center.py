"""Vista operativa derivada de datos existentes, sin duplicar persistencia."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
import unicodedata
from typing import Iterable, Mapping

from .domain import Movimiento, Tarea
from .movement_interpretation import interpret_movement


@dataclass(frozen=True)
class ActivityItem:
    kind: str
    title: str
    detail: str
    target: str
    priority: int
    due_at: datetime | None = None
    external_id: str = ""
    source: str = ""
    uncertain: bool = False
    task_key: str = ""
    confirmed: bool = False
    file_path: str = ""
    task_id: str = ""
    completed: bool = False
    urgency: str = ""


def activity_task_key(source: str, external_id: str, kind: str, title: str) -> str:
    identity = external_id.strip() or " ".join(title.casefold().split())
    return f"movimiento:{source.strip().casefold()}:{identity}:{kind.casefold()}"


def _movement_priority(due_at: datetime | None, uncertain: bool, now: datetime) -> int:
    if due_at is not None and due_at.date() < now.date():
        return 0
    if due_at is not None and due_at.date() <= (now + timedelta(days=7)).date():
        return 1
    if uncertain:
        return 2
    return 3


def due_urgency(due_at: datetime | None, now: datetime) -> str:
    if due_at is None:
        return ""
    if due_at.date() < now.date():
        return "Vencida"
    if due_at.date() == now.date():
        return "Hoy"
    if due_at.date() <= (now + timedelta(days=7)).date():
        return "Próxima"
    return "Programada"


def _search_tokens(value: str) -> tuple[str, ...]:
    plain = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    ignored = {"de", "del", "la", "el", "los", "las", "documento", "documentacion"}
    return tuple(token for token in re.findall(r"[a-z0-9]+", plain) if token not in ignored)


def matching_document(pending: str, available_paths: Iterable[str]) -> str:
    expected = _search_tokens(pending)
    if not expected:
        return ""
    for path in sorted(available_paths, key=str.casefold):
        filename_tokens = set(_search_tokens(path.rsplit("/", 1)[-1].rsplit(".", 1)[0]))
        if all(token in filename_tokens for token in expected):
            return path
    return ""


def build_case_activity(
    movements: Iterable[Movimiento],
    pending_documents: Iterable[str],
    received_documents: Iterable[str],
    task_status_by_key: Mapping[str, str] | None = None,
    available_document_paths: Iterable[str] = (),
    tasks: Iterable[Tarea] = (),
    show_completed: bool = False,
    pending_due_dates: Mapping[str, datetime] | None = None,
    *,
    now: datetime | None = None,
) -> tuple[ActivityItem, ...]:
    """Build a deterministic inbox from movements and the existing checklist."""
    reference = now or datetime.now()
    received = {" ".join(value.split()).casefold() for value in received_documents if value.strip()}
    task_statuses = dict(task_status_by_key or {})
    pending_dates = {key.casefold(): value for key, value in (pending_due_dates or {}).items()}
    items: list[ActivityItem] = []

    for task in tasks:
        if task.suggested_by != "manual" or task.status not in {"confirmada", "completada"}:
            continue
        is_completed = task.status == "completada"
        if is_completed and not show_completed:
            continue
        urgency = due_urgency(task.due_at, reference)
        items.append(
            ActivityItem(
                kind="Tarea",
                title=task.title,
                detail=("COMPLETADA · " if is_completed else (f"{urgency.upper()} · " if urgency else "")) + (
                    f"Fecha objetivo · {task.due_at.strftime('%d/%m/%Y %H:%M')}"
                    if task.due_at else "Sin fecha objetivo"
                ),
                target="history" if is_completed else "task",
                priority=4 if is_completed else _movement_priority(task.due_at, task.due_at is None, reference),
                due_at=task.due_at,
                confirmed=True,
                task_id=task.id,
                completed=is_completed,
                urgency=urgency,
            )
        )

    for value in pending_documents:
        title = " ".join(value.split()).strip()
        if not title or title.casefold() in received:
            continue
        matched_path = matching_document(title, available_document_paths)
        pending_due = pending_dates.get(title.casefold())
        pending_urgency = due_urgency(pending_due, reference)
        items.append(
            ActivityItem(
                kind="Posible recepción" if matched_path else "Documentación",
                title=title,
                detail=(f"{pending_urgency.upper()} · " if pending_urgency else "") + (
                    f"Revisar archivo compatible · {matched_path}"
                    if matched_path
                    else (
                        f"Fecha objetivo · {pending_due.strftime('%d/%m/%Y')}"
                        if pending_due else "Solicitada al cliente · pendiente de recibir"
                    )
                ),
                target="files" if matched_path else "pending",
                priority=(
                    min(1, _movement_priority(pending_due, False, reference))
                    if matched_path else _movement_priority(pending_due, pending_due is None, reference)
                ),
                file_path=matched_path,
                due_at=pending_due,
                urgency=pending_urgency,
            )
        )

    for movement in movements:
        for interpretation in interpret_movement(movement.title):
            uncertain = bool(interpretation.warning)
            due = interpretation.extracted_at
            urgency = due_urgency(due, reference)
            task_key = activity_task_key(
                movement.source, movement.external_id, interpretation.kind, movement.title
            )
            task_status = task_statuses.get(task_key, "")
            if task_status == "completada" and not show_completed:
                continue
            detail_parts = [movement.source.upper()]
            if due:
                detail_parts.append(urgency.upper())
                detail_parts.append(due.strftime("%d/%m/%Y" + (" · %H:%M" if due.hour or due.minute else "")))
            if uncertain:
                detail_parts.append("Requiere revisión profesional")
            if task_status == "confirmada":
                detail_parts.append("Confirmada como tarea")
            elif task_status == "completada":
                detail_parts.append("Tarea completada")
            items.append(
                ActivityItem(
                    kind=interpretation.kind,
                    title=movement.title,
                    detail=" · ".join(detail_parts),
                    target="portal",
                    priority=4 if task_status == "completada" else _movement_priority(due, uncertain, reference),
                    due_at=due,
                    external_id=movement.external_id,
                    source=movement.source,
                    uncertain=uncertain,
                    task_key=task_key,
                    confirmed=task_status == "confirmada",
                    completed=task_status == "completada",
                    urgency=urgency,
                )
            )

    far_future = datetime.max
    items.sort(
        key=lambda item: (
            item.priority,
            item.due_at or far_future,
            item.kind.casefold(),
            item.title.casefold(),
        )
    )
    return tuple(items)
