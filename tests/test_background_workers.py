import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gestor_documental.background_workers import (
    CedulaExtractionWorker,
    CompileWorker,
    StudyBackupWorker,
)
from gestor_documental.models import Case
from gestor_documental.services import CompilationCancelled


class BackgroundWorkerTests(unittest.TestCase):
    def test_compile_worker_reports_cancellation_separately(self):
        worker = CompileWorker(Case(Path("caso")), [], 1024, "salida.pdf")
        cancelled = []
        failed = []
        worker.cancelled.connect(lambda: cancelled.append(True))
        worker.failed.connect(failed.append)

        with patch(
            "gestor_documental.background_workers.compile_documents",
            side_effect=CompilationCancelled(),
        ):
            worker.run()

        self.assertEqual(cancelled, [True])
        self.assertEqual(failed, [])

    def test_cedula_worker_reports_extraction_errors(self):
        worker = CedulaExtractionWorker(Path("documento-inexistente.pdf"))
        errors = []
        worker.failed.connect(errors.append)

        with patch(
            "gestor_documental.background_workers.extract_cedula_text",
            side_effect=ValueError("PDF inválido"),
        ):
            worker.run()

        self.assertEqual(errors, ["PDF inválido"])

    def test_backup_worker_dispatches_backup_without_touching_real_studies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Estudio temporal"
            destination = root / "respaldo.zip"
            worker = StudyBackupWorker("backup", source, destination)
            completed = []
            worker.completed.connect(completed.append)

            with patch(
                "gestor_documental.background_workers.create_study_backup",
                return_value="respaldo-creado",
            ) as create_backup:
                worker.run()

            self.assertEqual(completed, ["respaldo-creado"])
            create_backup.assert_called_once()
            self.assertEqual(create_backup.call_args.args[:2], (source, destination))


if __name__ == "__main__":
    unittest.main()
