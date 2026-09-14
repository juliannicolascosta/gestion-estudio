import unittest
from datetime import datetime

from gestor_documental.activity_center import build_case_activity
from gestor_documental.domain import Movimiento, Tarea


class ActivityCenterTests(unittest.TestCase):
    def test_unifies_pending_documents_and_interpreted_movements(self):
        movements = [
            Movimiento(
                id="m1",
                expediente_id="e1",
                title="Audiencia fijada para el 18/09/2026 a las 09:30",
                source="sisfe",
                external_id="ext-1",
            ),
            Movimiento(
                id="m2",
                expediente_id="e1",
                title="Correr traslado a la contraria",
                source="sisfe",
                external_id="ext-2",
            ),
        ]
        items = build_case_activity(
            movements,
            ["DNI", "Recibo de sueldo"],
            ["DNI"],
            now=datetime(2026, 9, 14),
        )

        self.assertEqual([item.kind for item in items], ["Audiencia", "Documentación", "Traslado"])
        self.assertEqual(items[0].external_id, "ext-1")
        self.assertEqual(items[1].title, "Recibo de sueldo")
        self.assertTrue(items[2].uncertain)

    def test_overdue_explicit_date_has_highest_priority(self):
        movement = Movimiento(
            id="m1",
            expediente_id="e1",
            title="Vencimiento 10/09/2026",
            source="sisfe",
        )
        item = build_case_activity([movement], [], [], now=datetime(2026, 9, 14))[0]
        self.assertEqual(item.priority, 0)
        self.assertEqual(item.target, "portal")

    def test_does_not_show_received_or_unrelated_information(self):
        unrelated = Movimiento(id="m1", expediente_id="e1", title="Escrito presentado", source="sisfe")
        items = build_case_activity([unrelated], ["DNI"], [" dni "])
        self.assertEqual(items, ())

    def test_completed_task_removes_its_detection_from_the_inbox(self):
        movement = Movimiento(
            id="m1",
            expediente_id="e1",
            title="Audiencia 18/09/2026",
            source="sisfe",
            external_id="audiencia-1",
        )
        key = "movimiento:sisfe:audiencia-1:audiencia"
        self.assertEqual(build_case_activity([movement], [], [], {key: "completada"}), ())

    def test_conservative_filename_match_suggests_review_without_marking_received(self):
        items = build_case_activity(
            [],
            ["Recibo de sueldo"],
            [],
            available_document_paths=["Documental/RECIBO SUELDO agosto.pdf", "DNI.pdf"],
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "Posible recepción")
        self.assertEqual(items[0].target, "files")
        self.assertEqual(items[0].file_path, "Documental/RECIBO SUELDO agosto.pdf")

    def test_confirmed_manual_task_is_visible_until_completed(self):
        task = Tarea("t1", "e1", "Llamar al cliente", status="confirmada", suggested_by="manual")
        item = build_case_activity([], [], [], tasks=[task])[0]
        self.assertEqual((item.kind, item.target, item.task_id), ("Tarea", "task", "t1"))
        completed = Tarea("t1", "e1", "Llamar al cliente", status="completada", suggested_by="manual")
        self.assertEqual(build_case_activity([], [], [], tasks=[completed]), ())


if __name__ == "__main__":
    unittest.main()
