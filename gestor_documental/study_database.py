"""Persistencia relacional incremental para la gestión integral del Estudio.

La base se crea sólo cuando una pantalla o integración la solicita. No reordena
carpetas. ``.gestor-caso.json`` continúa siendo compatible y recibe una única
identidad interna para reconocer el caso después de trasladar el Estudio.
"""

from __future__ import annotations

import sqlite3
import uuid
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .domain import Cliente, Documento, Expediente, Movimiento, Tarea
from .models import Case
from .services import read_case_metadata, save_case_metadata


SCHEMA_VERSION = 9
DATABASE_NAME = ".gestor-estudio.sqlite3"
CASE_IDENTITY_FIELD = "Identificación interna del expediente"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def study_database_path(study_root: Path) -> Path:
    """Return the hidden study-level database path without creating anything."""
    return Path(study_root) / DATABASE_NAME


class StudyDatabase:
    """Small repository with explicit, forward-only SQLite migrations."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        try:
            self.migrate()
        except Exception:
            # SQLite mantiene el archivo bloqueado en Windows hasta cerrar la
            # conexión; incluso una migración rechazada debe liberar el lock.
            self.connection.close()
            raise

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def migrate(self):
        current = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        if current > SCHEMA_VERSION:
            raise RuntimeError("La base pertenece a una versión más nueva del Gestor.")
        if current < 1:
            self._migrate_to_1()
            self.connection.execute("PRAGMA user_version = 1")
            current = 1
        if current < 2:
            self._migrate_to_2()
            self.connection.execute("PRAGMA user_version = 2")
            current = 2
        if current < 3:
            self._migrate_to_3()
            self.connection.execute("PRAGMA user_version = 3")
            current = 3
        if current < 4:
            self._migrate_to_4()
            self.connection.execute("PRAGMA user_version = 4")
            current = 4
        if current < 5:
            self._migrate_to_5()
            self.connection.execute("PRAGMA user_version = 5")
            current = 5
        if current < 6:
            self._migrate_to_6()
            self.connection.execute("PRAGMA user_version = 6")
            current = 6
        if current < 7:
            self._migrate_to_7()
            self.connection.execute("PRAGMA user_version = 7")
            current = 7
        if current < 8:
            self._migrate_to_8()
            self.connection.execute("PRAGMA user_version = 8")
            current = 8
        if current < 9:
            self._migrate_to_9()
            self.connection.execute("PRAGMA user_version = 9")
        self.connection.commit()

    def _migrate_to_1(self):
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS expedientes (
                id TEXT PRIMARY KEY,
                folder_path TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                client_name TEXT NOT NULL DEFAULT '',
                case_number TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'activo',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS movimientos (
                id TEXT PRIMARY KEY,
                expediente_id TEXT NOT NULL REFERENCES expedientes(id),
                title TEXT NOT NULL,
                occurred_at TEXT,
                source TEXT NOT NULL DEFAULT 'manual',
                external_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documentos (
                id TEXT PRIMARY KEY,
                expediente_id TEXT NOT NULL REFERENCES expedientes(id),
                relative_path TEXT NOT NULL,
                sha256 TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'local',
                created_at TEXT NOT NULL,
                UNIQUE(expediente_id, relative_path)
            );

            CREATE TABLE IF NOT EXISTS tareas (
                id TEXT PRIMARY KEY,
                expediente_id TEXT NOT NULL REFERENCES expedientes(id),
                title TEXT NOT NULL,
                due_at TEXT,
                status TEXT NOT NULL DEFAULT 'pendiente',
                suggested_by TEXT NOT NULL DEFAULT '',
                confirmed_at TEXT,
                confirmed_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                actor TEXT NOT NULL DEFAULT '',
                details_json TEXT NOT NULL DEFAULT '{}'
            );

            -- Los movimientos manuales no tienen ID externo; los que sí lo
            -- tengan quedan deduplicados sin impedir múltiples altas manuales.
            CREATE UNIQUE INDEX IF NOT EXISTS movimientos_external_identity
            ON movimientos(source, external_id)
            WHERE external_id <> '';
            """
        )

    def _migrate_to_2(self):
        """Add a stable fallback identity for sources whose ID is unavailable."""
        self.connection.execute(
            "ALTER TABLE movimientos ADD COLUMN logical_key TEXT NOT NULL DEFAULT ''"
        )

    def _migrate_to_3(self):
        self.connection.execute(
            "ALTER TABLE expedientes ADD COLUMN tribunal TEXT NOT NULL DEFAULT ''"
        )
        self.connection.execute(
            """
            CREATE UNIQUE INDEX movimientos_logical_identity
            ON movimientos(expediente_id, source, logical_key)
            WHERE logical_key <> ''
            """
        )

    def _migrate_to_4(self):
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(documentos)")}
        if "category" not in columns:
            self.connection.execute("ALTER TABLE documentos ADD COLUMN category TEXT NOT NULL DEFAULT 'otro'")

    def _migrate_to_5(self):
        """Relate downloaded files to one or more procedural movements."""
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS movimiento_documentos (
                movimiento_id TEXT NOT NULL REFERENCES movimientos(id) ON DELETE CASCADE,
                documento_id TEXT NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
                role TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                PRIMARY KEY (movimiento_id, documento_id)
            );
            CREATE INDEX IF NOT EXISTS movimiento_documentos_documento
            ON movimiento_documentos(documento_id);
            """
        )

    def _migrate_to_6(self):
        """Add a shared client record without changing case folders or JSON."""
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(expedientes)")}
        if "client_id" not in columns:
            self.connection.execute("ALTER TABLE expedientes ADD COLUMN client_id TEXT NOT NULL DEFAULT ''")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS clientes (
                id TEXT PRIMARY KEY,
                identity_key TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL DEFAULT '',
                dni TEXT NOT NULL DEFAULT '',
                cuil TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS expedientes_client_id ON expedientes(client_id);
            """
        )

    def _migrate_to_7(self):
        """Add an identity that survives changes to the absolute folder path."""
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(expedientes)")}
        if "case_identity" not in columns:
            self.connection.execute(
                "ALTER TABLE expedientes ADD COLUMN case_identity TEXT NOT NULL DEFAULT ''"
            )
        self.connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS expedientes_portable_identity
            ON expedientes(case_identity) WHERE case_identity <> ''
            """
        )

    def _migrate_to_8(self):
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(movimientos)")}
        if "movement_kind" not in columns:
            self.connection.execute("ALTER TABLE movimientos ADD COLUMN movement_kind TEXT NOT NULL DEFAULT 'otro'")
        if "document_available" not in columns:
            self.connection.execute("ALTER TABLE movimientos ADD COLUMN document_available INTEGER NOT NULL DEFAULT 0")

    def _migrate_to_9(self):
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(movimientos)")}
        for name in ("observation", "presenter", "cargo_number"):
            if name not in columns:
                self.connection.execute(
                    f"ALTER TABLE movimientos ADD COLUMN {name} TEXT NOT NULL DEFAULT ''"
                )
        for row in self.connection.execute("SELECT id, title FROM movimientos").fetchall():
            normalized = unicodedata.normalize("NFKD", str(row["title"]).casefold())
            normalized = "".join(
                char for char in normalized if not unicodedata.combining(char)
            )
            if re.search(r"\bcedula\b", normalized):
                self.connection.execute(
                    "UPDATE movimientos SET movement_kind = 'cedula' WHERE id = ?",
                    (row["id"],),
                )

    @staticmethod
    def _client_values(metadata: dict[str, str]) -> dict[str, str]:
        name = (metadata.get("Nombre completo") or metadata.get("Actor") or "").strip()
        if not name:
            surname = metadata.get("Apellido del actor", "").strip()
            names = metadata.get("Nombres del actor", "").strip()
            name = ", ".join(part for part in (surname, names) if part)
        return {
            "name": name,
            "dni": (metadata.get("DNI del actor") or metadata.get("DNI/CUIT actor") or "").strip(),
            "cuil": metadata.get("CUIL del actor", "").strip(),
            "phone": metadata.get("Teléfono del actor", "").strip(),
            "email": metadata.get("Correo electrónico del actor", "").strip(),
            "address": (metadata.get("Domicilio real") or metadata.get("Domicilio actor") or "").strip(),
        }

    @staticmethod
    def _client_identity(values: dict[str, str]) -> str:
        for field in ("cuil", "dni"):
            digits = re.sub(r"\D", "", values[field])
            if digits:
                return f"{field}:{digits}"
        normalized = unicodedata.normalize("NFKD", values["name"].casefold())
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        normalized = " ".join(normalized.split())
        return f"name:{normalized}" if normalized else ""

    def sync_client_from_metadata(self, metadata: dict[str, str]) -> Cliente | None:
        """Create a minimal central profile, preserving already known details."""
        values = self._client_values(metadata)
        identity_key = self._client_identity(values)
        if not identity_key:
            return None
        row = self.connection.execute(
            "SELECT * FROM clientes WHERE identity_key = ?", (identity_key,)
        ).fetchone()
        now = utc_now().isoformat()
        if not row:
            record = Cliente(id=str(uuid.uuid4()), identity_key=identity_key, **values)
            self.connection.execute(
                """INSERT INTO clientes
                (id, identity_key, name, dni, cuil, phone, email, address, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (record.id, record.identity_key, record.name, record.dni, record.cuil,
                 record.phone, record.email, record.address, now, now),
            )
            self.connection.commit()
            return record
        merged = {field: row[field] or values[field] for field in values}
        if any(merged[field] != row[field] for field in values):
            self.connection.execute(
                """UPDATE clientes SET name = ?, dni = ?, cuil = ?, phone = ?, email = ?,
                address = ?, updated_at = ? WHERE id = ?""",
                (merged["name"], merged["dni"], merged["cuil"], merged["phone"],
                 merged["email"], merged["address"], now, row["id"]),
            )
            self.connection.commit()
            row = self.connection.execute("SELECT * FROM clientes WHERE id = ?", (row["id"],)).fetchone()
        return self._cliente_from_row(row)

    def list_client_cases(self, client_id: str) -> list[Expediente]:
        rows = self.connection.execute(
            "SELECT * FROM expedientes WHERE client_id = ? ORDER BY title COLLATE NOCASE", (client_id,)
        ).fetchall()
        return [self._expediente_from_row(row) for row in rows]

    def find_client_by_case_folder(self, folder_path: Path) -> Cliente | None:
        """Return the shared client profile without changing case metadata."""
        row = self.connection.execute(
            """
            SELECT clientes.*
            FROM expedientes
            INNER JOIN clientes ON clientes.id = expedientes.client_id
            WHERE expedientes.folder_path = ?
            """,
            (str(Path(folder_path).resolve()),),
        ).fetchone()
        return self._cliente_from_row(row) if row else None

    def import_case(self, case: Case) -> Expediente:
        """Register or refresh a case folder using a portable identity.

        ``.gestor-caso.json`` remains the source of truth during the transition
        to SQLite.  Reopening or saving a case therefore refreshes the small
        relational projection used by movements, documents and tasks.  Remote
        context received from SISFE is kept when the local JSON has no value.
        """
        folder_path = str(case.path.resolve())
        metadata = read_case_metadata(case)
        client = self.sync_client_from_metadata(metadata)
        client_id = client.id if client else ""
        row = self.connection.execute(
            "SELECT * FROM expedientes WHERE folder_path = ?", (folder_path,)
        ).fetchone()
        case_identity = metadata.get(CASE_IDENTITY_FIELD, "").strip()
        if row is None and case_identity:
            row = self.connection.execute(
                "SELECT * FROM expedientes WHERE case_identity = ?", (case_identity,)
            ).fetchone()
            if row:
                previous_path = Path(row["folder_path"])
                if previous_path.exists() and previous_path.resolve() != case.path.resolve():
                    raise RuntimeError(
                        "Hay dos carpetas con la misma identidad interna. "
                        "El Gestor no puede decidir cuál es el expediente original."
                    )
                now = utc_now().isoformat()
                self.connection.execute(
                    "UPDATE expedientes SET folder_path = ?, title = ?, updated_at = ? WHERE id = ?",
                    (folder_path, case.name, now, row["id"]),
                )
                self._audit("expediente", row["id"], "portable_path_recovered", now)
                self.connection.commit()
                row = self.connection.execute(
                    "SELECT * FROM expedientes WHERE id = ?", (row["id"],)
                ).fetchone()
        if row:
            if not case_identity:
                case_identity = self._assign_case_identity(case, metadata)
            title = case.name
            client_name = metadata.get("Actor", "").strip()
            case_number = metadata.get("CUIJ", "").strip() or row["case_number"]
            tribunal = metadata.get("Juzgado o tribunal", "").strip() or row["tribunal"]
            changed = any(
                (
                    title != row["title"],
                    client_name != row["client_name"],
                    case_number != row["case_number"],
                    tribunal != row["tribunal"],
                    client_id != row["client_id"],
                    case_identity != row["case_identity"],
                )
            )
            if changed:
                now = utc_now().isoformat()
                self.connection.execute(
                    """
                    UPDATE expedientes
                    SET title = ?, client_name = ?, case_number = ?, tribunal = ?,
                        client_id = ?, case_identity = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (title, client_name, case_number, tribunal, client_id, case_identity, now, row["id"]),
                )
                self._audit("expediente", row["id"], "synced_from_case_metadata", now)
                self.connection.commit()
                row = self.connection.execute(
                    "SELECT * FROM expedientes WHERE id = ?", (row["id"],)
                ).fetchone()
            return self._expediente_from_row(row)

        if not case_identity:
            case_identity = self._assign_case_identity(case, metadata)
        now = utc_now().isoformat()
        record = Expediente(
            id=str(uuid.uuid4()),
            folder_path=case.path.resolve(),
            title=case.name,
            client_name=metadata.get("Actor", ""),
            case_number=metadata.get("CUIJ", ""),
            tribunal=metadata.get("Juzgado o tribunal", ""),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.connection.execute(
            """
            INSERT INTO expedientes
                (id, folder_path, title, client_name, case_number, tribunal, client_id,
                 case_identity, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                folder_path,
                record.title,
                record.client_name,
                record.case_number,
                record.tribunal,
                client_id,
                case_identity,
                record.status,
                now,
                now,
            ),
        )
        self.connection.execute(
            """
            INSERT INTO audit_events (id, entity_type, entity_id, action, occurred_at)
            VALUES (?, 'expediente', ?, 'imported_from_case_folder', ?)
            """,
            (str(uuid.uuid4()), record.id, now),
        )
        self.connection.commit()
        return record

    @staticmethod
    def _assign_case_identity(case: Case, metadata: dict[str, str]) -> str:
        identity = f"GD-{uuid.uuid4().hex.upper()}"
        updated = dict(metadata)
        updated[CASE_IDENTITY_FIELD] = identity
        save_case_metadata(case, updated)
        metadata[CASE_IDENTITY_FIELD] = identity
        return identity

    def relocate_case(self, previous_folder_path: Path, case: Case) -> Expediente:
        """Keep the relational identity when the user renames a case folder."""
        previous = str(Path(previous_folder_path).resolve())
        row = self.connection.execute(
            "SELECT * FROM expedientes WHERE folder_path = ?", (previous,)
        ).fetchone()
        if not row:
            return self.import_case(case)
        metadata = read_case_metadata(case)
        client = self.sync_client_from_metadata(metadata)
        case_identity = metadata.get(CASE_IDENTITY_FIELD, "").strip() or row["case_identity"]
        if not case_identity:
            case_identity = self._assign_case_identity(case, metadata)
        now = utc_now().isoformat()
        self.connection.execute(
            """
            UPDATE expedientes
            SET folder_path = ?, title = ?, client_name = ?,
                case_number = ?, tribunal = ?, client_id = ?, case_identity = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                str(case.path.resolve()),
                case.name,
                metadata.get("Actor", "").strip(),
                metadata.get("CUIJ", "").strip() or row["case_number"],
                metadata.get("Juzgado o tribunal", "").strip() or row["tribunal"],
                client.id if client else "",
                case_identity,
                now,
                row["id"],
            ),
        )
        self._audit("expediente", row["id"], "case_folder_relocated", now)
        self.connection.commit()
        updated = self.connection.execute(
            "SELECT * FROM expedientes WHERE id = ?", (row["id"],)
        ).fetchone()
        return self._expediente_from_row(updated)

    def fill_sisfe_context(self, expediente_id: str, cuij: str, tribunal: str) -> Expediente:
        """Fill missing operational context without replacing user-entered case data."""
        row = self.connection.execute("SELECT * FROM expedientes WHERE id = ?", (expediente_id,)).fetchone()
        if not row:
            raise KeyError("No encontramos el expediente a actualizar.")
        case_number = row["case_number"] or cuij.strip()
        court = row["tribunal"] or tribunal.strip()
        if case_number == row["case_number"] and court == row["tribunal"]:
            return self._expediente_from_row(row)
        now = utc_now().isoformat()
        self.connection.execute(
            """
            UPDATE expedientes SET case_number = ?, tribunal = ?, updated_at = ? WHERE id = ?
            """,
            (case_number, court, now, expediente_id),
        )
        self._audit("expediente", expediente_id, "sisfe_context_received", now)
        self.connection.commit()
        updated = self.connection.execute("SELECT * FROM expedientes WHERE id = ?", (expediente_id,)).fetchone()
        return self._expediente_from_row(updated)

    def add_movement(
        self,
        expediente_id: str,
        title: str,
        *,
        occurred_at: datetime | None = None,
        source: str = "manual",
        external_id: str = "",
        logical_key: str = "",
        movement_kind: str = "otro",
        document_available: bool = False,
        observation: str = "",
        presenter: str = "",
        cargo_number: str = "",
    ) -> Movimiento:
        """Add a movement, or return the existing one for an external ID."""
        title = title.strip()
        source = source.strip() or "manual"
        external_id = external_id.strip()
        logical_key = logical_key.strip()
        if not title:
            raise ValueError("El movimiento necesita una descripción.")
        if external_id:
            row = self.connection.execute(
                "SELECT * FROM movimientos WHERE source = ? AND external_id = ?",
                (source, external_id),
            ).fetchone()
            if row:
                if movement_kind != "otro" or document_available or observation or presenter or cargo_number:
                    self.connection.execute(
                        """
                        UPDATE movimientos
                        SET movement_kind = CASE WHEN ? <> 'otro' THEN ? ELSE movement_kind END,
                            document_available = MAX(document_available, ?),
                            observation = CASE WHEN ? <> '' THEN ? ELSE observation END,
                            presenter = CASE WHEN ? <> '' THEN ? ELSE presenter END,
                            cargo_number = CASE WHEN ? <> '' THEN ? ELSE cargo_number END
                        WHERE id = ?
                        """,
                        (
                            movement_kind, movement_kind, int(document_available),
                            observation, observation, presenter, presenter,
                            cargo_number, cargo_number, row["id"],
                        ),
                    )
                    self.connection.commit()
                    row = self.connection.execute(
                        "SELECT * FROM movimientos WHERE id = ?", (row["id"],)
                    ).fetchone()
                return self._movimiento_from_row(row)
        if logical_key:
            row = self.connection.execute(
                """
                SELECT * FROM movimientos
                WHERE expediente_id = ? AND source = ? AND logical_key = ?
                """,
                (expediente_id, source, logical_key),
            ).fetchone()
            if row:
                return self._movimiento_from_row(row)
        now = utc_now().isoformat()
        record = Movimiento(
            id=str(uuid.uuid4()),
            expediente_id=expediente_id,
            title=title,
            occurred_at=occurred_at,
            source=source,
            external_id=external_id,
            movement_kind=movement_kind,
            document_available=document_available,
            observation=observation.strip(),
            presenter=presenter.strip(),
            cargo_number=cargo_number.strip(),
        )
        self.connection.execute(
            """
            INSERT INTO movimientos
                (id, expediente_id, title, occurred_at, source, external_id, logical_key,
                 movement_kind, document_available, observation, presenter, cargo_number, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.expediente_id,
                record.title,
                record.occurred_at.isoformat() if record.occurred_at else None,
                record.source,
                record.external_id,
                logical_key,
                record.movement_kind,
                int(record.document_available),
                record.observation,
                record.presenter,
                record.cargo_number,
                now,
            ),
        )
        self._audit("movimiento", record.id, "created", now)
        self.connection.commit()
        return record

    def find_movement_by_external_id(
        self,
        expediente_id: str,
        external_id: str,
        *,
        source: str = "sisfe",
    ) -> Movimiento | None:
        row = self.connection.execute(
            """
            SELECT * FROM movimientos
            WHERE expediente_id = ? AND source = ? AND external_id = ?
            """,
            (expediente_id, source.strip() or "sisfe", external_id.strip()),
        ).fetchone()
        return self._movimiento_from_row(row) if row else None

    def find_document_by_sha256(self, expediente_id: str, sha256: str) -> Documento | None:
        """Find a previously registered content hash within an expediente."""
        digest = sha256.strip().lower()
        if not digest:
            return None
        row = self.connection.execute(
            "SELECT * FROM documentos WHERE expediente_id = ? AND sha256 = ?",
            (expediente_id, digest),
        ).fetchone()
        return self._documento_from_row(row) if row else None

    def list_documents(self, expediente_id: str) -> list[Documento]:
        """Return registered files so the UI can show their operational category."""
        rows = self.connection.execute(
            "SELECT * FROM documentos WHERE expediente_id = ? ORDER BY relative_path",
            (expediente_id,),
        ).fetchall()
        return [self._documento_from_row(row) for row in rows]

    def find_expediente_by_folder(self, folder_path: Path) -> Expediente | None:
        row = self.connection.execute(
            "SELECT * FROM expedientes WHERE folder_path = ?", (str(Path(folder_path).resolve()),)
        ).fetchone()
        return self._expediente_from_row(row) if row else None

    def set_document_category(self, expediente_id: str, relative_path: Path, category: str) -> None:
        allowed = {"judicial", "parte", "cedula", "audiencia", "otro"}
        normalized = category.strip().casefold()
        if normalized not in allowed:
            raise ValueError("La categoría de documento no es válida.")
        path = Path(relative_path).as_posix()
        self.connection.execute(
            "UPDATE documentos SET category = ? WHERE expediente_id = ? AND relative_path = ?",
            (normalized, expediente_id, path),
        )
        self.connection.commit()

    def list_recent_movements(
        self, expediente_id: str, limit: int | None = 20
    ) -> list[Movimiento]:
        """Return newest operational movements first for the expediente inbox."""
        sql = """
            SELECT * FROM movimientos WHERE expediente_id = ?
            ORDER BY COALESCE(occurred_at, created_at) DESC, created_at DESC
        """
        parameters: tuple[object, ...] = (expediente_id,)
        if limit is not None:
            sql += " LIMIT ?"
            parameters += (max(1, int(limit)),)
        rows = self.connection.execute(sql, parameters).fetchall()
        return [self._movimiento_from_row(row) for row in rows]

    def relocate_documents(self, expediente_id: str, previous: Path, current: Path) -> int:
        """Move registered paths without changing document identity or links."""
        previous, current = Path(previous), Path(current)
        for path in (previous, current):
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError("La ruta debe estar dentro del expediente.")
        if previous == current:
            return 0
        changes = []
        for document in self.list_documents(expediente_id):
            try:
                suffix = document.relative_path.relative_to(previous)
            except ValueError:
                continue
            changes.append((document.id, (current / suffix).as_posix()))
        # Preflight all destinations before changing any record.
        for document_id, destination in changes:
            occupied = self.connection.execute(
                "SELECT id FROM documentos WHERE expediente_id = ? AND relative_path = ?",
                (expediente_id, destination),
            ).fetchone()
            if occupied and occupied["id"] != document_id:
                raise ValueError("El destino ya tiene un documento registrado; no se modificó el vínculo.")
        with self.connection:
            for document_id, destination in changes:
                self.connection.execute(
                    "UPDATE documentos SET relative_path = ? WHERE id = ?",
                    (destination, document_id),
                )
                self._audit("documento", document_id, "path_relocated", utc_now().isoformat())
        return len(changes)

    def add_document(
        self,
        expediente_id: str,
        relative_path: Path,
        *,
        sha256: str = "",
        source: str = "local",
        category: str = "otro",
    ) -> Documento:
        """Register a file reference; the file remains in its case folder."""
        relative_path = Path(relative_path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("El documento debe estar expresado dentro de la carpeta del expediente.")
        normalized_path = relative_path.as_posix()
        if not normalized_path or normalized_path == ".":
            raise ValueError("Indicá el archivo del documento.")
        row = self.connection.execute(
            "SELECT * FROM documentos WHERE expediente_id = ? AND relative_path = ?",
            (expediente_id, normalized_path),
        ).fetchone()
        if row:
            return self._documento_from_row(row)
        now = utc_now().isoformat()
        record = Documento(
            id=str(uuid.uuid4()),
            expediente_id=expediente_id,
            relative_path=Path(normalized_path),
            sha256=sha256.strip().lower(),
            source=source.strip() or "local",
            category=category.strip().casefold() or "otro",
        )
        self.connection.execute(
            """
            INSERT INTO documentos (id, expediente_id, relative_path, sha256, source, category, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (record.id, record.expediente_id, normalized_path, record.sha256, record.source, record.category, now),
        )
        self._audit("documento", record.id, "registered", now)
        self.connection.commit()
        return record

    def link_document_to_movement(
        self,
        movement_id: str,
        document_id: str,
        *,
        role: str = "",
    ) -> None:
        """Associate a stored document with its source movement idempotently."""
        if not movement_id.strip() or not document_id.strip():
            raise ValueError("Movimiento y documento son obligatorios para vincularlos.")
        now = utc_now().isoformat()
        self.connection.execute(
            """
            INSERT INTO movimiento_documentos (movimiento_id, documento_id, role, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(movimiento_id, documento_id) DO UPDATE SET role = excluded.role
            """,
            (movement_id, document_id, role.strip().casefold(), now),
        )
        self.connection.commit()

    def list_movement_documents(self, movement_id: str) -> list[Documento]:
        rows = self.connection.execute(
            """
            SELECT documentos.* FROM documentos
            INNER JOIN movimiento_documentos
                ON movimiento_documentos.documento_id = documentos.id
            WHERE movimiento_documentos.movimiento_id = ?
            ORDER BY movimiento_documentos.created_at, documentos.relative_path
            """,
            (movement_id,),
        ).fetchall()
        return [self._documento_from_row(row) for row in rows]

    def suggest_task(
        self,
        expediente_id: str,
        title: str,
        *,
        due_at: datetime | None = None,
        suggested_by: str = "",
    ) -> Tarea:
        """Create an informational task; it remains unconfirmed by default."""
        title = title.strip()
        if not title:
            raise ValueError("La tarea necesita una descripción.")
        now = utc_now().isoformat()
        record = Tarea(
            id=str(uuid.uuid4()),
            expediente_id=expediente_id,
            title=title,
            due_at=due_at,
            suggested_by=suggested_by.strip(),
        )
        self.connection.execute(
            """
            INSERT INTO tareas
                (id, expediente_id, title, due_at, status, suggested_by, confirmed_at, confirmed_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL, '', ?)
            """,
            (
                record.id,
                record.expediente_id,
                record.title,
                record.due_at.isoformat() if record.due_at else None,
                record.status,
                record.suggested_by,
                now,
            ),
        )
        self._audit("tarea", record.id, "suggested", now)
        self.connection.commit()
        return record

    def confirm_task(self, task_id: str, professional: str) -> Tarea:
        """Confirm a suggested deadline with the accountable professional."""
        professional = professional.strip()
        if not professional:
            raise ValueError("Indicá el profesional que confirma el vencimiento.")
        row = self.connection.execute("SELECT * FROM tareas WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise KeyError("No encontramos la tarea a confirmar.")
        now = utc_now().isoformat()
        self.connection.execute(
            """
            UPDATE tareas
            SET status = 'confirmada', confirmed_at = ?, confirmed_by = ?
            WHERE id = ?
            """,
            (now, professional, task_id),
        )
        self._audit("tarea", task_id, "confirmed", now, professional)
        self.connection.commit()
        confirmed = self.connection.execute("SELECT * FROM tareas WHERE id = ?", (task_id,)).fetchone()
        return self._tarea_from_row(confirmed)

    def list_tasks(self, expediente_id: str) -> list[Tarea]:
        rows = self.connection.execute(
            """
            SELECT * FROM tareas WHERE expediente_id = ?
            ORDER BY COALESCE(due_at, created_at), created_at
            """,
            (expediente_id,),
        ).fetchall()
        return [self._tarea_from_row(row) for row in rows]

    def create_manual_task(
        self,
        expediente_id: str,
        title: str,
        professional: str,
        *,
        due_at: datetime | None = None,
    ) -> Tarea:
        suggested = self.suggest_task(
            expediente_id, title, due_at=due_at, suggested_by="manual"
        )
        return self.confirm_task(suggested.id, professional)

    def update_manual_task(
        self,
        task_id: str,
        title: str,
        professional: str,
        *,
        due_at: datetime | None = None,
    ) -> Tarea:
        title = title.strip()
        professional = professional.strip()
        if not title:
            raise ValueError("La tarea necesita una descripción.")
        if not professional:
            raise ValueError("Indicá el profesional que modifica la tarea.")
        row = self.connection.execute("SELECT * FROM tareas WHERE id = ?", (task_id,)).fetchone()
        if not row or row["suggested_by"] != "manual":
            raise KeyError("No encontramos la tarea manual.")
        if row["status"] == "completada":
            raise ValueError("Una tarea completada no puede modificarse.")
        now = utc_now().isoformat()
        self.connection.execute(
            "UPDATE tareas SET title = ?, due_at = ? WHERE id = ?",
            (title, due_at.isoformat() if due_at else None, task_id),
        )
        self._audit("tarea", task_id, "updated", now, professional)
        self.connection.commit()
        updated = self.connection.execute("SELECT * FROM tareas WHERE id = ?", (task_id,)).fetchone()
        return self._tarea_from_row(updated)

    def complete_task(self, task_id: str, professional: str) -> Tarea:
        professional = professional.strip()
        if not professional:
            raise ValueError("Indicá el profesional que completa la tarea.")
        row = self.connection.execute("SELECT * FROM tareas WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise KeyError("No encontramos la tarea confirmada.")
        task = self._tarea_from_row(row)
        if task.status == "completada":
            return task
        if task.status != "confirmada":
            raise ValueError("La tarea debe estar confirmada antes de completarla.")
        now = utc_now().isoformat()
        self.connection.execute("UPDATE tareas SET status = 'completada' WHERE id = ?", (task.id,))
        self._audit("tarea", task.id, "completed", now, professional)
        self.connection.commit()
        completed = self.connection.execute("SELECT * FROM tareas WHERE id = ?", (task.id,)).fetchone()
        return self._tarea_from_row(completed)

    def confirm_activity_task(
        self,
        expediente_id: str,
        title: str,
        professional: str,
        *,
        due_at: datetime | None = None,
        task_key: str,
    ) -> Tarea:
        """Confirm an activity once; repeated clicks return the same task."""
        key = task_key.strip()
        if not key:
            raise ValueError("La tarea necesita identificar la actividad de origen.")
        existing = self.connection.execute(
            "SELECT * FROM tareas WHERE expediente_id = ? AND suggested_by = ? ORDER BY created_at LIMIT 1",
            (expediente_id, key),
        ).fetchone()
        if existing:
            task = self._tarea_from_row(existing)
            return task if task.status in {"confirmada", "completada"} else self.confirm_task(task.id, professional)
        suggested = self.suggest_task(
            expediente_id,
            title,
            due_at=due_at,
            suggested_by=key,
        )
        return self.confirm_task(suggested.id, professional)

    def complete_activity_task(self, expediente_id: str, task_key: str, professional: str) -> Tarea:
        row = self.connection.execute(
            "SELECT * FROM tareas WHERE expediente_id = ? AND suggested_by = ? ORDER BY created_at LIMIT 1",
            (expediente_id, task_key.strip()),
        ).fetchone()
        if not row:
            raise KeyError("No encontramos la tarea confirmada.")
        return self.complete_task(row["id"], professional)

    def _audit(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        occurred_at: str,
        actor: str = "",
    ):
        self.connection.execute(
            """
            INSERT INTO audit_events (id, entity_type, entity_id, action, occurred_at, actor)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), entity_type, entity_id, action, occurred_at, actor),
        )

    @staticmethod
    def _expediente_from_row(row: sqlite3.Row) -> Expediente:
        return Expediente(
            id=row["id"],
            folder_path=Path(row["folder_path"]),
            title=row["title"],
            client_name=row["client_name"],
            case_number=row["case_number"],
            tribunal=row["tribunal"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _cliente_from_row(row: sqlite3.Row) -> Cliente:
        return Cliente(
            id=row["id"], identity_key=row["identity_key"], name=row["name"], dni=row["dni"],
            cuil=row["cuil"], phone=row["phone"], email=row["email"], address=row["address"],
        )

    @staticmethod
    def _movimiento_from_row(row: sqlite3.Row) -> Movimiento:
        return Movimiento(
            id=row["id"],
            expediente_id=row["expediente_id"],
            title=row["title"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]) if row["occurred_at"] else None,
            source=row["source"],
            external_id=row["external_id"],
            movement_kind=row["movement_kind"] if "movement_kind" in row.keys() else "otro",
            document_available=bool(row["document_available"]) if "document_available" in row.keys() else False,
            observation=row["observation"] if "observation" in row.keys() else "",
            presenter=row["presenter"] if "presenter" in row.keys() else "",
            cargo_number=row["cargo_number"] if "cargo_number" in row.keys() else "",
        )

    @staticmethod
    def _documento_from_row(row: sqlite3.Row) -> Documento:
        return Documento(
            id=row["id"],
            expediente_id=row["expediente_id"],
            relative_path=Path(row["relative_path"]),
            sha256=row["sha256"],
            source=row["source"],
            category=row["category"] if "category" in row.keys() else "otro",
        )

    @staticmethod
    def _tarea_from_row(row: sqlite3.Row) -> Tarea:
        return Tarea(
            id=row["id"],
            expediente_id=row["expediente_id"],
            title=row["title"],
            due_at=datetime.fromisoformat(row["due_at"]) if row["due_at"] else None,
            status=row["status"],
            suggested_by=row["suggested_by"],
            confirmed_at=datetime.fromisoformat(row["confirmed_at"]) if row["confirmed_at"] else None,
            confirmed_by=row["confirmed_by"],
        )
