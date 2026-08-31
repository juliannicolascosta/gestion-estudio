"""Cliente SISFE de sólo lectura para una sesión ya autenticada en memoria.

No realiza login, no resuelve CAPTCHA y no guarda cookies. La sesión HTTP debe
ser creada por un puente manual futuro y se descarta al cerrar la aplicación.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from .models import Case
from .services import read_case_metadata
from .sisfe_import import SisfeCaseSnapshot, SisfeMovementPayload


class SisfeCaseNotFound(RuntimeError):
    pass


class SisfeHttpSnapshotProvider:
    """Fetch SISFE movements only; document downloads remain CAPTCHA-protected."""

    BROWSER_HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-AR,es;q=0.9",
        "Referer": "https://sisfe.justiciasantafe.gov.ar/",
        # SISFE serves these endpoints to its browser application. This is a
        # navigation identity, not an authentication secret.
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        ),
    }

    def __init__(
        self,
        session: requests.Session,
        *,
        base_url: str = "https://sisfe.justiciasantafe.gov.ar",
        days_of_news: int = 30,
        page_size: int = 100,
        timeout_seconds: int = 20,
    ):
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.days_of_news = days_of_news
        self.page_size = page_size
        self.timeout_seconds = timeout_seconds
        self.session.headers.update(self.BROWSER_HEADERS)

    def __call__(self, case: Case) -> SisfeCaseSnapshot:
        cuij = read_case_metadata(case).get("CUIJ", "")
        target = self._digits(cuij)
        if not target:
            raise ValueError("El caso necesita CUIJ para sincronizar novedades SISFE.")
        rows = self._get("/iol/expedientes/findByFilter", {
            "diasNovedades": self.days_of_news,
            "page": 0,
            "size": self.page_size,
        }).get("lista", [])
        selected = next((row for row in rows if self._row_matches_cuij(row, target)), None)
        if not selected:
            raise SisfeCaseNotFound("SISFE no devolvió el expediente seleccionado.")
        identifier = str(selected.get("id", "")).strip()
        if not identifier:
            raise SisfeCaseNotFound("SISFE devolvió un expediente sin identificador interno.")
        details = self._get("/iol/expedientes/findById", {"idExpediente": identifier})
        news = self._get(
            "/iol/expedientes/findNovedadesById",
            {"idExpediente": identifier, "page": 0, "size": self.page_size},
        ).get("lista", [])
        movements = tuple(
            SisfeMovementPayload(
                internal_id=str(row.get("id", "")),
                title=str(row.get("novedad") or row.get("tipoActuacion") or "Movimiento SISFE"),
                occurred_at=self._parse_date(row.get("fecha")),
            )
            for row in news
        )
        return SisfeCaseSnapshot(
            cuij=cuij,
            title=str(details.get("expCaratula") or selected.get("expCaratula") or case.name),
            tribunal=str(details.get("radicado") or selected.get("radicacionActual") or ""),
            movements=movements,
        )

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}{path}", params=params, timeout=self.timeout_seconds
        )
        if response.status_code in (401, 403):
            raise PermissionError(
                "SISFE no autorizó la sesión manual. Volvé a iniciar sesión de Matriculados."
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("SISFE devolvió una respuesta inesperada.")
        return payload

    @staticmethod
    def _digits(value: object) -> str:
        return "".join(char for char in str(value) if char.isdigit())

    @classmethod
    def _row_matches_cuij(cls, row: dict[str, Any], target: str) -> bool:
        return target in cls._digits(" ".join(str(value) for value in row.values()))

    @staticmethod
    def _parse_date(value: object) -> datetime | None:
        if not value:
            return None
        text = str(value).strip()
        for candidate in (text, text.replace("Z", "+00:00")):
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                pass
        for pattern in ("%d/%m/%Y", "%d/%m/%Y %H:%M"):
            try:
                return datetime.strptime(text, pattern)
            except ValueError:
                pass
        return None
