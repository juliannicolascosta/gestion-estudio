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

from .domain import Expediente
from .models import Case
from .services import read_case_metadata


SCHEMA_VERSION = 1
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
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.connection.execute(
            """
            INSERT INTO expedientes
                (id, folder_path, title, client_name, case_number, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                folder_path,
                record.title,
                record.client_name,
                record.case_number,
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
    def _expediente_from_row(row: sqlite3.Row) -> Expediente:
        return Expediente(
            id=row["id"],
            folder_path=Path(row["folder_path"]),
            title=row["title"],
            client_name=row["client_name"],
            case_number=row["case_number"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
