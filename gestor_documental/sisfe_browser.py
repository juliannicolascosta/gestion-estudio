"""Browser-context SISFE snapshot helpers.

The script is executed by the logged-in embedded SISFE page, so it shares the
portal's actual browser session without exporting cookies to disk or Python.
"""

from __future__ import annotations

import json
from base64 import b64decode
from binascii import Error as Base64Error
from datetime import datetime

from .sisfe_import import SisfeCaseSnapshot, SisfeDocumentPayload, SisfeMovementPayload


_PAGINATION_HELPERS = """
            const pageSize = 100;
            const rowsFrom = (payload) => Array.isArray(payload && payload.lista) ? payload.lista : [];
            const lastPage = (payload, page, rows) => {
              const reported = Number(
                payload && (payload.totalPages ?? payload.totalPaginas ?? payload.cantidadPaginas)
              );
              return (Number.isFinite(reported) && reported > 0 && page + 1 >= reported) ||
                rows.length < pageSize;
            };
            const pageSignature = (rows) => rows.map(row =>
              String((row && row.id) ?? JSON.stringify(row))
            ).join('|');
            const findPaged = async (loadPage, predicate) => {
              const seenPages = new Set();
              for (let page = 0; page < 100; page += 1) {
                const payload = await loadPage(page, pageSize);
                const rows = rowsFrom(payload);
                const signature = pageSignature(rows);
                if (seenPages.has(signature)) return null;
                seenPages.add(signature);
                const found = rows.find(predicate);
                if (found) return found;
                if (lastPage(payload, page, rows)) return null;
              }
              throw new Error('SISFE devolvió demasiadas páginas para una sola consulta');
            };
            const collectPaged = async (loadPage) => {
              const collected = [];
              const seenPages = new Set();
              const seenRows = new Set();
              for (let page = 0; page < 100; page += 1) {
                const payload = await loadPage(page, pageSize);
                const rows = rowsFrom(payload);
                const signature = pageSignature(rows);
                if (seenPages.has(signature)) break;
                seenPages.add(signature);
                for (const row of rows) {
                  const key = String((row && row.id) ?? JSON.stringify(row));
                  if (!seenRows.has(key)) {
                    seenRows.add(key);
                    collected.push(row);
                  }
                }
                if (lastPage(payload, page, rows)) break;
              }
              return collected;
            };
"""


def browser_validation_script() -> str:
    """Validate SISFE inside the logged-in page without exporting its token."""
    return """
        window.__gestorSisfeValidation = null;
        (async () => {
          try {
            const currentUser = JSON.parse(localStorage.getItem('currentUser') || 'null');
            if (!currentUser || !currentUser.token) {
              throw new Error('SISFE no entregó el token de la sesión');
            }
            const response = await fetch(
              '/iol/expedientes/findByFilter?diasNovedades=30&page=0&size=1',
              {
                credentials: 'include',
                headers: {Authorization: 'Bearer ' + currentUser.token}
              }
            );
            window.__gestorSisfeValidation = {ok: response.ok, status: response.status};
          } catch (error) {
            window.__gestorSisfeValidation = {ok: false, error: String(error.message || error)};
          }
        })();
    """


def browser_movement_detail_script(cuij: str, movement_id: str) -> str:
    target = json.dumps("".join(char for char in cuij if char.isdigit()))
    remote_movement = json.dumps(str(movement_id))
    return f"""
        window.__gestorSisfeMovement = null;
        (async () => {{
          try {{
            const target = {target};
            const movementId = {remote_movement};
            const currentUser = JSON.parse(localStorage.getItem('currentUser') || 'null');
            if (!currentUser || !currentUser.token) {{
              throw new Error('SISFE no entregó el token de la sesión');
            }}
            const getJson = async (path) => {{
              const response = await fetch(path, {{
                credentials: 'include',
                headers: {{Authorization: 'Bearer ' + currentUser.token}}
              }});
              if (!response.ok) throw new Error('SISFE devolvió ' + response.status);
              return response.json();
            }};
{_PAGINATION_HELPERS}
            const selected = await findPaged(
              (page, size) => getJson('/iol/expedientes/findByFilter?diasNovedades=30&page=' + page + '&size=' + size),
              row => JSON.stringify(row).replace(/\\D/g, '').includes(target)
            );
            if (!selected || !selected.id) throw new Error('SISFE no devolvió el expediente seleccionado');
            const news = await collectPaged((page, size) => getJson(
              '/iol/expedientes/findNovedadesById?idExpediente=' + encodeURIComponent(selected.id) +
              '&page=' + page + '&size=' + size
            ));
            const movementIndex = news.findIndex(row => String(row.id || '') === movementId);
            const movement = movementIndex >= 0 ? news[movementIndex] : null;
            if (!movement) throw new Error('SISFE no devolvió el movimiento seleccionado');
            window.__gestorSisfeMovement = {{
              ok: true,
              remote_case_id: String(selected.id),
              movement_id: movementId,
              title: String(movement.novedad || movement.tipoActuacion || 'Movimiento SISFE'),
              occurred_at: movement.fecha || null,
              observation: String(movement.observacion || ''),
              page_number: Math.floor(movementIndex / 25) + 1,
              row_number: movementIndex % 25,
              has_primary_document: movement.adjunto1 != null,
              has_related_organizations: movement.adjunto2 != null,
              has_additional_documents: movement.adjunto3 != null
            }};
          }} catch (error) {{
            window.__gestorSisfeMovement = {{ok: false, error: String(error.message || error)}};
          }}
        }})();
    """


def browser_prepare_official_movement_page_script(
    remote_case_id: str,
    page_number: int,
) -> str:
    """Select the official SISFE grid page before opening case details."""

    case_id = json.dumps(str(remote_case_id))
    page = max(1, int(page_number))
    return f"""
        (() => {{
          const caseId = {case_id};
          let previous = {{}};
          try {{ previous = JSON.parse(localStorage.getItem('paginaDetalle') || '{{}}'); }} catch (_) {{}}
          localStorage.setItem('paginaDetalle', JSON.stringify({{
            IdExpediente: Number(caseId),
            Orden: previous.Orden || {{}},
            PaginaActual: {page}
          }}));
          return true;
        }})();
    """


def browser_click_official_movement_attachment_script(
    title: str,
    row_number: int,
    attachment: str,
) -> str:
    """Click a movement clip in SISFE's rendered grid, exactly as a user would."""

    expected_title = json.dumps(str(title))
    row = max(0, int(row_number))
    use_last_clip = "true" if attachment == "additional" else "false"
    return f"""
        (() => {{
          const simplify = value => String(value || '').normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\\s+/g, ' ').trim();
          const rows = Array.from(document.querySelectorAll('app-grilla tbody tr'));
          if (!rows.length) return {{ok: false, pending: true, error: 'Esperando la grilla oficial'}};
          const expected = simplify({expected_title});
          let selected = rows[{row}];
          if (!selected || (expected && !simplify(selected.innerText).includes(expected))) {{
            selected = rows.find(item => simplify(item.innerText).includes(expected));
          }}
          if (!selected) return {{ok: false, error: 'No encontramos el movimiento en la página oficial'}};
          const clips = Array.from(selected.querySelectorAll('.fa-paperclip'));
          if (!clips.length) return {{ok: false, error: 'El movimiento no muestra un clip descargable'}};
          const icon = {use_last_clip} ? clips[clips.length - 1] : clips[0];
          const clickable = icon.closest('span, a, button, [role="button"]') || icon;
          clickable.click();
          return {{ok: true, clip_count: clips.length}};
        }})();
    """


def browser_click_official_additional_attachment_script(row_number: int) -> str:
    """Click one row in SISFE's official additional-attachments screen."""

    row = max(0, int(row_number))
    return f"""
        (() => {{
          if (!location.pathname.includes('/documentos-adjuntos/')) {{
            return {{ok: false, pending: true, error: 'Esperando la pantalla oficial de adjuntos'}};
          }}
          const rows = Array.from(document.querySelectorAll('app-grilla tbody tr'));
          if (!rows.length) return {{ok: false, pending: true, error: 'Esperando los adjuntos oficiales'}};
          if ({row} >= rows.length) return {{ok: true, complete: true, row_count: rows.length}};
          const icon = rows[{row}].querySelector('.fa-paperclip');
          if (!icon) return {{ok: false, error: 'El adjunto no muestra un clip descargable'}};
          const clickable = icon.closest('span, a, button, [role="button"]') || icon;
          clickable.click();
          return {{ok: true, complete: false, row_count: rows.length}};
        }})();
    """


def browser_sync_script(cuij: str) -> str:
    target = json.dumps("".join(char for char in cuij if char.isdigit()))
    return f"""
        window.__gestorSisfeResult = null;
        (async () => {{
          try {{
            const target = {target};
            const currentUser = JSON.parse(localStorage.getItem('currentUser') || 'null');
            if (!currentUser || !currentUser.token) {{
              throw new Error('SISFE no entregó el token de la sesión');
            }}
            const getJson = async (path) => {{
              const response = await fetch(path, {{
                credentials: 'include',
                headers: {{Authorization: 'Bearer ' + currentUser.token}}
              }});
              if (!response.ok) throw new Error('SISFE devolvió ' + response.status + ' al consultar ' + path);
              return response.json();
            }};
{_PAGINATION_HELPERS}
            const selected = await findPaged(
              (page, size) => getJson('/iol/expedientes/findByFilter?diasNovedades=30&page=' + page + '&size=' + size),
              row => JSON.stringify(row).replace(/\\D/g, '').includes(target)
            );
            if (!selected || !selected.id) throw new Error('SISFE no devolvió el expediente seleccionado');
            const details = await getJson('/iol/expedientes/findById?idExpediente=' + encodeURIComponent(selected.id));
            const news = await collectPaged((page, size) => getJson(
              '/iol/expedientes/findNovedadesById?idExpediente=' + encodeURIComponent(selected.id) +
              '&page=' + page + '&size=' + size
            ));
            window.__gestorSisfeResult = {{
              ok: true,
              cuij: target,
              title: details.expCaratula || selected.expCaratula || '',
              tribunal: details.radicado || selected.radicacionActual || '',
              movements: news.map(row => ({{
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
    if not isinstance(payload, dict):
        raise RuntimeError("SISFE devolvió una respuesta inválida.")
    if not payload.get("ok"):
        raise RuntimeError(str(payload.get("error", "SISFE devolvió una respuesta inválida.")))
    movements = tuple(
        SisfeMovementPayload(
            internal_id=str(row.get("internal_id", "")),
            title=str(row.get("title", "Movimiento SISFE")),
            occurred_at=_parse_date(row.get("occurred_at")),
            documents=_documents_from_browser_row(row),
        )
        for row in payload.get("movements", [])
        if isinstance(row, dict)
    )
    return SisfeCaseSnapshot(
        cuij=str(payload.get("cuij", "")),
        title=str(payload.get("title", "")),
        tribunal=str(payload.get("tribunal", "")),
        movements=movements,
        download_warnings=tuple(
            str(warning) for warning in payload.get("warnings", []) if str(warning).strip()
        ),
    )


def _documents_from_browser_row(row: dict) -> tuple[SisfeDocumentPayload, ...]:
    documents: list[SisfeDocumentPayload] = []
    for item in row.get("documents", []):
        if not isinstance(item, dict):
            continue
        encoded = str(item.get("content_base64", ""))
        try:
            content = b64decode(encoded, validate=True)
        except (Base64Error, ValueError) as error:
            raise RuntimeError("SISFE devolvió un documento inválido.") from error
        if not content.startswith(b"%PDF"):
            raise RuntimeError("SISFE devolvió un adjunto que no es PDF.")
        documents.append(
            SisfeDocumentPayload(
                name=str(item.get("name") or "Documento SISFE.pdf"),
                content=content,
                role=str(item.get("role") or ""),
            )
        )
    return tuple(documents)


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
