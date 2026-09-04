from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cffi  # noqa: F401
import cryptography  # noqa: F401
import docx  # noqa: F401
import lxml  # noqa: F401
import PIL  # noqa: F401
import pymupdf  # noqa: F401
import pypdf  # noqa: F401
from PyQt6.QtWidgets import QApplication

from gestor_documental.app import MainWindow
from gestor_documental.services import SettingsStore
from gestor_documental.extractor_core import SisfeExtractorService
from gestor_documental.sisfe_extractor import extract_cedula_text


app = QApplication.instance() or QApplication([])
with tempfile.TemporaryDirectory(prefix="gestor-instalador-") as directory:
    window = MainWindow(SettingsStore(Path(directory) / "appdata"))
    app.processEvents()
    assert window.windowTitle() == "Gestor de documental"
    assert window.limit_combo.count() == 4
    assert SisfeExtractorService.__module__.startswith("gestor_documental.extractor_core")
    catalog = PROJECT_ROOT / "gestor_documental" / "extractor_core" / "data" / "courts_catalog.json"
    assert catalog.is_file()
    sample = Path(directory) / "decreto-prueba.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "ROSARIO, 4 de septiembre de 2026")
    page.insert_text((72, 100), "Tengase presente. Notifiquese.")
    document.save(sample)
    document.close()
    extracted = extract_cedula_text(sample)
    assert "Notifiquese" in extracted.text
    assert extracted.pages == 1
    window.close()

print("PORTABLE_OK")
