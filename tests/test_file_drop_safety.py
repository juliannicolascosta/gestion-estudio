import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QMimeData, QUrl

from gestor_documental.ui.case_files import UnsafeFileDrop, local_file_paths_from_mime


class FileDropSafetyTests(unittest.TestCase):
    @staticmethod
    def mime_with_urls(*urls: QUrl) -> QMimeData:
        mime = QMimeData()
        mime.setUrls(list(urls))
        return mime

    def test_accepts_one_real_local_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "foto.jpg"
            source.write_bytes(b"image")
            mime = self.mime_with_urls(QUrl.fromLocalFile(str(source)))
            self.assertEqual(local_file_paths_from_mime(mime), [source.resolve()])

    def test_accepts_several_real_local_files(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / "uno.pdf", Path(directory) / "dos.jpg"]
            for path in paths:
                path.write_bytes(b"file")
            mime = self.mime_with_urls(*(QUrl.fromLocalFile(str(path)) for path in paths))
            self.assertEqual(local_file_paths_from_mime(mime), [path.resolve() for path in paths])

    def test_rejects_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            mime = self.mime_with_urls(QUrl.fromLocalFile(directory))
            with self.assertRaises(UnsafeFileDrop):
                local_file_paths_from_mime(mime)

    def test_rejects_https_browser_url(self):
        mime = self.mime_with_urls(QUrl("https://web.whatsapp.com/blob/foto"))
        with self.assertRaises(UnsafeFileDrop):
            local_file_paths_from_mime(mime)

    def test_rejects_empty_and_relative_paths(self):
        for raw in ("", "."):
            mime = self.mime_with_urls(QUrl.fromLocalFile(raw))
            with self.subTest(raw=raw), self.assertRaises(UnsafeFileDrop):
                local_file_paths_from_mime(mime)

    def test_rejects_current_working_directory(self):
        mime = self.mime_with_urls(QUrl.fromLocalFile(str(Path.cwd())))
        with self.assertRaises(UnsafeFileDrop):
            local_file_paths_from_mime(mime)

    def test_rejects_html_or_text_without_local_file(self):
        mime = QMimeData()
        mime.setHtml('<img src="https://web.whatsapp.com/foto">')
        mime.setText("foto")
        with self.assertRaises(UnsafeFileDrop):
            local_file_paths_from_mime(mime)

    def test_rejects_files_from_application_tree(self):
        mime = self.mime_with_urls(QUrl.fromLocalFile(str(Path(__file__).resolve())))
        with self.assertRaises(UnsafeFileDrop):
            local_file_paths_from_mime(mime)

    def test_invalid_browser_drop_does_not_modify_case_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            case_folder = Path(directory) / "Caso"
            case_folder.mkdir()
            before = tuple(case_folder.iterdir())
            mime = self.mime_with_urls(QUrl("https://web.whatsapp.com/foto.jpg"))
            with self.assertRaises(UnsafeFileDrop):
                local_file_paths_from_mime(mime)
            self.assertEqual(tuple(case_folder.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
