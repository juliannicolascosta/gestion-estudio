"""Respaldos autocontenidos y verificables de una Ubicacion del Estudio."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

from .study_database import DATABASE_NAME


MANIFEST_NAME = ".gestor-respaldo.json"
BACKUP_FORMAT = "gestor-documental-study-backup"
BACKUP_VERSION = 1
ProgressCallback = Callable[[int, int, str], None]


class StudyBackupError(RuntimeError):
    """Error controlado al crear, validar o restaurar un respaldo."""


@dataclass(frozen=True)
class BackupResult:
    path: Path
    file_count: int
    total_bytes: int
    archive_sha256: str


@dataclass(frozen=True)
class BackupValidation:
    path: Path
    study_name: str
    file_count: int
    total_bytes: int


@dataclass(frozen=True)
class RestoreResult:
    root: Path
    file_count: int
    total_bytes: int


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_stream(source) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _safe_relative_path(raw: object) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise StudyBackupError("El respaldo contiene una ruta de archivo invalida.")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise StudyBackupError("El respaldo contiene una ruta fuera de la ubicacion permitida.")
    if relative.as_posix() == MANIFEST_NAME:
        raise StudyBackupError("El manifiesto no puede figurar como documento del Estudio.")
    return relative


def _snapshot_database(source: Path, destination: Path) -> None:
    origin = None
    snapshot = None
    try:
        origin = sqlite3.connect(source)
        snapshot = sqlite3.connect(destination)
        origin.backup(snapshot)
    except sqlite3.Error as error:
        raise StudyBackupError(f"No pudimos obtener una copia coherente de la base: {error}") from error
    finally:
        if snapshot is not None:
            snapshot.close()
        if origin is not None:
            origin.close()


def create_study_backup(
    study_root: Path,
    destination: Path,
    progress: ProgressCallback | None = None,
) -> BackupResult:
    """Create an atomic ZIP backup containing every regular file in a Study."""
    root = Path(study_root).resolve()
    target = Path(destination).resolve()
    if not root.is_dir():
        raise StudyBackupError("La Ubicacion del Estudio ya no esta disponible.")
    if target == root or root in target.parents:
        raise StudyBackupError("Guarda el respaldo fuera de la Ubicacion del Estudio.")
    target.parent.mkdir(parents=True, exist_ok=True)

    files: list[tuple[Path, str]] = []
    database_sidecars = {f"{DATABASE_NAME}-wal", f"{DATABASE_NAME}-shm", f"{DATABASE_NAME}-journal"}
    for path in sorted(root.rglob("*"), key=lambda item: str(item).casefold()):
        if path.is_symlink():
            raise StudyBackupError(f"No se admiten accesos vinculados en el respaldo: {path}")
        if path.is_file() and not (path.parent == root and path.name in database_sidecars):
            files.append((path, path.relative_to(root).as_posix()))

    temporary_archive = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    manifest_files: list[dict[str, object]] = []
    total_bytes = 0
    try:
        with tempfile.TemporaryDirectory(prefix="gestor-respaldo-") as temp_dir:
            snapshot_path = Path(temp_dir) / DATABASE_NAME
            database_path = root / DATABASE_NAME
            if database_path.is_file():
                _snapshot_database(database_path, snapshot_path)

            with zipfile.ZipFile(
                temporary_archive,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
                allowZip64=True,
            ) as archive:
                for index, (source_path, relative) in enumerate(files, start=1):
                    archive_source = snapshot_path if source_path == database_path else source_path
                    size = archive_source.stat().st_size
                    digest = _sha256_file(archive_source)
                    archive.write(archive_source, relative)
                    manifest_files.append({"path": relative, "size": size, "sha256": digest})
                    total_bytes += size
                    if progress:
                        progress(index, len(files), relative)

                manifest = {
                    "format": BACKUP_FORMAT,
                    "version": BACKUP_VERSION,
                    "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    "study_name": root.name or "Estudio",
                    "files": manifest_files,
                }
                archive.writestr(
                    MANIFEST_NAME,
                    json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
                )
        os.replace(temporary_archive, target)
    except StudyBackupError:
        temporary_archive.unlink(missing_ok=True)
        raise
    except (OSError, zipfile.BadZipFile) as error:
        temporary_archive.unlink(missing_ok=True)
        raise StudyBackupError(f"No pudimos crear el respaldo: {error}") from error

    return BackupResult(target, len(files), total_bytes, _sha256_file(target))


def _read_and_validate_manifest(archive: zipfile.ZipFile) -> tuple[dict, list[tuple[PurePosixPath, int, str]]]:
    names = archive.namelist()
    if names.count(MANIFEST_NAME) != 1:
        raise StudyBackupError("El archivo no contiene un manifiesto de respaldo valido.")
    try:
        manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as error:
        raise StudyBackupError("El manifiesto del respaldo esta danado.") from error
    if manifest.get("format") != BACKUP_FORMAT or manifest.get("version") != BACKUP_VERSION:
        raise StudyBackupError("El formato de este respaldo no es compatible.")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise StudyBackupError("El manifiesto no contiene una lista de archivos valida.")

    entries: list[tuple[PurePosixPath, int, str]] = []
    seen: set[str] = set()
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise StudyBackupError("El manifiesto contiene una entrada invalida.")
        relative = _safe_relative_path(raw.get("path"))
        size = raw.get("size")
        digest = raw.get("sha256")
        if not isinstance(size, int) or size < 0 or not isinstance(digest, str) or len(digest) != 64:
            raise StudyBackupError(f"Datos de verificacion invalidos para {relative.as_posix()}.")
        if relative.as_posix() in seen:
            raise StudyBackupError(f"El respaldo repite el archivo {relative.as_posix()}.")
        seen.add(relative.as_posix())
        entries.append((relative, size, digest.casefold()))

    archived_file_names = [name for name in names if not name.endswith("/") and name != MANIFEST_NAME]
    archived_files = set(archived_file_names)
    if (
        archived_files != seen
        or len(archived_file_names) != len(archived_files)
        or len(archived_files) != len(entries)
    ):
        raise StudyBackupError("El contenido del respaldo no coincide con su manifiesto.")
    return manifest, entries


def validate_study_backup(
    backup_path: Path,
    progress: ProgressCallback | None = None,
) -> BackupValidation:
    path = Path(backup_path).resolve()
    if not path.is_file():
        raise StudyBackupError("No encontramos el archivo de respaldo.")
    total_bytes = 0
    try:
        with zipfile.ZipFile(path, "r") as archive:
            manifest, entries = _read_and_validate_manifest(archive)
            for index, (relative, expected_size, expected_hash) in enumerate(entries, start=1):
                with archive.open(relative.as_posix(), "r") as source:
                    digest, size = _sha256_stream(source)
                if size != expected_size or digest != expected_hash:
                    raise StudyBackupError(f"El archivo {relative.as_posix()} no supera la verificacion.")
                total_bytes += size
                if progress:
                    progress(index, len(entries), relative.as_posix())
    except zipfile.BadZipFile as error:
        raise StudyBackupError("El archivo elegido no es un respaldo ZIP valido.") from error
    study_name = str(manifest.get("study_name") or "Estudio")
    return BackupValidation(path, study_name, len(entries), total_bytes)


def restore_study_backup(
    backup_path: Path,
    destination: Path,
    progress: ProgressCallback | None = None,
) -> RestoreResult:
    """Validate fully, then restore atomically into a new or empty directory."""
    backup = Path(backup_path).resolve()
    target = Path(destination).resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise StudyBackupError("La restauracion solo puede hacerse en una carpeta nueva o vacia.")
    target.parent.mkdir(parents=True, exist_ok=True)
    validation = validate_study_backup(backup)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}-restaurando-", dir=target.parent))
    try:
        with zipfile.ZipFile(backup, "r") as archive:
            _, entries = _read_and_validate_manifest(archive)
            for index, (relative, _, _) in enumerate(entries, start=1):
                output = stage.joinpath(*relative.parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(relative.as_posix(), "r") as source, output.open("wb") as sink:
                    shutil.copyfileobj(source, sink, length=1024 * 1024)
                if progress:
                    progress(index, len(entries), relative.as_posix())
        if target.exists():
            target.rmdir()
        os.replace(stage, target)
    except Exception as error:
        shutil.rmtree(stage, ignore_errors=True)
        if isinstance(error, StudyBackupError):
            raise
        raise StudyBackupError(f"No pudimos restaurar el respaldo: {error}") from error
    return RestoreResult(target, validation.file_count, validation.total_bytes)
