import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QFrame, QPushButton, QVBoxLayout

from gestor_documental.services import create_case, read_case_metadata, save_case_metadata
from gestor_documental.ui.pending_documents import (
    CardHelpers,
    PendingDocumentsTab,
    pending_document_due_dates,
)


def _card():
    frame = QFrame()
    return frame, QVBoxLayout(frame)


HELPERS = CardHelpers(
    make_card=_card,
    section_heading=lambda *args: QVBoxLayout(),
    decorate_button=lambda button, *args: button,
    icon_button=lambda icon, tooltip, slot, **kw: QPushButton(tooltip),
)


class PendingDocumentsTabTests(unittest.TestCase):
    """La pestaña se prueba sin construir MainWindow: ese es el objetivo de extraerla."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _window(self, case):
        return SimpleNamespace(
            case=case,
            require_case=lambda: case is not None,
            statusBar=lambda: MagicMock(),
            pending_tab_index=-1,
            reload_activity=MagicMock(),
            sync_case_projection=MagicMock(),
            update_more_metadata_count=MagicMock(),
            update_case_badge=MagicMock(),
            _loaded_metadata={},
        )

    def test_full_cycle_without_main_window(self):
        with tempfile.TemporaryDirectory() as directory:
            case = create_case(Path(directory) / "Estudio", "Caso")
            save_case_metadata(case, {"Documentación pendiente": "DNI"})
            window = self._window(case)
            tab = PendingDocumentsTab(window, HELPERS)
            card = tab.build()  # retener: Qt destruye los hijos de una tarjeta suelta
            tab.reload()
            self.assertEqual(tab.list.count(), 1)
            self.assertEqual(tab.count_label.text(), "1 pendientes · 0 recibidos")

            with patch("gestor_documental.ui.pending_documents.QInputDialog.getText",
                       return_value=("Recibo de sueldo", True)):
                tab.add()
            self.assertEqual(tab.list.currentItem().text(), "Recibo de sueldo")

            tab.list.setCurrentRow(1)
            with patch("gestor_documental.ui.pending_documents.QInputDialog.getText",
                       return_value=("20/10/2026", True)):
                tab.set_due_date()
            metadata = read_case_metadata(case)
            self.assertIn("recibo de sueldo", pending_document_due_dates(metadata))

            tab.list.setCurrentRow(0)
            tab.complete()
            metadata = read_case_metadata(case)
            self.assertEqual(metadata["Documentación recibida"], "DNI")
            window.update_case_badge.assert_called()
            window.reload_activity.assert_called()

    def test_without_case_the_list_explains_what_to_do(self):
        tab = PendingDocumentsTab(self._window(None), HELPERS)
        card = tab.build()  # retener: Qt destruye los hijos de una tarjeta suelta
        tab.reload()
        self.assertEqual(tab.list.count(), 0)
        self.assertIn("Elegí un caso", tab.list.empty_state()[0])
        self.assertFalse(tab.received_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
