"""Case file operations that preserve their registered procedural identity."""

from pathlib import Path
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass

from .models import Case
from .services import rename_case_entry
from .study_database import StudyDatabase, study_database_path


@dataclass(frozen=True)
class RecoveryResult:
    recovered: tuple[tuple[Path, Path], ...] = ()
    unresolved: int = 0


def _fingerprint(path: Path) -> tuple[str, tuple[int, int]]:
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    signature = (after.st_size, after.st_mtime_ns)
    if signature != (before.st_size, before.st_mtime_ns):
        raise OSError("El archivo cambió durante la lectura.")
    return digest.hexdigest(), signature


def recover_document_links(case: Case) -> RecoveryResult:
    """Recover unique missing file references, never moving user files."""
    root = case.path.resolve()
    database_path = study_database_path(case.path.parent)
    if not database_path.is_file():
        return RecoveryResult()
    with StudyDatabase(database_path) as database:
        expediente = database.find_expediente_by_folder(case.path)
        if not expediente:
            return RecoveryResult()
        documents = database.list_documents(expediente.id)
        missing = [d for d in documents if not (root / d.relative_path).exists()]
        if not missing:
            return RecoveryResult()
        counts = Counter(d.sha256 for d in missing if d.sha256)
        wanted = {digest for digest, count in counts.items() if count == 1}
        candidates = defaultdict(list)
        occupied = {d.relative_path for d in documents}
        # Do not follow symlinks, hidden application files, or paths outside the case.
        if wanted:
            for path in root.rglob("*"):
                relative = path.relative_to(root)
                if any(part.startswith(".") for part in relative.parts):
                    continue
                if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
                    continue
                try:
                    digest, signature = _fingerprint(path)
                except OSError:
                    continue
                if digest in wanted:
                    candidates[digest].append((path, signature))
        recovered = []
        for document in missing:
            matches = candidates.get(document.sha256, [])
            if len(matches) != 1:
                continue
            target, signature = matches[0]
            previous = root / document.relative_path
            relative = target.relative_to(root)
            if relative in occupied or previous.exists():
                continue
            try:
                current = target.stat()
            except OSError:
                continue
            if (current.st_size, current.st_mtime_ns) != signature:
                continue
            # Recheck identity in case another operation renamed the record while scanning.
            row = database.connection.execute(
                "SELECT relative_path, sha256 FROM documentos WHERE id = ?", (document.id,)
            ).fetchone()
            if not row or row["relative_path"] != document.relative_path.as_posix() or row["sha256"] != document.sha256:
                continue
            database.relocate_documents(expediente.id, document.relative_path, relative)
            occupied.add(relative)
            recovered.append((previous, target))
        return RecoveryResult(tuple(recovered), len(missing) - len(recovered))


def rename_document_entry(case: Case, source: Path, name: str) -> Path:
    root = case.path.resolve()
    source = source.resolve()
    relative = source.relative_to(root)
    if not relative.parts:
        raise ValueError("Usá la opción de renombrar caso para cambiar su carpeta principal.")
    database_path = study_database_path(case.path.parent)
    if not database_path.is_file():
        return rename_case_entry(source, name)
    with StudyDatabase(database_path) as database:
        expediente = database.find_expediente_by_folder(case.path)
        target = rename_case_entry(source, name)
        if target == source or not expediente:
            return target
        try:
            database.relocate_documents(expediente.id, relative, target.relative_to(root))
        except Exception as error:
            try:
                target.rename(source)
            except OSError as rollback_error:
                raise RuntimeError(
                    f"No pudimos actualizar el registro ni restaurar el nombre. "
                    f"El archivo permanece en {target}. Error: {rollback_error}"
                ) from error
            raise
        return target
