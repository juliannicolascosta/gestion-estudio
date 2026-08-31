import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gestor_documental.services import create_case
from gestor_documental.sisfe_import import SisfeCaseSnapshot
from gestor_documental.sisfe_session import ManualSisfeSession
from gestor_documental.sisfe_sync import (
    SisfeSessionRequired,
    SisfeSnapshotProviderMissing,
    SisfeSyncCoordinator,
)


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

    def test_sync_requires_manual_session_and_explicit_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            case = create_case(Path(directory) / "Estudio", "Caso")
            session = ManualSisfeSession()
            coordinator = SisfeSyncCoordinator(session)
            with self.assertRaises(SisfeSessionRequired):
                coordinator.synchronize(case, case.path / "SISFE")

            with patch("gestor_documental.sisfe_session.webbrowser.open", return_value=True):
                session.open_portal()
            session.confirm_manual_login()
            with self.assertRaises(SisfeSnapshotProviderMissing):
                coordinator.synchronize(case, case.path / "SISFE")

            active = SisfeSyncCoordinator(session, snapshot_provider=lambda _: SisfeCaseSnapshot(cuij=""))
            result = active.synchronize(case, case.path / "SISFE")
            self.assertEqual(result.movements_registered, 0)
