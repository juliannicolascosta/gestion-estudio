import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from gestor_documental.ui.sisfe import SisfeLoginDialog


class SisfeBackgroundBrowserTests(unittest.TestCase):
    def test_background_sync_detaches_authenticated_page_from_visible_webview(self):
        portal_page = object()
        idle_page = object()
        browser = MagicMock()
        browser.page.return_value = portal_page
        dialog = SimpleNamespace(
            browser=browser,
            portal_page=portal_page,
            idle_page=idle_page,
        )

        SisfeLoginDialog._detach_portal_page(dialog)

        browser.hide.assert_called_once_with()
        browser.setPage.assert_called_once_with(idle_page)

    def test_interactive_login_reattaches_the_same_authenticated_page(self):
        portal_page = object()
        browser = MagicMock()
        browser.page.return_value = object()
        dialog = SimpleNamespace(browser=browser, portal_page=portal_page)

        SisfeLoginDialog._attach_portal_page(dialog)

        browser.setPage.assert_called_once_with(portal_page)
        browser.show.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
