import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from gestor_documental.ui.settings_dialogs import (
    ActivitySettingsDialog,
    ProfessionalProfileDialog,
    SisfeAccessDialog,
)


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
