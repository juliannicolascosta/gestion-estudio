import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from gestor_documental.compilation_draft import (
    CompilationDraft,
    DraftItem,
    compilation_draft_path,
    load_compilation_history,
    load_compilation_draft,
    record_compilation_history,
    save_compilation_draft,
)
from gestor_documental.models import Case


class CompilationDraftTests(unittest.TestCase):
    def test_history_keeps_order_and_can_restore_an_older_assembly(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Case(Path(directory) / "Caso")
            case.ensure()
            first = case.path / "01.pdf"
            second = case.path / "02.docx"
            output = case.path / "compilado.pdf"
            for path in (first, second, output):
                path.touch()
            record_compilation_history(
                case,
                (DraftItem(first), DraftItem(second, "writing")),
                output,
                "SISFE demanda/contestación · 6 MB",
                created_at=datetime(2026, 9, 15, 10, 30),
            )

            entries = load_compilation_history(case)

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].items, (DraftItem(first), DraftItem(second, "writing")))
            self.assertEqual(entries[0].output, output)
            self.assertEqual(entries[0].created_at, datetime(2026, 9, 15, 10, 30))

    def test_round_trip_uses_portable_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Case(Path(directory) / "Caso")
            case.ensure()
            documentary = case.path / "Documental" / "recibo.pdf"
            documentary.parent.mkdir()
            documentary.touch()
            writing = case.path / "escrito.docx"
            writing.touch()

            save_compilation_draft(
                case,
                (DraftItem(documentary), DraftItem(writing, "writing")),
                current_writing=writing,
                profile="SISFE demanda/contestación · 6 MB",
            )
            payload = json.loads(compilation_draft_path(case).read_text(encoding="utf-8"))
            self.assertEqual(payload["items"][0]["path"], "Documental/recibo.pdf")
            self.assertNotIn(str(case.path), compilation_draft_path(case).read_text(encoding="utf-8"))

            restored = load_compilation_draft(case)
            self.assertEqual(
                restored,
                CompilationDraft(
                    items=(DraftItem(documentary), DraftItem(writing, "writing")),
                    current_writing=writing,
                    profile="SISFE demanda/contestación · 6 MB",
                ),
            )

    def test_invalid_or_external_paths_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = Case(root / "Caso")
            case.ensure()
            valid = case.path / "válido.pdf"
            valid.touch()
            compilation_draft_path(case).write_text(
                json.dumps(
                    {
                        "version": 1,
                        "items": [
                            {"path": "válido.pdf", "kind": "document"},
                            {"path": "../externo.pdf", "kind": "writing"},
                        ],
                        "current_writing": "../externo.pdf",
                        "profile": "Perfil desconocido",
                    }
                ),
                encoding="utf-8",
            )

            restored = load_compilation_draft(case)
            self.assertEqual(restored.items, (DraftItem(valid),))
            self.assertIsNone(restored.current_writing)


if __name__ == "__main__":
    unittest.main()
