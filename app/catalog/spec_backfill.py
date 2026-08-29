from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from app.models.catalog import CategorySpecificationDefinition, Product, SpecValueKind, SpecValueSourceType, SpecVerificationStatus
from app.services.product_spec_value_service import ProductSpecValueService, SpecValueInput


@dataclass(frozen=True)
class BackfillResult:
    created_or_updated: int
    skipped: int


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _parse_number_with_unit(value: str, expected_unit: str | None) -> tuple[Decimal, str | None] | None:
    if not expected_unit:
        match = re.search(r"(?<!\d)(\d+(?:[\.,]\d+)?)", value)
        if not match:
            return None
        return Decimal(match.group(1).replace(",", ".")), None
    unit_pattern = re.escape(expected_unit).replace('\\"', '["”\'\']')
    suffix = "" if expected_unit == '"' else r"\b"
    match = re.search(rf"(?<!\d)(\d+(?:[\.,]\d+)?)\s*{unit_pattern}{suffix}", value, re.IGNORECASE)
    if not match:
        if expected_unit == "GB":
            match = re.search(r"(?<!\d)(\d+(?:[\.,]\d+)?)\s*(gb|gbyte|gigabyte|gigabytes)\b", value, re.IGNORECASE)
        elif expected_unit == "MHz":
            match = re.search(r"(?<!\d)(\d+(?:[\.,]\d+)?)\s*(mhz|mt/s)\b", value, re.IGNORECASE)
        elif expected_unit == "Hz":
            match = re.search(r"(?<!\d)(\d+(?:[\.,]\d+)?)\s*hz\b", value, re.IGNORECASE)
        elif expected_unit == "W":
            match = re.search(r"(?<!\d)(\d+(?:[\.,]\d+)?)\s*w\b", value, re.IGNORECASE)
        elif expected_unit == "Wh":
            match = re.search(r"(?<!\d)(\d+(?:[\.,]\d+)?)\s*wh\b", value, re.IGNORECASE)
    if not match:
        return None
    return Decimal(match.group(1).replace(",", ".")), expected_unit


def _parse_boolean(value: str) -> bool | None:
    normalized = _normalize(value)
    if normalized in {"si", "yes", "true", "incluye", "con"}:
        return True
    if normalized in {"no", "false", "sin", "no incluye"}:
        return False
    return None


def _storage_type(value: str) -> str | None:
    normalized = _normalize(value)
    if "ssd" in normalized or "estado solido" in normalized:
        return "SSD"
    if "hdd" in normalized or "disco duro" in normalized:
        return "HDD"
    if "emmc" in normalized:
        return "eMMC"
    return None


def _ram_type(value: str) -> str | None:
    normalized = _normalize(value).replace(" ", "")
    for ram_type in ("LPDDR5X", "LPDDR5", "DDR5", "LPDDR4X", "LPDDR4", "DDR4", "DDR3"):
        if ram_type.casefold() in normalized:
            return ram_type
    return None


def _resolution(value: str) -> str | None:
    match = re.search(r"(\d{3,4})\s*[x×]\s*(\d{3,4})", value, re.IGNORECASE)
    if match:
        return f"{match.group(1)} × {match.group(2)}"
    normalized = _normalize(value)
    aliases = {"fhd": "1920 × 1080", "full hd": "1920 × 1080", "hd": "1366 × 768", "wuxga": "1920 × 1200"}
    for alias, canonical in aliases.items():
        if alias in normalized:
            return canonical
    return None


SECTION_LABEL_KEY_MAP = {
    ("procesador", "procesador"): "processor",
    ("procesador", "nucleos"): "processor_cores",
    ("procesador", "subprocesos"): "processor_threads",
    ("procesador", "hilos"): "processor_threads",
    ("ram", "capacidad"): "ram_capacity",
    ("ram", "tipo"): "ram_type",
    ("ram", "velocidad"): "ram_speed",
    ("memoria", "capacidad"): "capacity",
    ("memoria", "tipo"): "type",
    ("memoria", "velocidad"): "speed",
    ("almacenamiento", "capacidad"): "storage_capacity",
    ("almacenamiento", "tipo"): "storage_type",
    ("almacenamiento", "interfaz"): "interface",
    ("pantalla", "tamano"): "screen_size",
    ("pantalla", "tamano y tipo"): "screen",
    ("pantalla", "resolucion"): "screen_resolution",
    ("pantalla", "frecuencia"): "screen_refresh_rate",
    ("pantalla", "tipo"): "panel_type",
    ("pantalla", "brillo"): "brightness",
    ("tarjeta de video", "modelo"): "gpu",
    ("tarjeta de video", "graficas"): "gpu",
    ("tarjeta de video", "vram"): "gpu_vram",
    ("puertos", "usb tipo c"): "ports",
    ("puertos", "usb tipo a"): "ports",
    ("puertos", "hdmi"): "ports",
    ("conectividad", "wi fi"): "wireless",
    ("conectividad", "bluetooth"): "wireless",
    ("conectividad", "red"): "connectivity",
    ("bateria", "duracion"): "battery",
    ("bateria", "capacidad"): "battery_capacity",
}


def _definition_for_item(definitions: dict[str, CategorySpecificationDefinition], section: str, label: str) -> CategorySpecificationDefinition | None:
    section_key = _normalize(section)
    label_key = _normalize(label)
    mapped = SECTION_LABEL_KEY_MAP.get((section_key, label_key))
    if mapped and mapped in definitions:
        return definitions[mapped]
    for definition in definitions.values():
        if _normalize(definition.label) == label_key:
            return definition
    return None


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _normalize(value))


def _raw_value_has_store_evidence(product: Product, raw_value: str) -> bool:
    raw = _compact(raw_value)
    if not raw:
        return False
    sources = [product.name or "", product.description or ""]
    return any(raw in _compact(source) for source in sources if source)


def _source_for_value(product: Product, raw_value: str) -> tuple[str, str | None, str]:
    if _raw_value_has_store_evidence(product, raw_value):
        stores = sorted({offer.store.name for offer in product.offers if offer.store})
        return SpecValueSourceType.STORE.value, ", ".join(stores) or "Tienda", "product_specs_json:store_evidence"
    return SpecValueSourceType.UNKNOWN.value, "Product.specs JSON", "product_specs_json:unverified_origin"


def _input_for_definition(product: Product, definition: CategorySpecificationDefinition, raw_value: str, *, source_name: str | None = None, source_type: str | None = None, extraction_method: str | None = None, force_source_update: bool = False) -> SpecValueInput:
    value = raw_value.strip()
    inferred_source_type, inferred_source_name, inferred_method = _source_for_value(product, value)
    resolved_source_type = source_type or inferred_source_type
    resolved_source_name = source_name if source_name is not None else inferred_source_name
    resolved_extraction_method = extraction_method or inferred_method
    if definition.data_type in {"integer", "decimal"}:
        parsed = _parse_number_with_unit(value, definition.unit)
        if parsed:
            number, unit = parsed
            return SpecValueInput(product_id=product.id, definition_id=definition.id, value_kind=SpecValueKind.NUMBER.value, raw_value=value, value_number=number, unit=unit, source_type=resolved_source_type, source_name=resolved_source_name, extraction_method=resolved_extraction_method, verification_status=SpecVerificationStatus.REVIEW.value, force_source_update=force_source_update)
    if definition.data_type == "boolean":
        parsed_bool = _parse_boolean(value)
        if parsed_bool is not None:
            return SpecValueInput(product_id=product.id, definition_id=definition.id, value_kind=SpecValueKind.BOOLEAN.value, raw_value=value, value_boolean=parsed_bool, source_type=resolved_source_type, source_name=resolved_source_name, extraction_method=resolved_extraction_method, verification_status=SpecVerificationStatus.REVIEW.value, force_source_update=force_source_update)

    structured_text = value
    if definition.key in {"ram_type", "type", "memory_type"}:
        structured_text = _ram_type(value) or value
    elif definition.key in {"storage_type"}:
        structured_text = _storage_type(value) or value
    elif definition.key in {"screen_resolution", "resolution"}:
        structured_text = _resolution(value) or value
    return SpecValueInput(product_id=product.id, definition_id=definition.id, value_kind=SpecValueKind.TEXT.value, raw_value=value, value_text=structured_text, source_type=resolved_source_type, source_name=resolved_source_name, extraction_method=resolved_extraction_method, verification_status=SpecVerificationStatus.REVIEW.value, force_source_update=force_source_update)


def backfill_product_specs(product: Product, service: ProductSpecValueService, *, source_name: str | None = None, source_type: str | None = None, extraction_method: str | None = None, force_source_update: bool = False) -> BackfillResult:
    if not product.specs or not product.category_entity:
        return BackfillResult(created_or_updated=0, skipped=0)
    definitions = {definition.key: definition for definition in product.category_entity.spec_definitions}
    if not definitions:
        return BackfillResult(created_or_updated=0, skipped=0)

    collected: dict[int, tuple[CategorySpecificationDefinition, list[tuple[str, str]]]] = {}
    skipped = 0
    for section in product.specs.get("sections") or []:
        section_title = str(section.get("title") or "")
        for item in section.get("items") or []:
            label = str(item.get("label") or "")
            raw_value = str(item.get("value") or "").strip()
            if not label or not raw_value:
                skipped += 1
                continue
            definition = _definition_for_item(definitions, section_title, label)
            if not definition:
                skipped += 1
                continue
            collected.setdefault(definition.id, (definition, []) )[1].append((label, raw_value))

    written = 0
    for definition, items in collected.values():
        if len(items) == 1:
            raw_value = items[0][1]
        else:
            raw_value = "; ".join(f"{label}: {value}" for label, value in items)
        service.upsert(_input_for_definition(product, definition, raw_value, source_name=source_name, source_type=source_type, extraction_method=extraction_method, force_source_update=force_source_update))
        written += 1
    return BackfillResult(created_or_updated=written, skipped=skipped)
