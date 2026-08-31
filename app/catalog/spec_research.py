"""LLM-based research extraction grounded in a canonical source page.

The LLM only sees the plain-text context extracted from the registered source
page and must quote an ``evidence`` fragment for every value. Extraction is
post-validated: a value is only kept when its evidence (or the value itself)
actually appears in the page context, so the pipeline never stores invented
facts. Resulting values are persisted with full provenance (source_type,
source_url, confidence, verification_status=review).
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.catalog.ai_config import AIResearchConfig
from app.catalog.spec_backfill import _parse_boolean, _parse_number_with_unit, _ram_type, _resolution, _storage_type
from app.catalog.spec_sources import SpecSource
from app.models.catalog import CategorySpecificationDefinition, Product, SpecValueKind, SpecValueSourceType, SpecVerificationStatus
from app.services.product_spec_value_service import SpecValueInput

EXTRACTION_METHOD = "spec_source_fetch:llm_extraction"
DEFAULT_CONFIDENCE = Decimal("0.90")
MAX_EXTRACTED_ITEMS = 40
MAX_VALUE_CHARS = 200

SYSTEM_INSTRUCTIONS = (
    "Eres un técnico que extrae especificaciones de un componente (CPU, GPU o celular) "
    "usando SOLO la página técnica de referencia que se te entrega.\n"
    "Reglas estrictas:\n"
    "1. Usa ÚNICAMENTE el texto de la página. NO inventes valores ni los completes con conocimiento previo.\n"
    "2. Cada valor debe citarse: incluye 'evidence', un fragmento literal corto del texto fuente donde aparece.\n"
    "3. Responde SOLO para el 'Modelo a investigar'; ignora otras variantes, modelos aledaños o filas vecinas.\n"
    "4. Usa únicamente claves de la lista de definiciones. Si un dato no aparece en el texto, omitelo.\n"
    "5. Normaliza la unidad al formato de la definición (GHz para frecuencia, MB para cache, W para TDP, "
    "mAh para batería, \\\" para pantallla, MP para cámaras). Incluye siempre la unidad en 'value'.\n"
    "6. Frecuencias: usa el valor máximo si la fuente dice 'hasta X GHz'; si menciona base y turbo, usa cada una.\n"
    "7. Booleanos: usa true/false sólo si el texto lo indica.\n"
    "8. VARIANTE DEL PRODUCTO: el producto que catalogamos es UNA variante concreta del modelo "
    "(p. ej. 'iPhone 15 128GB'). Si un dato existe en varias opciones de la familia "
    "(p. ej. almacenamiento 128/256/512 GB), devuelve SOLO el valor que corresponde a la variante "
    "indicada en 'Variante del producto'. Compara el número/valor del texto con el de la variante.\n"
    "9. Si pese a comparar no puedes determinar cuál corresponde a la variante, marca esa clave como "
    "AMBIGUA devolviendo value='' y evidence='' (no elijas un valor al azar ni inventes).\n"
    "10. No repitas una misma 'key' dos veces: cada key debe aparecer como máximo una vez en 'values'.\n"
    "11. Responde ÚNICAMENTE con un JSON válido con este esquema:\n"
    '   {"values":[{"key": string, "value": string, "evidence": string}]}\n'
    "   Sin texto adicional, sin comentarios, sin marcas de código."
)


@dataclass(frozen=True)
class ExtractedSpec:
    key: str
    value: str
    evidence: str


def _normalize_match(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.split())


def evidence_in_context(evidence: str, context: str) -> bool:
    needle = _normalize_match(evidence)
    haystack = _normalize_match(context)
    return bool(needle) and needle in haystack


def build_defs_block(defs: list[CategorySpecificationDefinition]) -> str:
    lines = []
    for definition in defs:
        unit = f" | unidad: {definition.unit}" if definition.unit else ""
        lines.append(f"- {definition.key} | {definition.label} | {definition.data_type}{unit}")
    return "\n".join(lines)


def build_prompt(context: str, entry: SpecSource, defs: list[CategorySpecificationDefinition], *, product_name: str | None = None) -> str:
    variant = f"Variante del producto: {product_name}\n" if product_name else ""
    return (
        "Extrae las especificaciones reales de este componente desde la página de referencia.\n"
        f"Modelo a investigar: {entry.target}\n"
        f"{variant}"
        f"Fuente: {entry.source_name}\n"
        f"URL: {entry.url}\n"
        f"Definiciones disponibles (key | label | tipo de dato | unit):\n{build_defs_block(defs)}\n"
        "Texto de la página de referencia (única información permitida):\n"
        "---\n"
        f"{context}\n"
        "---"
    )


def call_gemini(client: Any, model: str, timeout_seconds: float, prompt: str) -> str:
    from google.genai import types

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    systemInstruction=SYSTEM_INSTRUCTIONS,
                    temperature=0.2,
                    maxOutputTokens=2000,
                ),
            )
            return (getattr(response, "text", "") or "").strip()
        except Exception as error:  # provider flakiness is retried
            last_error = error
            print(f"  LLM error (intento {attempt + 1}): {type(error).__name__}")
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"LLM falló tras 3 intentos: {last_error!r}")


def _clean_text(value: str) -> str:
    value = value.strip().strip("`")
    if value.startswith("json"):
        value = value[4:].lstrip()
    return value.strip()


def _extract_json(text: str) -> dict:
    candidate = _clean_text(text)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        if start < 0:
            raise ValueError("respuesta sin objeto JSON")
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(candidate)):
            ch = candidate[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    data = json.loads(candidate[start : i + 1])
                    break
        else:
            raise ValueError("objeto JSON sin cerrar")
    if not isinstance(data, dict):
        raise ValueError("respuesta no es un objeto JSON")
    return data


def extract_specs(payload: Any, allowed_keys: set[str], context: str) -> list[ExtractedSpec]:
    """Validate the LLM output: every value must be grounded in the page context."""
    if not isinstance(payload, dict):
        raise ValueError("payload no es un dict")
    raw_values = payload.get("values")
    if not isinstance(raw_values, list):
        raise ValueError("sin lista 'values' en la extracción")
    found: list[ExtractedSpec] = []
    rejected: list[str] = []
    for raw in raw_values[:MAX_EXTRACTED_ITEMS]:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        value = str(raw.get("value") or "").strip()
        evidence = str(raw.get("evidence") or "").strip()
        if key not in allowed_keys:
            rejected.append(f"{key or '(sin key)'}: clave no permitida")
            continue
        if not value or len(value) > MAX_VALUE_CHARS:
            rejected.append(f"{key}: sin valor o muy largo")
            continue
        if not (evidence_in_context(evidence, context) or evidence_in_context(value, context)):
            rejected.append(f"{key}={value[:30]}: sin respaldo en el texto fuente")
            continue
        found.append(ExtractedSpec(key=key, value=value, evidence=evidence))
    if not found:
        raise ValueError("extracción sin valores válidos")
    return found


def extracted_input(product: Product, definition: CategorySpecificationDefinition, spec: ExtractedSpec, entry: SpecSource, *, force_source_update: bool = False) -> SpecValueInput:
    value = spec.value.strip()
    if definition.data_type in {"integer", "decimal"}:
        parsed = _parse_number_with_unit(value, definition.unit)
        if parsed:
            number, unit = parsed
            return SpecValueInput(
                product_id=product.id,
                definition_id=definition.id,
                value_kind=SpecValueKind.NUMBER.value,
                raw_value=value,
                value_number=number,
                unit=unit,
                source_type=entry.source_type,
                source_name=entry.source_name,
                source_url=entry.url,
                extraction_method=EXTRACTION_METHOD,
                confidence=DEFAULT_CONFIDENCE,
                verification_status=SpecVerificationStatus.REVIEW.value,
                note=f"Evidencia: {spec.evidence}",
                force_source_update=force_source_update,
            )
    if definition.data_type == "boolean":
        parsed_bool = _parse_boolean(value)
        if parsed_bool is not None:
            return SpecValueInput(
                product_id=product.id,
                definition_id=definition.id,
                value_kind=SpecValueKind.BOOLEAN.value,
                raw_value=value,
                value_boolean=parsed_bool,
                source_type=entry.source_type,
                source_name=entry.source_name,
                source_url=entry.url,
                extraction_method=EXTRACTION_METHOD,
                confidence=DEFAULT_CONFIDENCE,
                verification_status=SpecVerificationStatus.REVIEW.value,
                note=f"Evidencia: {spec.evidence}",
                force_source_update=force_source_update,
            )

    structured_text = value
    if definition.key in {"ram_type", "type", "memory_type"}:
        structured_text = _ram_type(value) or value
    elif definition.key in {"storage_type"}:
        structured_text = _storage_type(value) or value
    elif definition.key in {"screen_resolution", "resolution"}:
        structured_text = _resolution(value) or value
    return SpecValueInput(
        product_id=product.id,
        definition_id=definition.id,
        value_kind=SpecValueKind.TEXT.value,
        raw_value=value,
        value_text=structured_text,
        source_type=entry.source_type,
        source_name=entry.source_name,
        source_url=entry.url,
        extraction_method=EXTRACTION_METHOD,
        confidence=DEFAULT_CONFIDENCE,
        verification_status=SpecVerificationStatus.REVIEW.value,
        note=f"Evidencia: {spec.evidence}",
        force_source_update=force_source_update,
    )


def allowed_keys_for(defs: dict[str, CategorySpecificationDefinition], entry: SpecSource) -> set[str]:
    keys = set(defs)
    if entry.allow_keys:
        keys &= set(entry.allow_keys)
    return keys


def extracted_input_multi(product: Product, definition: CategorySpecificationDefinition, specs: list[ExtractedSpec], entry: SpecSource, *, force_source_update: bool = False) -> SpecValueInput:
    """Build a multivalue (``filter_type="multi"``) input keeping all options in ``value_json``."""
    values = [spec.value for spec in specs]
    evidence = " | ".join(spec.evidence for spec in specs if spec.evidence)
    return SpecValueInput(
        product_id=product.id,
        definition_id=definition.id,
        value_kind=SpecValueKind.JSON.value,
        raw_value="; ".join(values),
        value_json=values,
        source_type=entry.source_type,
        source_name=entry.source_name,
        source_url=entry.url,
        extraction_method=EXTRACTION_METHOD,
        confidence=DEFAULT_CONFIDENCE,
        verification_status=SpecVerificationStatus.REVIEW.value,
        note=f"Multivalor; evidencia: {evidence}".strip(),
        force_source_update=force_source_update,
    )


_VARIANT_UNIT_ALIASES = {
    "gb": "gb",
    "tb": "gb",
    "mb": "mb",
    "ghz": "ghz",
    "mhz": "mhz",
    "hz": "hz",
    "w": "w",
    "wh": "wh",
    "mah": "mah",
    "mp": "mp",
    "g": "g",
    '"': '"',
    "pulgadas": '"',
    "inch": '"',
}


def interpret_variant_hints(product_name: str | None) -> list[tuple[Decimal, str]]:
    """Extract ``(number, canonical_unit)`` pairs from a product name.

    Used to resolve which of several family options corresponds to the concrete
    SKU being catalogued (e.g. "iPhone 15 128GB" -> (128, "gb")).
    """
    if not product_name:
        return []
    normalized = product_name.casefold()
    hints: list[tuple[Decimal, str]] = []
    for match in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(gb|tb|mb|ghz|mhz|hz|w|wh|mah|mp|g|[\"”']|pulgadas|inch)", normalized):
        raw_number = Decimal(match.group(1).replace(",", "."))
        raw_unit = match.group(2)
        unit = _VARIANT_UNIT_ALIASES.get(raw_unit, raw_unit)
        if unit == "gb" and raw_unit == "tb":
            raw_number = raw_number * 1024
        hints.append((raw_number, unit))
    return hints


def _canonical_definition_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    return _VARIANT_UNIT_ALIASES.get(unit.casefold(), unit.casefold())


@dataclass(frozen=True)
class ResolvedValue:
    """A single value decided for persistence after variant disambiguation."""
    definition: CategorySpecificationDefinition
    spec: ExtractedSpec | None
    ambiguous: bool = False
    candidates: tuple[ExtractedSpec, ...] = ()


def _matching_hint_numbers(value: str, definition: CategorySpecificationDefinition, hints: list[tuple[Decimal, str]]) -> set[Decimal]:
    """Numbers among the parsed candidate that match a variant hint for the unit."""
    parsed = _parse_number_with_unit(value, definition.unit)
    if not parsed:
        return set()
    number, _unit = parsed
    canon_unit = _canonical_definition_unit(definition.unit)
    return {
        hint_number
        for hint_number, hint_unit in hints
        if hint_unit == canon_unit and hint_number == number
    }


def resolve_values(specs: list[ExtractedSpec], defs: dict[str, CategorySpecificationDefinition], product_name: str | None = None) -> list[ResolvedValue]:
    """Decide, per definition key, the single value to persist.

    - unique scalar -> resolved with that spec;
    - ``filter_type="multi"`` -> resolved with the first spec (the multivalue
      set is reconstructed by the caller from all grouped keys);
    - several scalar candidates -> kept only when exactly one matches a variant
      hint; otherwise marked ambiguous (no arbitrary pick).
    """
    hints = interpret_variant_hints(product_name)
    groups: dict[str, list[ExtractedSpec]] = {}
    for spec in specs:
        groups.setdefault(spec.key, []).append(spec)

    resolved: list[ResolvedValue] = []
    for key, group in groups.items():
        definition = defs.get(key)
        if definition is None:
            continue
        deduped: list[ExtractedSpec] = []
        seen: set[tuple[str, str]] = set()
        for spec in group:
            marker = (spec.key, spec.value)
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(spec)

        if len(deduped) == 1:
            resolved.append(ResolvedValue(definition=definition, spec=deduped[0]))
            continue

        if definition.filter_type == "multi":
            resolved.append(ResolvedValue(definition=definition, spec=deduped[0], candidates=tuple(deduped)))
            continue

        per_candidate_matches = [(_matching_hint_numbers(spec.value, definition, hints), spec) for spec in deduped]
        matched = [spec for matches, spec in per_candidate_matches if matches]
        if len(matched) == 1:
            resolved.append(ResolvedValue(definition=definition, spec=matched[0], candidates=tuple(deduped)))
            continue

        resolved.append(ResolvedValue(definition=definition, spec=None, ambiguous=True, candidates=tuple(deduped)))
    return resolved


@dataclass(frozen=True)
class ResearchOutcome:
    """Final persistence decision for one spec key after variant + cross-validation."""
    definition: CategorySpecificationDefinition
    spec: ExtractedSpec | None
    source: SpecSource | None
    source_count: int = 0
    conflict: bool = False
    ambiguous: bool = False
    note: str | None = None


def _spec_values_equivalent(a: ExtractedSpec, b: ExtractedSpec, definition: CategorySpecificationDefinition) -> bool:
    a_parsed = _parse_number_with_unit(a.value, definition.unit)
    b_parsed = _parse_number_with_unit(b.value, definition.unit)
    if a_parsed and b_parsed:
        return a_parsed[0] == b_parsed[0]
    if definition.data_type == "boolean":
        return _parse_boolean(a.value) == _parse_boolean(b.value)
    return _normalize_match(a.value) == _normalize_match(b.value)


def cross_validate_outcome(key_pairs: list[tuple[SpecSource, ExtractedSpec]], definition: CategorySpecificationDefinition, config: AIResearchConfig, *, product_name: str | None = None) -> ResearchOutcome:
    """Combine values for one key coming from several trusted sources.

    - variant resolution keeps only the concrete SKU value;
    - important keys that other sources disagree on are marked as a conflict
      (review) instead of picking a value arbitrarily;
    - otherwise the (primary, highest-priority) source value is returned.
    """
    if not key_pairs:
        return ResearchOutcome(definition=definition, spec=None, source=None)

    resolved = resolve_values([pair[1] for pair in key_pairs], {definition.key: definition}, product_name=product_name)
    resolved_value = resolved[0] if resolved else None

    distinct_sources = sorted({p[0] for p in key_pairs}, key=lambda s: s.priority)

    if resolved_value is None or resolved_value.spec is None:
        # Variant resolution could not pick a single value. If the differing
        # candidates come from two independent sources this is a cross-source
        # conflict worth flagging for review, otherwise it is plain ambiguity.
        if definition.key in config.cross_validation_keys and len(distinct_sources) >= 2:
            primary_source = distinct_sources[0]
            primary_spec = next(p[1] for p in key_pairs if p[0].url == primary_source.url)
            disagreements = [
                (p[0], p[1])
                for p in key_pairs
                if p[0].url != primary_source.url and not _spec_values_equivalent(p[1], primary_spec, definition)
            ]
            if disagreements:
                secondary = "; ".join(f"{src.source_name}: {spec.value}" for src, spec in disagreements)
                return ResearchOutcome(
                    definition=definition,
                    spec=primary_spec,
                    source=primary_source,
                    source_count=len(distinct_sources),
                    conflict=True,
                    note=f"Conflicto entre fuentes (revisar): {primary_source.source_name}: {primary_spec.value} vs {secondary}",
                )
        return ResearchOutcome(
            definition=definition,
            spec=None,
            source=None,
            source_count=len(distinct_sources),
            ambiguous=True,
        )

    primary_spec = resolved_value.spec
    primary_source = next((p[0] for p in key_pairs if p[1].value == primary_spec.value and p[1].evidence == primary_spec.evidence), key_pairs[0][0])

    if definition.key in config.cross_validation_keys and len(distinct_sources) >= 2:
        disagreements = [
            (p[0], p[1])
            for p in key_pairs
            if p[0].url != primary_source.url and not _spec_values_equivalent(p[1], primary_spec, definition)
        ]
        if disagreements:
            secondary = "; ".join(f"{src.source_name}: {spec.value}" for src, spec in disagreements)
            return ResearchOutcome(
                definition=definition,
                spec=primary_spec,
                source=primary_source,
                source_count=len(distinct_sources),
                conflict=True,
                note=f"Conflicto entre fuentes (revisar): {primary_source.source_name}: {primary_spec.value} vs {secondary}",
            )
        return ResearchOutcome(
            definition=definition,
            spec=primary_spec,
            source=primary_source,
            source_count=len(distinct_sources),
            conflict=False,
            note=f"Confirmado por {len(distinct_sources)} fuentes ({', '.join(s.source_name for s in distinct_sources)}).",
        )

    return ResearchOutcome(
        definition=definition,
        spec=primary_spec,
        source=primary_source,
        source_count=len(distinct_sources),
    )


def research_input(product: Product, outcome: ResearchOutcome, entry: SpecSource, *, force_source_update: bool = False, confidence: Decimal | None = None, verification_status: str | None = None, note_extra: str | None = None) -> SpecValueInput:
    """Build the persistence input for a researched value, tagging it as ai_research."""
    if outcome.spec is None:
        raise ValueError("outcome sin spec para persistir")
    incoming = extracted_input(product, outcome.definition, outcome.spec, entry, force_source_update=force_source_update)
    incoming = SpecValueInput(
        product_id=incoming.product_id,
        definition_id=incoming.definition_id,
        value_kind=incoming.value_kind,
        raw_value=incoming.raw_value,
        value_text=incoming.value_text,
        value_number=incoming.value_number,
        value_boolean=incoming.value_boolean,
        value_json=incoming.value_json,
        unit=incoming.unit,
        source_type=SpecValueSourceType.AI_RESEARCH.value,
        source_name=entry.source_name,
        source_url=entry.url,
        extraction_method=EXTRACTION_METHOD,
        confidence=confidence if confidence is not None else incoming.confidence,
        verification_status=verification_status if verification_status is not None else incoming.verification_status,
        note=" / ".join(filter(None, [incoming.note, note_extra])),
        force_source_update=force_source_update,
    )
    return incoming