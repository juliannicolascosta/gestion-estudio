import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from gestor_documental.case_activity import (
    case_activities,
    case_activity,
    normalized_activity_settings,
    set_case_archived,
)
from gestor_documental.services import create_case
from gestor_documental.study_database import StudyDatabase, study_database_path


class CaseActivityTests(unittest.TestCase):
    def test_thresholds_and_archived_state_are_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            document = case.path / "documento.pdf"
            document.write_bytes(b"pdf")
            activity_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
            os.utime(document, (activity_at.timestamp(), activity_at.timestamp()))

            self.assertEqual(
                case_activity(case, now=datetime(2026, 2, 14, tzinfo=timezone.utc)).status,
                "green",
            )
            self.assertEqual(
                case_activity(case, now=datetime(2026, 2, 15, tzinfo=timezone.utc)).status,
                "yellow",
            )
            self.assertEqual(
                case_activity(case, now=datetime(2026, 4, 1, tzinfo=timezone.utc)).status,
                "red",
            )
            set_case_archived(case, True)
            self.assertTrue(case_activity(case).archived)
            set_case_archived(case, False)
            self.assertFalse(case_activity(case).archived)

    def test_portal_movement_counts_as_activity(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory) / "Estudio"
            case = create_case(study, "Caso")
            old_file = case.path / "viejo.pdf"
            old_file.write_bytes(b"pdf")
            old_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
            os.utime(old_file, (old_at.timestamp(), old_at.timestamp()))
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                database.add_movement(
                    expediente.id,
                    "Providencia",
                    occurred_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                )

            activities = case_activities(
                [case],
                now=datetime(2026, 9, 3, tzinfo=timezone.utc),
            )
            self.assertEqual(activities[case.path].status, "green")
            self.assertEqual(activities[case.path].inactive_days, 14)

    def test_invalid_threshold_order_is_normalized(self):
        policy = normalized_activity_settings({"yellow_days": 90, "red_days": 30})
        self.assertEqual(policy["yellow_days"], 90)
        self.assertEqual(policy["red_days"], 91)


if __name__ == "__main__":
    unittest.main()
