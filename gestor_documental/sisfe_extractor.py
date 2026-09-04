"""Stable adapter to the Extractor SISFE engine bundled with the Gestor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExtractedCedulaText:
    text: str
    pages: int
    signers_detected: bool
    catalog_message: str


def extract_cedula_text(pdf_path: Path) -> ExtractedCedulaText:
    source = Path(pdf_path)
    if source.suffix.lower() != ".pdf" or not source.is_file():
        raise ValueError("Elegí un PDF descargado para generar la cédula.")
    try:
        from .extractor_core import ExtractorOptions, SisfeExtractorService
    except ImportError as error:
        raise RuntimeError("No pudimos iniciar el motor Extractor-SISFE.") from error
    catalog = Path(__file__).resolve().parent / "extractor_core" / "data" / "courts_catalog.json"
    result = SisfeExtractorService(
        options=ExtractorOptions(catalog_path=catalog),
    ).extract(str(source))
    return ExtractedCedulaText(
        text=result.text,
        pages=result.pages,
        signers_detected=result.signers_detected,
        catalog_message=result.catalog_message,
    )
