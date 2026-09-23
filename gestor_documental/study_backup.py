"""Copias portables, verificables y transaccionales de un Estudio FORO."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

from . import __version__
from .study_database import DATABASE_NAME

LOGGER = logging.getLogger(__name__)
MANIFEST_NAME = "manifest.json"
LEGACY_MANIFEST_NAME = ".gestor-respaldo.json"
BACKUP_FORMAT = "foro-study-backup"
LEGACY_BACKUP_FORMAT = "gestor-documental-study-backup"
BACKUP_VERSION = 2
ProgressCallback = Callable[[int, int, str], None]
CancelCallback = Callable[[], bool]

EXCLUDED_DIRECTORIES = {
    ".git", ".venv", "__pycache__", "cache", "caches", "dist", "installer-build",
    "logs", "portable-build", "runtime", "temp", "tmp", "webview", "webview2",
    "browserprofile", "sisfe-browser-profile", ".gestor-conversion",
}
EXCLUDED_SUFFIXES = {".log", ".lock", ".tmp"}
INSTITUTIONAL_SETTINGS = {
    "professionals", "professional_profiles", "current_professional",
    "activity_settings", "naming_pattern",
}


class StudyBackupError(RuntimeError):
    """Error controlado al crear, validar o restaurar una copia."""


class StudyBackupCancelled(StudyBackupError):
    """La persona usuaria detuvo la operación sin alterar el Estudio."""


@dataclass(frozen=True)
class BackupResult:
    path: Path
    file_count: int
    total_bytes: int
    archive_sha256: str
    case_count: int = 0


@dataclass(frozen=True)
class BackupValidation:
    path: Path
    study_name: str
    file_count: int
    total_bytes: int
    case_count: int = 0
    created_at: str = ""
    foro_version: str = ""
    backup_format_version: int = BACKUP_VERSION


@dataclass(frozen=True)
class RestoreResult:
    root: Path
    file_count: int
    total_bytes: int
    case_count: int = 0
    safety_backup: Path | None = None


def _cancel_if_requested(cancelled: CancelCallback | None) -> None:
    if cancelled and cancelled():
        raise StudyBackupCancelled("Operación cancelada.")


def _sha256_file(path: Path, cancelled: CancelCallback | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            _cancel_if_requested(cancelled)
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_stream(source, cancelled: CancelCallback | None = None) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        _cancel_if_requested(cancelled)
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def _write_archive_file(
    archive: zipfile.ZipFile,
    source_path: Path,
    relative: str,
    cancelled: CancelCallback | None,
) -> tuple[str, int]:
    """Comprime por bloques, sin cargar el archivo en memoria y permitiendo cancelar."""
    digest = hashlib.sha256()
    size = 0
    info = zipfile.ZipInfo.from_file(source_path, arcname=relative)
    info.compress_type = zipfile.ZIP_DEFLATED
    with source_path.open("rb") as source, archive.open(info, "w", force_zip64=True) as sink:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            _cancel_if_requested(cancelled)
            sink.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _content_checksum(entries: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: str(item["path"])):
        digest.update(f'{entry["path"]}\0{entry["size"]}\0{entry["sha256"]}\n'.encode("utf-8"))
    return digest.hexdigest()


def _safe_relative_path(raw: object, manifest_name: str = MANIFEST_NAME) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise StudyBackupError("La copia contiene una ruta de archivo inválida.")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise StudyBackupError("La copia contiene una ruta fuera de la ubicación permitida.")
    if relative.as_posix() in {manifest_name, MANIFEST_NAME, LEGACY_MANIFEST_NAME}:
        raise StudyBackupError("El manifiesto no puede figurar como documento del Estudio.")
    return relative


def _snapshot_database(source: Path, destination: Path) -> None:
    origin = snapshot = None
    try:
        origin = sqlite3.connect(source)
        snapshot = sqlite3.connect(destination)
        origin.backup(snapshot)
        result = snapshot.execute("PRAGMA integrity_check").fetchone()
        if not result or str(result[0]).casefold() != "ok":
            raise StudyBackupError("La base del Estudio no supera la verificación de integridad.")
    except sqlite3.Error as error:
        raise StudyBackupError(f"No pudimos obtener una copia coherente de la base: {error}") from error
    finally:
        if snapshot is not None:
            snapshot.close()
        if origin is not None:
            origin.close()


def _is_excluded(relative: Path) -> bool:
    lowered = [part.casefold() for part in relative.parts]
    if any(part in EXCLUDED_DIRECTORIES for part in lowered[:-1]):
        return True
    name = relative.name.casefold()
    if (
        name.startswith("~$")
        or name.startswith(".gestor-nuevo-")
        or any(name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES)
    ):
        return True
    return name in {f"{DATABASE_NAME}-wal", f"{DATABASE_NAME}-shm", f"{DATABASE_NAME}-journal"}


def _collect_files(root: Path, prefix: str) -> list[tuple[Path, str]]:
    result: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item).casefold()):
        relative = path.relative_to(root)
        if _is_excluded(relative):
            continue
        if path.is_symlink():
            raise StudyBackupError(f"No se admiten accesos vinculados en la copia: {path}")
        if path.is_file():
            result.append((path, f"{prefix}/{relative.as_posix()}"))
    return result


def _sanitized_settings(app_dir: Path | None) -> dict[str, object]:
    if app_dir is None:
        return {}
    try:
        payload = json.loads((app_dir / "config.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {key: payload[key] for key in INSTITUTIONAL_SETTINGS if key in payload}


def _database_cases(snapshot: Path, root: Path) -> list[dict[str, str]]:
    if not snapshot.is_file():
        return []
    records: list[dict[str, str]] = []
    connection = None
    try:
        connection = sqlite3.connect(snapshot)
        connection.row_factory = sqlite3.Row
        columns = {row[1] for row in connection.execute("PRAGMA table_info(expedientes)")}
        if not {"id", "folder_path"}.issubset(columns):
            return []
        for row in connection.execute("SELECT id, folder_path FROM expedientes"):
            try:
                relative = Path(row["folder_path"]).resolve().relative_to(root).as_posix()
            except (OSError, ValueError):
                continue
            records.append({"id": str(row["id"]), "relative_path": relative})
    except sqlite3.Error:
        return []
    finally:
        if connection is not None:
            connection.close()
    return records


def _check_free_space(folder: Path, required: int, action: str) -> None:
    try:
        free = shutil.disk_usage(folder).free
    except OSError:
        return
    reserve = max(64 * 1024 * 1024, required // 20)
    if free < required + reserve:
        raise StudyBackupError(f"No hay espacio libre suficiente para {action} de forma segura.")


def create_study_backup(
    study_root: Path,
    destination: Path,
    progress: ProgressCallback | None = None,
    *,
    app_dir: Path | None = None,
    app_version: str = __version__,
    cancelled: CancelCallback | None = None,
) -> BackupResult:
    """Crea atómicamente una copia portable del Estudio y sus datos institucionales."""
    root = Path(study_root).resolve()
    target = Path(destination).resolve()
    if not root.is_dir():
        raise StudyBackupError("La ubicación del Estudio ya no está disponible.")
    if target == root or root in target.parents:
        raise StudyBackupError("Guardá la copia fuera de la ubicación del Estudio.")
    target.parent.mkdir(parents=True, exist_ok=True)
    study_files = _collect_files(root, "study")
    models_dir = Path(app_dir).resolve() / "Modelos" if app_dir else None
    model_files = _collect_files(models_dir, "models") if models_dir and models_dir.is_dir() else []
    settings = _sanitized_settings(Path(app_dir) if app_dir else None)
    estimated = sum(path.stat().st_size for path, _ in study_files + model_files)
    _check_free_space(target.parent, estimated, "crear la copia")

    temporary_archive = target.with_name(f".{target.name}.{os.getpid()}.partial")
    manifest_files: list[dict[str, object]] = []
    total_bytes = 0
    LOGGER.info("Inicio de copia del Estudio en %s", target)
    try:
        with tempfile.TemporaryDirectory(prefix="foro-backup-") as temp_dir:
            snapshot_path = Path(temp_dir) / DATABASE_NAME
            database_path = root / DATABASE_NAME
            if database_path.is_file():
                _snapshot_database(database_path, snapshot_path)
            else:
                # Algunos Estudios todavía no activaron funciones relacionales.
                # Se incluye igualmente una base SQLite válida para que la copia
                # sea autocontenida y FORO pueda migrarla al abrirla.
                sqlite3.connect(snapshot_path).close()
                study_files.append((database_path, f"study/{DATABASE_NAME}"))
            settings_path = Path(temp_dir) / "institutional.json"
            settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
            sources = study_files + model_files + [(settings_path, "settings/institutional.json")]
            with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=6, allowZip64=True) as archive:
                for index, (source_path, relative) in enumerate(sources, start=1):
                    _cancel_if_requested(cancelled)
                    archive_source = snapshot_path if source_path == database_path else source_path
                    digest, size = _write_archive_file(
                        archive, archive_source, relative, cancelled
                    )
                    manifest_files.append({"path": relative, "size": size, "sha256": digest})
                    total_bytes += size
                    if progress:
                        progress(index, len(sources) + 1, relative)
                cases = _database_cases(snapshot_path, root)
                if not cases:
                    cases = [{"id": "", "relative_path": path.parent.relative_to(root).as_posix()}
                             for path, _ in study_files if path.name == ".gestor-caso.json"]
                manifest = {
                    "format": BACKUP_FORMAT,
                    "backup_format_version": BACKUP_VERSION,
                    "foro_version": app_version,
                    "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    "backup_id": str(uuid.uuid4()),
                    "study_name": root.name or "Estudio",
                    "case_count": len(cases),
                    "file_count": len(study_files) + len(model_files),
                    "total_bytes": total_bytes,
                    "content_sha256": _content_checksum(manifest_files),
                    "cases": cases,
                    "files": manifest_files,
                }
                archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
                if progress:
                    progress(len(sources) + 1, len(sources) + 1, "Verificando copia")
        _cancel_if_requested(cancelled)
        validate_study_backup(temporary_archive, cancelled=cancelled)
        os.replace(temporary_archive, target)
    except StudyBackupCancelled:
        temporary_archive.unlink(missing_ok=True)
        LOGGER.info("Copia cancelada: %s", target)
        raise
    except StudyBackupError:
        temporary_archive.unlink(missing_ok=True)
        LOGGER.exception("Falló la copia del Estudio")
        raise
    except (OSError, zipfile.BadZipFile) as error:
        temporary_archive.unlink(missing_ok=True)
        LOGGER.exception("Falló la copia del Estudio")
        raise StudyBackupError(f"No pudimos crear la copia: {error}") from error
    LOGGER.info("Copia del Estudio terminada: %s", target)
    return BackupResult(target, len(study_files) + len(model_files), total_bytes, _sha256_file(target), len(cases))


def _read_and_validate_manifest(archive: zipfile.ZipFile) -> tuple[dict, list[tuple[PurePosixPath, int, str]], str, bool]:
    names = archive.namelist()
    manifest_names = [name for name in (MANIFEST_NAME, LEGACY_MANIFEST_NAME) if names.count(name) == 1]
    if len(manifest_names) != 1:
        raise StudyBackupError("El archivo no contiene un manifiesto de copia válido.")
    manifest_name = manifest_names[0]
    try:
        manifest = json.loads(archive.read(manifest_name).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError) as error:
        raise StudyBackupError("El manifiesto de la copia está dañado.") from error
    legacy = manifest.get("format") == LEGACY_BACKUP_FORMAT and manifest.get("version") == 1
    current = manifest.get("format") == BACKUP_FORMAT and manifest.get("backup_format_version") == BACKUP_VERSION
    if not (legacy or current):
        raise StudyBackupError("El formato de esta copia no es compatible con esta versión de FORO.")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise StudyBackupError("El manifiesto no contiene una lista de archivos válida.")
    entries: list[tuple[PurePosixPath, int, str]] = []
    seen: set[str] = set()
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise StudyBackupError("El manifiesto contiene una entrada inválida.")
        relative = _safe_relative_path(raw.get("path"), manifest_name)
        size, digest = raw.get("size"), raw.get("sha256")
        if not isinstance(size, int) or size < 0 or not isinstance(digest, str) or len(digest) != 64:
            raise StudyBackupError(f"Datos de verificación inválidos para {relative.as_posix()}.")
        if relative.as_posix() in seen:
            raise StudyBackupError(f"La copia repite el archivo {relative.as_posix()}.")
        seen.add(relative.as_posix())
        entries.append((relative, size, digest.casefold()))
    archived_names = [name for name in names if not name.endswith("/") and name != manifest_name]
    archived = set(archived_names)
    if archived != seen or len(archived_names) != len(archived) or len(archived) != len(entries):
        raise StudyBackupError("El contenido de la copia no coincide con su manifiesto.")
    if current and manifest.get("content_sha256") != _content_checksum(raw_files):
        raise StudyBackupError("La verificación global del contenido no coincide.")
    return manifest, entries, manifest_name, legacy


def validate_study_backup(backup_path: Path, progress: ProgressCallback | None = None, *,
                          cancelled: CancelCallback | None = None) -> BackupValidation:
    path = Path(backup_path).resolve()
    if not path.is_file():
        raise StudyBackupError("No encontramos el archivo de copia.")
    total_bytes = 0
    try:
        with zipfile.ZipFile(path, "r") as archive:
            manifest, entries, _, legacy = _read_and_validate_manifest(archive)
            for index, (relative, expected_size, expected_hash) in enumerate(entries, start=1):
                _cancel_if_requested(cancelled)
                with archive.open(relative.as_posix(), "r") as source:
                    digest, size = _sha256_stream(source, cancelled)
                if size != expected_size or digest != expected_hash:
                    raise StudyBackupError(f"El archivo {relative.as_posix()} no supera la verificación.")
                total_bytes += size
                if progress:
                    progress(index, len(entries), relative.as_posix())
    except zipfile.BadZipFile as error:
        raise StudyBackupError("El archivo elegido no es una copia válida.") from error
    visible_count = int(manifest.get("file_count") if not legacy else len(entries))
    return BackupValidation(path, str(manifest.get("study_name") or "Estudio"), visible_count, total_bytes,
                            int(manifest.get("case_count") or 0), str(manifest.get("created_at") or ""),
                            str(manifest.get("foro_version") or ""), 1 if legacy else BACKUP_VERSION)


def inspect_study_backup(backup_path: Path) -> BackupValidation:
    """Lee un resumen seguro; la validación completa se repite antes de restaurar."""
    path = Path(backup_path).resolve()
    try:
        with zipfile.ZipFile(path, "r") as archive:
            manifest, entries, _, legacy = _read_and_validate_manifest(archive)
    except (OSError, zipfile.BadZipFile) as error:
        raise StudyBackupError("El archivo elegido no es una copia válida.") from error
    visible_count = int(manifest.get("file_count") if not legacy else len(entries))
    return BackupValidation(path, str(manifest.get("study_name") or "Estudio"), visible_count,
                            int(manifest.get("total_bytes") or sum(size for _, size, _ in entries)),
                            int(manifest.get("case_count") or 0), str(manifest.get("created_at") or ""),
                            str(manifest.get("foro_version") or ""), 1 if legacy else BACKUP_VERSION)


def _extract_payload(backup: Path, stage: Path, progress: ProgressCallback | None,
                     cancelled: CancelCallback | None) -> tuple[dict, bool]:
    with zipfile.ZipFile(backup, "r") as archive:
        manifest, entries, _, legacy = _read_and_validate_manifest(archive)
        for index, (relative, _, _) in enumerate(entries, start=1):
            _cancel_if_requested(cancelled)
            if legacy:
                output = stage / "study" / Path(*relative.parts)
            elif relative.parts[0] in {"study", "models", "settings"}:
                output = stage / relative.parts[0] / Path(*relative.parts[1:])
            else:
                raise StudyBackupError("La copia contiene una sección desconocida.")
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(relative.as_posix(), "r") as source, output.open("wb") as sink:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    _cancel_if_requested(cancelled)
                    sink.write(chunk)
            if progress:
                progress(index, len(entries), relative.as_posix())
    return manifest, legacy


def _prepare_restored_database(
    database: Path,
    target: Path,
    manifest: dict,
    *,
    allow_missing: bool = False,
) -> None:
    if not database.is_file():
        if allow_missing:
            return
        raise StudyBackupError("La copia no contiene la base de datos principal del Estudio.")
    connection = None
    try:
        connection = sqlite3.connect(database)
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if not result or str(result[0]).casefold() != "ok":
            raise StudyBackupError("La base restaurada no supera la verificación de integridad.")
        for case in manifest.get("cases", []):
            if not isinstance(case, dict) or not case.get("id") or not case.get("relative_path"):
                continue
            relative = _safe_relative_path(str(case["relative_path"]))
            folder = target.joinpath(*relative.parts).resolve()
            if target != folder and target not in folder.parents:
                raise StudyBackupError("Una referencia de expediente sale de la ubicación restaurada.")
            connection.execute("UPDATE expedientes SET folder_path = ? WHERE id = ?", (str(folder), str(case["id"])))
        connection.commit()
    except sqlite3.Error as error:
        raise StudyBackupError(f"No pudimos preparar la base restaurada: {error}") from error
    finally:
        if connection is not None:
            connection.close()


def _merge_institutional_settings(app_dir: Path, payload: dict[str, object]) -> None:
    config = app_dir / "config.json"
    try:
        current = json.loads(config.read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError, OSError):
        current = {}
    if not isinstance(current, dict):
        current = {}
    for key in INSTITUTIONAL_SETTINGS:
        if key in payload:
            current[key] = payload[key]
    temporary = config.with_suffix(".restoring.tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, config)


def restore_study_backup(
    backup_path: Path, destination: Path, progress: ProgressCallback | None = None, *,
    app_dir: Path | None = None, current_study_root: Path | None = None,
    safety_backup_path: Path | None = None, replace_existing: bool = False,
    cancelled: CancelCallback | None = None,
) -> RestoreResult:
    """Valida, restaura en staging y reemplaza con reversión ante cualquier error."""
    backup, target = Path(backup_path).resolve(), Path(destination).resolve()
    current = Path(current_study_root).resolve() if current_study_root else None
    if target.exists() and not target.is_dir():
        raise StudyBackupError("La ubicación elegida no es una carpeta.")
    nonempty = target.exists() and any(target.iterdir())
    if nonempty and not replace_existing:
        raise StudyBackupError("La restauración sólo puede reemplazar el Estudio actual o usar una carpeta vacía.")
    if nonempty and current != target:
        raise StudyBackupError("Para proteger tus archivos, no se reemplaza una carpeta ajena al Estudio actual.")
    target.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Inicio de restauración desde %s", backup)
    validation = validate_study_backup(backup, cancelled=cancelled)
    _check_free_space(target.parent, validation.total_bytes * 2, "restaurar la copia")
    safety: Path | None = None
    if current and current.is_dir():
        if safety_backup_path is None:
            stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
            safety_backup_path = current.parent / f"FORO-Antes-de-restaurar-{stamp}.foro-backup"
        safety = Path(safety_backup_path).resolve()
        if safety == backup:
            safety = safety.with_name(f"{safety.stem}-estado-actual{safety.suffix}")
        counter = 2
        candidate = safety
        while candidate.exists():
            candidate = safety.with_name(f"{safety.stem}-{counter}{safety.suffix}")
            counter += 1
        safety = candidate
        create_study_backup(current, safety, app_dir=app_dir, cancelled=cancelled)

    operation_stage = Path(tempfile.mkdtemp(prefix=f".{target.name}-restaurando-", dir=target.parent))
    old_study = target.with_name(f".{target.name}-antes-{uuid.uuid4().hex}")
    app_config_backup: bytes | None = None
    models_backup: Path | None = None
    app_state_touched = False
    study_swapped = False
    try:
        manifest, legacy = _extract_payload(backup, operation_stage, progress, cancelled)
        stage_study = operation_stage / "study"
        if not stage_study.is_dir():
            raise StudyBackupError("La copia no contiene la carpeta del Estudio.")
        _prepare_restored_database(
            stage_study / DATABASE_NAME,
            target,
            manifest,
            allow_missing=legacy,
        )
        _cancel_if_requested(cancelled)
        if target.exists():
            if any(target.iterdir()):
                os.replace(target, old_study)
            else:
                target.rmdir()
        os.replace(stage_study, target)
        study_swapped = True

        if app_dir and not legacy:
            app_path = Path(app_dir).resolve()
            app_path.mkdir(parents=True, exist_ok=True)
            config = app_path / "config.json"
            app_config_backup = config.read_bytes() if config.is_file() else None
            app_state_touched = True
            settings_file = operation_stage / "settings" / "institutional.json"
            if settings_file.is_file():
                settings_payload = json.loads(settings_file.read_text(encoding="utf-8"))
                if isinstance(settings_payload, dict):
                    _merge_institutional_settings(app_path, settings_payload)
            restored_models = operation_stage / "models"
            if restored_models.is_dir():
                current_models = app_path / "Modelos"
                if current_models.exists():
                    models_backup = app_path / f".Modelos-antes-{uuid.uuid4().hex}"
                    os.replace(current_models, models_backup)
                os.replace(restored_models, current_models)
        shutil.rmtree(old_study, ignore_errors=True)
        if models_backup:
            shutil.rmtree(models_backup, ignore_errors=True)
    except Exception as error:
        if study_swapped:
            shutil.rmtree(target, ignore_errors=True)
            if old_study.exists():
                os.replace(old_study, target)
        if app_dir and app_state_touched:
            config = Path(app_dir) / "config.json"
            if app_config_backup is None:
                config.unlink(missing_ok=True)
            else:
                config.write_bytes(app_config_backup)
            if models_backup and models_backup.exists():
                shutil.rmtree(Path(app_dir) / "Modelos", ignore_errors=True)
                os.replace(models_backup, Path(app_dir) / "Modelos")
        if isinstance(error, StudyBackupError):
            raise
        raise StudyBackupError(f"No pudimos restaurar la copia: {error}") from error
    finally:
        shutil.rmtree(operation_stage, ignore_errors=True)
        if not study_swapped:
            shutil.rmtree(old_study, ignore_errors=True)
    LOGGER.info("Restauración terminada en %s", target)
    return RestoreResult(target, validation.file_count, validation.total_bytes,
                         validation.case_count, safety)
