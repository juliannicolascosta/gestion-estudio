import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from gestor_documental.services import create_case, save_case_metadata
from gestor_documental.sisfe_import import (
    SisfeCaseSnapshot,
    SisfeDocumentPayload,
    SisfeImportMismatch,
    SisfeImportService,
    SisfeMovementPayload,
    metadata_from_extractor_result,
)
from gestor_documental.study_database import StudyDatabase, study_database_path


class ExtractorResult:
    cuij = "21-12345678-9"
    caratula = "Pérez c/ Provincia"
    court_line = "Juzgado Laboral 1"
    date = "2026-08-31"
    signers = "Firma de prueba"
    notifiable_text = "Texto sintético"


class SisfeImportTests(unittest.TestCase):
    def test_extractor_result_is_adapted_without_importing_its_ui(self):
        metadata = metadata_from_extractor_result(ExtractorResult())
        self.assertEqual(metadata.cuij, "21-12345678-9")
        self.assertEqual(metadata.title, "Pérez c/ Provincia")
        self.assertEqual(metadata.tribunal, "Juzgado Laboral 1")

    def test_imports_synthetic_snapshot_idempotently_without_changing_json(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Pérez c/ Provincia")
            save_case_metadata(case, {"CUIJ": "21-12345678-9"})
            json_before = (case.path / ".gestor-caso.json").read_bytes()
            snapshot = SisfeCaseSnapshot(
                cuij="21-12345678-9",
                title="Pérez c/ Provincia",
                tribunal="Juzgado Laboral 1",
                movements=(
                    SisfeMovementPayload(
                        internal_id="mov-100",
                        title="Cédula electrónica",
                        occurred_at=datetime(2026, 8, 31, 12, tzinfo=timezone.utc),
                        documents=(
                            SisfeDocumentPayload("Cédula de prueba.pdf", b"PDF SINTETICO"),
                        ),
                    ),
                ),
            )
            service = SisfeImportService()
            destination = case.path / "Documentos SISFE"
            first = service.import_snapshot(case, snapshot, destination)
            second = service.import_snapshot(case, snapshot, destination)

            self.assertEqual(first.movements_registered, 1)
            self.assertEqual(first.documents_registered, 1)
            self.assertEqual(second.movements_registered, 0)
            self.assertEqual(second.documents_registered, 0)
            self.assertEqual(second.documents_skipped, 1)
            self.assertEqual((destination / "Cédula de prueba.pdf").read_bytes(), b"PDF SINTETICO")
            self.assertEqual((case.path / ".gestor-caso.json").read_bytes(), json_before)
            with StudyDatabase(study_database_path(study)) as database:
                self.assertEqual(database.connection.execute("SELECT COUNT(*) FROM movimientos").fetchone()[0], 1)
                self.assertEqual(database.connection.execute("SELECT COUNT(*) FROM documentos").fetchone()[0], 1)
                self.assertEqual(
                    database.connection.execute("SELECT tribunal FROM expedientes").fetchone()[0], "Juzgado Laboral 1"
                )

    def test_rejects_snapshot_for_another_case_before_creating_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            save_case_metadata(case, {"CUIJ": "21-12345678-9"})
            snapshot = SisfeCaseSnapshot(
                cuij="21-00000000-0",
                movements=(
                    SisfeMovementPayload(
                        title="No corresponde",
                        documents=(SisfeDocumentPayload("no.pdf", b"SINTETICO"),),
                    ),
                ),
            )

            with self.assertRaises(SisfeImportMismatch):
                SisfeImportService().import_snapshot(case, snapshot, case.path / "SISFE")
            self.assertFalse((case.path / "SISFE").exists())


if __name__ == "__main__":
    unittest.main()
