from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

import pymupdf as fitz

from .resolution_data import ResolutionData
from .signer import Signer, format_signers
from .signature_extractor import SignatureExtractor


class PDFManager:
    def __init__(self) -> None:
        self.signature_extractor = SignatureExtractor()

    COURT_PREFIXES = (
        "JUZG.",
        "JUZGADO",
        "TRIBUNAL",
        "CÁMARA",
        "CAMARA",
        "CORTE",
    )

    VISTO_MARKERS = ("Y VISTOS", "Y VISTO", "VISTOS", "VISTO")
    CONSIDERANDO_MARKERS = (
        "Y CONSIDERANDOS",
        "Y CONSIDERANDO",
        "CONSIDERANDOS",
        "CONSIDERANDO",
    )
    DISPOSITIVE_MARKERS = (
        "RESUELVEN",
        "RESUELVE",
        "RESUELVO",
        "FALLAN",
        "FALLA",
        "FALLO",
    )
    DISPOSITIVE_INTRODUCTIONS = (
        "POR TODO LO EXPUESTO",
        "POR LO EXPUESTO",
        "POR ELLO",
        "POR ESTAS CONSIDERACIONES",
        "EN MÉRITO DE LO EXPUESTO",
        "EN MERITO DE LO EXPUESTO",
        "POR LOS FUNDAMENTOS EXPUESTOS",
        "EN CONSECUENCIA",
    )
    DISPOSITIVE_SUBJECTS = (
        "EL TRIBUNAL",
        "LA CÁMARA",
        "LA CAMARA",
        "ESTE JUZGADO",
        "EL JUZGADO",
        "SE",
    )

    def load_source(self, file_path: str) -> dict:
        path = str(Path(file_path).resolve())

        try:
            with fitz.open(path) as document:
                raw_text = self._extract_text(document)
                signatures = self.signature_extractor.extract(document)
                metadata = self._extract_metadata(
                    raw_text,
                    signatures.formatted_signers,
                )
                metadata.texto = self._extract_notifiable_text(
                    signatures.text_without_signatures or raw_text,
                    metadata,
                )

                return {
                    "path": path,
                    "name": Path(path).name,
                    "pages": document.page_count,
                    "raw_text": raw_text,
                    "metadata": metadata,
                }
        except Exception as error:
            raise RuntimeError(
                f"No se pudo leer el archivo PDF:\n{path}\n\n{error}"
            ) from error

    def count_pages(self, file_path: str) -> int:
        path = str(Path(file_path).resolve())

        try:
            with fitz.open(path) as document:
                return document.page_count
        except Exception as error:
            raise RuntimeError(
                f"No se pudo leer la documental adjunta:\n{path}\n\n{error}"
            ) from error

    def _extract_text(self, document: fitz.Document) -> str:
        pages = [
            page.get_text("text", sort=True)
            for page in document
        ]
        return "\n".join(pages).replace("\r", "").strip()

    def _extract_metadata(
        self,
        text: str,
        firmantes: str = "",
    ) -> ResolutionData:
        data = ResolutionData()
        lines = self._clean_lines(text)

        cuij_match = re.search(r"\b\d{2}-\d{8}-\d\b", text)
        if cuij_match:
            data.cuij = self._digits(cuij_match.group(0))

        barcode_match = re.search(r"\*(\d{8,20})\*", text)
        if barcode_match:
            data.barcode = self._digits(barcode_match.group(1))

        data.caratula = self._extract_caratula(lines, data.cuij)
        if data.caratula:
            por, contra, sobre = self._split_caratula(data.caratula)
            data.por = por
            data.contra = contra
            data.sobre = sobre

        data.tribunal_detectado = self._extract_court_line(lines, data.cuij)
        data.localidad_detectada = self._extract_locality(text)
        data.fecha = self._extract_date(text)
        data.firmantes = firmantes or self._extract_signers_from_text(text)

        resolution_marker = self._find_dispositive_marker(text)
        data.tipo_interno = "resolution" if resolution_marker else "decree"

        return data

    def _extract_caratula(
        self,
        lines: list[str],
        cuij_digits: str,
    ) -> str:
        if not cuij_digits:
            return ""

        cuij_index = -1
        for index, line in enumerate(lines):
            if self._digits(line) == cuij_digits:
                cuij_index = index
                break

        if cuij_index <= 0:
            return ""

        candidates: list[str] = []
        for index in range(cuij_index - 1, max(-1, cuij_index - 7), -1):
            line = lines[index].strip()

            if not line:
                continue

            if re.fullmatch(r"\*?\d{8,}\*?", line):
                break

            upper = line.upper()
            if upper.startswith(self.COURT_PREFIXES):
                break

            candidates.append(line)

            joined = " ".join(reversed(candidates))
            if re.search(r"\sC\s*/\s", joined, re.IGNORECASE) and re.search(
                r"\sS\s*/\s",
                joined,
                re.IGNORECASE,
            ):
                break

        caratula = " ".join(reversed(candidates))
        caratula = re.sub(r"\s+", " ", caratula).strip(" -")
        return caratula

    def _split_caratula(self, caratula: str) -> tuple[str, str, str]:
        """Separa carátulas aun cuando no exista parte demandada.

        Formas frecuentes:
        - ACTOR C/ DEMANDADO S/ CAUSA
        - ACTOR S/ CAUSA
        - ACTOR C/ DEMANDADO
        """
        text = re.sub(r"\s+", " ", caratula or "").strip(" -")
        if not text:
            return "", "", ""

        c_separator = r"\s+ C \s* / \s*"
        s_separator = r"\s+ S \s* / \s*"

        standard = re.match(
            rf"^(.+?){c_separator}(.+?){s_separator}(.+)$",
            text,
            flags=re.IGNORECASE | re.VERBOSE,
        )
        if standard:
            values = standard.groups()
        else:
            without_defendant = re.match(
                rf"^(.+?){s_separator}(.+)$",
                text,
                flags=re.IGNORECASE | re.VERBOSE,
            )
            if without_defendant:
                actor, cause = without_defendant.groups()
                values = (actor, "", cause)
            else:
                without_cause = re.match(
                    rf"^(.+?){c_separator}(.+)$",
                    text,
                    flags=re.IGNORECASE | re.VERBOSE,
                )
                if without_cause:
                    actor, defendant = without_cause.groups()
                    values = (actor, defendant, "")
                else:
                    # No se inventa una estructura: se conserva como parte actora.
                    values = (text, "", "")

        return tuple(
            re.sub(r"\s+", " ", value).strip(" ,;-").upper()
            for value in values
        )

    def _extract_court_line(self, lines: list[str], cuij_digits: str = "") -> str:
        # Prioridad: la primera línea institucional posterior al CUIJ.
        if cuij_digits:
            for index, line in enumerate(lines):
                if self._digits(line) != cuij_digits:
                    continue
                for candidate in lines[index + 1 : index + 6]:
                    upper = candidate.upper()
                    if upper.startswith(self.COURT_PREFIXES):
                        return candidate.strip(" .,-")
                break

        # Contingencia para PDFs con otro orden visual.
        for line in lines:
            upper = line.upper()
            if upper.startswith(self.COURT_PREFIXES):
                return line.strip(" .,-")
        return ""

    def _extract_locality(self, text: str) -> str:
        date_pattern = re.compile(
            r"^\s*([A-Za-zÁÉÍÓÚáéíóúÑñ .]{2,60}?)\s*,\s*"
            r"\d{1,2}\s+de\s+[A-Za-zÁÉÍÓÚáéíóúÑñ]+\s+de\s+\d{4}\.?\s*$",
            flags=re.IGNORECASE,
        )
        incomplete_date_pattern = re.compile(
            r"^\s*(?:N[.º°o]*\s*)?([A-Za-zÁÉÍÓÚáéíóúÑñ .]{2,60}?)\s*,\s*"
            r"(?:de\s+)?[A-Za-zÁÉÍÓÚáéíóúÑñ]+\s+de\s+\d{4}\.?-?\s*$",
            flags=re.IGNORECASE,
        )
        forbidden = {
            "poder judicial",
            "tribunales",
            "cedula",
            "notificacion",
            "deberia",
            "configurable",
        }
        for line in text.splitlines():
            match = date_pattern.match(line) or incomplete_date_pattern.match(line)
            if not match:
                continue
            locality = re.sub(r"\s+", " ", match.group(1)).strip(" .,-")
            normalized = locality.casefold()
            if any(word in normalized for word in forbidden):
                continue
            if len(locality.split()) > 6:
                continue
            return locality.title()
        return ""

    def _extract_date(self, text: str) -> str:
        header = self._find_date_header(text)
        if not header:
            return ""

        textual = header.groupdict().get("textual_date")
        if textual:
            parsed = self.parse_spanish_date(textual)
            if parsed:
                return parsed.strftime("%d/%m/%Y")

        numeric = header.groupdict().get("numeric_date")
        if numeric:
            day, month, year = re.split(r"[/-]", numeric)
            return f"{int(day):02d}/{int(month):02d}/{year}"

        return ""

    def _extract_signers_from_text(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        role_pattern = re.compile(
            r"\b(Juez(?:a)?|Secretari[oa]|Prosecretari[oa]|Vocal|"
            r"Ministr[oa]|Presidente|Presidenta)\b",
            flags=re.IGNORECASE,
        )
        for index in range(len(lines) - 1, 0, -1):
            roles = role_pattern.findall(lines[index])
            names = [
                match.group(0).strip(" ,;-")
                for match in re.finditer(
                    r"(?:Dr|Dra)\.\s+.*?(?=(?:Dr|Dra)\.\s+|$)",
                    lines[index - 1],
                    flags=re.IGNORECASE,
                )
            ]
            if not names or len(names) != len(roles):
                continue
            signers: list[Signer] = []
            for order, (name, role) in enumerate(zip(names, roles)):
                treatment_match = re.match(
                    r"^(Dr|Dra)\.\s+(.+)$",
                    name,
                    flags=re.IGNORECASE,
                )
                if treatment_match:
                    treatment = treatment_match.group(1) + "."
                    clean_name = treatment_match.group(2)
                else:
                    treatment = ""
                    clean_name = name
                signers.append(
                    Signer(
                        name=clean_name,
                        role=role,
                        treatment=treatment,
                        order=order,
                        source="text_fallback",
                    )
                )
            return format_signers(signers)
        return ""

    def _extract_notifiable_text(
        self,
        text: str,
        metadata: ResolutionData,
    ) -> str:
        text = re.sub(r"\*+\d+\*+", "", text)

        disposition = self._find_dispositive_marker(text)
        if disposition:
            prefixes: list[str] = []
            vistos = self._find_marker(
                text[: disposition.start()], self.VISTO_MARKERS
            )
            considerandos = self._find_marker(
                text[: disposition.start()], self.CONSIDERANDO_MARKERS
            )
            if vistos:
                prefixes.append(
                    f"{self._canonical_marker(vistos.group('marker'))}: (...)"
                )
            if considerandos:
                prefixes.append(
                    f"{self._canonical_marker(considerandos.group('marker'))}: (...)"
                )

            dispositive_text = text[disposition.end():].strip()
            marker = self._canonical_marker(disposition.group("marker"))
            parts = prefixes + [f"{marker}: {dispositive_text}".strip()]
            return self._to_single_line(". ".join(part.rstrip(" .") for part in parts))

        date_line_match = self._find_date_header(text)

        if date_line_match:
            return self._to_single_line(text[date_line_match.start():])

        lines = self._clean_lines(text)
        if metadata.cuij:
            for index, line in enumerate(lines):
                if self._digits(line) == metadata.cuij:
                    lines = lines[index + 2 :]
                    break

        return self._to_single_line(" ".join(lines))

    def _marker_pattern(self, markers: tuple[str, ...]) -> re.Pattern[str]:
        alternatives = self._marker_alternatives(markers)
        return re.compile(
            rf"(?im)^[ \t]*(?P<marker>{alternatives})[ \t]*:?[ \t]*"
        )

    def _dispositive_marker_pattern(self) -> re.Pattern[str]:
        introductions = "|".join(
            self._phrase_pattern(value)
            for value in self.DISPOSITIVE_INTRODUCTIONS
        )
        subjects = "|".join(
            self._phrase_pattern(value)
            for value in self.DISPOSITIVE_SUBJECTS
        )
        markers = self._marker_alternatives(self.DISPOSITIVE_MARKERS)
        return re.compile(
            rf"(?im)^[ \t]*"
            rf"(?:(?:{introductions})[ \t]*[,;:]?[ \t]*)?"
            rf"(?:(?:{subjects})[ \t]+)?"
            rf"(?P<marker>{markers})[ \t]*:?[ \t]*"
        )

    def _marker_alternatives(self, markers: tuple[str, ...]) -> str:
        alternatives: list[str] = []
        for marker in sorted(markers, key=len, reverse=True):
            words = marker.split()
            word_patterns = [
                r"[ \t]*".join(re.escape(letter) for letter in word)
                for word in words
            ]
            alternatives.append(r"[ \t]+".join(word_patterns))
        return "|".join(alternatives)

    def _phrase_pattern(self, value: str) -> str:
        return r"[ \t]+".join(re.escape(word) for word in value.split())

    def _find_marker(
        self,
        text: str,
        markers: tuple[str, ...],
    ) -> re.Match[str] | None:
        return self._marker_pattern(markers).search(text or "")

    def _find_dispositive_marker(self, text: str) -> re.Match[str] | None:
        return self._dispositive_marker_pattern().search(text or "")

    def _find_date_header(self, text: str) -> re.Match[str] | None:
        locality = r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ .]{2,60}?"
        month = r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+"
        textual = re.compile(
            rf"(?im)^[ \t]*(?:N[.º°o]*[ \t]*)?"
            rf"(?P<locality>{locality})[ \t]*,[ \t]*"
            rf"(?P<textual_date>\d{{1,2}}[ \t]+de[ \t]+{month}"
            rf"[ \t]+de[ \t]+\d{{4}})[ \t]*\.?-?[ \t]*$"
        )
        numeric = re.compile(
            rf"(?im)^[ \t]*(?:N[.º°o]*[ \t]*)?"
            rf"(?P<locality_numeric>{locality})[ \t]*,[ \t]*"
            rf"(?P<numeric_date>\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{4}})"
            rf"[ \t]*\.?-?[ \t]*$"
        )
        matches = [
            match
            for match in (textual.search(text or ""), numeric.search(text or ""))
            if match is not None
        ]
        return min(matches, key=lambda match: match.start()) if matches else None

    def _canonical_marker(self, value: str) -> str:
        compact = re.sub(r"\s+", "", value or "").upper()
        mapping = {
            "YVISTOS": "Y VISTOS",
            "YVISTO": "Y VISTO",
            "VISTOS": "VISTOS",
            "VISTO": "VISTO",
            "YCONSIDERANDOS": "Y CONSIDERANDOS",
            "YCONSIDERANDO": "Y CONSIDERANDO",
            "CONSIDERANDOS": "CONSIDERANDOS",
            "CONSIDERANDO": "CONSIDERANDO",
            "RESUELVEN": "RESUELVEN",
            "RESUELVE": "RESUELVE",
            "RESUELVO": "RESUELVO",
            "FALLAN": "FALLAN",
            "FALLA": "FALLA",
            "FALLO": "FALLO",
        }
        return mapping.get(compact, compact)

    def _clean_lines(self, text: str) -> list[str]:
        return [
            re.sub(r"\s+", " ", line).strip()
            for line in text.splitlines()
            if line.strip()
        ]

    def _to_single_line(self, text: str) -> str:
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _digits(self, value: str) -> str:
        return "".join(character for character in value if character.isdigit())

    @staticmethod
    def parse_spanish_date(value: str) -> datetime | None:
        months = {
            "enero": 1,
            "febrero": 2,
            "marzo": 3,
            "abril": 4,
            "mayo": 5,
            "junio": 6,
            "julio": 7,
            "agosto": 8,
            "septiembre": 9,
            "setiembre": 9,
            "octubre": 10,
            "noviembre": 11,
            "diciembre": 12,
        }
        match = re.search(
            r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúÑñ]+)\s+de\s+(\d{4})",
            value,
            flags=re.IGNORECASE,
        )
        if not match:
            return None

        day = int(match.group(1))
        month_name = match.group(2).lower()
        month = months.get(month_name)
        year = int(match.group(3))

        if not month:
            return None

        try:
            return datetime(year, month, day)
        except ValueError:
            return None
