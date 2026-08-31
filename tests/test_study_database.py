import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
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

    def test_external_movements_deduplicate_but_manual_movements_do_not(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                first = database.add_movement(
                    expediente.id, "Cédula recibida", source="sisfe", external_id="mov-42"
                )
                second = database.add_movement(
                    expediente.id, "Cédula recibida", source="sisfe", external_id="mov-42"
                )
                manual_a = database.add_movement(expediente.id, "Llamado al cliente")
                manual_b = database.add_movement(expediente.id, "Llamado al cliente")

            self.assertEqual(first.id, second.id)
            self.assertNotEqual(manual_a.id, manual_b.id)

    def test_logical_movement_identity_deduplicates_when_external_id_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                first = database.add_movement(
                    expediente.id, "Providencia", source="sisfe", logical_key="2026-08-31|providencia"
                )
                second = database.add_movement(
                    expediente.id, "Providencia", source="sisfe", logical_key="2026-08-31|providencia"
                )

            self.assertEqual(first.id, second.id)

    def test_recent_movements_are_returned_newest_first(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                database.add_movement(
                    expediente.id,
                    "Primero",
                    occurred_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
                )
                database.add_movement(
                    expediente.id,
                    "Último",
                    occurred_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
                )
                movements = database.list_recent_movements(expediente.id)

            self.assertEqual([movement.title for movement in movements], ["Último", "Primero"])

    def test_documents_stay_relative_to_case_and_tasks_require_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            due_at = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                document = database.add_document(
                    expediente.id,
                    Path("Notificaciones") / "cedula.pdf",
                    sha256="ABC123",
                    source="sisfe",
                )
                task = database.suggest_task(
                    expediente.id, "Revisar cédula", due_at=due_at, suggested_by="sisfe"
                )
                confirmed = database.confirm_task(task.id, "Dra. Ana Pérez")
                audit_actions = [
                    row[0]
                    for row in database.connection.execute(
                        "SELECT action FROM audit_events WHERE entity_id = ? ORDER BY rowid", (task.id,)
                    )
                ]

                with self.assertRaises(ValueError):
                    database.add_document(expediente.id, Path("..") / "outside.pdf")
                with self.assertRaises(ValueError):
                    database.confirm_task(task.id, "")

            self.assertEqual(document.relative_path, Path("Notificaciones/cedula.pdf"))
            self.assertEqual(document.sha256, "abc123")
            self.assertEqual(task.status, "pendiente")
            self.assertEqual(confirmed.status, "confirmada")
            self.assertEqual(confirmed.confirmed_by, "Dra. Ana Pérez")
            self.assertEqual(audit_actions, ["suggested", "confirmed"])


if __name__ == "__main__":
    unittest.main()
