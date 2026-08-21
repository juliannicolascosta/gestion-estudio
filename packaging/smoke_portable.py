from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


app = QApplication.instance() or QApplication([])
with tempfile.TemporaryDirectory(prefix="gestor-instalador-") as directory:
    window = MainWindow(SettingsStore(Path(directory) / "appdata"))
    app.processEvents()
    assert window.windowTitle() == "Gestor de documental"
    assert window.limit_combo.count() == 4
    window.close()

print("PORTABLE_OK")
