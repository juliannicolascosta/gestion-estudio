"""Case file operations that preserve their registered procedural identity."""

from pathlib import Path

from .models import Case
from .services import rename_case_entry
from .study_database import StudyDatabase, study_database_path


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
