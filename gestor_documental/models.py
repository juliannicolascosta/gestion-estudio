from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


SRT_LIMIT = 1 * 1024 * 1024
SISFE_COMMON_LIMIT = 3 * 1024 * 1024
SISFE_SPECIAL_LIMIT = 6 * 1024 * 1024
BUENOS_AIRES_LIMIT = 20 * 1024 * 1024

PRESENTATION_PROFILES = {
    "SRT · 1 MB": SRT_LIMIT,
    "SISFE común · 3 MB": SISFE_COMMON_LIMIT,
    "SISFE demanda/contestación · 6 MB": SISFE_SPECIAL_LIMIT,
    "Provincia de Buenos Aires · 20 MB": BUENOS_AIRES_LIMIT,
}

DEFAULT_PROFILE = "SISFE común · 3 MB"

CASE_FIELDS = (
    "Actor",
    "Demandado",
    "Causa",
    "Derivación",
    "CUIJ",
    "Expediente SRT",
    "Radicación",
    "Abogado",
    "Contraparte",
)

# La ficha cotidiana conserva sólo los cinco datos necesarios para identificar
# el caso y generar escritos sencillos. Los demás siguen disponibles en
# ``Más datos`` y en los modelos Word, sin pérdida de compatibilidad.
VISIBLE_CASE_FIELDS = (
    "Actor",
    "Demandado",
    "Causa",
    "Derivación",
    "CUIJ",
    "Radicación",
)

CASE_FIELD_LABELS = {
    "CUIJ": "Número de expediente",
    "Expediente SRT": "Número de expediente SRT",
}

ADVANCED_CASE_FIELDS = (
    "Nombre corto para archivos",
    "Jurisdicción",
    "Fuero",
    "Juzgado o tribunal",
    "Secretaría",
    "Sala",
    "Localidad",
    "DNI/CUIT actor",
    "DNI/CUIT demandado",
    "Domicilio actor",
    "Domicilio demandado",
    "Domicilio legal",
    "Domicilio electrónico",
    "Matrícula",
    "Tomo/Folio",
)

ADVANCED_FIELD_VARIABLES = {
    "Nombre corto para archivos": "NOMBRE_CORTO",
    "Jurisdicción": "JURISDICCION",
    "Fuero": "FUERO",
    "Juzgado o tribunal": "JUZGADO",
    "Secretaría": "SECRETARIA",
    "Sala": "SALA",
    "Localidad": "LOCALIDAD",
    "DNI/CUIT actor": "DOCUMENTO_ACTOR",
    "DNI/CUIT demandado": "DOCUMENTO_DEMANDADO",
    "Domicilio actor": "DOMICILIO_ACTOR",
    "Domicilio demandado": "DOMICILIO_DEMANDADO",
    "Domicilio del demandado": "DOMICILIO_DEMANDADO",
    "Domicilio legal": "DOMICILIO_LEGAL",
    "Domicilio electrónico": "DOMICILIO_ELECTRONICO",
    "Matrícula": "MATRICULA",
    "Tomo/Folio": "TOMO_FOLIO",
    "Portal jurídico asociado": "PORTAL_JURIDICO",
    "Radicación segunda instancia": "RADICACION_SEGUNDA_INSTANCIA",
    "Abogado de la contraparte": "ABOGADO_CONTRAPARTE",
    "Domicilio procesal de la contraparte": "DOMICILIO_PROCESAL_CONTRAPARTE",
    "Domicilio electrónico de la contraparte": "DOMICILIO_ELECTRONICO_CONTRAPARTE",
}


def limit_for(profile: str) -> int:
    try:
        return PRESENTATION_PROFILES[profile]
    except KeyError as exc:
        raise ValueError(f"Perfil de presentación desconocido: {profile}") from exc


@dataclass(frozen=True)
class Case:
    """A case directory; nested folders are honored when the user created them."""

    path: Path

    @property
    def name(self) -> str:
        return self.path.name

    def ensure(self):
        self.path.mkdir(parents=True, exist_ok=True)

    def files(self) -> list[Path]:
        if not self.path.is_dir():
            return []
        return sorted(
            (
                item
                for item in self.path.rglob("*")
                if item.is_file()
                and not any(part.startswith(".") for part in item.relative_to(self.path).parts)
            ),
            key=lambda item: item.relative_to(self.path).as_posix().casefold(),
        )

    def entries(self) -> list[Path]:
        """Visible user-created folders and files, recursively, without creating any."""
        if not self.path.is_dir():
            return []
        return sorted(
            (
                item
                for item in self.path.rglob("*")
                if not any(part.startswith(".") for part in item.relative_to(self.path).parts)
            ),
            key=lambda item: (
                item.relative_to(self.path).as_posix().casefold(),
                0 if item.is_dir() else 1,
            ),
        )


@dataclass
class AppSettings:
    study_roots: list[Path] = field(default_factory=list)
    active_study_root: Path | None = None
    professionals: list[str] = field(default_factory=list)
    professional_profiles: dict[str, dict[str, str]] = field(default_factory=dict)
    current_professional: str = ""
    signer_path: Path | None = None
    mev_profiles: dict[str, dict[str, str]] = field(default_factory=dict)
    layout_state: dict[str, object] = field(default_factory=dict)
    activity_settings: dict[str, object] = field(default_factory=dict)

    @property
    def study_root(self) -> Path | None:
        if self.active_study_root in self.study_roots:
            return self.active_study_root
        return self.study_roots[0] if self.study_roots else None

    @study_root.setter
    def study_root(self, path: Path | None):
        if path is None:
            self.active_study_root = None
            return
        path = Path(path)
        if path not in self.study_roots:
            self.study_roots.append(path)
        self.active_study_root = path


@dataclass(frozen=True)
class CompilationResult:
    output: Path
    limit: int
    compressed: bool
    exceeds_limit: bool
