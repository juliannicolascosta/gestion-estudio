import sqlite3
import tempfile
import unittest
from pathlib import Path

from gestor_documental.services import create_case, read_case_metadata, save_case_metadata
from gestor_documental.study_database import SCHEMA_VERSION, StudyDatabase, study_database_path


class StudyDatabaseTests(unittest.TestCase):
    def test_creates_versioned_relational_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = study_database_path(Path(directory) / "Estudio")
            database_path.parent.mkdir()
            with StudyDatabase(database_path) as database:
                version = database.connection.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    row[0]
                    for row in database.connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }

            self.assertEqual(version, SCHEMA_VERSION)
            self.assertTrue({"expedientes", "movimientos", "documentos", "tareas", "audit_events"} <= tables)

    def test_import_is_idempotent_and_preserves_case_folder_and_json(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Rosales c/ Provincia")
            metadata = {"Actor": "Pablo Rosales", "CUIJ": "21-12345678-9"}
            save_case_metadata(case, metadata)
            json_before = (case.path / ".gestor-caso.json").read_bytes()

            with StudyDatabase(study_database_path(study)) as database:
                first = database.import_case(case)
                second = database.import_case(case)
                total = database.connection.execute("SELECT COUNT(*) FROM expedientes").fetchone()[0]
                events = database.connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]

            self.assertEqual(first.id, second.id)
            self.assertEqual(first.folder_path, case.path.resolve())
            self.assertEqual(first.client_name, "Pablo Rosales")
            self.assertEqual(first.case_number, "21-12345678-9")
            self.assertEqual(total, 1)
            self.assertEqual(events, 1)
            self.assertTrue(case.path.is_dir())
            self.assertEqual(read_case_metadata(case), metadata)
            self.assertEqual((case.path / ".gestor-caso.json").read_bytes(), json_before)

    def test_rejects_database_from_a_future_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "future.sqlite3"
            connection = sqlite3.connect(database_path)
            try:
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
                connection.commit()
            finally:
                connection.close()

            with self.assertRaises(RuntimeError):
                StudyDatabase(database_path)


if __name__ == "__main__":
    unittest.main()
