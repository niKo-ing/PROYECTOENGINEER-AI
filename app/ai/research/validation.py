"""Evidence validation — agreement, conflict, variant mismatch, missing.

The validator never invents agreement: when the evidence cannot confirm a claim
it returns ``INSUFFICIENT_EVIDENCE`` and the assistant is told to say "no sé".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

from app.ai.evidence import Evidence
from app.ai.research.sources import variant_matches


class EvidenceVerdict(StrEnum):
    AGREEMENT = "agreement"
    CONFLICT = "conflict"
    VARIANT_MISMATCH = "variant_mismatch"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass
class ClaimVerdict:
    claim: str
    verdict: EvidenceVerdict
    supported_by: list[Evidence] = field(default_factory=list)
    conflicts_with: list[Evidence] = field(default_factory=list)
    confidence: float = 0.0
    note: str | None = None


_NUMBER_UNIT = re.compile(r"(\d+(?:[.,]\d+)?)\s*([a-z%\"']+|\\\")", re.IGNORECASE)

_UNIT_ALIASES = {
    "gigabyte": "gb", "gigabytes": "gb", "gigas": "gb", "gigs": "gb",
    "megabyte": "mb", "megabytes": "mb",
    "gigahertz": "ghz", "megahertz": "mhz", "hertz": "hz",
    "watt": "w", "watts": "w",
    "mah": "mah", "volts": "v",
}


def normalize_value(value: str | None) -> str:
    """Fold text for comparison: lower, de-accent, collapse whitespace."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def extract_number_units(text: str) -> list[tuple[float, str]]:
    """Return ``(number, unit)`` pairs found in a free-text fragment."""
    if not text:
        return []
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    pairs: list[tuple[float, str]] = []
    for match in _NUMBER_UNIT.finditer(normalized):
        try:
            number = float(match.group(1).replace(",", "."))
        except ValueError:
            continue
        unit = re.sub(r"[^a-z%\"']", "", match.group(2).casefold())
        pairs.append((number, _UNIT_ALIASES.get(unit, unit)))
    return pairs


def values_equivalent(first: str, second: str) -> bool:
    """Two fragments agree when their number+unit fingerprint is equivalent."""
    first_values = extract_number_units(first)
    second_values = extract_number_units(second)
    if first_values and second_values:
        return {rounded for rounded, _unit in first_values} == {rounded for rounded, _unit in second_values} and {unit for _rounded, unit in first_values} == {unit for _rounded, unit in second_values}
    return normalize_value(first) == normalize_value(second) and bool(first)


def classify_evidence(items: list[Evidence], *, claim: str, target_model: str | None = None) -> ClaimVerdict:
    """Classify a claim against a group of evidence items.

    - no usable items                            -> INSUFFICIENT_EVIDENCE
    - items describe a different product variant -> VARIANT_MISMATCH
    - all items agree on the claim value          -> AGREEMENT
    - items carry conflicting values             -> CONFLICT
    - items are qualitative and cannot be compared -> INSUFFICIENT_EVIDENCE
    """
    if not items:
        return ClaimVerdict(claim=claim, verdict=EvidenceVerdict.INSUFFICIENT_EVIDENCE, note="Sin evidencia externa.")

    relevant: list[Evidence] = []
    mismatched: list[Evidence] = []
    for item in items:
        text = _evidence_text(item)
        if not target_model:
            relevant.append(item)
            continue
        if not _mentions_model(text, target_model):
            continue
        if variant_matches(target_model, [text]):
            relevant.append(item)
        else:
            mismatched.append(item)

    if mismatched and not relevant:
        return ClaimVerdict(
            claim=claim,
            verdict=EvidenceVerdict.VARIANT_MISMATCH,
            supported_by=[],
            conflicts_with=mismatched,
            confidence=0.0,
            note="La evidencia corresponde a otra variante del producto, no a esta.",
        )
    if not relevant:
        return ClaimVerdict(claim=claim, verdict=EvidenceVerdict.INSUFFICIENT_EVIDENCE, note="Sin evidencia usable para la variante.")

    return _decide_between(relevant, claim)


def _decide_between(relevant: list[Evidence], claim: str) -> ClaimVerdict:
    """Decide agreement/conflict over the variant-filtered evidence."""
    fingerprint = [(_number_units(text), normalize_value(text)) for text in (_evidence_text(item) for item in relevant)]
    numeric = [fp for fp, _ in fingerprint if fp]

    conflicting = _pairwise_conflict(relevant, fingerprint)
    if conflicting:
        return ClaimVerdict(
            claim=claim,
            verdict=EvidenceVerdict.CONFLICT,
            supported_by=[relevant[0]],
            conflicts_with=conflicting,
            confidence=0.0,
            note="Fuentes en desacuerdo sobre el mismo dato.",
        )

    base = max(item.confidence for item in relevant)
    if numeric:
        consensus_count = len([fp for fp, _ in fingerprint if fp])
        confidence = round(min(0.95, base + 0.15 * (consensus_count - 1)), 2)
        return ClaimVerdict(
            claim=claim,
            verdict=EvidenceVerdict.AGREEMENT,
            supported_by=relevant,
            confidence=confidence,
            note=f"Confirmado por {len(relevant)} fuente(s).",
        )

    unique_texts = {normalized for _fp, normalized in fingerprint if normalized}
    if len(unique_texts) == 1:
        return ClaimVerdict(
            claim=claim,
            verdict=EvidenceVerdict.AGREEMENT,
            supported_by=relevant,
            confidence=round(min(0.9, base), 2),
            note="Fuentes que coinciden en la misma afirmación.",
        )
    return ClaimVerdict(
        claim=claim,
        verdict=EvidenceVerdict.INSUFFICIENT_EVIDENCE,
        supported_by=relevant,
        confidence=0.0,
        note="La evidencia no permite confirmar ni descartar el dato.",
    )


def _pairwise_conflict(relevant: list[Evidence], fingerprint: list[tuple[list[tuple[float, str]], str]]) -> list[Evidence]:
    conflicts: list[Evidence] = []
    for index in range(len(relevant)):
        for jndex in range(index + 1, len(relevant)):
            first_fp, first_text = fingerprint[index]
            second_fp, second_text = fingerprint[jndex]
            if not first_fp or not second_fp:
                continue
            if _conflicting_numeric(first_fp, second_fp):
                conflicts.append(relevant[jndex])
    return conflicts


def _conflicting_numeric(first: list[tuple[float, str]], second: list[tuple[float, str]]) -> bool:
    """Two fragments conflict when the same unit carries no shared value."""
    by_unit_first: dict[str, set[float]] = {}
    by_unit_second: dict[str, set[float]] = {}
    for number, unit in first:
        by_unit_first.setdefault(unit, set()).add(number)
    for number, unit in second:
        by_unit_second.setdefault(unit, set()).add(number)
    shared_units = by_unit_first.keys() & by_unit_second.keys()
    if not shared_units:
        return False
    return any(not (by_unit_first[unit] & by_unit_second[unit]) for unit in shared_units)


def _number_units(text: str) -> list[tuple[float, str]]:
    return extract_number_units(text)


def _mentions_model(text: str, target_model: str) -> bool:
    normalized = normalize_value(target_model)
    tokens = [token for token in re.findall(r"[a-z0-9]+", normalized) if token.isalnum()]
    haystack = normalize_value(text)
    return any(_word_at(haystack, token) for token in tokens)


def _word_at(haystack: str, token: str) -> bool:
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])", haystack))


def _evidence_text(item: Evidence) -> str:
    parts = [item.title, item.content]
    return " ".join(part for part in parts if part) or ""