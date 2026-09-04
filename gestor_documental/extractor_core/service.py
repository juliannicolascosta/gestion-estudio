from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from .court_matcher import choose_best_match
from .pdf_manager import PDFManager
from .signer import (
    extract_treatment,
    format_person_name_preserving_order,
    format_signers,
    name_match_score,
    parse_signers,
)


@dataclass(frozen=True)
class ExtractorOptions:
    catalog_path: Path | None = None


@dataclass(frozen=True)
class ExtractedText:
    text: str
    source_path: str
    source_name: str
    pages: int
    signers_detected: bool
    catalog_used: bool
    catalog_message: str = ""


class PublicCourtCatalog:
    """Catálogo judicial público en JSON; nunca usa una base SQLite privada."""

    def __init__(self, path: Path | str | None) -> None:
        self.path = Path(path) if path else None
        self._courts: list[dict[str, Any]] | None = None
        self._message = ""

    @property
    def message(self) -> str:
        self._ensure_loaded()
        return self._message

    def enrich_signers(
        self,
        *,
        raw_text: str,
        court_line: str,
        locality_hint: str,
        signers: str,
    ) -> tuple[str, bool]:
        self._ensure_loaded()
        courts = self._courts or []
        parsed = parse_signers(signers)
        if not courts or not parsed:
            return signers.strip(), False

        match = choose_best_match(
            courts,
            text=raw_text,
            court_line=court_line,
            locality_hint=locality_hint,
            signers=signers,
        )
        court = match.court
        if court is None:
            return signers.strip(), False

        authorities = list(court.get("authorities") or [])
        changed = False
        for signer in parsed:
            ranked = sorted(
                (
                    (
                        name_match_score(
                            signer.name,
                            str(authority.get("name") or authority.get("display_name") or ""),
                        ),
                        authority,
                    )
                    for authority in authorities
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            if not ranked or ranked[0][0] < 0.62:
                continue
            if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.12:
                continue

            authority = ranked[0][1]
            canonical = str(authority.get("name") or authority.get("display_name") or "").strip()
            if canonical:
                _treatment, canonical_name = extract_treatment(canonical)
                signer.name = format_person_name_preserving_order(canonical_name or canonical)
                changed = True

            if signer.role in {"FIRMANTE", "CARGO A VERIFICAR"}:
                role = str(authority.get("original_role") or authority.get("role") or signer.role).strip()
                if role:
                    signer.role = role
                    changed = True
            if not signer.treatment:
                treatment = str(authority.get("treatment") or "").strip()
                if treatment:
                    signer.treatment = treatment
                    changed = True

        return format_signers(parsed), changed

    def _ensure_loaded(self) -> None:
        if self._courts is not None:
            return
        if self.path is None or not self.path.is_file():
            self._courts = []
            self._message = "Catálogo público no disponible."
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            self._courts = []
            self._message = f"No se pudo leer el catálogo: {error}"
            return

        if isinstance(payload, list):
            dependencies = payload
            metadata: dict[str, Any] = {}
        else:
            dependencies = payload.get("dependencies") if isinstance(payload, dict) else None
            metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        if not isinstance(dependencies, list):
            self._courts = []
            self._message = "El catálogo no contiene dependencias válidas."
            return
        self._courts = [value for value in dependencies if isinstance(value, dict)]
        version = str(metadata.get("version") or "").strip()
        suffix = f" · versión {version}" if version else ""
        self._message = f"Catálogo disponible{suffix}."


class SisfeExtractorService:
    """Motor independiente que conserva las reglas probadas en Cedulador."""

    def __init__(
        self,
        *,
        pdf_manager: PDFManager | None = None,
        options: ExtractorOptions | None = None,
    ) -> None:
        self.pdf_manager = pdf_manager or PDFManager()
        self.options = options or ExtractorOptions()

    def extract(self, file_path: str) -> ExtractedText:
        info = self.pdf_manager.load_source(file_path)
        metadata = info["metadata"]
        signers = str(metadata.firmantes or "").strip()
        catalog = PublicCourtCatalog(self.options.catalog_path)
        signers, catalog_used = catalog.enrich_signers(
            raw_text=str(info.get("raw_text") or ""),
            court_line=str(metadata.tribunal_detectado or ""),
            locality_hint=str(metadata.localidad_detectada or ""),
            signers=signers,
        )

        output = format_cedula_paragraph(
            text=str(metadata.texto or ""),
            signers=signers,
            locality=str(metadata.localidad_detectada or ""),
            date_value=str(metadata.fecha or ""),
        )
        return ExtractedText(
            text=output,
            source_path=str(info.get("path") or file_path),
            source_name=str(info.get("name") or Path(file_path).name),
            pages=int(info.get("pages") or 0),
            signers_detected=bool(signers),
            catalog_used=catalog_used,
            catalog_message=catalog.message,
        )


def format_cedula_paragraph(
    *,
    text: str,
    signers: str,
    locality: str = "",
    date_value: str = "",
) -> str:
    body = _single_line(text)
    body = _remove_outer_quotes(body)
    body = _normalize_leading_place_date(body, locality=locality, date_value=date_value)
    body = _strip_one_terminal_period(body)
    if not body:
        body = "[TEXTO NO DETECTADO]"

    normalized_signers = _normalize_signers(signers)
    if not normalized_signers:
        normalized_signers = "[FIRMANTES NO DETECTADOS]."
    return f"“{body}”. FDO.: {normalized_signers}"


def _normalize_signers(value: str) -> str:
    parsed = parse_signers(value)
    if parsed:
        return format_signers(parsed)
    fallback = re.sub(r"^\s*FDO\.?\s*:\s*", "", value or "", flags=re.IGNORECASE)
    fallback = _single_line(fallback).upper()
    if fallback and not fallback.endswith("."):
        fallback += "."
    return fallback


def _normalize_leading_place_date(text: str, *, locality: str, date_value: str) -> str:
    if not text or not locality or not date_value:
        return text
    try:
        parsed = datetime.strptime(date_value, "%d/%m/%Y")
    except ValueError:
        return text
    months = (
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    )
    normalized = f"{_sentence_case_locality(locality)}, {parsed.day} de {months[parsed.month - 1]} de {parsed.year}"
    date_prefix = re.compile(
        r"^\s*[A-Za-zÁÉÍÓÚÜÑáéíóúüñ .]{2,80}\s*,?\s*"
        r"\d{1,2}\s+de\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+\s+de\s+\d{4}\.?",
        flags=re.IGNORECASE,
    )
    match = date_prefix.match(text)
    if not match:
        return text
    remainder = text[match.end():].lstrip()
    return f"{normalized}. {remainder}" if remainder else normalized


def _sentence_case_locality(value: str) -> str:
    particles = {"de", "del", "la", "las", "los", "y"}
    words: list[str] = []
    for index, raw in enumerate(_single_line(value).split()):
        lower = raw.lower()
        words.append(lower if index > 0 and lower in particles else lower[:1].upper() + lower[1:])
    return " ".join(words)


def _remove_outer_quotes(value: str) -> str:
    text = value.strip()
    for opening, closing in (("\"", "\""), ("“", "”"), ("«", "»")):
        if text.startswith(opening) and text.endswith(closing):
            return text[len(opening):-len(closing)].strip()
    return text


def _strip_one_terminal_period(value: str) -> str:
    return re.sub(r"\.(?=\s*$)", "", value, count=1).rstrip()


def _single_line(value: str) -> str:
    value = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", value or "")
    return re.sub(r"\s+", " ", value).strip()
