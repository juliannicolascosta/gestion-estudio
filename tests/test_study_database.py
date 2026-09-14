import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from gestor_documental.services import create_case, read_case_metadata, save_case_metadata
from gestor_documental.study_database import SCHEMA_VERSION, StudyDatabase, study_database_path


class StudyDatabaseTests(unittest.TestCase):

    def test_cases_with_the_same_person_share_a_client_and_receive_distinct_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            first = create_case(study, "Pérez c/ ART")
            second = create_case(study, "Pérez c/ Empleador")
            metadata = {
                "Actor": "PÉREZ, JUAN",
                "DNI del actor": "30.123.456",
                "Teléfono del actor": "341 555 000",
            }
            save_case_metadata(first, metadata)
            save_case_metadata(second, {**metadata, "CUIJ": "21-123"})
            with StudyDatabase(study_database_path(study)) as database:
                first_record = database.import_case(first)
                second_record = database.import_case(second)
                client_rows = database.connection.execute("SELECT * FROM clientes").fetchall()
                client_id = database.connection.execute(
                    "SELECT client_id FROM expedientes WHERE id = ?", (first_record.id,)
                ).fetchone()["client_id"]
                linked_cases = database.list_client_cases(client_id)

            self.assertEqual(len(client_rows), 1)
            self.assertEqual({case.id for case in linked_cases}, {first_record.id, second_record.id})
            first_identity = read_case_metadata(first)["Identificación interna del expediente"]
            second_identity = read_case_metadata(second)["Identificación interna del expediente"]
            self.assertNotEqual(first_identity, second_identity)
            self.assertEqual(read_case_metadata(first)["Actor"], metadata["Actor"])
            self.assertEqual(read_case_metadata(second)["CUIJ"], "21-123")
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
                columns = {
                    row["name"]
                    for row in database.connection.execute("PRAGMA table_info(expedientes)")
                }

            self.assertEqual(version, SCHEMA_VERSION)
            self.assertTrue(
                {
                    "expedientes",
                    "movimientos",
                    "documentos",
                    "movimiento_documentos",
                    "tareas",
                    "audit_events",
                }
                <= tables
            )
            self.assertIn("case_identity", columns)

    def test_import_is_idempotent_and_only_adds_portable_identity_to_metadata(self):
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
            stored = read_case_metadata(case)
            self.assertEqual({key: stored[key] for key in metadata}, metadata)
            self.assertRegex(stored["Identificación interna del expediente"], r"^GD-[A-F0-9]{32}$")
            self.assertNotEqual((case.path / ".gestor-caso.json").read_bytes(), json_before)

    def test_whole_study_move_recovers_case_and_history_by_portable_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            original_study = Path(directory) / "Anterior" / "Estudio"
            case = create_case(original_study, "Caso")
            save_case_metadata(case, {"Actor": "Ana", "CUIJ": "21-1"})
            with StudyDatabase(study_database_path(original_study)) as database:
                original = database.import_case(case)
                movement = database.add_movement(
                    original.id, "Resolución", source="sisfe", external_id="portable-1"
                )
                identity = read_case_metadata(case)["Identificación interna del expediente"]

            moved_study = Path(directory) / "Nueva computadora" / "Estudio"
            moved_study.parent.mkdir()
            original_study.rename(moved_study)
            moved_case = type(case)(moved_study / case.name)
            with StudyDatabase(study_database_path(moved_study)) as database:
                recovered = database.import_case(moved_case)
                count = database.connection.execute("SELECT COUNT(*) FROM expedientes").fetchone()[0]
                stored_identity = database.connection.execute(
                    "SELECT case_identity FROM expedientes WHERE id = ?", (recovered.id,)
                ).fetchone()[0]
                recovered_movement = database.find_movement_by_external_id(
                    recovered.id, "portable-1"
                )

            self.assertEqual(recovered.id, original.id)
            self.assertEqual(recovered.folder_path, moved_case.path.resolve())
            self.assertEqual(recovered_movement.id, movement.id)
            self.assertEqual(stored_identity, identity)
            self.assertEqual(count, 1)

    def test_duplicate_case_identity_does_not_hijack_existing_case(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            original = create_case(study, "Original")
            with StudyDatabase(study_database_path(study)) as database:
                record = database.import_case(original)
                metadata = read_case_metadata(original)
                duplicate = create_case(study, "Copia")
                save_case_metadata(duplicate, metadata)
                with self.assertRaisesRegex(RuntimeError, "misma identidad"):
                    database.import_case(duplicate)
                current = database.find_expediente_by_folder(original.path)
                self.assertEqual(current.id, record.id)
                self.assertIsNone(database.find_expediente_by_folder(duplicate.path))

    def test_import_refreshes_relational_projection_from_case_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso inicial")
            save_case_metadata(case, {"Actor": "Ana", "CUIJ": "21-1"})

            with StudyDatabase(study_database_path(study)) as database:
                original = database.import_case(case)
                save_case_metadata(
                    case,
                    {
                        "Actor": "Beatriz",
                        "CUIJ": "21-2",
                        "Juzgado o tribunal": "Juzgado Laboral 1",
                    },
                )
                refreshed = database.import_case(case)
                events = database.connection.execute(
                    "SELECT action FROM audit_events WHERE entity_id = ? ORDER BY rowid",
                    (original.id,),
                ).fetchall()

            self.assertEqual(refreshed.id, original.id)
            self.assertEqual(refreshed.title, "Caso inicial")
            self.assertEqual(refreshed.client_name, "Beatriz")
            self.assertEqual(refreshed.case_number, "21-2")
            self.assertEqual(refreshed.tribunal, "Juzgado Laboral 1")
            self.assertEqual(
                [row["action"] for row in events],
                ["imported_from_case_folder", "synced_from_case_metadata"],
            )

    def test_relocate_case_preserves_relational_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso inicial")
            with StudyDatabase(study_database_path(study)) as database:
                original = database.import_case(case)
                previous_path = case.path
                renamed_path = previous_path.with_name("Caso actualizado")
                previous_path.rename(renamed_path)
                relocated = database.relocate_case(previous_path, type(case)(renamed_path))
                count = database.connection.execute(
                    "SELECT COUNT(*) FROM expedientes"
                ).fetchone()[0]

            self.assertEqual(relocated.id, original.id)
            self.assertEqual(relocated.folder_path, renamed_path.resolve())
            self.assertEqual(relocated.title, "Caso actualizado")
            self.assertEqual(count, 1)

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

    def test_repair_migration_does_not_add_category_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "repair.sqlite3"
            with StudyDatabase(database_path) as database:
                database.connection.execute("PRAGMA user_version = 3")
                database.connection.commit()

            with StudyDatabase(database_path) as database:
                columns = [
                    row["name"]
                    for row in database.connection.execute("PRAGMA table_info(documentos)")
                ]
                version = database.connection.execute("PRAGMA user_version").fetchone()[0]

            self.assertEqual(columns.count("category"), 1)
            self.assertEqual(version, SCHEMA_VERSION)

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
                listed_documents = database.list_documents(expediente.id)
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
            self.assertEqual(listed_documents, [document])
            self.assertEqual(task.status, "pendiente")
            self.assertEqual(confirmed.status, "confirmada")
            self.assertEqual(confirmed.confirmed_by, "Dra. Ana Pérez")
            self.assertEqual(audit_actions, ["suggested", "confirmed"])

    def test_activity_confirmation_is_idempotent_and_listable(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                first = database.confirm_activity_task(
                    expediente.id,
                    "Audiencia: comparecer",
                    "Dra. Ana Pérez",
                    due_at=datetime(2026, 9, 18, 9, 30),
                    task_key="movimiento:sisfe:audiencia-1:audiencia",
                )
                second = database.confirm_activity_task(
                    expediente.id,
                    "Audiencia: comparecer",
                    "Dra. Ana Pérez",
                    due_at=datetime(2026, 9, 18, 9, 30),
                    task_key="movimiento:sisfe:audiencia-1:audiencia",
                )
                completed = database.complete_activity_task(
                    expediente.id,
                    "movimiento:sisfe:audiencia-1:audiencia",
                    "Dra. Ana Pérez",
                )
                repeated = database.complete_activity_task(
                    expediente.id,
                    "movimiento:sisfe:audiencia-1:audiencia",
                    "Dra. Ana Pérez",
                )
                tasks = database.list_tasks(expediente.id)

            self.assertEqual(first.id, second.id)
            self.assertEqual(len(tasks), 1)
            self.assertEqual(completed.id, repeated.id)
            self.assertEqual(tasks[0].status, "completada")
            self.assertEqual(tasks[0].confirmed_by, "Dra. Ana Pérez")

    def test_document_links_to_its_external_movement_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                movement = database.add_movement(
                    expediente.id,
                    "Decreto",
                    source="sisfe",
                    external_id="mov-500",
                )
                document = database.add_document(
                    expediente.id,
                    Path("Documentos SISFE") / "decreto.pdf",
                    sha256="abc",
                    source="sisfe",
                )
                database.link_document_to_movement(movement.id, document.id, role="primary")
                database.link_document_to_movement(movement.id, document.id, role="primary")
                linked = database.list_movement_documents(movement.id)
                relation = database.connection.execute(
                    "SELECT role FROM movimiento_documentos WHERE movimiento_id = ?",
                    (movement.id,),
                ).fetchall()

            self.assertEqual(linked, [document])
            self.assertEqual([row["role"] for row in relation], ["primary"])


if __name__ == "__main__":
    unittest.main()
