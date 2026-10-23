from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from gestor_documental.icons import (
    _PHOSPHOR_ASSETS,
    _PHOSPHOR_DUOTONE_DIR,
    badged_icon,
    movement_icon,
    ui_icon,
)


class PhosphorIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_every_foro_icon_has_a_local_phosphor_duotone_asset(self):
        for foro_name, asset_name in _PHOSPHOR_ASSETS.items():
            with self.subTest(icon=foro_name):
                asset = _PHOSPHOR_DUOTONE_DIR / f"{asset_name}-duotone.svg"
                self.assertTrue(asset.is_file(), asset)
                svg = asset.read_text(encoding="utf-8")
                self.assertIn('viewBox="0 0 256 256"', svg)
                self.assertIn('fill="currentColor"', svg)

    def test_every_icon_renders_with_requested_color_and_size(self):
        for foro_name in _PHOSPHOR_ASSETS:
            with self.subTest(icon=foro_name):
                icon = ui_icon(foro_name, "#7B55A6", 19)
                pixmap = icon.pixmap(19, 19)
                self.assertFalse(icon.isNull())
                self.assertFalse(pixmap.isNull())
                self.assertTrue(pixmap.toImage().hasAlphaChannel())
                self.assertTrue(any(
                    pixmap.toImage().pixelColor(x, y).alpha() > 0
                    for x in range(pixmap.width())
                    for y in range(pixmap.height())
                ))

    def test_duotone_secondary_surface_is_not_rendered_as_gray_background(self):
        image = ui_icon("plus", "#2B7564", 24).pixmap(24, 24).toImage()
        self.assertEqual(image.pixelColor(5, 5).alpha(), 0)

    def test_badges_and_movement_icons_keep_qt_states(self):
        for icon in (
            badged_icon("folder", "#2B7564", 7),
            movement_icon("judicial", "#C9493C", True),
        ):
            self.assertFalse(icon.isNull())
            self.assertFalse(icon.pixmap(24, 24, QIcon.Mode.Normal).isNull())
            self.assertFalse(icon.pixmap(24, 24, QIcon.Mode.Disabled).isNull())
            self.assertFalse(icon.pixmap(24, 24, QIcon.Mode.Selected).isNull())


if __name__ == "__main__":
    unittest.main()
