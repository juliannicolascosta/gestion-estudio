import unittest

from gestor_documental.movement_interpretation import interpret_movement


class MovementInterpretationTests(unittest.TestCase):
    def test_audience_extracts_explicit_date_and_time(self):
        results = interpret_movement("Se fija audiencia para el 15/09/2026 a las 09:30")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].kind, "Audiencia")
        self.assertEqual(results[0].extracted_at.strftime("%d/%m/%Y %H:%M"), "15/09/2026 09:30")
        self.assertEqual(results[0].warning, "")

    def test_transfer_without_explicit_date_is_flagged_for_review(self):
        results = interpret_movement("Córrase traslado a la demandada por cinco días")
        self.assertEqual(results[0].kind, "Traslado")
        self.assertIsNone(results[0].extracted_at)
        self.assertIn("revisión profesional", results[0].warning)

    def test_only_explicit_deadline_language_is_detected(self):
        self.assertEqual(interpret_movement("Escritos presentados varios"), ())
        results = interpret_movement("El vencimiento opera el 30-09-2026")
        self.assertEqual(results[0].kind, "Vencimiento")
        self.assertEqual(results[0].extracted_at.day, 30)


if __name__ == "__main__":
    unittest.main()
