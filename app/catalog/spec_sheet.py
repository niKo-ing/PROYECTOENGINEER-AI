from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models.catalog import Product, ProductSpecValue


def _display_number(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(int(value)) if value == value.to_integral_value() else f"{value.normalize():f}"
    return str(value)


def format_spec_value(value: ProductSpecValue) -> str:
    if value.value_boolean is not None:
        return "Sí" if value.value_boolean else "No"
    if value.value_number is not None:
        number = _display_number(value.value_number)
        if value.unit == '"':
            return f'{number}"'
        return f"{number} {value.unit}" if value.unit else number
    if value.value_text:
        return value.value_text
    if value.value_json is not None:
        return format_json_value(value.value_json)
    return value.raw_value or ""


def format_json_value(value: dict | list) -> str:
    """Render structured JSON items into a readable, single-line string."""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return ""
        if all(isinstance(item, str) for item in value):
            return ", ".join(value)
        if all(isinstance(item, dict) for item in value):
            rows: list[str] = []
            for item in value:
                version = item.get("version") or item.get("generation")
                label = _json_item_label(item)
                descriptor = f"{version} " if version and version != label else ""
                counts = "; ".join(_json_count_parts(item))
                if span := _json_dimension_str(item):
                    rows.append(f"{label} {span}".strip())
                    continue
                rows.append(f"{label} {descriptor}({counts})".strip())
            return ", ".join(rows)
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        if "form_factor" in value:
            return _json_dimension_str(value) or (", ".join(f"{k}: {v}" for k, v in value.items()))
        return ", ".join(f"{k}: {v}" for k, v in value.items())
    return str(value)


def _json_item_label(item: dict) -> str:
    for field in ("type", "kind", "interface", "name", "feat", "value", "slot"):
        label = item.get(field)
        if label:
            return str(label)
    return ""


def _json_count_parts(item: dict) -> list[str]:
    parts: list[str] = []
    for field in ("count", "pins", "lanes", "form_factors", "heads", "type?"):
        if field.endswith("?"):
            continue
        if item.get(field) not in (None, "", []):
            parts.append(f"{field}={item[field]}")
    return parts


_DIM_FIELDS = {
    "width_mm": "ancho",
    "depth_mm": "profundidad",
    "width": "ancho",
    "depth": "profundidad",
    "length": "largo",
    "height": "alto",
    "thickness": "grosor",
    "form_factor": "formato",
}


def _json_dimension_str(item: dict) -> str:
    """Render a dict with form_factor / width / depth / length as a human string."""
    unit = item.get("unit")
    parts: list[str] = []
    for key, label in _DIM_FIELDS.items():
        value = item.get(key)
        if value in (None, ""):
            continue
        suffix = ""
        if key != "form_factor":
            suffix = " mm" if key.endswith("_mm") else (f" {unit}" if unit else "")
        parts.append(f"{label}: {value}{suffix}")
    return ", ".join(parts)


def build_canonical_spec_sheet(product: Product) -> dict | None:
    sections: list[dict] = []
    general_items = []
    if product.brand:
        general_items.append({"key": "brand", "label": "Marca", "value": product.brand})
    if product.model:
        general_items.append({"key": "model", "label": "Modelo", "value": product.model})
    if product.category_entity:
        general_items.append({"key": "category", "label": "Categoría", "value": product.category_entity.name})
    if general_items:
        sections.append({"title": "Información general", "items": general_items})

    values = sorted(
        product.spec_values or [],
        key=lambda item: (item.definition.group if item.definition else "General", item.definition.sort_order if item.definition else 0, item.definition.label if item.definition else ""),
    )
    grouped: dict[str, list[dict]] = {}
    for spec_value in values:
        if not spec_value.definition:
            continue
        display_value = format_spec_value(spec_value)
        if not display_value:
            continue
        grouped.setdefault(spec_value.definition.group, []).append(
            {
                "key": spec_value.definition.key,
                "label": spec_value.definition.label,
                "value": display_value,
                "raw_value": spec_value.raw_value,
                "unit": spec_value.unit,
                "value_kind": spec_value.value_kind,
                "value_json": spec_value.value_json,
                "item_schema": spec_value.definition.item_schema,
                "source_type": spec_value.source_type,
                "source_name": spec_value.source_name,
                "source_url": spec_value.source_url,
                "verification_status": spec_value.verification_status,
                "conflict_status": spec_value.conflict_status,
            }
        )

    sections.extend({"title": title, "items": items} for title, items in grouped.items() if items)
    if not sections:
        return None
    return {"sections": sections}
