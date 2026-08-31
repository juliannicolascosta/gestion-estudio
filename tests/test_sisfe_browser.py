import unittest

from gestor_documental.sisfe_browser import browser_sync_script, snapshot_from_browser_payload


class SisfeBrowserTests(unittest.TestCase):
    def test_script_queries_inside_browser_context_without_exposing_cookies(self):
        script = browser_sync_script("21-12345678-9")
        self.assertIn("credentials: 'include'", script)
        self.assertIn("findNovedadesById", script)
        self.assertNotIn("document.cookie", script)
        self.assertNotIn("Authorization", script)

    def test_browser_payload_maps_to_import_snapshot(self):
        snapshot = snapshot_from_browser_payload(
            {
                "ok": True,
                "cuij": "21123456789",
                "title": "Caso de prueba",
                "tribunal": "Juzgado 1",
                "movements": [
                    {"internal_id": "9", "title": "Cédula", "occurred_at": "2026-08-31T12:00:00"}
                ],
            }
        )
        self.assertEqual(snapshot.title, "Caso de prueba")
        self.assertEqual(snapshot.movements[0].internal_id, "9")
        self.assertEqual(snapshot.movements[0].occurred_at.year, 2026)

    def test_browser_error_is_not_imported(self):
        with self.assertRaises(RuntimeError):
            snapshot_from_browser_payload({"ok": False, "error": "SISFE devolvió 403"})
