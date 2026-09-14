"""Vista operativa derivada de datos existentes, sin duplicar persistencia."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from .domain import Movimiento
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


def _movement_priority(due_at: datetime | None, uncertain: bool, now: datetime) -> int:
    if due_at is not None and due_at < now:
        return 0
    if due_at is not None and due_at <= now + timedelta(days=7):
        return 1
    if uncertain:
        return 2
    return 3


def build_case_activity(
    movements: Iterable[Movimiento],
    pending_documents: Iterable[str],
    received_documents: Iterable[str],
    *,
    now: datetime | None = None,
) -> tuple[ActivityItem, ...]:
    """Build a deterministic inbox from movements and the existing checklist."""
    reference = now or datetime.now()
    received = {" ".join(value.split()).casefold() for value in received_documents if value.strip()}
    items: list[ActivityItem] = []

    for value in pending_documents:
        title = " ".join(value.split()).strip()
        if not title or title.casefold() in received:
            continue
        items.append(
            ActivityItem(
                kind="Documentación",
                title=title,
                detail="Solicitada al cliente · pendiente de recibir",
                target="pending",
                priority=2,
            )
        )

    for movement in movements:
        for interpretation in interpret_movement(movement.title):
            uncertain = bool(interpretation.warning)
            due = interpretation.extracted_at
            detail_parts = [movement.source.upper()]
            if due:
                detail_parts.append(due.strftime("%d/%m/%Y" + (" · %H:%M" if due.hour or due.minute else "")))
            if uncertain:
                detail_parts.append("Requiere revisión profesional")
            items.append(
                ActivityItem(
                    kind=interpretation.kind,
                    title=movement.title,
                    detail=" · ".join(detail_parts),
                    target="portal",
                    priority=_movement_priority(due, uncertain, reference),
                    due_at=due,
                    external_id=movement.external_id,
                    source=movement.source,
                    uncertain=uncertain,
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
