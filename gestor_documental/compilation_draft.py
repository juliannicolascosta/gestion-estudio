"""Portable, case-local persistence for an unfinished PDF compilation.

Only paths relative to the case directory are stored.  This keeps the draft
usable when the Study is opened from another computer at a different absolute
path and prevents a malformed draft from reaching files outside the case.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import DEFAULT_PROFILE, PRESENTATION_PROFILES, Case


DRAFT_FILE_NAME = ".gestor-compilacion.json"
DRAFT_VERSION = 1
VALID_ITEM_KINDS = {"document", "writing"}


@dataclass(frozen=True)
class DraftItem:
    path: Path
    kind: str = "document"


@dataclass(frozen=True)
class CompilationDraft:
    items: tuple[DraftItem, ...] = ()
    current_writing: Path | None = None
    last_compiled: Path | None = None
    last_signed: Path | None = None
    profile: str = DEFAULT_PROFILE


def compilation_draft_path(case: Case) -> Path:
    return case.path / DRAFT_FILE_NAME


def _relative_path(case: Case, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        relative = Path(path).resolve().relative_to(case.path.resolve())
    except (OSError, ValueError):
        return None
    if not relative.parts:
        return None
    return relative.as_posix()


def _case_path(case: Case, value: object, *, must_exist: bool = True) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    candidate = case.path.joinpath(*relative.parts)
    try:
        candidate.resolve().relative_to(case.path.resolve())
    except (OSError, ValueError):
        return None
    if must_exist and not candidate.is_file():
        return None
    return candidate


def load_compilation_draft(case: Case) -> CompilationDraft:
    try:
        payload = json.loads(compilation_draft_path(case).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, TypeError, ValueError):
        return CompilationDraft()
    if not isinstance(payload, dict) or payload.get("version") != DRAFT_VERSION:
        return CompilationDraft()

    items: list[DraftItem] = []
    seen: set[Path] = set()
    for row in payload.get("items", []):
        if not isinstance(row, dict):
            continue
        path = _case_path(case, row.get("path"))
        kind = str(row.get("kind", "document"))
        if path is None or path in seen:
            continue
        seen.add(path)
        items.append(DraftItem(path, kind if kind in VALID_ITEM_KINDS else "document"))

    profile = str(payload.get("profile", DEFAULT_PROFILE))
    if profile not in PRESENTATION_PROFILES:
        profile = DEFAULT_PROFILE
    current_writing = _case_path(case, payload.get("current_writing"))
    if current_writing is None:
        current_writing = next((item.path for item in items if item.kind == "writing"), None)

    return CompilationDraft(
        items=tuple(items),
        current_writing=current_writing,
        last_compiled=_case_path(case, payload.get("last_compiled")),
        last_signed=_case_path(case, payload.get("last_signed")),
        profile=profile,
    )


def save_compilation_draft(
    case: Case,
    items: Iterable[DraftItem],
    *,
    current_writing: Path | None = None,
    last_compiled: Path | None = None,
    last_signed: Path | None = None,
    profile: str = DEFAULT_PROFILE,
) -> Path:
    serialized_items = []
    seen: set[str] = set()
    for item in items:
        relative = _relative_path(case, item.path)
        if relative is None or relative in seen:
            continue
        seen.add(relative)
        kind = item.kind if item.kind in VALID_ITEM_KINDS else "document"
        serialized_items.append({"path": relative, "kind": kind})

    payload = {
        "version": DRAFT_VERSION,
        "items": serialized_items,
        "current_writing": _relative_path(case, current_writing),
        "last_compiled": _relative_path(case, last_compiled),
        "last_signed": _relative_path(case, last_signed),
        "profile": profile if profile in PRESENTATION_PROFILES else DEFAULT_PROFILE,
    }
    target = compilation_draft_path(case)
    temporary = target.with_name(f"{target.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, target)
    return target
