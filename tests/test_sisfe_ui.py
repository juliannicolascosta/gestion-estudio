import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage

from gestor_documental.sisfe_session import ManualSisfeSession
from gestor_documental.ui.sisfe import SisfeLoginDialog


class SisfeBackgroundBrowserTests(unittest.TestCase):
    def test_background_sync_detaches_authenticated_page_from_native_surface(self):
        portal_page = object()
        parking_page = object()
        browser = MagicMock()
        browser.page.return_value = portal_page
        dialog = SimpleNamespace(
            browser=browser,
            portal_page=portal_page,
            _parking_page=parking_page,
        )

        SisfeLoginDialog._detach_portal_page(dialog)

        browser.hide.assert_called_once_with()
        browser.setPage.assert_called_once_with(parking_page)
        browser.show.assert_not_called()

    def test_interactive_login_reattaches_the_same_authenticated_page(self):
        portal_page = object()
        browser = MagicMock()
        browser.page.return_value = object()
        dialog = SimpleNamespace(browser=browser, portal_page=portal_page)

        SisfeLoginDialog._attach_portal_page(dialog)

        browser.setPage.assert_called_once_with(portal_page)
        browser.show.assert_called_once_with()

    def test_authentication_error_invalidates_only_the_expired_confirmation(self):
        session = ManualSisfeSession()
        session.mark_portal_opened()
        session.confirm_manual_login()
        dialog = SimpleNamespace(
            ready_for_sync=True,
            _checking_saved_session=True,
            _validating_saved_session=True,
            session=session,
        )

        SisfeLoginDialog.invalidate_authentication(dialog)

        self.assertFalse(dialog.ready_for_sync)
        self.assertFalse(dialog._checking_saved_session)
        self.assertFalse(dialog._validating_saved_session)
        self.assertFalse(session.active)
        self.assertIsNotNone(session.portal_opened_at)
        self.assertTrue(SisfeLoginDialog.is_authentication_error(RuntimeError("SISFE devolvió 401")))
        self.assertTrue(SisfeLoginDialog.is_authentication_error(RuntimeError("No autorizado")))
        self.assertFalse(SisfeLoginDialog.is_authentication_error(RuntimeError("Sin resultados")))

    def test_reopening_expired_session_reloads_same_portal_page(self):
        session = ManualSisfeSession()
        session.mark_portal_opened()
        portal_page = MagicMock()
        portal_page.url.return_value = QUrl(
            "https://sisfe.justiciasantafe.gov.ar/buscar-expediente"
        )
        dialog = SimpleNamespace(
            browser=MagicMock(),
            portal_page=portal_page,
            ready_for_sync=False,
            session=session,
            _checking_saved_session=False,
            _prefill_attempts=9,
            validation_status=MagicMock(),
        )
        dialog.browser.page.return_value = portal_page
        dialog._attach_portal_page = lambda: SisfeLoginDialog._attach_portal_page(dialog)

        SisfeLoginDialog.prepare_for_open(dialog)

        portal_page.triggerAction.assert_called_once_with(QWebEnginePage.WebAction.Reload)
        portal_page.setUrl.assert_not_called()
        self.assertTrue(dialog._checking_saved_session)


if __name__ == "__main__":
    unittest.main()
