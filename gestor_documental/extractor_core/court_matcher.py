from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Any, Iterable


ORDINALS = {
    "1": "primera",
    "01": "primera",
    "primera": "primera",
    "primer": "primera",
    "1ra": "primera",
    "1ro": "primera",
    "2": "segunda",
    "02": "segunda",
    "segunda": "segunda",
    "segundo": "segunda",
    "2da": "segunda",
    "2do": "segunda",
    "3": "tercera",
    "03": "tercera",
    "tercera": "tercera",
    "tercer": "tercera",
    "3ra": "tercera",
    "4": "cuarta",
    "04": "cuarta",
    "cuarta": "cuarta",
    "4ta": "cuarta",
    "5": "quinta",
    "05": "quinta",
    "quinta": "quinta",
    "5ta": "quinta",
    "6": "sexta",
    "06": "sexta",
    "sexta": "sexta",
    "6ta": "sexta",
    "7": "septima",
    "07": "septima",
    "septima": "septima",
    "7ma": "septima",
    "8": "octava",
    "08": "octava",
    "octava": "octava",
    "8va": "octava",
    "9": "novena",
    "09": "novena",
    "novena": "novena",
    "9na": "novena",
    "10": "decima",
    "decima": "decima",
    "10ma": "decima",
    "11": "decimo primera",
    "11ra": "decimo primera",
    "12": "decimo segunda",
    "12da": "decimo segunda",
    "13": "decimo tercera",
    "13ra": "decimo tercera",
    "14": "decimo cuarta",
    "14ta": "decimo cuarta",
}

ROMAN_TO_NUMBER = {
    "i": "1",
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "x": "10",
}

ORDINAL_TO_NUMBER = {
    "primera": "1",
    "segunda": "2",
    "tercera": "3",
    "cuarta": "4",
    "quinta": "5",
    "sexta": "6",
    "septima": "7",
    "octava": "8",
    "novena": "9",
    "decima": "10",
    "decimo primera": "11",
    "decimo segunda": "12",
    "decimo tercera": "13",
    "decimo cuarta": "14",
}

NUMBER_TO_ORDINAL = {number: ordinal for ordinal, number in ORDINAL_TO_NUMBER.items()}

ROLE_WORDS = {
    "juez",
    "jueza",
    "secretario",
    "secretaria",
    "prosecretario",
    "prosecretaria",
    "vocal",
    "presidente",
    "presidenta",
}

STOP_NAME_WORDS = {
    "dr",
    "dra",
    "doctor",
    "doctora",
    "juez",
    "jueza",
    "secretario",
    "secretaria",
    "prosecretario",
    "prosecretaria",
    "vocal",
    "presidente",
    "presidenta",
    "titular",
    "subrogante",
}


@dataclass
class MatchFeatures:
    normalized_text: str = ""
    normalized_court_line: str = ""
    locality: str = ""
    fuero: str = ""
    organ_type: str = ""
    nomination: str = ""
    number: str = ""
    sala: str = ""
    signer_text: str = ""


@dataclass
class CandidateScore:
    court: dict[str, Any]
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    authority_matches: int = 0


@dataclass
class CourtMatchResult:
    court: dict[str, Any] | None
    score: int = 0
    second_score: int = 0
    reasons: list[str] = field(default_factory=list)
    ambiguous: bool = False
    method: str = ""


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(character for character in value if unicodedata.category(character) != "Mn")
    value = value.casefold()

    replacements = {
        r"\bjuzg\.?\b": "juzgado",
        r"\b1ra\.?\b": "primera",
        r"\b1ro\.?\b": "primera",
        r"\b2da\.?\b": "segunda",
        r"\b2do\.?\b": "segunda",
        r"\b3ra\.?\b": "tercera",
        r"\b4ta\.?\b": "cuarta",
        r"\b5ta\.?\b": "quinta",
        r"\b6ta\.?\b": "sexta",
        r"\b7ma\.?\b": "septima",
        r"\b8va\.?\b": "octava",
        r"\b9na\.?\b": "novena",
        r"\b10ma\.?\b": "decima",
        r"\binst\.?\b": "instancia",
        r"\bnom\.?\b": "nominacion",
        r"\bcam\.?\b": "camara",
        r"\blab\.?\b": "laboral",
        r"\bciv\.?\b": "civil",
        r"\bcom\.?\b": "comercial",
        r"\bfam\.?\b": "familia",
        # N.º, Nº, N°, Nro., No. y variantes con espacios/puntos.
        r"\bn\s*(?:[.º°o]|ro)*\s*(\d{1,2})\b": r"numero \1",
    }
    for pattern, replacement in replacements.items():
        value = re.sub(pattern, replacement, value)

    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _tokens(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if len(token) > 1}


def _extract_nomination(value: str) -> str:
    normalized = normalize_text(value)
    ordinal_pattern = (
        r"primera|segunda|tercera|cuarta|quinta|sexta|septima|"
        r"octava|novena|decima|decimo primera|decimo segunda|"
        r"decimo tercera|decimo cuarta"
    )
    patterns = [
        rf"\b({ordinal_pattern})\s+nominacion\b",
        rf"\bnominacion\s+({ordinal_pattern})\b",
        r"\b(?:nominacion|nomina)\s+(\d{1,2})\b",
        r"\b(\d{1,2})\s+nominacion\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            raw = match.group(1)
            return ORDINALS.get(raw, NUMBER_TO_ORDINAL.get(str(int(raw))) if raw.isdigit() else raw)

    # En las bases oficiales muchos juzgados numerados equivalen a una
    # nominación expresada con ordinal en el PDF: N.º 6 == Sexta Nominación.
    number_match = re.search(r"\bnumero\s+(\d{1,2})\b", normalized)
    if number_match:
        return NUMBER_TO_ORDINAL.get(str(int(number_match.group(1))), "")

    return ""


def _extract_number(value: str) -> str:
    normalized = normalize_text(value)
    match = re.search(r"\bnumero\s+(\d{1,2})\b", normalized)
    if match:
        return str(int(match.group(1)))

    # La línea SISFE suele usar «6ta. Nom.» en lugar de «N.º 6».
    nomination = _extract_nomination(normalized)
    return ORDINAL_TO_NUMBER.get(nomination, "")

def _extract_sala(value: str) -> str:
    normalized = normalize_text(value)
    match = re.search(r"\bsala\s+(i{1,3}|iv|v|vi{0,3}|ix|x|\d{1,2})\b", normalized)
    if not match:
        return ""
    raw = match.group(1)
    if raw.isdigit():
        return str(int(raw))
    return ROMAN_TO_NUMBER.get(raw, "")


def _extract_fuero(value: str) -> str:
    normalized = normalize_text(value)
    if "responsabilidad extracontractual" in normalized:
        return "responsabilidad extracontractual"
    if "contencioso administrativo" in normalized:
        return "contencioso administrativo"
    if "ejecucion civil" in normalized:
        return "ejecucion civil"
    if "familia" in normalized:
        return "familia"
    if "laboral" in normalized or "trabajo" in normalized:
        return "laboral"
    if "civil" in normalized and "comercial" in normalized:
        return "civil comercial"
    if "circuito" in normalized:
        return "circuito"
    if "comunitario" in normalized or "pequenas causas" in normalized:
        return "justicia comunitaria"
    return ""


def _extract_organ_type(value: str) -> str:
    normalized = normalize_text(value)
    if "corte suprema" in normalized:
        return "corte"
    if "sala" in normalized and "camara" in normalized:
        return "sala"
    if "camara" in normalized:
        return "camara"
    if "juzgado" in normalized:
        return "juzgado"
    if "tribunal" in normalized:
        return "tribunal"
    return ""


def build_features(
    text: str,
    court_line: str = "",
    locality_hint: str = "",
    signers: str = "",
) -> MatchFeatures:
    combined = f"{court_line}\n{text}"
    return MatchFeatures(
        normalized_text=normalize_text(text),
        normalized_court_line=normalize_text(court_line),
        locality=normalize_text(locality_hint),
        fuero=_extract_fuero(court_line or combined),
        organ_type=_extract_organ_type(court_line or combined),
        nomination=_extract_nomination(court_line or combined),
        number=_extract_number(court_line or combined),
        sala=_extract_sala(court_line or combined),
        signer_text=normalize_text(signers or text),
    )


def _court_feature(court: dict[str, Any], key: str) -> str:
    if key == "locality":
        return normalize_text(str(court.get("locality") or ""))
    source_parts = [
        str(court.get(field) or "")
        for field in (
            "name",
            "category",
            "fuero",
            "header_text",
            "detection_patterns",
        )
    ]
    source = " ".join(source_parts)
    if key == "fuero":
        return _extract_fuero(source)
    if key == "organ_type":
        return _extract_organ_type(source)
    if key == "nomination":
        return _extract_nomination(source)
    if key == "number":
        return _extract_number(source)
    if key == "sala":
        return _extract_sala(source)
    return ""


def _compatible_fuero(detected: str, candidate: str) -> bool:
    if not detected or not candidate:
        return True
    if detected == candidate:
        return True
    if detected == "laboral" and "laboral" in candidate:
        return True
    if detected == "civil comercial" and candidate in {"civil comercial", "circuito"}:
        return True
    return False


def _authority_match(authority: dict[str, Any], signer_text: str) -> bool:
    if not signer_text:
        return False
    raw_name = str(authority.get("name") or authority.get("display_name") or "")
    normalized_name = normalize_text(raw_name)
    if not normalized_name:
        return False
    if normalized_name in signer_text:
        return True

    name_tokens = [
        token
        for token in normalized_name.split()
        if token not in STOP_NAME_WORDS and len(token) > 1
    ]
    if len(name_tokens) < 2:
        return False

    first = name_tokens[0]
    surname = name_tokens[-1]
    return first in signer_text.split() and surname in signer_text.split()


def _candidate_patterns(court: dict[str, Any]) -> Iterable[str]:
    yield str(court.get("name") or "")
    for field in ("detection_patterns", "header_text"):
        for line in str(court.get(field) or "").splitlines():
            line = line.strip()
            if line:
                yield line


def score_candidate(
    court: dict[str, Any],
    features: MatchFeatures,
) -> CandidateScore:
    result = CandidateScore(court=court)
    court_name_normalized = normalize_text(str(court.get("name") or ""))

    # Coincidencias literales y de patrones tienen máxima prioridad.
    for pattern in _candidate_patterns(court):
        normalized_pattern = normalize_text(pattern)
        if not normalized_pattern:
            continue
        if features.normalized_court_line and normalized_pattern == features.normalized_court_line:
            result.score += 140
            result.reasons.append("denominación exacta")
            break
        pattern_tokens = _tokens(normalized_pattern)
        candidate_locality = _court_feature(court, "locality")
        candidate_fuero = _court_feature(court, "fuero")
        candidate_nomination = _court_feature(court, "nomination")
        candidate_number = _court_feature(court, "number")
        is_specific = (
            normalized_pattern == court_name_normalized
            or bool(candidate_locality and candidate_locality in normalized_pattern)
            or bool(candidate_fuero and candidate_fuero in normalized_pattern)
            or bool(candidate_nomination and candidate_nomination in normalized_pattern)
            or bool(candidate_number and re.search(rf"\b{re.escape(candidate_number)}\b", normalized_pattern))
        )
        if (
            len(pattern_tokens) >= 5
            and is_specific
            and normalized_pattern in features.normalized_text
        ):
            result.score += 110
            result.reasons.append("nombre o patrón contenido en el PDF")
            break

    locality = _court_feature(court, "locality")
    if features.locality:
        if locality == features.locality:
            result.score += 35
            result.reasons.append("localidad")
        elif locality:
            result.score -= 70
            result.reasons.append("localidad incompatible")
    elif locality and locality in features.normalized_text:
        result.score += 22
        result.reasons.append("localidad encontrada en el texto")

    detected_fuero = features.fuero
    candidate_fuero = _court_feature(court, "fuero")
    if detected_fuero:
        if _compatible_fuero(detected_fuero, candidate_fuero):
            result.score += 30
            result.reasons.append("fuero")
        elif candidate_fuero:
            result.score -= 55
            result.reasons.append("fuero incompatible")

    detected_type = features.organ_type
    candidate_type = _court_feature(court, "organ_type")
    if detected_type:
        if detected_type == candidate_type:
            result.score += 15
            result.reasons.append("tipo de órgano")
        elif candidate_type:
            result.score -= 20

    detected_nomination = features.nomination
    candidate_nomination = _court_feature(court, "nomination")
    if detected_nomination:
        if candidate_nomination == detected_nomination:
            result.score += 48
            result.reasons.append(f"{detected_nomination} nominación")
        elif candidate_nomination:
            result.score -= 90
            result.reasons.append("nominación incompatible")
        else:
            result.score -= 35

    detected_number = features.number
    candidate_number = _court_feature(court, "number")
    if detected_number:
        if candidate_number == detected_number:
            result.score += 45
            result.reasons.append(f"número {detected_number}")
        elif candidate_number:
            result.score -= 80

    detected_sala = features.sala
    candidate_sala = _court_feature(court, "sala")
    if detected_sala:
        if candidate_sala == detected_sala:
            result.score += 110
            result.reasons.append(f"Sala {detected_sala}")
        elif candidate_sala:
            result.score -= 180
            result.reasons.append("sala incompatible")
        else:
            result.score -= 60

    # Similitud de palabras, útil para abreviaturas normalizadas.
    source_tokens = _tokens(features.normalized_court_line)
    court_tokens = _tokens(court_name_normalized)
    if source_tokens and court_tokens:
        shared = source_tokens & court_tokens
        coverage = len(shared) / max(1, len(source_tokens))
        similarity_points = min(24, round(coverage * 24))
        if similarity_points >= 6:
            result.score += similarity_points
            result.reasons.append("términos de la denominación")

    for authority in court.get("authorities") or []:
        if _authority_match(authority, features.signer_text):
            result.authority_matches += 1
            result.score += 28
            display = authority.get("display_name") or authority.get("name") or "autoridad"
            result.reasons.append(f"autoridad: {display}")

    if result.authority_matches >= 2:
        result.score += 20
        result.reasons.append("dos o más autoridades coincidentes")

    return result


def explicit_structure_conflicts(
    court: dict[str, Any],
    features: MatchFeatures,
) -> bool:
    """Descarta alias que contradicen datos explícitos del PDF."""
    checks = (
        (features.locality, _court_feature(court, "locality")),
        (features.nomination, _court_feature(court, "nomination")),
        (features.number, _court_feature(court, "number")),
        (features.sala, _court_feature(court, "sala")),
    )
    for detected, candidate in checks:
        if detected and candidate and detected != candidate:
            return True

    detected_type = features.organ_type
    candidate_type = _court_feature(court, "organ_type")
    if detected_type == "sala" and candidate_type and candidate_type != "sala":
        return True

    detected_fuero = features.fuero
    candidate_fuero = _court_feature(court, "fuero")
    if detected_fuero and candidate_fuero and not _compatible_fuero(detected_fuero, candidate_fuero):
        return True
    return False


def choose_best_match(
    courts: list[dict[str, Any]],
    text: str,
    court_line: str = "",
    locality_hint: str = "",
    signers: str = "",
    minimum_score: int = 70,
    minimum_margin: int = 18,
) -> CourtMatchResult:
    features = build_features(text, court_line, locality_hint, signers)
    scored = [score_candidate(court, features) for court in courts]
    scored.sort(key=lambda item: item.score, reverse=True)

    if not scored or scored[0].score < minimum_score:
        return CourtMatchResult(
            court=None,
            score=scored[0].score if scored else 0,
            second_score=scored[1].score if len(scored) > 1 else 0,
            reasons=scored[0].reasons if scored else [],
            ambiguous=False,
            method="sin_coincidencia",
        )

    best = scored[0]
    second_score = scored[1].score if len(scored) > 1 else 0
    margin = best.score - second_score
    if len(scored) > 1 and margin < minimum_margin:
        return CourtMatchResult(
            court=None,
            score=best.score,
            second_score=second_score,
            reasons=best.reasons,
            ambiguous=True,
            method="ambiguo",
        )

    method = "autoridades" if best.authority_matches else "estructura"
    if any("exacta" in reason or "patrón" in reason for reason in best.reasons):
        method = "patron"
    return CourtMatchResult(
        court=best.court,
        score=best.score,
        second_score=second_score,
        reasons=best.reasons,
        ambiguous=False,
        method=method,
    )
