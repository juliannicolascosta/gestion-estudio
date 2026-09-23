import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from gestor_documental.study_backup import (
    BACKUP_FORMAT,
    BACKUP_VERSION,
    MANIFEST_NAME,
    StudyBackupError,
    StudyBackupCancelled,
    create_study_backup,
    restore_study_backup,
    validate_study_backup,
)
from gestor_documental.study_database import DATABASE_NAME


class StudyBackupTests(unittest.TestCase):
    @staticmethod
    def create_portable_database(path: Path, case_id: str, folder: Path):
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "CREATE TABLE expedientes (id TEXT PRIMARY KEY, folder_path TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO expedientes VALUES (?, ?)", (case_id, str(folder.resolve()))
            )
            connection.commit()
        finally:
            connection.close()

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

    def test_backup_includes_models_and_sanitized_institutional_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            study = base / "Estudio"
            case = study / "CASO"
            case.mkdir(parents=True)
            self.create_portable_database(study / DATABASE_NAME, "case-1", case)
            app_dir = base / "AppData"
            models = app_dir / "Modelos"
            models.mkdir(parents=True)
            (models / "Oficio.docx").write_bytes(b"modelo")
            (app_dir / "config.json").write_text(
                json.dumps(
                    {
                        "professionals": ["Dra. Prueba"],
                        "professional_profiles": {"Dra. Prueba": {"name": "Dra. Prueba"}},
                        "activity_settings": {"green_days": 7},
                        "naming_pattern": "{fecha} - {titulo}",
                        "sisfe_profiles": {"Dra. Prueba": {"password_protected": "SECRETO"}},
                        "layout_state": {"window": [1, 2]},
                        "signer_path": "C:/Programa/Firmador.exe",
                    }
                ),
                encoding="utf-8",
            )
            backup = base / "copia.foro-backup"

            create_study_backup(study, backup, app_dir=app_dir)

            with zipfile.ZipFile(backup) as archive:
                names = set(archive.namelist())
                settings = json.loads(archive.read("settings/institutional.json"))
                manifest = json.loads(archive.read(MANIFEST_NAME))
            self.assertIn("models/Oficio.docx", names)
            self.assertEqual(settings["professionals"], ["Dra. Prueba"])
            self.assertNotIn("sisfe_profiles", settings)
            self.assertNotIn("layout_state", settings)
            self.assertNotIn("signer_path", settings)
            self.assertEqual(manifest["backup_format_version"], BACKUP_VERSION)
            self.assertEqual(manifest["case_count"], 1)
            self.assertEqual(len(manifest["content_sha256"]), 64)

    def test_cache_logs_credentials_and_temporaries_are_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            study = base / "Estudio"
            study.mkdir()
            self.create_portable_database(study / DATABASE_NAME, "case-1", study / "CASO")
            (study / "documento.pdf").write_bytes(b"pdf")
            (study / "logs").mkdir()
            (study / "logs" / "diagnostico.log").write_text("privado")
            (study / "__pycache__").mkdir()
            (study / "__pycache__" / "mod.pyc").write_bytes(b"cache")
            (study / "temporal.tmp").write_text("tmp")
            backup = base / "copia.foro-backup"

            create_study_backup(study, backup)

            with zipfile.ZipFile(backup) as archive:
                names = set(archive.namelist())
            self.assertIn("study/documento.pdf", names)
            self.assertFalse(any("logs/" in name or "__pycache__" in name for name in names))
            self.assertNotIn("study/temporal.tmp", names)

    def test_cancelled_backup_leaves_no_apparently_valid_file(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            study = base / "Estudio"
            study.mkdir()
            self.create_portable_database(study / DATABASE_NAME, "case-1", study / "CASO")
            (study / "documento.pdf").write_bytes(b"contenido")
            backup = base / "copia.foro-backup"

            with self.assertRaises(StudyBackupCancelled):
                create_study_backup(study, backup, cancelled=lambda: True)

            self.assertFalse(backup.exists())
            self.assertEqual(list(base.glob("*.partial")), [])

    def test_restore_rebases_database_and_preserves_local_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            study = base / "Origen"
            case = study / "CASO UNO"
            case.mkdir(parents=True)
            self.create_portable_database(study / DATABASE_NAME, "case-1", case)
            app_dir = base / "AppData"
            (app_dir / "Modelos").mkdir(parents=True)
            (app_dir / "Modelos" / "Modelo.docx").write_bytes(b"original")
            (app_dir / "config.json").write_text(
                json.dumps({"professionals": ["Dr. Uno"], "layout_state": {"width": 800},
                            "sisfe_profiles": {"Dr. Uno": {"password_protected": "local"}}}),
                encoding="utf-8",
            )
            backup = base / "copia.foro-backup"
            create_study_backup(study, backup, app_dir=app_dir)
            (app_dir / "config.json").write_text(
                json.dumps({"professionals": ["Otro"], "layout_state": {"width": 1200},
                            "sisfe_profiles": {"Otro": {"password_protected": "sigue-local"}}}),
                encoding="utf-8",
            )
            destination = base / "Destino"

            restore_study_backup(backup, destination, app_dir=app_dir)

            connection = sqlite3.connect(destination / DATABASE_NAME)
            try:
                restored_path = connection.execute(
                    "SELECT folder_path FROM expedientes WHERE id = 'case-1'"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(Path(restored_path), (destination / "CASO UNO").resolve())
            restored_settings = json.loads((app_dir / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(restored_settings["professionals"], ["Dr. Uno"])
            self.assertEqual(restored_settings["layout_state"], {"width": 1200})
            self.assertEqual(
                restored_settings["sisfe_profiles"],
                {"Otro": {"password_protected": "sigue-local"}},
            )

    def test_replace_current_study_creates_safety_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "Fuente"
            source.mkdir()
            self.create_portable_database(source / DATABASE_NAME, "new", source / "NUEVO")
            (source / "nuevo.txt").write_text("nuevo")
            incoming = base / "entrada.foro-backup"
            create_study_backup(source, incoming)
            current = base / "Actual"
            current.mkdir()
            self.create_portable_database(current / DATABASE_NAME, "old", current / "VIEJO")
            (current / "anterior.txt").write_text("anterior")
            safety = base / "antes.foro-backup"

            result = restore_study_backup(
                incoming, current, current_study_root=current,
                safety_backup_path=safety, replace_existing=True,
            )

            self.assertEqual(result.safety_backup, safety.resolve())
            self.assertTrue(safety.is_file())
            validate_study_backup(safety)
            self.assertEqual((current / "nuevo.txt").read_text(), "nuevo")
            self.assertFalse((current / "anterior.txt").exists())

    def test_restore_failure_rolls_back_current_study(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "Fuente"
            source.mkdir()
            self.create_portable_database(source / DATABASE_NAME, "new", source / "NUEVO")
            (source / "nuevo.txt").write_text("nuevo")
            app_dir = base / "AppData"
            (app_dir / "Modelos").mkdir(parents=True)
            (app_dir / "config.json").write_text("{}", encoding="utf-8")
            incoming = base / "entrada.foro-backup"
            create_study_backup(source, incoming, app_dir=app_dir)
            current = base / "Actual"
            current.mkdir()
            self.create_portable_database(current / DATABASE_NAME, "old", current / "VIEJO")
            (current / "anterior.txt").write_text("anterior")

            with patch(
                "gestor_documental.study_backup._merge_institutional_settings",
                side_effect=OSError("fallo simulado"),
            ):
                with self.assertRaises(StudyBackupError):
                    restore_study_backup(
                        incoming, current, app_dir=app_dir, current_study_root=current,
                        safety_backup_path=base / "antes.foro-backup", replace_existing=True,
                    )

            self.assertEqual((current / "anterior.txt").read_text(), "anterior")
            self.assertFalse((current / "nuevo.txt").exists())


if __name__ == "__main__":
    unittest.main()
