import unittest
from base64 import b64encode

from gestor_documental.sisfe_browser import (
    browser_movement_detail_script,
    browser_movement_documents_script,
    browser_sync_script,
    browser_validation_script,
    snapshot_from_browser_payload,
)


class SisfeBrowserTests(unittest.TestCase):
    def test_script_queries_inside_browser_context_without_exposing_cookies(self):
        script = browser_sync_script("21-12345678-9")
        self.assertIn("credentials: 'include'", script)
        self.assertIn("localStorage.getItem('currentUser')", script)
        self.assertIn("Authorization: 'Bearer ' + currentUser.token", script)
        self.assertIn("findNovedadesById", script)
        self.assertIn("al consultar", script)
        self.assertNotIn("document.cookie", script)
        self.assertNotIn("window.__gestorSisfeResult = currentUser", script)

    def test_validation_uses_sisfe_bearer_token_only_inside_browser(self):
        script = browser_validation_script()
        self.assertIn("localStorage.getItem('currentUser')", script)
        self.assertIn("Authorization: 'Bearer ' + currentUser.token", script)
        self.assertIn("window.__gestorSisfeValidation = {ok: response.ok", script)
        self.assertNotIn("document.cookie", script)
        self.assertNotIn("window.__gestorSisfeValidation = currentUser", script)

    def test_movement_detail_exposes_actions_without_exposing_token(self):
        script = browser_movement_detail_script("21-12345678-9", "44")
        self.assertIn("findNovedadesById", script)
        self.assertIn("has_primary_document", script)
        self.assertIn("has_additional_documents", script)
        self.assertIn("Authorization: 'Bearer ' + currentUser.token", script)
        self.assertNotIn("__gestorSisfeMovement = currentUser", script)

    def test_document_script_uses_official_movement_attachment_endpoints(self):
        script = browser_movement_documents_script("21-12345678-9", "44")
        self.assertIn("actuaciones/findDocumentoAdjuntoById", script)
        self.assertIn("cargos/findDocumentosAdjuntosById", script)
        self.assertIn("cargos/findDocumentoAdjuntoByAdjuntoCargoId", script)
        self.assertIn("config/getRecaptchaVisible", script)
        self.assertIn("config.sitekeyV3", script)
        self.assertIn("findDocumentoAdjuntoById'", script)
        self.assertIn("findDocumentoAdjuntoByAdjuntoCargoId'", script)
        self.assertIn("grecaptcha.execute", script)
        self.assertIn("FileReader", script)
        self.assertIn("Documento principal", script)
        self.assertIn("Adjunto de cargo", script)
        self.assertIn("warnings: warnings", script)
        self.assertNotIn("document.cookie", script)

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

    def test_browser_payload_decodes_downloaded_pdf(self):
        content = b"%PDF-1.7\nexample"
        snapshot = snapshot_from_browser_payload(
            {
                "ok": True,
                "cuij": "21123456789",
                "movements": [
                    {
                        "internal_id": "44",
                        "title": "Resolución",
                        "documents": [
                            {
                                "name": "resolucion.pdf",
                                "content_base64": b64encode(content).decode("ascii"),
                            }
                        ],
                    }
                ],
            }
        )
        self.assertEqual(snapshot.movements[0].documents[0].name, "resolucion.pdf")
        self.assertEqual(snapshot.movements[0].documents[0].content, content)

    def test_browser_payload_preserves_partial_download_warnings(self):
        snapshot = snapshot_from_browser_payload(
            {"ok": True, "cuij": "21123456789", "warnings": ["Documento principal: SISFE devolvió 500"]}
        )
        self.assertEqual(snapshot.download_warnings, ("Documento principal: SISFE devolvió 500",))

    def test_browser_error_is_not_imported(self):
        with self.assertRaises(RuntimeError):
            snapshot_from_browser_payload({"ok": False, "error": "SISFE devolvió 403"})

    def test_pending_browser_result_is_reported_without_attribute_error(self):
        with self.assertRaisesRegex(RuntimeError, "respuesta inválida"):
            snapshot_from_browser_payload(None)
