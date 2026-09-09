"""Deterministic intent detection for the conversational AI.

Intents are classified by rule-based Spanish pattern matching so the behaviour
is testable without a provider and does not rely on LLM-only business logic.
The LLM is free to add nuance later, but the structured plan (intent +
entities + constraints) is produced here and handed to the planner.
"""

from __future__ import annotations

import re
from typing import Any

from app.ai.conversation_state import ConversationState, _looks_like_follow_up, reference_indices
from app.ai.schemas.intent import AIEntity, AIEntityType, AIIntent, AIIntentType
from app.catalog.synonyms import normalize_spanish

# Known brands (case-insensitive, accent-normalized) used to tag entities.
_KNOWN_BRANDS: tuple[str, ...] = (
    "apple",
    "samsung",
    "xiaomi",
    "poco",
    "honor",
    "realme",
    "motorola",
    "nokia",
    "huawei",
    "lg",
    "sony",
    "google",
    "asus",
    "gigabyte",
    "msi",
    "amd",
    "intel",
    "nvidia",
    "ryzen",
    "core",
    "acer",
    "lenovo",
    "hp",
    "dell",
    "asus",
    "tplink",
    "jbl",
    "logitech",
)

_USE_CASE_TERMS: dict[str, tuple[tuple[str, str], ...]] = {
    "gaming": (("jug", "high"), ("gaming", "high"), ("videojuego", "high"), ("fps", "medium")),
    "camera": (("foto", "high"), ("camara", "high"), ("fotograf", "high"), ("video", "medium")),
    "battery": (("bateria", "high"), ("duracion", "high"), ("dura mucho", "high")),
    "productivity": (("trabajo", "high"), ("productividad", "high"), ("oficina", "medium"), ("estudio", "medium"), ("estudiar", "medium")),
    "price_value": (("buen precio", "high"), ("precio/calidad", "high"), ("vale la pena", "medium"), ("barat", "medium"), ("econom", "medium")),
    "longevity": (("durable", "high"), ("actualizacion", "medium"), ("soporte", "medium")),
}

# Intents hit in order; first match wins for the primary intent.
_SEARCH_VERBS = ("busca", "busco", "buscar", "busqu", "encuentr", "muestrame", "hay", "que tienen", "catalogo de", "productos de", "productos para")
_SPEC_TERMS = ("spec", "especificacion", "caracteristica", "especificaciones", "que tiene", "que trae", "cuanto ram tiene", "cuantos nucleos", "con que")
_COMPARE_TERMS = ("compar", "cual es mejor", "mejor opcion", "mejor entre", "contra", " vs ", "o el", "o la", "diferencia entre", "mejor compra", "cual conviene", "que conviene")
_RECOMMEND_TERMS = ("me conviene", "recomienda", "recomendame", "cual elegiria", "cual elegir", "mejor para mi", "cual me recomiendas", "recomendacion", "vale la pena")
_PRICE_CHECK_TERMS = ("cuanto cuesta", "cuanto val", "precio", "cual es el precio", "barat", "econom", "$$$", "$", "lucas", " mil ", " pesos", "clp")
_COMPATIBILITY_TERMS = ("compatible", "sirve pa", "funciona con", "sirve para mi", "se puede usar con", "compatibilidad", "sirve para el", "sirve con")


def detect_intent(message: str, state: ConversationState | None = None) -> AIIntent:
    """Classify the user message into a structured intent."""
    text = (message or "").strip()
    norm = normalize_spanish(text)
    entities: list[AIEntity] = []
    constraints: dict[str, Any] = {}
    requires_clarification = False

    price = parse_price_clp(text)
    if price is not None:
        constraints["max_price"] = price
        entities.append(AIEntity(type=AIEntityType.PRICE, value=str(price), price_clp=price))

    use_cases = extract_use_cases(text)
    if use_cases:
        constraints["use_case"] = use_cases

    brands, model_tokens = _brand_model_terms(text)
    for brand in brands:
        entities.append(AIEntity(type=AIEntityType.BRAND, value=brand, brand=brand))

    _extract_category_entities(text, entities)
    _extract_spec_entities(text, entities)
    _extract_product_term(text, brands, model_tokens, entities)

    has_active = bool(state and state.has_active_products())
    ref_indices = reference_indices(text, len(state.active_products)) if state else []

    # Follow-ups that reference previous context take priority.
    if has_active and _is_follow_up(text, norm, ref_indices):
        if _wants_recommend(norm) or "cual es mejor" in norm or "mejor opcion" in norm or "cual me conviene" in norm:
            return _intent(AIIntentType.RECOMMEND, entities, constraints, state, ref_indices)
        if _wants_compare(norm):
            return _intent(AIIntentType.COMPARE, entities, constraints, state, ref_indices)
        if "por que" in norm or "porque" in norm or "explica" in norm:
            return _intent(AIIntentType.FOLLOW_UP, entities, constraints, state, ref_indices)
        if _wants_spec(norm):
            return _intent(AIIntentType.SPECIFICATION, entities, constraints, state, ref_indices)
        if _wants_price(norm):
            return _intent(AIIntentType.PRICE_CHECK, entities, constraints, state, ref_indices)
        _attach_active_products(ref_indices, entities, state)
        return _intent(AIIntentType.FOLLOW_UP, entities, constraints, state, ref_indices)

    # Compatibility / spec / price / compare / recommend / search checks.
    if "compatible" in norm or "compatibilidad" in norm or _has_any(norm, _COMPATIBILITY_TERMS):
        return _intent(AIIntentType.COMPATIBILITY, entities, constraints, state)
    if _wants_spec(norm) or any(token in norm for token in _SPEC_TERMS):
        return _intent(AIIntentType.SPECIFICATION, entities, constraints, state)
    if "cual tiene mejor" in norm or "que tiene mejor" in norm:
        return _intent(AIIntentType.SPECIFICATION, entities, constraints, state)
    if "me conviene" in norm or "recomienda" in norm or "recomendame" in norm or "cual elegir" in norm or "mejor para mi" in norm:
        return _intent(AIIntentType.RECOMMEND, entities, constraints, state)
    if _wants_compare(norm):
        return _intent(AIIntentType.COMPARE, entities, constraints, state)
    if _wants_price(norm) or "precio" in norm or "lucas" in norm or " mil" in norm or "$" in text:
        return _intent(AIIntentType.PRICE_CHECK, entities, constraints, state)
    if _wants_search(norm, text) or price is not None or _names_catalog_entity(entities):
        return _intent(AIIntentType.SEARCH, entities, constraints, state)

    if not text:
        requires_clarification = True
        return _intent(AIIntentType.GENERAL_QUESTION, entities, constraints, state, requires_clarification=True)

    greeting = ("hola", "buenas", "hey", "buenos dias", "buenas tardes", "que tal", "hello", "hi")
    if normalize_spanish(text) in greeting or text.casefold().strip() in greeting:
        return AIIntent(intent=AIIntentType.GENERAL_QUESTION, confidence=0.98, entities=[], constraints={})

    return _intent(AIIntentType.GENERAL_QUESTION, entities, constraints, state)


def _intent(
    intent_type: AIIntentType,
    entities: list[AIEntity],
    constraints: dict[str, Any],
    state: ConversationState | None,
    ref_indices: list[int] | None = None,
    requires_clarification: bool = False,
) -> AIIntent:
    if state and ref_indices:
        _attach_active_products(ref_indices, entities, state)
    if intent_type in (AIIntentType.SEARCH, AIIntentType.PRODUCT_DETAIL, AIIntentType.GENERAL_QUESTION) and not entities and state and not state.active_products:
        pass
    return AIIntent(
        intent=intent_type,
        confidence=1.0,
        entities=entities,
        constraints=constraints,
        requires_clarification=requires_clarification,
    )


def _attach_active_products(indices: list[int], entities: list[AIEntity], state: ConversationState) -> None:
    if not indices:
        return
    ids = state.active_product_ids()
    resolved = [ids[i] for i in indices if i < len(ids)]
    if resolved:
        entities.append(AIEntity(type=AIEntityType.PRODUCT, value=", ".join(str(i) for i in resolved), resolved_product_ids=resolved))


def _is_follow_up(text: str, norm: str, ref_indices: list[int]) -> bool:
    return bool(ref_indices) or _looks_like_follow_up(text)


def _wants_compare(norm: str) -> bool:
    if "compar" in norm or "cual es mejor" in norm or "mejor opcion" in norm or "best" in norm:
        return True
    if _has_any(norm, ("contra", " vs ", "entre los", "entre estas", "entre estos", "cual conviene", "que conviene")):
        return True
    if "es mejor" in norm and _has_any(norm, (" o ", "entre ", "contra ", " vs ")):
        return True
    return False


def _wants_recommend(norm: str) -> bool:
    return any(token in norm for token in ("me conviene", "recomienda", "recomiendame", "cual elegir", "mejor para mi", "vale la pena"))


def _wants_price(norm: str) -> bool:
    return any(token in norm for token in ("cuanto cuesta", "cuanto vale", "cuanto val", "precio", "barat", "econom", "lucas"))


def _wants_spec(norm: str) -> bool:
    return any(token in norm for token in _SPEC_TERMS) or "cual tiene mejor" in norm


def _wants_search(norm: str, raw: str) -> bool:
    if any(token in norm for token in _SEARCH_VERBS):
        return True
    if any(token in raw.casefold().split() for token in ("un", "una", "algún", "alguno", "alguna", "los", "soy", "necesito")):
        return True
    return False


def _has_any(norm: str, terms: tuple[str, ...]) -> bool:
    return any(term in norm for term in terms)


def _names_catalog_entity(entities: list[AIEntity]) -> bool:
    return any(
        entity.type in (AIEntityType.PRODUCT, AIEntityType.PRODUCT_FAMILY, AIEntityType.BRAND, AIEntityType.CATEGORY)
        for entity in entities
    )


def parse_price_clp(text: str) -> int | None:
    """Interpret a CLP price constraint from free text.

    Supports ``500 lucas`` (lucas = thousands), ``500 mil``, ``500.000``,
    ``$500.000`` and plain ``500000``. Returns the integer value or None.
    """
    norm = text.casefold().strip()

    def _to_int(segment: str) -> int:
        cleaned = segment.replace(".", "").replace(" ", "").replace(",", "")
        return int(cleaned)

    unit_match = re.search(r"(?P<num>\d[\d.,\s]{0,15})\s*(?P<unit>lucas|mil|pesos|clp)\b", norm)
    if unit_match:
        number = _to_int(unit_match.group("num"))
        unit = unit_match.group("unit")
        if unit in ("lucas", "mil"):
            return number * 1000
        return number

    plain = re.search(r"\d[\d.,]{1,15}", norm)
    if plain:
        number = _to_int(plain.group(0))
        if number >= 1000:
            return number
    return None


def extract_use_cases(text: str) -> dict[str, str]:
    norm = normalize_spanish(text)
    found: dict[str, str] = {}
    for use_case, terms in _USE_CASE_TERMS.items():
        for trigger, level in terms:
            if trigger in norm:
                found[use_case] = level
                break
    return found


def _brand_model_terms(text: str) -> tuple[list[str], list[str]]:
    norm = normalize_spanish(text)
    tokens = norm.split()
    brands: list[str] = []
    model_tokens: list[str] = []
    for i, token in enumerate(tokens):
        if token in _KNOWN_BRANDS:
            if token not in brands:
                brands.append(token)
            # A following numeric/model token is the model/family.
            if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                model_tokens.append(f"{token} {tokens[i + 1]}")
    # family markers like "poco", "iphone"
    for family in ("iphone", "poco", "galaxy", "ryzen", "core"):
        if family in norm and family not in brands:
            # "iphone 15" → precise product token "iphone 15"
            offset = tokens.index(family)
            if offset + 1 < len(tokens) and tokens[offset + 1].isdigit():
                model_tokens.append(f"{family} {tokens[offset + 1]}")
            else:
                model_tokens.append(family)
    return brands, model_tokens


def _extract_category_entities(text: str, entities: list[AIEntity]) -> None:
    norm = normalize_spanish(text)
    categories = {
        "gpu": ("grafica", "tarjeta grafica", "graphics card", "gpu"),
        "ram": ("memoria ram", "ram", "rams"),
        "ssd": ("ssd", "disco solido", "solido"),
        "notebook": ("notebook", "laptop", "portatil", "computador"),
        "monitor": ("monitor", "pantalla"),
        "smartphone": ("celular", "smartphone", "telefono", "celu"),
        "cpu": ("procesador", "cpu"),
    }
    for category, triggers in categories.items():
        if any(trigger in norm for trigger in triggers):
            entities.append(AIEntity(type=AIEntityType.CATEGORY, value=category, category=category))


def _extract_spec_entities(text: str, entities: list[AIEntity]) -> None:
    specs = {
        "camera": ("camara", "foto", "fotograf", "lente"),
        "battery": ("bateria", "duracion"),
        "performance": ("rendimiento", "rpm", "ghz", "mhz", "procesador", "cpu"),
        "screen": ("pantalla", "display", "resolucion"),
        "storage": ("almacenamiento", "gb de", "memoria interna"),
        "connectivity": ("wifi", "bluetooth", "5g", "usb"),
    }
    for spec, triggers in specs.items():
        if any(trigger in normalize_spanish(text) for trigger in triggers):
            entities.append(AIEntity(type=AIEntityType.SPECIFICATION, value=spec, specification=spec))


def _extract_product_term(text: str, brands: list[str], model_tokens: list[str], entities: list[AIEntity]) -> None:
    norm = normalize_spanish(text)
    for model in model_tokens:
        brand = _matching_brand(norm, model)
        if "_" not in model and " " not in model:
            entities.append(AIEntity(type=AIEntityType.PRODUCT_FAMILY, value=model, brand=brand, family=model))
        else:
            entities.append(AIEntity(type=AIEntityType.PRODUCT, value=model, brand=brand, model=model))


def _matching_brand(norm: str, model: str) -> str | None:
    for brand in _KNOWN_BRANDS:
        if brand in norm and brand in model:
            return brand
    return None