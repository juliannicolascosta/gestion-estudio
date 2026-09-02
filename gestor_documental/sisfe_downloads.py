"""Persistence boundary for files downloaded by the official SISFE browser."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .models import Case
from .services import move_to_recycle_bin
from .study_database import StudyDatabase, study_database_path


@dataclass(frozen=True)
class RegisteredSisfeDownload:
    path: Path
    duplicate: bool
    linked_to_movement: bool


class SisfeDownloadRegistry:
    """Register one completed official download and its procedural origin."""

    def register(
        self,
        case: Case,
        target: Path,
        *,
        movement_external_id: str = "",
        role: str = "",
    ) -> RegisteredSisfeDownload:
        target = Path(target)
        case_root = case.path.resolve()
        resolved_target = target.resolve()
        if resolved_target != case_root and case_root not in resolved_target.parents:
            raise ValueError("El documento SISFE debe pertenecer al expediente seleccionado.")
        if not target.is_file():
            raise FileNotFoundError("No encontramos el documento descargado por SISFE.")

        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        duplicate = False
        linked = False
        saved_path = target
        with StudyDatabase(study_database_path(case.path.parent)) as database:
            expediente = database.import_case(case)
            movement = None
            if movement_external_id.strip():
                movement = database.find_movement_by_external_id(
                    expediente.id,
                    movement_external_id,
                    source="sisfe",
                )
                if movement is None:
                    raise RuntimeError(
                        "La novedad SISFE no está registrada en este expediente; sincronizá y reintentá."
                    )
            existing = database.find_document_by_sha256(expediente.id, digest)
            existing_path = case.path / existing.relative_path if existing else None
            duplicate = bool(existing_path and existing_path.is_file())
            if duplicate:
                document = existing
                saved_path = existing_path
            else:
                document = database.add_document(
                    expediente.id,
                    target.relative_to(case.path),
                    sha256=digest,
                    source="sisfe",
                )
            if movement:
                database.link_document_to_movement(movement.id, document.id, role=role)
                linked = True

        if duplicate:
            move_to_recycle_bin([target])
        return RegisteredSisfeDownload(saved_path, duplicate, linked)
