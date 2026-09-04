import tempfile
import unittest
from pathlib import Path

import pymupdf

from gestor_documental.extractor_core.pdf_manager import PDFManager
from gestor_documental.extractor_core.service import format_cedula_paragraph
from gestor_documental.sisfe_extractor import extract_cedula_text


class IntegratedSisfeExtractorTests(unittest.TestCase):
    def test_engine_and_catalog_live_inside_the_gestor_package(self):
        package = Path(__file__).resolve().parents[1] / "gestor_documental"
        self.assertTrue((package / "extractor_core" / "service.py").is_file())
        self.assertTrue((package / "extractor_core" / "data" / "courts_catalog.json").is_file())

    def test_proven_resolution_rules_are_preserved(self):
        text = """*10067528842*
LENTI JUAN MANUEL C/ EXPERTA A.R.T. S.A. S/ ACCIDENTES
21-27296084-1
JUZG. DE 1RA. INST. DE DISTRITO EN LO LABORAL
VISTOS: Los antecedentes.
Y CONSIDERANDO: Los fundamentos.
Por todo lo expuesto, FALLO: 1. Rechazar las excepciones; 2. Hacer lugar a la demanda;
Insértese y hágase saber
"""
        manager = PDFManager()
        metadata = manager._extract_metadata(text)
        extracted = manager._extract_notifiable_text(text, metadata)
        self.assertEqual(metadata.tipo_interno, "resolution")
        self.assertEqual(
            extracted,
            "VISTOS: (...). Y CONSIDERANDO: (...). FALLO: 1. Rechazar las excepciones; "
            "2. Hacer lugar a la demanda; Insértese y hágase saber",
        )

    def test_cedula_flow_extracts_a_pdf_without_external_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "decreto.pdf"
            document = pymupdf.open()
            page = document.new_page()
            page.insert_text((72, 72), "ROSARIO, 4 de septiembre de 2026")
            page.insert_text((72, 100), "Tengase presente. Notifiquese.")
            document.save(source)
            document.close()

            result = extract_cedula_text(source)
            self.assertEqual(result.pages, 1)
            self.assertIn("Notifiquese", result.text)
            self.assertIn("FDO.", result.text)

    def test_cedula_format_keeps_the_previous_contract(self):
        result = format_cedula_paragraph(
            text="Notifíquese.",
            signers="Dra. María Acosta (Secretaria).",
        )
        self.assertEqual(result, "“Notifíquese”. FDO.: DRA. MARÍA ACOSTA (SECRETARIA).")


if __name__ == "__main__":
    unittest.main()
