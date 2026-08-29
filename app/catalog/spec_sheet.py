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
        if isinstance(value.value_json, list):
            return ", ".join(str(item) for item in value.value_json)
        return str(value.value_json)
    return value.raw_value or ""


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
                "source_type": spec_value.source_type,
                "source_name": spec_value.source_name,
                "verification_status": spec_value.verification_status,
                "conflict_status": spec_value.conflict_status,
            }
        )

    sections.extend({"title": title, "items": items} for title, items in grouped.items() if items)
    if not sections:
        return None
    return {"sections": sections}
