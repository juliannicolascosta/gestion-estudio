from __future__ import annotations

from dataclasses import dataclass, replace
import re
import unicodedata


_TREATMENTS = (
    "DR.",
    "DRA.",
    "LIC.",
    "ABG.",
    "ABOG.",
    "ING.",
    "CR.",
    "CRA.",
)


@dataclass
class Signer:
    name: str
    role: str = "FIRMANTE"
    treatment: str = ""
    source: str = ""
    order: int = 0
    confidence: float = 0.0

    def normalized(self) -> "Signer":
        return replace(
            self,
            # El orden sólo se interpreta al leer un certificado digital.
            # En el resto del flujo se respeta la secuencia ya detectada o canónica.
            name=format_person_name_preserving_order(self.name),
            role=normalize_role(self.role),
            treatment=normalize_treatment(self.treatment),
        )


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(character for character in normalized if not unicodedata.combining(character))


def normalize_for_match(value: str) -> str:
    value = strip_accents(value).casefold()
    value = re.sub(r"\b(?:dr|dra|lic|abg|abog|ing|cr|cra)\.?\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_treatment(value: str) -> str:
    compact = re.sub(r"\s+", " ", (value or "").strip()).upper()
    if not compact:
        return ""
    compact = compact.rstrip(".") + "."
    aliases = {
        "DOCTOR.": "DR.",
        "DOCTORA.": "DRA.",
        "ABOGADO.": "ABOG.",
        "ABOGADA.": "ABOG.",
        "LICENCIADO.": "LIC.",
        "LICENCIADA.": "LIC.",
    }
    return aliases.get(compact, compact)


def extract_treatment(value: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", (value or "").strip(" ,;-—"))
    match = re.match(
        r"^(Dr|Dra|Lic|Abg|Abog|Ing|Cr|Cra)\.\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return "", text
    return normalize_treatment(match.group(1)), match.group(2).strip()


def _title_token(token: str) -> str:
    if not token:
        return token
    if re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]\.", token):
        return token.upper()
    if token.casefold() in {"de", "del", "la", "las", "los", "y", "e"}:
        return token.casefold()
    return token[:1].upper() + token[1:].lower()


def format_person_name_preserving_order(value: str) -> str:
    """Normaliza grafía sin alterar el orden de las palabras.

    Debe utilizarse cuando el orden ya proviene de una fuente confiable
    (texto visible, autoridad canónica o nombre digital ya interpretado).
    """
    treatment, text = extract_treatment(value)
    del treatment
    text = re.sub(r"\s+", " ", text.strip(" ,;.-—"))
    if not text:
        return ""
    return " ".join(_title_token(token) for token in text.split())


def normalize_person_name(value: str) -> str:
    treatment, text = extract_treatment(value)
    del treatment
    text = re.sub(r"\s+", " ", text.strip(" ,;.-—"))
    if not text:
        return ""

    tokens = text.split()

    # Los certificados de firma suelen exportar APELLIDO Nombre SegundoNombre.
    # La rotación se aplica una sola vez al interpretar el certificado.
    leading_upper: list[str] = []
    remaining: list[str] = []
    for token in tokens:
        letters = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", token)
        if not remaining and letters and letters == letters.upper() and len(letters) > 1:
            leading_upper.append(token)
        else:
            remaining.append(token)
    if leading_upper and remaining and any(
        re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", token).islower()
        or (
            re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", token)
            and not re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", token).isupper()
        )
        for token in remaining
    ):
        tokens = remaining + leading_upper

    return format_person_name_preserving_order(" ".join(tokens))


def normalize_role(value: str) -> str:
    raw = re.sub(r"\s+", " ", (value or "").strip(" .,:;-—"))
    if not raw:
        return "FIRMANTE"
    normalized = normalize_for_match(raw)
    subrogante = "subrog" in normalized

    if "prosecret" in normalized:
        base = "PROSECRETARIA" if "prosecretaria" in normalized else "PROSECRETARIO"
    elif "secret" in normalized:
        base = "SECRETARIA" if "secretaria" in normalized else "SECRETARIO"
    elif "ministra" in normalized:
        base = "MINISTRA"
    elif "ministro" in normalized:
        base = "MINISTRO"
    elif "presidenta" in normalized:
        base = "PRESIDENTA"
    elif "presidente" in normalized:
        base = "PRESIDENTE"
    elif "jueza" in normalized:
        base = "JUEZA"
    elif "juez" in normalized:
        base = "JUEZ"
    elif "vocal" in normalized:
        base = "VOCAL"
    elif normalized in {"firmante", "firma"}:
        base = "FIRMANTE"
    else:
        base = raw.upper()

    if subrogante and "SUBROGANTE" not in base:
        base += " SUBROGANTE"
    return base


def role_rank(role: str) -> int:
    normalized = normalize_role(role)
    if any(word in normalized for word in ("MINISTR", "VOCAL", "PRESIDENT", "JUEZ", "JUEZA")):
        return 10
    if "PROSECRET" in normalized:
        return 30
    if "SECRET" in normalized:
        return 20
    return 40


def signer_sort_key(signer: Signer) -> tuple[int, int, str]:
    return role_rank(signer.role), signer.order, normalize_for_match(signer.name)


def parse_signers(value: str) -> list[Signer]:
    text = re.sub(r"^\s*FDO\.?\s*:\s*", "", value or "", flags=re.IGNORECASE)
    results: list[Signer] = []
    pattern = re.compile(r"([^()]+?)\s*\(([^()]+)\)\s*\.?", flags=re.DOTALL)
    for index, match in enumerate(pattern.finditer(text)):
        raw_name = match.group(1).strip(" \t\r\n.;:—-")
        raw_name = re.sub(r"(?:\s+-\s+|\s+—\s+)$", "", raw_name).strip()
        treatment, name = extract_treatment(raw_name)
        if not name:
            continue
        results.append(
            Signer(
                name=name,
                role=match.group(2),
                treatment=treatment,
                source="parsed",
                order=index,
            ).normalized()
        )
    return results


def format_signers(signers: list[Signer]) -> str:
    normalized = [signer.normalized() for signer in signers if signer.name.strip()]
    normalized.sort(key=signer_sort_key)
    parts: list[str] = []
    for signer in normalized:
        display = " ".join(
            part for part in (signer.treatment, signer.name) if part
        ).strip()
        role = normalize_role(signer.role)
        if role == "FIRMANTE":
            role = "CARGO A VERIFICAR"
        parts.append(f"{display.upper()} ({role.upper()}).")
    return " ".join(parts)


def _name_tokens(value: str) -> list[str]:
    return [token for token in normalize_for_match(value).split() if token]


def name_match_score(first: str, second: str) -> float:
    left = _name_tokens(first)
    right = _name_tokens(second)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    left_set = set(left)
    right_set = set(right)
    exact = len(left_set & right_set)

    initial_matches = 0
    for token in left:
        if len(token) != 1:
            continue
        if any(other.startswith(token) for other in right if len(other) > 1):
            initial_matches += 1
    for token in right:
        if len(token) != 1:
            continue
        if any(other.startswith(token) for other in left if len(other) > 1):
            initial_matches += 1

    denominator = max(len(left_set), len(right_set), 1)
    score = (exact + 0.65 * initial_matches) / denominator

    # El apellido coincidente pesa especialmente.
    if left[-1] == right[-1]:
        score += 0.25
    elif left[0] == right[-1] or left[-1] == right[0]:
        score += 0.2

    return min(score, 1.0)
