"""Ingreso local de resultados SISFE sin sesión, red ni automatización web.

El módulo recibe datos ya obtenidos por un cliente SISFE futuro o por
``SisfeExtractorService``. No conoce credenciales, CAPTCHA ni endpoints.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .models import Case
from .services import normalize_filename, unique_path
from .study_database import StudyDatabase, study_database_path


class SisfeImportMismatch(ValueError):
    """Raised when incoming SISFE data belongs to another expediente."""


@dataclass(frozen=True)
class SisfeDocumentPayload:
    name: str
    content: bytes
    sha256: str = ""


@dataclass(frozen=True)
class SisfeMovementPayload:
    title: str
    internal_id: str = ""
    occurred_at: datetime | None = None
    documents: tuple[SisfeDocumentPayload, ...] = ()


@dataclass(frozen=True)
class SisfeCaseSnapshot:
    """Normalized, non-sensitive SISFE data ready to be stored locally."""

    cuij: str
    title: str = ""
    tribunal: str = ""
    movements: tuple[SisfeMovementPayload, ...] = ()
    download_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SisfeExtractionMetadata:
    """Subset of the extractor result useful to a later SISFE client."""

    cuij: str = ""
    title: str = ""
    tribunal: str = ""
    date: str = ""
    signers: str = ""
    notifiable_text: str = ""


@dataclass(frozen=True)
class SisfeImportResult:
    expediente_id: str
    movements_registered: int
    documents_registered: int
    documents_skipped: int


def metadata_from_extractor_result(result: object) -> SisfeExtractionMetadata:
    """Adapt the public-shaped result of ``SisfeExtractorService`` by attributes.

    Keeping this structural avoids a hard dependency on the separate extractor
    project while allowing that library to be supplied by the desktop runtime.
    """
    return SisfeExtractionMetadata(
        cuij=str(getattr(result, "cuij", "") or ""),
        title=str(getattr(result, "caratula", "") or ""),
        tribunal=str(getattr(result, "court_line", "") or ""),
        date=str(getattr(result, "date", "") or ""),
        signers=str(getattr(result, "signers", "") or ""),
        notifiable_text=str(getattr(result, "notifiable_text", "") or ""),
    )


class SisfeImportService:
    """Persist a manually obtained SISFE snapshot into an existing case."""

    source = "sisfe"

    def import_snapshot(
        self,
        case: Case,
        snapshot: SisfeCaseSnapshot,
        document_directory: Path,
    ) -> SisfeImportResult:
        """Import only into an explicit folder within the selected case.

        Documents are deduplicated by their SHA-256. Movements use the SISFE
        internal ID when available and a stable logical identity otherwise.
        """
        case_root = case.path.resolve()
        directory = Path(document_directory).resolve()
        if directory != case_root and case_root not in directory.parents:
            raise ValueError("La carpeta de documentos SISFE debe pertenecer al caso seleccionado.")

        with StudyDatabase(study_database_path(case.path.parent)) as database:
            expediente = database.import_case(case)
            self._ensure_matching_case(expediente.case_number, snapshot.cuij)
            expediente = database.fill_sisfe_context(expediente.id, snapshot.cuij, snapshot.tribunal)
            self._validate_document_hashes(snapshot)
            movements_registered = 0
            documents_registered = 0
            documents_skipped = 0
            for movement in snapshot.movements:
                before = database.connection.total_changes
                database.add_movement(
                    expediente.id,
                    movement.title,
                    occurred_at=movement.occurred_at,
                    source=self.source,
                    external_id=movement.internal_id,
                    logical_key=self._movement_key(movement),
                )
                if database.connection.total_changes > before:
                    movements_registered += 1
                for document in movement.documents:
                    digest = hashlib.sha256(document.content).hexdigest()
                    expected = document.sha256.strip().lower()
                    if expected and expected != digest:
                        raise ValueError("El hash del documento SISFE no coincide con su contenido.")
                    if database.find_document_by_sha256(expediente.id, digest):
                        documents_skipped += 1
                        continue
                    directory.mkdir(parents=True, exist_ok=True)
                    filename = normalize_filename(document.name, ".pdf")
                    target = unique_path(directory / filename)
                    target.write_bytes(document.content)
                    database.add_document(
                        expediente.id,
                        target.relative_to(case.path),
                        sha256=digest,
                        source=self.source,
                    )
                    documents_registered += 1
            return SisfeImportResult(
                expediente_id=expediente.id,
                movements_registered=movements_registered,
                documents_registered=documents_registered,
                documents_skipped=documents_skipped,
            )

    @staticmethod
    def _validate_document_hashes(snapshot: SisfeCaseSnapshot):
        for movement in snapshot.movements:
            for document in movement.documents:
                expected = document.sha256.strip().lower()
                actual = hashlib.sha256(document.content).hexdigest()
                if expected and expected != actual:
                    raise ValueError("El hash del documento SISFE no coincide con su contenido.")

    @staticmethod
    def _ensure_matching_case(case_number: str, incoming_cuij: str):
        known = "".join(char for char in case_number if char.isdigit())
        received = "".join(char for char in incoming_cuij if char.isdigit())
        if known and received and known != received:
            raise SisfeImportMismatch("El CUIJ recibido no corresponde al caso seleccionado.")

    @staticmethod
    def _movement_key(movement: SisfeMovementPayload) -> str:
        stamp = movement.occurred_at.isoformat() if movement.occurred_at else ""
        text = unicodedata.normalize("NFKD", movement.title.casefold())
        normalized = "".join(char for char in text if not unicodedata.combining(char))
        return f"{stamp}|{' '.join(normalized.split())}"
