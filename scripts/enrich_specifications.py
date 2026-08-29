"""Enrich Product.specs with known component facts.

This is deterministic enrichment, not free-form generation: it only adds facts
from local reference tables when an exact CPU/GPU model alias appears in the
product name or current structured specs. It never guesses RAM type, screen
panel, battery, ports or SKU-specific values not present in the source.

Usage:
    python -m scripts.enrich_specifications [--product-id 55] [--dry-run]
"""

from __future__ import annotations

import argparse
import copy
import sys
import unicodedata

from app.catalog.component_specs import ComponentSpec, known_components
from app.db import SessionLocal
from app.models.catalog import Product


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def _spec_text(product: Product, specs: dict) -> str:
    parts = [product.name or "", product.brand or "", product.model or "", product.mpn or ""]
    for highlight in specs.get("highlights") or []:
        parts.append(str(highlight))
    for section in specs.get("sections") or []:
        parts.append(str(section.get("title", "")))
        for item in section.get("items") or []:
            parts.append(str(item.get("label", "")))
            parts.append(str(item.get("value", "")))
    return _normalize("\n".join(parts))


def _find_section(specs: dict, title: str) -> dict:
    sections = specs.setdefault("sections", [])
    for section in sections:
        if _normalize(str(section.get("title", ""))) == _normalize(title):
            section.setdefault("items", [])
            return section
    section = {"title": title, "items": []}
    sections.append(section)
    return section


def _has_label(section: dict, label: str) -> bool:
    wanted = _normalize(label)
    equivalents = {
        "nucleos": ("nucleo",),
        "hilos": ("hilo", "subproceso"),
        "frecuencia turbo": ("turbo", "boost", "maxima", "máxima"),
        "frecuencia base": ("base",),
        "cache": ("cache", "caché"),
        "tdp": ("tdp", "consumo"),
        "graficos integrados": ("grafico integrado", "gráficos integrados", "graficas integradas", "gráficas integradas"),
        "vram": ("vram", "memoria de video"),
    }
    needles = equivalents.get(wanted, (wanted,))
    for item in section.get("items") or []:
        current = _normalize(str(item.get("label", "")))
        if any(needle in current for needle in needles):
            return True
    return False


def _has_highlight(specs: dict, highlight: str) -> bool:
    wanted = _normalize(highlight)
    return any(_normalize(str(current)) == wanted for current in specs.get("highlights") or [])


def _component_matches(component: ComponentSpec, source: str) -> bool:
    return any(_normalize(alias) in source for alias in component.aliases)


def enrich_specs(product: Product) -> tuple[dict, list[str]]:
    specs = copy.deepcopy(product.specs or {"highlights": [], "sections": []})
    specs.setdefault("highlights", [])
    specs.setdefault("sections", [])
    source = _spec_text(product, specs)
    changes: list[str] = []

    for component in known_components():
        if not _component_matches(component, source):
            continue
        section = _find_section(specs, component.section)
        for label, value in component.items:
            if _has_label(section, label):
                continue
            section["items"].append({"label": label, "value": value})
            changes.append(f"{component.section}.{label}")
        for highlight in component.highlights:
            if len(specs["highlights"]) >= 9 or _has_highlight(specs, highlight):
                continue
            specs["highlights"].append(highlight)
            changes.append(f"highlight:{highlight}")

    return specs, changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-id", type=int, help="Enriquecer solo este producto")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar cambios sin persistir")
    args = parser.parse_args()

    db = SessionLocal()
    updated = 0
    try:
        query = db.query(Product).order_by(Product.id)
        if args.product_id:
            query = query.filter(Product.id == args.product_id)
        for product in query.all():
            specs, changes = enrich_specs(product)
            if not changes:
                continue
            updated += 1
            print(f"#{product.id} {product.name[:54]} -> {len(changes)} cambios: {', '.join(changes[:8])}")
            if not args.dry_run:
                product.specs = specs
                db.commit()
        print(f"Productos enriquecidos: {updated}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
