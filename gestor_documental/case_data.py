from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    kind: str = "text"
    choices: tuple[str, ...] = ()
    placeholder: str = ""
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SectionSpec:
    title: str
    description: str
    fields: tuple[FieldSpec, ...]


@dataclass(frozen=True)
class RepeatedSpec:
    key: str
    title: str
    columns: tuple[str, ...]
    description: str = ""


DATE_PLACEHOLDER = "DD/MM/AAAA"


GENERAL_SECTIONS = (
    SectionSpec(
        "Persona actora / cliente",
        "Datos personales reutilizables en escritos y formularios.",
        (
            FieldSpec("Apellido del actor", "Apellido"),
            FieldSpec("Nombres del actor", "Nombres"),
            FieldSpec("DNI del actor", "DNI", aliases=("DNI/CUIT actor",)),
            FieldSpec("CUIL del actor", "CUIL"),
            FieldSpec("Fecha de nacimiento", "Fecha de nacimiento", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec(
                "Estado civil",
                "Estado civil",
                "combo",
                ("Soltero/a", "Casado/a", "Divorciado/a", "Viudo/a", "Conviviente"),
            ),
            FieldSpec("Domicilio real", "Domicilio real", aliases=("Domicilio actor",)),
            FieldSpec("Localidad del actor", "Localidad"),
            FieldSpec("Provincia del actor", "Provincia"),
            FieldSpec("Teléfono del actor", "Teléfono"),
            FieldSpec("Correo electrónico del actor", "Correo electrónico"),
        ),
    ),
    SectionSpec(
        "Datos laborales básicos",
        "Información estable de la relación laboral.",
        (
            FieldSpec("Empleador principal", "Empleador principal"),
            FieldSpec("CUIT del empleador", "CUIT del empleador"),
            FieldSpec("Domicilio legal del empleador", "Domicilio legal o sede social"),
            FieldSpec("Domicilio del establecimiento", "Domicilio del establecimiento"),
            FieldSpec("Localidad del establecimiento", "Localidad del establecimiento"),
            FieldSpec("Actividad del empleador", "Actividad del empleador"),
            FieldSpec("Fecha de ingreso", "Fecha de ingreso", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec("Fecha de egreso", "Fecha de egreso", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec("Puesto o categoría real", "Puesto o categoría real"),
            FieldSpec("Jornada laboral", "Jornada laboral"),
            FieldSpec("Remuneración percibida", "Remuneración percibida", "money"),
            FieldSpec(
                "Periodicidad de la remuneración",
                "Periodicidad",
                "combo",
                ("Mensual", "Diaria", "Semanal", "Quincenal", "Horaria"),
            ),
            FieldSpec("ART", "ART"),
            FieldSpec("Número de contrato SRT", "Número de contrato SRT"),
        ),
    ),
    SectionSpec(
        "Datos del proceso",
        "Datos judiciales y del profesional que pueden completar modelos.",
        (
            FieldSpec(
                "Tipo de proceso",
                "Tipo de proceso",
                "combo",
                ("Laboral común", "Accidente laboral", "Enfermedad profesional", "Otro"),
            ),
            FieldSpec("Causa", "Objeto principal del reclamo"),
            FieldSpec("Jurisdicción", "Jurisdicción"),
            FieldSpec("Fuero", "Fuero"),
            FieldSpec("Juzgado o tribunal", "Juzgado"),
            FieldSpec("Secretaría", "Secretaría"),
            FieldSpec("Sala", "Sala"),
            FieldSpec("Localidad del juzgado", "Localidad del juzgado"),
            FieldSpec("Fecha de inicio de la causa", "Fecha de inicio", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec("Abogado", "Profesional interviniente"),
            FieldSpec("Demandado", "Demandado/s"),
            FieldSpec("Matrícula", "Matrícula"),
            FieldSpec("Tomo/Folio", "Tomo / Folio"),
            FieldSpec("Domicilio legal", "Domicilio legal constituido"),
            FieldSpec("Domicilio electrónico", "Domicilio electrónico"),
            FieldSpec("Nombre corto para archivos", "Nombre corto para archivos", placeholder="Ej.: YOCCA"),
            FieldSpec("Observaciones procesales", "Observaciones procesales", "textarea"),
        ),
    ),
)


GENERAL_REPEATED = (
    RepeatedSpec(
        "Responsables solidarios",
        "Responsables solidarios",
        ("Nombre", "Domicilio", "Localidad", "Actividad"),
        "Agregá una fila por cada posible codemandado solidario.",
    ),
)


INTERVIEW_SECTIONS = (
    SectionSpec(
        "Antecedentes personales y previsionales",
        "Las credenciales no se guardan: sólo se registra si el acceso fue informado o verificado.",
        (
            FieldSpec("Obra social", "Obra social"),
            FieldSpec(
                "Estado de acceso ARCA/AFIP",
                "Acceso ARCA/AFIP",
                "combo",
                ("No informado", "Cliente manifiesta poseerlo", "Verificado"),
            ),
            FieldSpec(
                "Estado de acceso ANSES",
                "Acceso Seguridad Social ANSES",
                "combo",
                ("No informado", "Cliente manifiesta poseerlo", "Verificado"),
            ),
            FieldSpec("Mano hábil", "Mano hábil", "combo", ("Diestro/a", "Zurdo/a")),
            FieldSpec("Tiene preexistencias médicas", "Preexistencias médicas", "combo", ("Sí", "No", "No sabe")),
            FieldSpec("Descripción de preexistencias", "Descripción de preexistencias", "textarea"),
            FieldSpec("Tuvo reclamos LRT anteriores", "Reclamos LRT anteriores", "combo", ("Sí", "No", "No sabe")),
            FieldSpec("Cobró prestaciones LRT", "Prestaciones LRT cobradas", "combo", ("Sí", "No", "No sabe")),
        ),
    ),
    SectionSpec(
        "Relevamiento de la relación laboral",
        "Datos de entrevista para analizar registración, categoría y diferencias salariales.",
        (
            FieldSpec("Fecha de ingreso fáctico", "Ingreso fáctico", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec("Fecha de ingreso formal", "Ingreso formal / registrado", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec("Fecha de egreso fáctico", "Egreso fáctico", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec("Fecha de egreso formal", "Egreso formal / registrado", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec("Puestos anteriores", "Puestos anteriores", "textarea"),
            FieldSpec("Sector de trabajo", "Sector de trabajo"),
            FieldSpec("Descripción detallada de tareas", "Descripción detallada de tareas", "textarea"),
            FieldSpec("Tareas de puestos anteriores", "Tareas de puestos anteriores", "textarea"),
            FieldSpec("Convenio colectivo aplicable", "Convenio colectivo aplicable"),
            FieldSpec("Categoría convencional aplicable", "Categoría convencional aplicable"),
            FieldSpec("Remuneración conforme CCT", "Remuneración conforme CCT", "money"),
            FieldSpec(
                "Modalidad de registración",
                "Modalidad de registración",
                "combo",
                ("Registrada", "No registrada", "Defectuosa"),
            ),
            FieldSpec("Historia laboral", "Historia laboral / relato cronológico", "textarea"),
            FieldSpec("Reclamos previos y respuesta patronal", "Reclamos previos y respuesta patronal", "textarea"),
        ),
    ),
    SectionSpec(
        "Prueba y documentación",
        "Información de trabajo interno; no se incorpora automáticamente a escritos.",
        (
            FieldSpec("Notas internas del profesional", "Notas internas del profesional", "textarea"),
        ),
    ),
    SectionSpec(
        "Datos médicos y del siniestro",
        "Completá sólo lo aplicable a accidente o enfermedad profesional.",
        (
            FieldSpec("Fecha del accidente", "Fecha del accidente", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec("Hora del accidente", "Hora del accidente", placeholder="HH:MM"),
            FieldSpec("Tipo de accidente", "Tipo de accidente", "combo", ("Laboral", "In itinere")),
            FieldSpec("Lugar exacto del accidente", "Lugar exacto del accidente"),
            FieldSpec("Localidad de ocurrencia", "Localidad de ocurrencia"),
            FieldSpec("Relato del accidente", "Relato del accidente", "textarea"),
            FieldSpec("Mecanismo lesional", "Mecanismo lesional", "textarea"),
            FieldSpec("Lesiones denunciadas", "Lesiones denunciadas", "textarea"),
            FieldSpec("Fecha de alta médica", "Fecha de alta médica", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec("Fecha de reingreso laboral", "Fecha de reingreso laboral", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec("Factores de riesgo o exposiciones", "Factores de riesgo / exposiciones", "textarea"),
            FieldSpec("Tareas riesgosas", "Tareas riesgosas", "textarea"),
            FieldSpec("Fecha de primera manifestación invalidante", "Primera manifestación invalidante", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec("Fecha de denuncia ante ART", "Fecha de denuncia ante ART", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec("Porcentaje de incapacidad reclamado", "Incapacidad estimada o reclamada (%)"),
        ),
    ),
)


INTERVIEW_REPEATED = (
    RepeatedSpec("Antecedentes LRT", "Antecedentes LRT", ("Tipo", "Fecha", "Detalle")),
    RepeatedSpec("Prestaciones LRT recibidas", "Prestaciones LRT recibidas", ("Fecha", "Prestación", "Detalle")),
    RepeatedSpec("Posibles testigos", "Posibles testigos", ("Nombre", "Datos de contacto")),
    RepeatedSpec("Documentación aportada", "Documentación aportada", ("Documento",)),
    RepeatedSpec("Documentación pendiente", "Documentación pendiente", ("Documento",)),
    RepeatedSpec("Afecciones o enfermedades", "Afecciones o enfermedades denunciadas", ("Afección", "Detalle")),
    RepeatedSpec("Atenciones médicas", "Atenciones médicas", ("Fecha", "Centro", "Atención recibida")),
    RepeatedSpec("Estudios médicos", "Estudios médicos", ("Fecha", "Estudio", "Lugar y resguardo")),
)


RAEO_SECTIONS = (
    SectionSpec(
        "Datos específicos del trabajador",
        "Los restantes datos personales se toman automáticamente de Datos generales.",
        (
            FieldSpec("Tipo de documento RAEO", "Tipo de documento", "combo", ("DNI", "LE", "LC", "Pasaporte")),
            FieldSpec("Edad RAEO manual", "Edad (sólo si necesitás corregir el cálculo)", "integer"),
            FieldSpec("Vínculo del actor con el accidentado", "Vínculo del actor con el accidentado"),
        ),
    ),
    SectionSpec(
        "Accidente o enfermedad",
        "Se sugieren los datos ya cargados en la entrevista; estos campos permiten precisar el formulario.",
        (
            FieldSpec("Fecha contingencia RAEO", "Fecha del accidente o enfermedad", "date", placeholder=DATE_PLACEHOLDER),
            FieldSpec("Localidad de ocurrencia RAEO", "Localidad de ocurrencia"),
            FieldSpec("Circunstancias RAEO", "Circunstancias de lugar y modo", "textarea"),
            FieldSpec("Lesión o enfermedad RAEO", "Lesión y/o enfermedad denunciada", "textarea"),
        ),
    ),
    SectionSpec(
        "Datos del reclamo",
        "El monto siempre queda editable; no se aplica una fórmula jurídica sin confirmación profesional.",
        (
            FieldSpec("Concepto del reclamo RAEO", "Concepto del reclamo"),
            FieldSpec("Monto reclamado", "Monto reclamado", "money"),
        ),
    ),
    SectionSpec(
        "Responsables demandados",
        "Elegí cuál debe aparecer como responsable principal cuando existan varios.",
        (
            FieldSpec("Responsable principal RAEO", "Empleador o responsable principal", "combo"),
            FieldSpec("Domicilio responsable RAEO", "Domicilio"),
            FieldSpec("Localidad responsable RAEO", "Localidad"),
            FieldSpec("Ramo o actividad RAEO", "Ramo o actividad"),
        ),
    ),
    SectionSpec(
        "Datos del proceso para RAEO",
        "CUIJ y carátula se consumen del expediente y nunca se vuelven a cargar.",
        (
            FieldSpec("Profesionales del actor RAEO", "Profesionales del actor"),
            FieldSpec("Acción interpuesta RAEO", "Acción interpuesta", "combo", ("Especial", "Civil")),
            FieldSpec("Observaciones RAEO", "Observaciones", "textarea"),
        ),
    ),
)


RAEO_REPEATED = (
    RepeatedSpec("Otros responsables RAEO", "Otros responsables demandados", ("Nombre", "Domicilio", "Localidad", "Actividad")),
)


SYSTEM_METADATA_KEYS = {
    "Identificación interna del expediente",
    "Fecha de creación del registro",
    "Profesional creador",
    "Documentación recibida",
}


def all_defined_keys() -> set[str]:
    sections = GENERAL_SECTIONS + INTERVIEW_SECTIONS + RAEO_SECTIONS
    keys = {field.key for section in sections for field in section.fields}
    keys.update(spec.key for spec in GENERAL_REPEATED + INTERVIEW_REPEATED + RAEO_REPEATED)
    keys.update(SYSTEM_METADATA_KEYS)
    return keys


def field_initial_value(metadata: dict[str, str], field: FieldSpec) -> str:
    value = str(metadata.get(field.key, "")).strip()
    if value:
        return value
    for alias in field.aliases:
        value = str(metadata.get(alias, "")).strip()
        if value:
            return value
    return ""


def parse_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def format_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def calculate_age(birth: date | None, at_date: date | None = None) -> int | None:
    if not birth:
        return None
    reference = at_date or date.today()
    if reference < birth:
        return None
    return reference.year - birth.year - ((reference.month, reference.day) < (birth.month, birth.day))


def calculate_seniority(start: date | None, end: date | None = None) -> str:
    if not start:
        return ""
    finish = end or date.today()
    if finish < start:
        return ""
    months = (finish.year - start.year) * 12 + finish.month - start.month
    if finish.day < start.day:
        months -= 1
    years, remaining = divmod(max(0, months), 12)
    parts = []
    if years:
        parts.append(f"{years} año{'s' if years != 1 else ''}")
    if remaining or not parts:
        parts.append(f"{remaining} mes{'es' if remaining != 1 else ''}")
    return " y ".join(parts)


def parse_decimal(value: str | None) -> Decimal | None:
    text = re.sub(r"[^0-9,.-]", "", str(value or "").strip())
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    fixed = f"{value.quantize(Decimal('0.01')):,.2f}"
    return fixed.replace(",", "_").replace(".", ",").replace("_", ".")


def event_date(metadata: dict[str, str]) -> date | None:
    for key in (
        "Fecha contingencia RAEO",
        "Fecha del accidente",
        "Fecha de primera manifestación invalidante",
    ):
        parsed = parse_date(metadata.get(key))
        if parsed:
            return parsed
    return None


def build_case_caption(metadata: dict[str, str], fallback: str = "") -> str:
    actor = str(metadata.get("Actor", "")).strip()
    if not actor:
        surname = str(metadata.get("Apellido del actor", "")).strip()
        names = str(metadata.get("Nombres del actor", "")).strip()
        actor = ", ".join(value for value in (surname, names) if value)
    defendant = str(metadata.get("Demandado", "")).strip() or str(metadata.get("Empleador principal", "")).strip()
    cause = str(metadata.get("Causa", "")).strip() or str(metadata.get("Concepto del reclamo RAEO", "")).strip()
    caption = actor
    if defendant:
        caption = f"{caption} C/ {defendant}" if caption else defendant
    if cause:
        caption = f"{caption} S/ {cause}" if caption else cause
    return (caption or fallback).upper()


def ensure_system_metadata(
    metadata: dict[str, str],
    *,
    professional: str = "",
    today: date | None = None,
) -> dict[str, str]:
    result = dict(metadata)
    current = today or date.today()
    if not str(result.get("Identificación interna del expediente", "")).strip():
        result["Identificación interna del expediente"] = (
            f"GD-{current.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        )
    result.setdefault("Fecha de creación del registro", current.isoformat())
    if professional.strip():
        result.setdefault("Profesional creador", professional.strip())
        result.setdefault("Profesionales del actor RAEO", professional.strip())
    if not str(result.get("Actor", "")).strip():
        surname = str(result.get("Apellido del actor", "")).strip()
        names = str(result.get("Nombres del actor", "")).strip()
        generated_actor = ", ".join(value for value in (surname, names) if value)
        if generated_actor:
            result["Actor"] = generated_actor
    return result


def computed_values(metadata: dict[str, str], today: date | None = None) -> dict[str, str]:
    current = today or date.today()
    contingency = event_date(metadata)
    birth = parse_date(metadata.get("Fecha de nacimiento"))
    manual_age = str(metadata.get("Edad RAEO manual", "")).strip()
    age = manual_age or (str(calculate_age(birth, contingency or current)) if birth else "")

    start = (
        parse_date(metadata.get("Fecha de ingreso fáctico"))
        or parse_date(metadata.get("Fecha de ingreso"))
        or parse_date(metadata.get("Fecha de ingreso formal"))
    )
    end = contingency or parse_date(metadata.get("Fecha de egreso fáctico")) or parse_date(metadata.get("Fecha de egreso")) or current

    accident = parse_date(metadata.get("Fecha del accidente"))
    art_report = parse_date(metadata.get("Fecha de denuncia ante ART"))
    medical_discharge = parse_date(metadata.get("Fecha de alta médica"))
    return_to_work = parse_date(metadata.get("Fecha de reingreso laboral"))

    perceived = parse_decimal(metadata.get("Remuneración percibida"))
    frequency = str(metadata.get("Periodicidad de la remuneración", "Mensual")).casefold()
    factor = Decimal("1")
    if frequency == "diaria":
        factor = Decimal("25")
    elif frequency == "semanal":
        factor = Decimal("4.33")
    elif frequency == "quincenal":
        factor = Decimal("2")
    elif frequency == "horaria":
        factor = Decimal("200")
    monthly = perceived * factor if perceived is not None else None
    cct = parse_decimal(metadata.get("Remuneración conforme CCT"))
    difference = cct - monthly if cct is not None and monthly is not None else None

    def days_between(first: date | None, second: date | None) -> str:
        return str((second - first).days) if first and second and second >= first else ""

    return {
        "EDAD": age,
        "EDAD_RAEO": age,
        "ANTIGUEDAD_LABORAL": calculate_seniority(start, end),
        "DIAS_ACCIDENTE_DENUNCIA_ART": days_between(accident, art_report),
        "DIAS_ACCIDENTE_ALTA_MEDICA": days_between(accident, medical_discharge),
        "DIAS_ALTA_REINGRESO": days_between(medical_discharge, return_to_work),
        "REMUNERACION_MENSUAL_ESTIMADA": format_decimal(monthly),
        "DIFERENCIA_REMUNERACION_CONVENIO": format_decimal(difference),
    }


def raeo_effective_values(metadata: dict[str, str]) -> dict[str, str]:
    computed = computed_values(metadata)
    return {
        "Actor": str(metadata.get("Actor", "")).strip() or build_case_caption(metadata).split(" C/ ", 1)[0],
        "Documento": str(metadata.get("DNI del actor", "")).strip() or str(metadata.get("DNI/CUIT actor", "")).strip(),
        "Edad": computed["EDAD_RAEO"],
        "Estado civil": str(metadata.get("Estado civil", "")).strip(),
        "Domicilio": str(metadata.get("Domicilio real", "")).strip() or str(metadata.get("Domicilio actor", "")).strip(),
        "Localidad": str(metadata.get("Localidad del actor", "")).strip(),
        "Actividad o puesto": str(metadata.get("Puesto o categoría real", "")).strip(),
        "Antigüedad": computed["ANTIGUEDAD_LABORAL"],
        "Fecha contingencia": str(metadata.get("Fecha contingencia RAEO", "")).strip()
        or str(metadata.get("Fecha del accidente", "")).strip()
        or str(metadata.get("Fecha de primera manifestación invalidante", "")).strip(),
        "Localidad ocurrencia": str(metadata.get("Localidad de ocurrencia RAEO", "")).strip()
        or str(metadata.get("Localidad de ocurrencia", "")).strip(),
        "Circunstancias": str(metadata.get("Circunstancias RAEO", "")).strip()
        or str(metadata.get("Relato del accidente", "")).strip(),
        "Lesión o enfermedad": str(metadata.get("Lesión o enfermedad RAEO", "")).strip()
        or str(metadata.get("Lesiones denunciadas", "")).strip()
        or str(metadata.get("Afecciones o enfermedades", "")).strip(),
        "Responsable principal": str(metadata.get("Responsable principal RAEO", "")).strip()
        or str(metadata.get("Empleador principal", "")).strip()
        or str(metadata.get("Demandado", "")).strip(),
        "CUIJ": str(metadata.get("CUIJ", "")).strip() or str(metadata.get("Número de expediente", "")).strip(),
        "Carátula": build_case_caption(metadata),
        "Juzgado": str(metadata.get("Juzgado o tribunal", "")).strip(),
        "Localidad juzgado": str(metadata.get("Localidad del juzgado", "")).strip(),
        "Fecha inicio": str(metadata.get("Fecha de inicio de la causa", "")).strip(),
    }


def raeo_missing_fields(metadata: dict[str, str]) -> list[str]:
    effective = raeo_effective_values(metadata)
    direct = {
        "Tipo de documento": metadata.get("Tipo de documento RAEO", ""),
        "Concepto del reclamo": metadata.get("Concepto del reclamo RAEO", "") or metadata.get("Causa", ""),
        "Porcentaje de incapacidad": metadata.get("Porcentaje de incapacidad reclamado", ""),
        "Monto reclamado": metadata.get("Monto reclamado", ""),
        "Profesionales del actor": metadata.get("Profesionales del actor RAEO", "") or metadata.get("Abogado", ""),
        "Acción interpuesta": metadata.get("Acción interpuesta RAEO", ""),
    }
    required_effective = (
        "Actor",
        "Documento",
        "Domicilio",
        "Localidad",
        "Actividad o puesto",
        "Fecha contingencia",
        "Localidad ocurrencia",
        "Circunstancias",
        "Lesión o enfermedad",
        "Responsable principal",
        "CUIJ",
        "Juzgado",
        "Localidad juzgado",
        "Fecha inicio",
    )
    missing = [label for label in required_effective if not str(effective.get(label, "")).strip()]
    missing.extend(label for label, value in direct.items() if not str(value).strip())
    return missing


def case_suggestions(metadata: dict[str, str]) -> list[str]:
    suggestions: list[str] = []
    process_type = str(metadata.get("Tipo de proceso", "")).casefold()
    if "accidente" in process_type or "enfermedad" in process_type:
        missing = raeo_missing_fields(metadata)
        if missing:
            suggestions.append(f"RAEO: faltan {len(missing)} datos para tener el formulario completo.")
        else:
            suggestions.append("RAEO: los datos necesarios están completos.")
    if str(metadata.get("ART", "")).strip() and (
        not str(metadata.get("Número de contrato SRT", "")).strip()
        or not str(metadata.get("Fecha de denuncia ante ART", "")).strip()
    ):
        suggestions.append("Verificá el número de contrato SRT y la fecha de denuncia ante ART.")
    mode = str(metadata.get("Modalidad de registración", "")).casefold()
    factual = parse_date(metadata.get("Fecha de ingreso fáctico"))
    formal = parse_date(metadata.get("Fecha de ingreso formal"))
    if "no registrada" in mode or "defectuosa" in mode or (factual and formal and factual != formal):
        suggestions.append("Revisá los rubros vinculados con falta o deficiente registración.")
    if str(metadata.get("Responsables solidarios", "")).strip():
        suggestions.append("Hay responsables solidarios cargados: revisá si deben incorporarse como codemandados.")
    medical_data = any(
        str(metadata.get(key, "")).strip()
        for key in ("Lesiones denunciadas", "Afecciones o enfermedades", "Estudios médicos")
    )
    if medical_data and not str(metadata.get("Porcentaje de incapacidad reclamado", "")).strip():
        suggestions.append("Hay información médica, pero falta indicar la incapacidad estimada o reclamada.")
    return suggestions


def template_key(label: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(label))
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_").upper() or "DATO"
