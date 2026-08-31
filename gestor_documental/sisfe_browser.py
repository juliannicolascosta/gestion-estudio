"""Browser-context SISFE snapshot helpers.

The script is executed by the logged-in embedded SISFE page, so it shares the
portal's actual browser session without exporting cookies to disk or Python.
"""

from __future__ import annotations

import json
from datetime import datetime

from .sisfe_import import SisfeCaseSnapshot, SisfeMovementPayload


def browser_sync_script(cuij: str) -> str:
    target = json.dumps("".join(char for char in cuij if char.isdigit()))
    return f"""
        window.__gestorSisfeResult = null;
        (async () => {{
          try {{
            const target = {target};
            const getJson = async (path) => {{
              const response = await fetch(path, {{credentials: 'include'}});
              if (!response.ok) throw new Error('SISFE devolvió ' + response.status);
              return response.json();
            }};
            const list = await getJson('/iol/expedientes/findByFilter?diasNovedades=30&page=0&size=100');
            const selected = (list.lista || []).find(row =>
              JSON.stringify(row).replace(/\\D/g, '').includes(target)
            );
            if (!selected || !selected.id) throw new Error('SISFE no devolvió el expediente seleccionado');
            const details = await getJson('/iol/expedientes/findById?idExpediente=' + encodeURIComponent(selected.id));
            const news = await getJson('/iol/expedientes/findNovedadesById?idExpediente=' +
              encodeURIComponent(selected.id) + '&page=0&size=100');
            window.__gestorSisfeResult = {{
              ok: true,
              cuij: target,
              title: details.expCaratula || selected.expCaratula || '',
              tribunal: details.radicado || selected.radicacionActual || '',
              movements: (news.lista || []).map(row => ({{
                internal_id: String(row.id || ''),
                title: String(row.novedad || row.tipoActuacion || 'Movimiento SISFE'),
                occurred_at: row.fecha || null
              }}))
            }};
          }} catch (error) {{
            window.__gestorSisfeResult = {{ok: false, error: String(error.message || error)}};
          }}
        }})();
    """


def snapshot_from_browser_payload(payload: dict) -> SisfeCaseSnapshot:
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError(str(payload.get("error", "SISFE devolvió una respuesta inválida.")))
    movements = tuple(
        SisfeMovementPayload(
            internal_id=str(row.get("internal_id", "")),
            title=str(row.get("title", "Movimiento SISFE")),
            occurred_at=_parse_date(row.get("occurred_at")),
        )
        for row in payload.get("movements", [])
        if isinstance(row, dict)
    )
    return SisfeCaseSnapshot(
        cuij=str(payload.get("cuij", "")),
        title=str(payload.get("title", "")),
        tribunal=str(payload.get("tribunal", "")),
        movements=movements,
    )


def _parse_date(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for pattern in ("%d/%m/%Y", "%d/%m/%Y %H:%M"):
            try:
                return datetime.strptime(str(value), pattern)
            except ValueError:
                pass
    return None
