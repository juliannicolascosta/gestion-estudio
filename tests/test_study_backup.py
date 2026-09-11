import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from gestor_documental.study_backup import (
    BACKUP_FORMAT,
    BACKUP_VERSION,
    MANIFEST_NAME,
    StudyBackupError,
    create_study_backup,
    restore_study_backup,
    validate_study_backup,
)
from gestor_documental.study_database import DATABASE_NAME


class StudyBackupTests(unittest.TestCase):
    def test_round_trip_preserves_documents_metadata_and_database(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            study = base / "Estudio original"
            case = study / "PEREZ, JUAN"
            documents = case / "Documentos SISFE"
            documents.mkdir(parents=True)
            (case / ".gestor-caso.json").write_text('{"Actor": "PEREZ, JUAN"}', encoding="utf-8")
            (documents / "decreto.pdf").write_bytes(b"%PDF-1.4\ncontenido")
            database = study / DATABASE_NAME
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE prueba (valor TEXT)")
                connection.execute("INSERT INTO prueba VALUES ('conservado')")
                connection.commit()
            finally:
                connection.close()

            backup = base / "respaldo.zip"
            created = create_study_backup(study, backup)
            checked = validate_study_backup(backup)
            restored = base / "Estudio restaurado"
            result = restore_study_backup(backup, restored)

            self.assertEqual(created.file_count, 3)
            self.assertEqual(checked.file_count, 3)
            self.assertEqual(result.root, restored.resolve())
            self.assertEqual(
                (restored / "PEREZ, JUAN" / "Documentos SISFE" / "decreto.pdf").read_bytes(),
                b"%PDF-1.4\ncontenido",
            )
            self.assertEqual(
                json.loads((restored / "PEREZ, JUAN" / ".gestor-caso.json").read_text(encoding="utf-8"))["Actor"],
                "PEREZ, JUAN",
            )
            connection = sqlite3.connect(restored / DATABASE_NAME)
            try:
                value = connection.execute("SELECT valor FROM prueba").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(value, "conservado")

    def test_tampered_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            study = base / "Estudio"
            study.mkdir()
            (study / "documento.txt").write_text("original", encoding="utf-8")
            backup = base / "respaldo.zip"
            create_study_backup(study, backup)
            with zipfile.ZipFile(backup, "r") as archive:
                manifest = archive.read(MANIFEST_NAME)
            with zipfile.ZipFile(backup, "w") as archive:
                archive.writestr("documento.txt", b"alterado")
                archive.writestr(MANIFEST_NAME, manifest)

            with self.assertRaises(StudyBackupError):
                validate_study_backup(backup)

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "malicioso.zip"
            manifest = {
                "format": BACKUP_FORMAT,
                "version": BACKUP_VERSION,
                "study_name": "Estudio",
                "files": [{"path": "../fuera.txt", "size": 0, "sha256": "0" * 64}],
            }
            with zipfile.ZipFile(backup, "w") as archive:
                archive.writestr("../fuera.txt", b"")
                archive.writestr(MANIFEST_NAME, json.dumps(manifest))

            with self.assertRaises(StudyBackupError):
                validate_study_backup(backup)

    def test_restore_rejects_nonempty_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            study = base / "Estudio"
            study.mkdir()
            (study / "dato.txt").write_text("dato", encoding="utf-8")
            backup = base / "respaldo.zip"
            create_study_backup(study, backup)
            destination = base / "ocupado"
            destination.mkdir()
            (destination / "existente.txt").write_text("no tocar", encoding="utf-8")

            with self.assertRaises(StudyBackupError):
                restore_study_backup(backup, destination)
            self.assertEqual((destination / "existente.txt").read_text(encoding="utf-8"), "no tocar")

    def test_backup_must_be_outside_study(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            study.mkdir()
            with self.assertRaises(StudyBackupError):
                create_study_backup(study, study / "respaldo.zip")


if __name__ == "__main__":
    unittest.main()
