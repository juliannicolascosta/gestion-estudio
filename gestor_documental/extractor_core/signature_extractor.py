from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import Any

import pymupdf as fitz

from .signer import (
    Signer,
    extract_treatment,
    format_person_name_preserving_order,
    format_signers,
    name_match_score,
    normalize_for_match,
    normalize_person_name,
    normalize_role,
)


logger = logging.getLogger(__name__)


_ROLE_RE = re.compile(
    r"\b(?:juez|jueza|juez\s+subrogante|jueza\s+subrogante|"
    r"secretario|secretaria|secretario\s+subrogante|secretaria\s+subrogante|"
    r"prosecretario|prosecretaria|prosecretario\s+subrogante|"
    r"prosecretaria\s+subrogante|vocal|ministro|ministra|presidente|presidenta|"
    r"actuario|actuaria)\b",
    flags=re.IGNORECASE,
)

_TITLE_RE = re.compile(
    r"^(?:Dr|Dra|Lic|Abg|Abog|Ing|Cr|Cra)\.$",
    flags=re.IGNORECASE,
)


@dataclass
class SignatureExtraction:
    signers: list[Signer] = field(default_factory=list)
    formatted_signers: str = ""
    text_without_signatures: str = ""
    confidence: str = "none"
    page_cutoffs: dict[int, float] = field(default_factory=dict)


@dataclass
class _Line:
    page: int
    block: int
    line: int
    words: list[dict[str, Any]]
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def text(self) -> str:
        return " ".join(str(word["text"]) for word in self.words).strip()

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class _VisualSigner:
    signer: Signer
    page: int
    name_y: float
    name_x: float
    cutoff_y: float


class SignatureExtractor:
    """Extrae firmantes sin IA usando firmas PDF, cargos y geometría visual."""

    def extract(self, document: fitz.Document) -> SignatureExtraction:
        digital = self._extract_digital_signers(document)
        self._restore_visible_name_spelling(document, digital)
        visual = self._extract_visual_signers(document, digital)
        merged = self._merge_signers(digital, visual)

        cutoffs: dict[int, float] = {}
        for candidate in visual:
            current = cutoffs.get(candidate.page)
            if current is None or candidate.cutoff_y < current:
                cutoffs[candidate.page] = candidate.cutoff_y

        for page_number, cutoff in self._signature_only_page_cutoffs(
            document, digital
        ).items():
            current = cutoffs.get(page_number)
            if current is None or cutoff < current:
                cutoffs[page_number] = cutoff

        text_without = self._extract_text_before_cutoffs(document, cutoffs)
        confidence = "none"
        if visual and digital:
            confidence = "very_high"
        elif visual:
            confidence = "high"
        elif digital:
            confidence = "high"

        return SignatureExtraction(
            signers=merged,
            formatted_signers=format_signers(merged),
            text_without_signatures=text_without,
            confidence=confidence,
            page_cutoffs=cutoffs,
        )

    def _extract_digital_signers(self, document: fitz.Document) -> list[Signer]:
        signers: list[Signer] = []
        seen_widgets: set[int] = set()
        order = 0

        for page in document:
            try:
                widgets = list(page.widgets() or [])
            except Exception:
                logger.warning(
                    "No se pudieron leer los campos de firma digital de la página %s.",
                    page.number + 1,
                    exc_info=True,
                )
                widgets = []
            for widget in widgets:
                if widget.xref in seen_widgets or widget.field_type_string != "Signature":
                    continue
                seen_widgets.add(widget.xref)
                widget_object = document.xref_object(widget.xref, compressed=False)
                value_match = re.search(r"/V\s+(\d+)\s+0\s+R", widget_object)
                if not value_match:
                    continue
                signature_object = document.xref_object(
                    int(value_match.group(1)),
                    compressed=False,
                )
                reason = self._pdf_string_value(signature_object, "Reason")
                name = self._name_from_reason(reason)
                if not name:
                    name = self._pdf_string_value(signature_object, "Name")
                if not name:
                    continue
                signers.append(
                    Signer(
                        name=normalize_person_name(name),
                        role="FIRMANTE",
                        treatment="",
                        source="digital",
                        order=order,
                        confidence=1.0,
                    )
                )
                order += 1

        deduplicated: list[Signer] = []
        for signer in signers:
            duplicate = next(
                (
                    existing
                    for existing in deduplicated
                    if name_match_score(existing.name, signer.name) >= 0.9
                ),
                None,
            )
            if duplicate is None:
                deduplicated.append(signer)
        return deduplicated

    def _pdf_string_value(self, object_text: str, key: str) -> str:
        literal = re.search(
            rf"/{re.escape(key)}\s*\(((?:\\.|[^\\)])*)\)",
            object_text,
            flags=re.DOTALL,
        )
        if literal:
            return self._decode_pdf_literal(literal.group(1))

        hexadecimal = re.search(
            rf"/{re.escape(key)}\s*<([0-9A-Fa-f\s]+)>",
            object_text,
            flags=re.DOTALL,
        )
        if not hexadecimal:
            return ""
        compact = re.sub(r"\s+", "", hexadecimal.group(1))
        if len(compact) % 2:
            compact += "0"
        try:
            raw = bytes.fromhex(compact)
        except ValueError:
            return ""
        if raw.startswith(b"\xfe\xff"):
            value = raw[2:].decode("utf-16-be", errors="replace")
        elif raw.startswith(b"\xff\xfe"):
            value = raw[2:].decode("utf-16-le", errors="replace")
        else:
            try:
                value = raw.decode("utf-8")
            except UnicodeDecodeError:
                value = raw.decode("latin-1", errors="replace")
        return re.sub(r"\s+", " ", value).strip()

    def _decode_pdf_literal(self, value: str) -> str:
        output: list[str] = []
        index = 0
        escapes = {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "b": "\b",
            "f": "\f",
            "(": "(",
            ")": ")",
            "\\": "\\",
        }
        while index < len(value):
            character = value[index]
            if character != "\\":
                output.append(character)
                index += 1
                continue

            index += 1
            if index >= len(value):
                break
            escaped = value[index]
            if escaped in "\r\n":
                if escaped == "\r" and index + 1 < len(value) and value[index + 1] == "\n":
                    index += 1
                index += 1
                continue
            if escaped in "01234567":
                digits = escaped
                index += 1
                while index < len(value) and len(digits) < 3 and value[index] in "01234567":
                    digits += value[index]
                    index += 1
                output.append(chr(int(digits, 8)))
                continue
            output.append(escapes.get(escaped, escaped))
            index += 1

        decoded = "".join(output)
        try:
            utf8_candidate = decoded.encode("latin-1").decode("utf-8")
            if any(marker in decoded for marker in ("Ã", "Â")):
                decoded = utf8_candidate
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        return re.sub(r"\s+", " ", decoded).strip()

    def _name_from_reason(self, reason: str) -> str:
        match = re.search(
            r"Firmado\s+Digitalmente\s+por\s+(.+?)(?:,\s*el\b|$)",
            reason or "",
            flags=re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    def _restore_visible_name_spelling(
        self,
        document: fitz.Document,
        signers: list[Signer],
    ) -> None:
        """Recupera tildes visibles que pueden faltar en el certificado."""
        visible_tokens: dict[str, str] = {}
        for page in document:
            for word in page.get_text("words", sort=True):
                token = str(word[4]).strip(" ,.;:()[]{}")
                normalized = normalize_for_match(token)
                if normalized and any(character.isalpha() for character in token):
                    previous = visible_tokens.get(normalized, "")
                    # Se prefiere la variante con diacríticos o mayor información.
                    if not previous or (token != normalized and previous == normalize_for_match(previous)):
                        visible_tokens[normalized] = token

        for signer in signers:
            tokens = normalize_person_name(signer.name).split()
            restored: list[str] = []
            for token in tokens:
                normalized = normalize_for_match(token)
                restored.append(visible_tokens.get(normalized, token))
            signer.name = format_person_name_preserving_order(" ".join(restored))

    def _signature_only_page_cutoffs(
        self,
        document: fitz.Document,
        digital_signers: list[Signer],
    ) -> dict[int, float]:
        """Excluye páginas finales que contienen sólo repeticiones de firmas."""
        allowed: set[str] = set()
        for signer in digital_signers:
            allowed.update(normalize_for_match(signer.name).split())
        allowed.update(
            {
                "dr", "dra", "juez", "jueza", "secretario", "secretaria",
                "prosecretario", "prosecretaria", "vocal", "ministro",
                "ministra", "presidente", "presidenta", "art", "ley",
            }
        )
        if not allowed:
            return {}

        result: dict[int, float] = {}
        for page_number, page in enumerate(document):
            words = [str(word[4]).strip() for word in page.get_text("words", sort=True)]
            normalized_words = [normalize_for_match(word) for word in words]
            normalized_words = [word for word in normalized_words if word]
            if not normalized_words or len(normalized_words) > 10:
                continue
            tokens = [token for word in normalized_words for token in word.split()]
            if tokens and all(token in allowed or token.isdigit() for token in tokens):
                signer_tokens = [token for token in tokens if token in allowed]
                if signer_tokens:
                    result[page_number] = 0.0
        return result

    def _extract_visual_signers(
        self,
        document: fitz.Document,
        digital_signers: list[Signer],
    ) -> list[_VisualSigner]:
        candidates: list[_VisualSigner] = []
        for page_number, page in enumerate(document):
            lines = self._page_lines(page, page_number)
            if not lines:
                continue
            candidates.extend(
                self._visual_from_inline_role_names(lines, page.rect.height)
            )
            candidates.extend(
                self._visual_from_role_lines(lines, page.rect.height)
            )
            candidates.extend(
                self._visual_from_digital_names(
                    lines,
                    digital_signers,
                    page.rect.height,
                    candidates,
                )
            )

        deduplicated: list[_VisualSigner] = []
        for candidate in sorted(candidates, key=lambda item: (item.page, item.name_y, item.name_x)):
            duplicate = next(
                (
                    existing
                    for existing in deduplicated
                    if existing.page == candidate.page
                    and name_match_score(existing.signer.name, candidate.signer.name) >= 0.8
                ),
                None,
            )
            if duplicate:
                if duplicate.signer.role == "FIRMANTE" and candidate.signer.role != "FIRMANTE":
                    duplicate.signer.role = candidate.signer.role
                if not duplicate.signer.treatment and candidate.signer.treatment:
                    duplicate.signer.treatment = candidate.signer.treatment
                duplicate.cutoff_y = min(duplicate.cutoff_y, candidate.cutoff_y)
                continue
            deduplicated.append(candidate)
        return deduplicated

    def _page_lines(self, page: fitz.Page, page_number: int) -> list[_Line]:
        groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for word in page.get_text("words", sort=True):
            x0, y0, x1, y1, text, block, line, word_index = word[:8]
            groups.setdefault((int(block), int(line)), []).append(
                {
                    "x0": float(x0),
                    "y0": float(y0),
                    "x1": float(x1),
                    "y1": float(y1),
                    "text": str(text),
                    "word": int(word_index),
                }
            )

        lines: list[_Line] = []
        for (block, line_number), words in groups.items():
            words.sort(key=lambda item: item["x0"])
            lines.append(
                _Line(
                    page=page_number,
                    block=block,
                    line=line_number,
                    words=words,
                    x0=min(word["x0"] for word in words),
                    y0=min(word["y0"] for word in words),
                    x1=max(word["x1"] for word in words),
                    y1=max(word["y1"] for word in words),
                )
            )
        lines.sort(key=lambda item: (item.y0, item.x0))

        # Distintos generadores PDF pueden guardar una misma línea visual en
        # bloques separados. Se unifican por coordenada vertical para que las
        # firmas en columnas sigan siendo una sola línea lógica.
        merged: list[_Line] = []
        for current in lines:
            if merged and abs(merged[-1].y0 - current.y0) <= 2.0:
                previous = merged[-1]
                words = sorted(previous.words + current.words, key=lambda item: item["x0"])
                merged[-1] = _Line(
                    page=page_number,
                    block=min(previous.block, current.block),
                    line=min(previous.line, current.line),
                    words=words,
                    x0=min(previous.x0, current.x0),
                    y0=min(previous.y0, current.y0),
                    x1=max(previous.x1, current.x1),
                    y1=max(previous.y1, current.y1),
                )
            else:
                merged.append(current)
        return merged

    def _visual_from_inline_role_names(
        self,
        lines: list[_Line],
        page_height: float,
    ) -> list[_VisualSigner]:
        results: list[_VisualSigner] = []
        pattern = re.compile(
            r"^\s*(Secretar[ií]a|Secretari[oa]|Prosecretar[ií]a|"
            r"Prosecretari[oa]|Juez|Jueza|Vocal|Presidencia|"
            r"Presidente|Presidenta|Ministro|Ministra)\s*:\s*(.+?)\s*$",
            flags=re.IGNORECASE,
        )
        for line in lines:
            if line.y0 < page_height * 0.25:
                continue
            match = pattern.match(line.text)
            if not match:
                continue
            role_text, raw_name = match.groups()
            treatment, name = extract_treatment(raw_name)
            if not name or len(normalize_for_match(name).split()) < 2:
                continue
            role = normalize_role(role_text)
            if role in {"SECRETARIA", "SECRETARIO"}:
                role = "SECRETARIO" if treatment == "DR." else "SECRETARIA"
            elif role in {"PROSECRETARIA", "PROSECRETARIO"}:
                role = "PROSECRETARIO" if treatment == "DR." else "PROSECRETARIA"
            elif role == "PRESIDENCIA":
                role = "PRESIDENTE" if treatment == "DR." else "PRESIDENTA"
            results.append(
                _VisualSigner(
                    signer=Signer(
                        name=name,
                        role=role,
                        treatment=treatment,
                        source="visual_inline_role",
                        order=len(results),
                        confidence=0.98,
                    ),
                    page=line.page,
                    name_y=line.y0,
                    name_x=line.center_x,
                    cutoff_y=line.y0,
                )
            )
        return results

    def _visual_from_role_lines(self, lines: list[_Line], page_height: float) -> list[_VisualSigner]:
        results: list[_VisualSigner] = []
        for index, role_line in enumerate(lines):
            if role_line.y0 < page_height * 0.25:
                continue
            role_groups = self._role_groups(role_line)
            if not role_groups:
                continue

            previous_lines = [
                line
                for line in lines[max(0, index - 4):index]
                if 0 <= role_line.y0 - line.y1 <= 65
            ]
            if not previous_lines:
                continue

            name_line = max(previous_lines, key=lambda line: line.y0)
            name_groups = self._split_word_groups(name_line.words)
            name_groups = [group for group in name_groups if self._looks_like_name(group)]
            if not name_groups:
                continue

            used: set[int] = set()
            for role_text, role_x in role_groups:
                ranked = sorted(
                    enumerate(name_groups),
                    key=lambda item: abs(self._group_center(item[1]) - role_x),
                )
                selected_index = next((idx for idx, _ in ranked if idx not in used), None)
                if selected_index is None:
                    continue
                used.add(selected_index)
                group = name_groups[selected_index]
                raw_name = " ".join(word["text"] for word in group)
                treatment, name = extract_treatment(raw_name)
                if not name:
                    continue
                cutoff = self._signature_cutoff(lines, name_line)
                results.append(
                    _VisualSigner(
                        signer=Signer(
                            name=name,
                            role=normalize_role(role_text),
                            treatment=treatment,
                            source="visual_role",
                            order=len(results),
                            confidence=0.95,
                        ),
                        page=role_line.page,
                        name_y=name_line.y0,
                        name_x=self._group_center(group),
                        cutoff_y=cutoff,
                    )
                )
        return results

    def _role_groups(self, line: _Line) -> list[tuple[str, float]]:
        groups: list[tuple[str, float]] = []
        words = line.words
        index = 0
        while index < len(words):
            token = words[index]["text"].strip(" .,:;-")
            candidate = token
            if index + 1 < len(words) and words[index + 1]["text"].casefold().startswith("subrog"):
                candidate += " " + words[index + 1]["text"]
            if _ROLE_RE.fullmatch(candidate):
                x1 = words[index + 1]["x1"] if " " in candidate else words[index]["x1"]
                groups.append((candidate, (words[index]["x0"] + x1) / 2))
                index += 2 if " " in candidate else 1
                continue
            index += 1
        return groups

    def _split_word_groups(self, words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        if not words:
            return []
        groups: list[list[dict[str, Any]]] = [[words[0]]]
        average_height = sum(word["y1"] - word["y0"] for word in words) / len(words)
        threshold = max(28.0, average_height * 2.2)
        for word in words[1:]:
            gap = word["x0"] - groups[-1][-1]["x1"]
            if gap > threshold:
                groups.append([word])
            else:
                groups[-1].append(word)
        return groups

    def _looks_like_name(self, group: list[dict[str, Any]]) -> bool:
        tokens = [str(word["text"]).strip(" ,;-") for word in group]
        tokens = [token for token in tokens if token]
        if len(tokens) < 2:
            return False
        if _TITLE_RE.match(tokens[0]):
            return len(tokens) >= 3
        letters = [re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", token) for token in tokens]
        letters = [token for token in letters if token]
        if len(letters) < 2:
            return False
        uppercase = sum(token == token.upper() for token in letters if len(token) > 1)
        return uppercase >= max(1, len(letters) - 1)

    def _group_center(self, group: list[dict[str, Any]]) -> float:
        return (group[0]["x0"] + group[-1]["x1"]) / 2

    def _signature_cutoff(self, lines: list[_Line], name_line: _Line) -> float:
        cutoff = name_line.y0
        previous = [
            line
            for line in lines
            if line.page == name_line.page and 0 < name_line.y0 - line.y1 <= 35
        ]
        if previous:
            closest = max(previous, key=lambda line: line.y0)
            compact = re.sub(r"\s+", "", closest.text)
            if compact.count(".") >= 8 or compact.count("_") >= 6 or "…" in compact:
                cutoff = min(cutoff, closest.y0)
        return cutoff

    def _visual_from_digital_names(
        self,
        lines: list[_Line],
        digital_signers: list[Signer],
        page_height: float,
        existing: list[_VisualSigner],
    ) -> list[_VisualSigner]:
        results: list[_VisualSigner] = []
        for digital in digital_signers:
            if any(name_match_score(digital.name, item.signer.name) >= 0.8 for item in existing + results):
                continue
            best: tuple[float, _Line, list[dict[str, Any]]] | None = None
            for line in lines:
                if line.y0 < page_height * 0.25:
                    continue
                for group in self._split_word_groups(line.words):
                    group_text = " ".join(word["text"] for word in group)
                    if self._looks_like_name(group):
                        score = name_match_score(digital.name, group_text)
                    else:
                        visible_tokens = normalize_for_match(group_text).split()
                        digital_tokens = normalize_for_match(digital.name).split()
                        if (
                            len(visible_tokens) == 1
                            and visible_tokens[0] in digital_tokens
                            and len(visible_tokens[0]) >= 4
                            and group_text.strip().upper() == group_text.strip()
                        ):
                            token = visible_tokens[0]
                            score = 0.9 if token in {digital_tokens[0], digital_tokens[-1]} else 0.7
                        else:
                            continue
                    if score >= 0.62 and (best is None or score > best[0]):
                        best = (score, line, group)
            if best is None:
                continue
            score, name_line, group = best
            treatment, visible_name = extract_treatment(
                " ".join(word["text"] for word in group)
            )
            role = self._role_below_name(lines, name_line, self._group_center(group))
            results.append(
                _VisualSigner(
                    signer=Signer(
                        name=digital.name or visible_name,
                        role=role or "FIRMANTE",
                        treatment=treatment,
                        source="visual_digital",
                        order=len(existing) + len(results),
                        confidence=0.85 if role else 0.72,
                    ),
                    page=name_line.page,
                    name_y=name_line.y0,
                    name_x=self._group_center(group),
                    cutoff_y=self._signature_cutoff(lines, name_line),
                )
            )
        return results

    def _role_below_name(self, lines: list[_Line], name_line: _Line, name_x: float) -> str:
        next_lines = [
            line
            for line in lines
            if line.page == name_line.page and 0 <= line.y0 - name_line.y1 <= 45
        ]
        for line in sorted(next_lines, key=lambda item: item.y0):
            roles = self._role_groups(line)
            if not roles:
                continue
            return min(roles, key=lambda item: abs(item[1] - name_x))[0]
        return ""

    def _merge_signers(
        self,
        digital: list[Signer],
        visual: list[_VisualSigner],
    ) -> list[Signer]:
        merged: list[Signer] = []
        used_digital: set[int] = set()

        for visual_index, candidate in enumerate(visual):
            best_index = -1
            best_score = 0.0
            for index, digital_signer in enumerate(digital):
                if index in used_digital:
                    continue
                score = name_match_score(candidate.signer.name, digital_signer.name)
                if score > best_score:
                    best_score = score
                    best_index = index
            signer = candidate.signer
            if best_index >= 0 and best_score >= 0.58:
                used_digital.add(best_index)
                digital_signer = digital[best_index]
                signer = Signer(
                    name=self._merge_name_spelling(
                        digital_signer.name,
                        signer.name,
                    ),
                    role=signer.role,
                    treatment=signer.treatment,
                    source="digital+visual",
                    order=visual_index,
                    confidence=1.0,
                )
            merged.append(signer)

        for index, signer in enumerate(digital):
            if index in used_digital:
                continue
            merged.append(
                Signer(
                    name=signer.name,
                    role=signer.role,
                    treatment=signer.treatment,
                    source=signer.source,
                    order=len(visual) + index,
                    confidence=signer.confidence,
                )
            )

        deduplicated: list[Signer] = []
        for signer in merged:
            duplicate = next(
                (
                    existing
                    for existing in deduplicated
                    if name_match_score(existing.name, signer.name) >= 0.88
                ),
                None,
            )
            if duplicate is None:
                deduplicated.append(signer)
                continue
            if duplicate.role == "FIRMANTE" and signer.role != "FIRMANTE":
                duplicate.role = signer.role
            if not duplicate.treatment and signer.treatment:
                duplicate.treatment = signer.treatment
            if signer.confidence > duplicate.confidence:
                duplicate.confidence = signer.confidence
                duplicate.source = signer.source
            duplicate.order = min(duplicate.order, signer.order)
        return deduplicated

    def _merge_name_spelling(self, full_name: str, visible_name: str) -> str:
        full_tokens = format_person_name_preserving_order(full_name).split()
        visible_tokens = format_person_name_preserving_order(visible_name).split()
        if not full_tokens or not visible_tokens:
            return normalize_person_name(full_name or visible_name)

        visible_by_normalized = {
            normalize_for_match(token): token
            for token in visible_tokens
            if normalize_for_match(token)
        }
        merged: list[str] = []
        for token in full_tokens:
            normalized = normalize_for_match(token)
            merged.append(visible_by_normalized.get(normalized, token))
        return format_person_name_preserving_order(" ".join(merged))

    def _extract_text_before_cutoffs(
        self,
        document: fitz.Document,
        cutoffs: dict[int, float],
    ) -> str:
        pages: list[str] = []
        for page_number, page in enumerate(document):
            cutoff = cutoffs.get(page_number)
            if cutoff is None:
                pages.append(page.get_text("text", sort=True).strip())
                continue

            output_lines: list[str] = []
            page_dict = page.get_text("dict", sort=True)
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    bbox = line.get("bbox") or (0, 0, 0, 0)
                    if float(bbox[1]) >= cutoff - 0.5:
                        continue
                    text = "".join(
                        str(span.get("text", ""))
                        for span in line.get("spans", [])
                    ).rstrip()
                    if text.strip():
                        output_lines.append(text)
            pages.append("\n".join(output_lines).strip())
        return "\n".join(page for page in pages if page).strip()
