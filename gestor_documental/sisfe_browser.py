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
            const movement = news.find(row => String(row.id || '') === movementId);
            if (!movement) throw new Error('SISFE no devolvió el movimiento seleccionado');
            window.__gestorSisfeMovement = {{
              ok: true,
              remote_case_id: String(selected.id),
              movement_id: movementId,
              title: String(movement.novedad || movement.tipoActuacion || 'Movimiento SISFE'),
              occurred_at: movement.fecha || null,
              observation: String(movement.observacion || ''),
              has_primary_document: movement.adjunto1 != null,
              has_related_organizations: movement.adjunto2 != null,
              has_additional_documents: movement.adjunto3 != null
            }};
          }} catch (error) {{
            window.__gestorSisfeMovement = {{ok: false, error: String(error.message || error)}};
          }}
        }})();
    """


def browser_movement_documents_script(cuij: str, movement_id: str) -> str:
    target = json.dumps("".join(char for char in cuij if char.isdigit()))
    remote_movement = json.dumps(str(movement_id))
    return f"""
        window.__gestorSisfeDocuments = null;
        (async () => {{
          try {{
            const target = {target};
            const movementId = {remote_movement};
            const currentUser = JSON.parse(localStorage.getItem('currentUser') || 'null');
            if (!currentUser || !currentUser.token) {{
              throw new Error('SISFE no entregó el token de la sesión');
            }}
            const options = {{
              credentials: 'include',
              headers: {{Authorization: 'Bearer ' + currentUser.token}}
            }};
            const getJson = async (path) => {{
              const response = await fetch(path, options);
              if (!response.ok) throw new Error('SISFE devolvió ' + response.status + ' al consultar ' + path);
              return response.json();
            }};
{_PAGINATION_HELPERS}
            const captchaSetting = await getJson('/iol/config/getRecaptchaVisible');
            const captchaRequired = captchaSetting === true || captchaSetting === 1 || captchaSetting === '1';
            const captchaFor = async (action) => {{
              if (!captchaRequired) return '';
              const config = await getJson('/assets/config/config.json');
              const siteKey = config.sitekeyV3;
              if (!siteKey) throw new Error('SISFE no informó la configuración de CAPTCHA');
              if (!window.grecaptcha || !window.grecaptcha.execute) {{
                await new Promise((resolve, reject) => {{
                  const existing = document.querySelector('script[data-gestor-recaptcha]');
                  if (existing) {{
                    existing.addEventListener('load', resolve, {{once: true}});
                    existing.addEventListener('error', reject, {{once: true}});
                    return;
                  }}
                  const script = document.createElement('script');
                  script.src = 'https://www.google.com/recaptcha/api.js?render=' + encodeURIComponent(siteKey);
                  script.async = true;
                  script.dataset.gestorRecaptcha = 'true';
                  script.onload = resolve;
                  script.onerror = () => reject(new Error('No pudimos cargar la validación CAPTCHA'));
                  document.head.appendChild(script);
                }});
              }}
              await new Promise(resolve => window.grecaptcha.ready(resolve));
              return window.grecaptcha.execute(siteKey, {{action: action}});
            }};
            const getPdf = async (path, fallbackName, captchaAction) => {{
              const captcha = await captchaFor(captchaAction);
              const requestPath = captcha
                ? path + '&grecaptchaResponse=' + encodeURIComponent(captcha)
                : path;
              const response = await fetch(requestPath, options);
              if (!response.ok) {{
                if (response.status === 401 || response.status === 403) {{
                  throw new Error('SISFE exige validar nuevamente la sesión o completar el CAPTCHA');
                }}
                throw new Error('SISFE devolvió ' + response.status + ' al descargar el documento');
              }}
              const blob = await response.blob();
              if (!blob.size) throw new Error('SISFE devolvió un documento vacío');
              if (blob.size > 20 * 1024 * 1024) {{
                throw new Error('El documento supera 20 MB; abrilo directamente en SISFE');
              }}
              const dataUrl = await new Promise((resolve, reject) => {{
                const reader = new FileReader();
                reader.onload = () => resolve(String(reader.result));
                reader.onerror = () => reject(new Error('No pudimos leer el documento descargado'));
                reader.readAsDataURL(blob);
              }});
              return {{name: fallbackName, content_base64: dataUrl.split(',', 2)[1] || ''}};
            }};
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
            const movement = news.find(row => String(row.id || '') === movementId);
            if (!movement) throw new Error('SISFE no devolvió el movimiento seleccionado');
            const documents = [];
            const warnings = [];
            const tryDownload = async (label, download) => {{
              try {{
                documents.push(await download());
              }} catch (error) {{
                warnings.push(label + ': ' + String(error.message || error));
              }}
            }};
            if (movement.adjunto1 != null) {{
              await tryDownload('Documento principal', () => getPdf(
                '/iol/actuaciones/findDocumentoAdjuntoById?idActuacion=' + encodeURIComponent(movementId),
                'Movimiento SISFE ' + movementId + '.pdf',
                'findDocumentoAdjuntoById'
              ));
            }}
            if (movement.adjunto3 != null) {{
              try {{
                const attached = await getJson('/iol/cargos/findDocumentosAdjuntosById?idCargo=' +
                  encodeURIComponent(movementId));
                for (const row of (attached.lista || [])) {{
                  await tryDownload('Adjunto de cargo', () => getPdf(
                  '/iol/cargos/findDocumentoAdjuntoByAdjuntoCargoId?idAdjuntoCargo=' +
                    encodeURIComponent(row.idAdjuntoCargo),
                  String(row.adjunto || ('Adjunto SISFE ' + row.idAdjuntoCargo + '.pdf')),
                  'findDocumentoAdjuntoByAdjuntoCargoId'
                  ));
                }}
              }} catch (error) {{
                warnings.push('Adjuntos de cargo: ' + String(error.message || error));
              }}
            }}
            if (!documents.length) {{
              throw new Error(warnings.join(' · ') || 'Este movimiento no tiene documentos descargables');
            }}
            window.__gestorSisfeDocuments = {{
              ok: true,
              cuij: target,
              title: details.expCaratula || selected.expCaratula || '',
              tribunal: details.radicado || selected.radicacionActual || '',
              movements: [{{
                internal_id: movementId,
                title: String(movement.novedad || movement.tipoActuacion || 'Movimiento SISFE'),
                occurred_at: movement.fecha || null,
                documents: documents
              }}],
              warnings: warnings
            }};
          }} catch (error) {{
            window.__gestorSisfeDocuments = {{ok: false, error: String(error.message || error)}};
          }}
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
