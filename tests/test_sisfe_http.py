import tempfile
import unittest
from pathlib import Path

from gestor_documental.services import create_case, save_case_metadata
from gestor_documental.sisfe_http import SisfeCaseNotFound, SisfeHttpSnapshotProvider


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.headers = {}

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return FakeResponse(self.responses[url.rsplit("/", 1)[-1]])


class SisfeHttpTests(unittest.TestCase):
    def test_maps_authenticated_read_only_responses_to_snapshot(self):
        responses = {
            "findByFilter": {"lista": [{"id": 42, "expediente": "21-12345678-9", "expCaratula": "Caso"}]},
            "findById": {"expCaratula": "Pérez c/ Provincia", "radicado": "Juzgado Laboral 1"},
            "findNovedadesById": {
                "lista": [{"id": 9, "novedad": "Cédula electrónica", "fecha": "2026-08-31T12:00:00"}]
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            case = create_case(Path(directory) / "Estudio", "Caso")
            save_case_metadata(case, {"CUIJ": "21-12345678-9"})
            session = FakeSession(responses)
            snapshot = SisfeHttpSnapshotProvider(session)(case)

        self.assertEqual(snapshot.title, "Pérez c/ Provincia")
        self.assertEqual(snapshot.tribunal, "Juzgado Laboral 1")
        self.assertEqual(snapshot.movements[0].internal_id, "9")
        self.assertEqual(snapshot.movements[0].title, "Cédula electrónica")
        self.assertEqual(len(session.calls), 3)
        self.assertTrue(all("Authorization" not in str(call) for call in session.calls))
        self.assertIn("Mozilla/5.0", session.headers["User-Agent"])
        self.assertEqual(session.headers["Referer"], "https://sisfe.justiciasantafe.gov.ar/")

    def test_requires_case_cuij_and_matching_remote_case(self):
        with tempfile.TemporaryDirectory() as directory:
            case = create_case(Path(directory) / "Estudio", "Caso")
            provider = SisfeHttpSnapshotProvider(FakeSession({"findByFilter": {"lista": []}}))
            with self.assertRaises(ValueError):
                provider(case)

            save_case_metadata(case, {"CUIJ": "21-12345678-9"})
            with self.assertRaises(SisfeCaseNotFound):
                provider(case)
