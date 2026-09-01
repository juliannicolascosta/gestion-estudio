"""Modelos de dominio independientes de la interfaz y del origen de datos.

Estos tipos no reemplazan todavía los metadatos ``.gestor-caso.json``. Dan una
forma estable de representar la información operativa que se incorporará en la
base SQLite, sin acoplarla a la estructura de carpetas existente.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Expediente:
    """Un expediente vinculado a una carpeta ya existente del Estudio."""

    id: str
    folder_path: Path
    title: str
    client_name: str = ""
    case_number: str = ""
    tribunal: str = ""
    status: str = "activo"
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Movimiento:
    """Hecho procesal u operativo asociado a un expediente."""

    id: str
    expediente_id: str
    title: str
    occurred_at: datetime | None = None
    source: str = "manual"
    external_id: str = ""


@dataclass(frozen=True)
class Documento:
    """Referencia a un archivo; el contenido continúa en la carpeta del caso."""

    id: str
    expediente_id: str
    relative_path: Path
    sha256: str = ""
    source: str = "local"
    category: str = "otro"


@dataclass(frozen=True)
class Tarea:
    """Tarea o vencimiento. La confirmación profesional se modelará explícitamente."""

    id: str
    expediente_id: str
    title: str
    due_at: datetime | None = None
    status: str = "pendiente"
    suggested_by: str = ""
    confirmed_at: datetime | None = None
    confirmed_by: str = ""
