import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from gestor_documental.case_registry import open_case_database
from gestor_documental.services import create_case
from gestor_documental.study_database import study_database_path

PACKAGE = Path(__file__).resolve().parents[1] / "gestor_documental"
DIRECT_CASE_OPEN = re.compile(r"StudyDatabase\(\s*study_database_path\([^)]*\.path\.parent\)")


class CaseRegistryTests(unittest.TestCase):
    def test_opens_the_study_database_of_the_case_and_closes_it(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            with open_case_database(case) as database:
                self.assertEqual(database.path, study_database_path(study))
                expediente = database.import_case(case)
                self.assertTrue(expediente.id)
            with self.assertRaises(sqlite3.ProgrammingError):
                database.connection.execute("SELECT 1")

    def test_no_module_opens_a_case_database_behind_the_registry(self):
        offenders = []
        for source in PACKAGE.rglob("*.py"):
            if source.name in {"case_registry.py", "study_database.py"}:
                continue
            for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
                if DIRECT_CASE_OPEN.search(line):
                    offenders.append(f"{source.relative_to(PACKAGE)}:{number}")
        self.assertEqual(offenders, [], "Usar open_case_database(case)")


if __name__ == "__main__":
    unittest.main()
