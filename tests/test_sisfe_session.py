import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from gestor_documental.services import create_case
from gestor_documental.sisfe_import import SisfeCaseSnapshot
from gestor_documental.sisfe_session import ManualSisfeSession
from gestor_documental.sisfe_sync import SisfePortalService, SisfeSessionRequired


class SisfeSessionTests(unittest.TestCase):
    def test_session_is_manual_and_never_contains_credentials(self):
        session = ManualSisfeSession()
        with patch("gestor_documental.sisfe_session.webbrowser.open", return_value=True) as opened:
            self.assertTrue(session.open_portal())
        opened.assert_called_once()
        self.assertFalse(session.active)
        session.confirm_manual_login()
        self.assertTrue(session.active)
        self.assertNotIn("password", vars(session))
        self.assertNotIn("cookie", vars(session))
        session.close()
        self.assertFalse(session.active)
        self.assertNotIn("http_session", vars(session))

    def test_portal_import_requires_the_manual_browser_session(self):
        with tempfile.TemporaryDirectory() as directory:
            case = create_case(Path(directory) / "Estudio", "Caso")
            session = ManualSisfeSession()
            importer = MagicMock()
            expected = object()
            importer.import_snapshot.return_value = expected
            portal = SisfePortalService(session, importer)
            snapshot = SisfeCaseSnapshot(cuij="")
            with self.assertRaises(SisfeSessionRequired):
                portal.import_snapshot(case, snapshot, case.path / "SISFE")

            with patch("gestor_documental.sisfe_session.webbrowser.open", return_value=True):
                session.open_portal()
            session.confirm_manual_login()
            result = portal.import_snapshot(case, snapshot, case.path / "SISFE")
            self.assertIs(result, expected)
            importer.import_snapshot.assert_called_once_with(
                case, snapshot, case.path / "SISFE"
            )
