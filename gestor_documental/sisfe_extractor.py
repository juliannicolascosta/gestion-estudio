"""Small adapter around the proven Extractor-SISFE core library."""

from __future__ import annotations

import sys
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
    extractor_source = Path(__file__).resolve().parent.parent / "vendor" / "Extractor-SISFE" / "src"
    if not extractor_source.is_dir():
        raise RuntimeError("No encontramos el motor Extractor-SISFE en esta instalación.")
    if str(extractor_source) not in sys.path:
        sys.path.insert(0, str(extractor_source))
    try:
        from extractor_core import SisfeExtractorService
    except ImportError as error:
        raise RuntimeError("No pudimos iniciar el motor Extractor-SISFE.") from error
    result = SisfeExtractorService().extract(str(source))
    return ExtractedCedulaText(
        text=result.text,
        pages=result.pages,
        signers_detected=result.signers_detected,
        catalog_message=result.catalog_message,
    )
