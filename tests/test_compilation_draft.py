import json
import tempfile
import unittest
from pathlib import Path

from gestor_documental.compilation_draft import (
    CompilationDraft,
    DraftItem,
    compilation_draft_path,
    load_compilation_draft,
    save_compilation_draft,
)
from gestor_documental.models import Case


class CompilationDraftTests(unittest.TestCase):
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
