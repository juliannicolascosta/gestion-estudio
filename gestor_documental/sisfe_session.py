"""Sesión SISFE explícitamente manual y sólo vigente durante la aplicación."""

from __future__ import annotations

import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests


SISFE_MATRICULADOS_URL = "https://sisfe.justiciasantafe.gov.ar/"


@dataclass
class ManualSisfeSession:
    """Tracks confirmation, never credentials, cookies or CAPTCHA data."""

    portal_opened_at: datetime | None = None
    confirmed_at: datetime | None = None
    http_session: requests.Session = field(default_factory=requests.Session, repr=False)

    @property
    def active(self) -> bool:
        return self.confirmed_at is not None

    @property
    def has_http_cookies(self) -> bool:
        return bool(self.http_session.cookies)

    def open_portal(self) -> bool:
        self.mark_portal_opened()
        return bool(webbrowser.open(SISFE_MATRICULADOS_URL))

    def mark_portal_opened(self):
        self.portal_opened_at = datetime.now(timezone.utc)

    def attach_runtime_cookie(self, name: str, value: str, domain: str, path: str = "/"):
        """Keep a browser cookie only in the transient requests session."""
        if name and domain.endswith("justiciasantafe.gov.ar"):
            self.http_session.cookies.set(name, value, domain=domain, path=path or "/")

    def confirm_manual_login(self):
        if self.portal_opened_at is None:
            raise RuntimeError("Primero abrí SISFE e iniciá sesión manualmente.")
        self.confirmed_at = datetime.now(timezone.utc)

    def close(self):
        self.portal_opened_at = None
        self.confirmed_at = None
        self.http_session.cookies.clear()
