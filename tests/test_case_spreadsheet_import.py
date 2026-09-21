import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

from gestor_documental.case_spreadsheet_import import (
    ImportRow,
    ImportStatus,
    classify_rows,
    import_rows,
    mapped_rows,
    preview_spreadsheet,
    read_spreadsheet,
)
from gestor_documental.services import create_case, read_case_metadata, save_case_metadata


class CaseSpreadsheetImportTests(unittest.TestCase):
    def write_csv(self, root: Path, body: str) -> Path:
        path = root / "casos.csv"
        path.write_text(body, encoding="utf-8-sig")
        return path

    def test_reads_valid_xlsx(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "casos.xlsx"
            workbook = Workbook()
            workbook.active.append(["ACTOR", "DEMANDADO", "CAUSA", "N° EXPEDIENTE"])
            workbook.active.append(["Gómez, Luis", "SIJAM S.A.", "Despido", "SN-1"])
            workbook.save(path)
            _, rows = preview_spreadsheet(path, [])
            self.assertEqual(rows[0].actor, "Gómez, Luis")
            self.assertEqual(rows[0].status, ImportStatus.NEW)

    def test_reads_valid_semicolon_csv_and_optional_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.write_csv(
                root,
                "Actor;Demandado;Causa;Expediente;Observaciones;Carátula original\n"
                "Pérez, Ana;Empresa;Daños;21-1;Nota;Texto original\n",
            )
            _, rows = preview_spreadsheet(path, [])
            self.assertEqual(rows[0].case_number, "21-1")
            self.assertEqual(rows[0].notes, "Nota")
            self.assertEqual(rows[0].original_caption, "Texto original")

    def test_imports_case_with_number_through_normal_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            study.mkdir()
            row = ImportRow(2, "Gómez, Luis", "SIJAM", "Despido", "SN-1351-2026")
            outcomes = import_rows(study, [row])
            self.assertIsNotNone(outcomes[0].case)
            metadata = read_case_metadata(outcomes[0].case)
            self.assertEqual(metadata["CUIJ"], "SN-1351-2026")
            self.assertEqual(metadata["Actor"], "Gómez, Luis")

    def test_imports_case_without_number(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            study.mkdir()
            row = ImportRow(2, "Maccey, Sandra", "Federación Patronal", "Enfermedades")
            outcome = import_rows(study, [row])[0]
            self.assertIsNotNone(outcome.case)
            self.assertNotIn("CUIJ", read_case_metadata(outcome.case))

    def test_detects_duplicate_by_case_number_with_conservative_normalization(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory)
            existing = create_case(study, "Existente")
            save_case_metadata(existing, {"CUIJ": " SN-1351-2026 "})
            row = ImportRow(2, "Otro actor", case_number="sn-1351-2026")
            classify_rows([row], [existing])
            self.assertEqual(row.status, ImportStatus.EXISTS)
            self.assertFalse(row.selected)

    def test_warns_possible_duplicate_without_case_number(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory)
            existing = create_case(study, "Existente")
            save_case_metadata(existing, {"Actor": "Pérez, Ana", "Demandado": "Empresa", "Causa": "Daños"})
            row = ImportRow(2, " PÉREZ, ANA ", "empresa", "daños")
            classify_rows([row], [existing])
            self.assertEqual(row.status, ImportStatus.POSSIBLE_DUPLICATE)
            self.assertFalse(row.selected)

    def test_invalid_headers_require_actor_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(Path(directory), "Cliente,Contraria\nAna,Empresa\n")
            data = read_spreadsheet(path)
            self.assertNotIn("actor", data.mapping)
            with self.assertRaisesRegex(ValueError, "actor"):
                mapped_rows(data, data.mapping)

    def test_partially_empty_row_requires_review_only_when_actor_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(Path(directory), "ACTOR,DEMANDADO,CAUSA\n,Empresa,Daños\nAna,,\n")
            _, rows = preview_spreadsheet(path, [])
            self.assertEqual(rows[0].status, ImportStatus.REVIEW)
            self.assertFalse(rows[0].selected)
            self.assertEqual(rows[1].status, ImportStatus.NEW)
            self.assertTrue(rows[1].selected)

    def test_reimport_marks_existing_case_and_does_not_select_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            path = self.write_csv(root, "ACTOR,N° EXPEDIENTE\nAna Pérez,21-99\n")
            _, first = preview_spreadsheet(path, [])
            imported = import_rows(study, first)[0].case
            _, second = preview_spreadsheet(path, [imported])
            self.assertEqual(second[0].status, ImportStatus.EXISTS)
            self.assertFalse(second[0].selected)

    def test_individual_failure_does_not_stop_batch_or_leave_partial_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            study.mkdir()
            rows = [ImportRow(2, "Primero"), ImportRow(3, "Segundo")]
            real_save = save_case_metadata

            def fail_first(case, metadata):
                if metadata["Actor"] == "Primero":
                    raise OSError("sin espacio")
                return real_save(case, metadata)

            with patch("gestor_documental.case_spreadsheet_import.save_case_metadata", side_effect=fail_first):
                outcomes = import_rows(study, rows)
            self.assertTrue(outcomes[0].error)
            self.assertFalse((study / "PRIMERO").exists())
            self.assertIsNotNone(outcomes[1].case)
            self.assertTrue(outcomes[1].case.path.is_dir())


if __name__ == "__main__":
    unittest.main()
