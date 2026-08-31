"""Persistencia relacional incremental para la gestión integral del Estudio.

La base se crea sólo cuando una futura pantalla o integración la solicite. No
reordena carpetas ni escribe en ``.gestor-caso.json``: durante la transición,
ese archivo continúa siendo compatible con el gestor documental actual.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .domain import Documento, Expediente, Movimiento, Tarea
from .models import Case
from .services import read_case_metadata


SCHEMA_VERSION = 3
DATABASE_NAME = ".gestor-estudio.sqlite3"


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

    def import_case(self, case: Case) -> Expediente:
        """Register an existing case folder once, preserving its JSON unchanged."""
        folder_path = str(case.path.resolve())
        row = self.connection.execute(
            "SELECT * FROM expedientes WHERE folder_path = ?", (folder_path,)
        ).fetchone()
        if row:
            return self._expediente_from_row(row)

        metadata = read_case_metadata(case)
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
                (id, folder_path, title, client_name, case_number, tribunal, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                folder_path,
                record.title,
                record.client_name,
                record.case_number,
                record.tribunal,
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
        )
        self.connection.execute(
            """
            INSERT INTO movimientos
                (id, expediente_id, title, occurred_at, source, external_id, logical_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.expediente_id,
                record.title,
                record.occurred_at.isoformat() if record.occurred_at else None,
                record.source,
                record.external_id,
                logical_key,
                now,
            ),
        )
        self._audit("movimiento", record.id, "created", now)
        self.connection.commit()
        return record

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

    def find_expediente_by_folder(self, folder_path: Path) -> Expediente | None:
        row = self.connection.execute(
            "SELECT * FROM expedientes WHERE folder_path = ?", (str(Path(folder_path).resolve()),)
        ).fetchone()
        return self._expediente_from_row(row) if row else None

    def list_recent_movements(self, expediente_id: str, limit: int = 20) -> list[Movimiento]:
        """Return newest operational movements first for the expediente inbox."""
        rows = self.connection.execute(
            """
            SELECT * FROM movimientos WHERE expediente_id = ?
            ORDER BY COALESCE(occurred_at, created_at) DESC, created_at DESC
            LIMIT ?
            """,
            (expediente_id, max(1, limit)),
        ).fetchall()
        return [self._movimiento_from_row(row) for row in rows]

    def add_document(
        self,
        expediente_id: str,
        relative_path: Path,
        *,
        sha256: str = "",
        source: str = "local",
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
        )
        self.connection.execute(
            """
            INSERT INTO documentos (id, expediente_id, relative_path, sha256, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (record.id, record.expediente_id, normalized_path, record.sha256, record.source, now),
        )
        self._audit("documento", record.id, "registered", now)
        self.connection.commit()
        return record

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
    def _movimiento_from_row(row: sqlite3.Row) -> Movimiento:
        return Movimiento(
            id=row["id"],
            expediente_id=row["expediente_id"],
            title=row["title"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]) if row["occurred_at"] else None,
            source=row["source"],
            external_id=row["external_id"],
        )

    @staticmethod
    def _documento_from_row(row: sqlite3.Row) -> Documento:
        return Documento(
            id=row["id"],
            expediente_id=row["expediente_id"],
            relative_path=Path(row["relative_path"]),
            sha256=row["sha256"],
            source=row["source"],
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
