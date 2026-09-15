import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton

from gestor_documental.ui.settings_dialogs import (
    ActivitySettingsDialog,
    ApplicationSettingsDialog,
    NamingPatternDialog,
    ProfessionalProfileDialog,
    SisfeAccessDialog,
)
from gestor_documental.ui.case_import import ExternalCaseImportDialog


class SettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_activity_settings_normalize_thresholds_and_invalid_colors(self):
        dialog = ActivitySettingsDialog({"yellow_days": 30, "red_days": 15})
        dialog.yellow_days.setValue(45)
        dialog.red_days.setValue(30)
        dialog.color_edits["green_color"].setText("no-es-un-color")

        values = dialog.values()

        self.assertEqual(values["yellow_days"], 45)
        self.assertEqual(values["red_days"], 46)
        self.assertTrue(values["green_color"].startswith("#"))
        dialog.close()

    def test_application_settings_groups_actions_and_refreshes_summaries(self):
        dialog = ApplicationSettingsDialog(
            {
                "professional": "Ana Pérez",
                "profile_fields": 8,
                "models_count": 3,
                "models_path": "C:/Modelos",
                "signer": "XolidoSign.exe",
                "naming_pattern": "{fecha}_{titulo}",
            }
        )
        requested = []
        dialog.actionRequested.connect(requested.append)

        self.assertEqual(
            [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())],
            ["Profesionales", "Modelos", "Firmador"],
        )
        self.assertIn("Ana Pérez", dialog.professional_summary.text())
        self.assertIn("3", dialog.models_summary.text())
        self.assertIn("{fecha}_{titulo}", dialog.models_summary.text())
        self.assertIn("XolidoSign.exe", dialog.signer_summary.text())
        professional_buttons = dialog.tabs.widget(0).findChildren(QPushButton)
        professional_buttons[0].click()
        self.assertEqual(requested, ["add_professional"])
        dialog.close()

    def test_naming_pattern_dialog_shows_live_preview(self):
        dialog = NamingPatternDialog("{fecha}-{actor}")
        self.assertEqual(dialog.value(), "{fecha}-{actor}")
        self.assertIn("2026-09-15-PEREZ.pdf", dialog.preview.text())
        dialog.close()

    def test_external_case_preview_normalizes_name_and_shows_destination(self):
        dialog = ExternalCaseImportDialog(
            Path("C:/Origen/Caso externo"),
            Path("C:/Estudio"),
            12,
            2048,
        )
        dialog.name_edit.setText('Pérez: c/ "Empresa"')

        self.assertEqual(dialog.case_name, "Pérez- c- -Empresa")
        self.assertIn("Pérez- c- -Empresa", dialog.destination_label.text())
        dialog.close()

    def test_professional_profile_trims_values_and_omits_empty_fields(self):
        dialog = ProfessionalProfileDialog({"name": "  Ana Pérez  ", "dni": ""})

        self.assertEqual(dialog.values(), {"name": "Ana Pérez"})
        dialog.close()

    def test_sisfe_profile_preserves_password_and_trims_user(self):
        dialog = SisfeAccessDialog({"user": "  matricula  ", "password": " clave "})

        self.assertEqual(
            dialog.values(),
            {"user": "matricula", "password": " clave "},
        )
        dialog.close()


if __name__ == "__main__":
    unittest.main()
