from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MovementInterpretation:
    kind: str
    source_text: str
    extracted_at: datetime | None = None
    warning: str = ""


def _plain(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def _explicit_date(text: str) -> datetime | None:
    match = re.search(
        r"\b([0-3]?\d)[/.-]([01]?\d)[/.-](\d{2}|\d{4})(?:\s+(?:a\s+las\s+)?([0-2]?\d)(?::|\.)([0-5]\d))?\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    day, month, year, hour, minute = match.groups()
    numeric_year = int(year)
    if numeric_year < 100:
        numeric_year += 2000
    try:
        return datetime(
            numeric_year,
            int(month),
            int(day),
            int(hour or 0),
            int(minute or 0),
        )
    except ValueError:
        return None


def interpret_movement(text: str) -> tuple[MovementInterpretation, ...]:
    source = " ".join(str(text).split()).strip()
    if not source:
        return ()
    normalized = _plain(source)
    extracted = _explicit_date(source)
    detected: list[MovementInterpretation] = []
    rules = (
        ("Audiencia", r"\baudiencia\b"),
        ("Traslado", r"\btraslado\b|\bcorrase\s+traslado\b"),
        ("Vencimiento", r"\bvencimiento\b|\bvence\b|\bfecha\s+limite\b|\bhasta\s+el\b"),
    )
    for kind, pattern in rules:
        if not re.search(pattern, normalized):
            continue
        warning = "" if extracted else "No se encontró una fecha explícita; requiere revisión profesional."
        detected.append(MovementInterpretation(kind, source, extracted, warning))
    return tuple(detected)
