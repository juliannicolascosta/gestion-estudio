import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gestor_documental.services import create_case
from gestor_documental.sisfe_downloads import SisfeDownloadRegistry
from gestor_documental.study_database import StudyDatabase, study_database_path


class SisfeDownloadRegistryTests(unittest.TestCase):
    def test_registers_official_download_and_links_it_to_the_movement(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            target = case.path / "Documentos SISFE" / "decreto.pdf"
            target.parent.mkdir()
            target.write_bytes(b"%PDF-1.4 synthetic")
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                movement = database.add_movement(
                    expediente.id,
                    "Decreto",
                    source="sisfe",
                    external_id="mov-10",
                )

            result = SisfeDownloadRegistry().register(
                case,
                target,
                movement_external_id="mov-10",
                role="primary",
            )

            self.assertEqual(result.path, target)
            self.assertFalse(result.duplicate)
            self.assertTrue(result.linked_to_movement)
            with StudyDatabase(study_database_path(study)) as database:
                linked = database.list_movement_documents(movement.id)
                role = database.connection.execute(
                    "SELECT role FROM movimiento_documentos"
                ).fetchone()["role"]
            self.assertEqual([document.relative_path for document in linked], [target.relative_to(case.path)])
            self.assertEqual(role, "primary")

    def test_duplicate_download_reuses_registered_document(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            directory_path = case.path / "Documentos SISFE"
            directory_path.mkdir()
            original = directory_path / "original.pdf"
            duplicate = directory_path / "otra copia.pdf"
            original.write_bytes(b"%PDF duplicate")
            duplicate.write_bytes(original.read_bytes())
            registry = SisfeDownloadRegistry()
            registry.register(case, original)

            with patch("gestor_documental.sisfe_downloads.move_to_recycle_bin") as recycle:
                result = registry.register(case, duplicate)

            self.assertTrue(result.duplicate)
            self.assertEqual(result.path, original)
            recycle.assert_called_once_with([duplicate])

    def test_rejects_a_download_outside_the_selected_case(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            outside = Path(directory) / "outside.pdf"
            outside.write_bytes(b"%PDF outside")

            with self.assertRaises(ValueError):
                SisfeDownloadRegistry().register(case, outside)

    def test_does_not_silently_lose_the_requested_movement_link(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            target = case.path / "documento.pdf"
            target.write_bytes(b"%PDF movement missing")

            with self.assertRaisesRegex(RuntimeError, "sincronizá"):
                SisfeDownloadRegistry().register(
                    case,
                    target,
                    movement_external_id="missing",
                    role="primary",
                )
            with StudyDatabase(study_database_path(study)) as database:
                self.assertEqual(database.connection.execute("SELECT COUNT(*) FROM documentos").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
