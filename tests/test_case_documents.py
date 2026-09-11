import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gestor_documental.case_documents import rename_document_entry
from gestor_documental.services import create_case
from gestor_documental.study_database import StudyDatabase, study_database_path


class CaseDocumentTests(unittest.TestCase):
    def test_file_rename_preserves_movement_category_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            case = create_case(Path(directory), "Caso")
            source = case.path / "decreto.pdf"
            source.write_bytes(b"original")
            db_path = study_database_path(case.path.parent)
            with StudyDatabase(db_path) as database:
                expediente = database.import_case(case)
                movement = database.add_movement(expediente.id, "Decreto", external_id="1", source="sisfe")
                document = database.add_document(expediente.id, Path(source.name), sha256="abc", source="sisfe", category="judicial")
                database.link_document_to_movement(movement.id, document.id, role="primary")
            target = rename_document_entry(case, source, "Resolución")
            self.assertFalse(source.exists())
            self.assertEqual(target.read_bytes(), b"original")
            with StudyDatabase(db_path) as database:
                linked, = database.list_movement_documents(movement.id)
                self.assertEqual(linked.id, document.id)
                self.assertEqual(linked.relative_path, Path(target.name))
                self.assertEqual((linked.category, linked.sha256, linked.source), ("judicial", "abc", "sisfe"))
                role = database.connection.execute("SELECT role FROM movimiento_documentos").fetchone()[0]
                self.assertEqual(role, "primary")

    def test_folder_rename_updates_descendants_only_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            case = create_case(Path(directory), "Caso")
            folder = case.path / "Documentos"
            (folder / "Internos").mkdir(parents=True)
            (folder / "Internos" / "decreto.pdf").write_bytes(b"original")
            with StudyDatabase(study_database_path(case.path.parent)) as database:
                expediente = database.import_case(case)
                child = database.add_document(expediente.id, Path("Documentos/Internos/decreto.pdf"))
                other = database.add_document(expediente.id, Path("Documentos extra/otro.pdf"))
            target = rename_document_entry(case, folder, "Recibidos")
            with StudyDatabase(study_database_path(case.path.parent)) as database:
                records = {item.id: item.relative_path for item in database.list_documents(expediente.id)}
                self.assertEqual(records[child.id], Path("Recibidos/Internos/decreto.pdf"))
                self.assertEqual(records[other.id], other.relative_path)
                self.assertEqual(database.relocate_documents(expediente.id, Path("Documentos"), Path("Recibidos")), 0)
            self.assertTrue((target / "Internos" / "decreto.pdf").is_file())

    def test_database_failure_restores_original_file(self):
        with tempfile.TemporaryDirectory() as directory:
            case = create_case(Path(directory), "Caso")
            source = case.path / "original.pdf"
            source.write_bytes(b"original")
            with StudyDatabase(study_database_path(case.path.parent)) as database:
                database.import_case(case)
            with patch.object(StudyDatabase, "relocate_documents", side_effect=sqlite3.OperationalError("locked")):
                with self.assertRaises(sqlite3.OperationalError):
                    rename_document_entry(case, source, "nuevo")
            self.assertEqual(source.read_bytes(), b"original")
            self.assertFalse((case.path / "nuevo.pdf").exists())

    def test_registered_destination_conflict_preserves_every_record(self):
        with tempfile.TemporaryDirectory() as directory:
            case = create_case(Path(directory), "Caso")
            folder = case.path / "Antes"
            folder.mkdir()
            with StudyDatabase(study_database_path(case.path.parent)) as database:
                expediente = database.import_case(case)
                database.add_document(expediente.id, Path("Antes/a.pdf"))
                database.add_document(expediente.id, Path("Antes/b.pdf"))
                database.add_document(expediente.id, Path("Después/b.pdf"))
                before = database.list_documents(expediente.id)
            with self.assertRaises(ValueError):
                rename_document_entry(case, folder, "Después")
            self.assertTrue(folder.is_dir())
            self.assertFalse((case.path / "Después").exists())
            with StudyDatabase(study_database_path(case.path.parent)) as database:
                self.assertEqual(database.list_documents(expediente.id), before)

    def test_unindexed_file_rename_needs_no_database_and_rejects_outside_case(self):
        with tempfile.TemporaryDirectory() as directory:
            case = create_case(Path(directory), "Caso")
            source = case.path / "original.pdf"
            source.write_bytes(b"original")
            self.assertTrue(rename_document_entry(case, source, "nuevo").is_file())
            self.assertFalse(study_database_path(case.path.parent).exists())
            outside = Path(directory) / "externo.pdf"
            outside.write_bytes(b"externo")
            with self.assertRaises(ValueError):
                rename_document_entry(case, outside, "otro")
            self.assertTrue(outside.exists())
