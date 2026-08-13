import tempfile, unittest
from pathlib import Path
from pypdf import PdfWriter
from preparador_sisfe.models import Case
from preparador_sisfe.services import safe_name, split_pdf

class ServiceTests(unittest.TestCase):
    def test_case_structure(self):
        with tempfile.TemporaryDirectory() as d:
            case=Case("Prueba",Path(d)/"Prueba"); case.ensure()
            self.assertTrue(case.writings.is_dir()); self.assertTrue(case.evidence.is_dir()); self.assertTrue(case.output.is_dir())
    def test_safe_name(self):
        self.assertEqual(safe_name('Gómez: c/ "SIJAM"'), "Gómez- c- -SIJAM")
    def test_split_pdf(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/"a.pdf"; w=PdfWriter()
            for _ in range(3): w.add_blank_page(width=595,height=842)
            with source.open("wb") as f:w.write(f)
            parts=split_pdf(source,600,root,"DOC")
            self.assertGreaterEqual(len(parts),1)

if __name__ == "__main__": unittest.main()
