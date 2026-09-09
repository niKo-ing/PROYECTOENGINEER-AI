"""Backfill obvious canonical specs from product titles and known source pages.

This is deterministic and conservative: it only writes values that appear in
the catalog title or in a registered source URL for the matched component.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import selectinload

from app.catalog.spec_fetch import fetch_page, normalize_context
from app.catalog.spec_sources import sources_for_product
from app.db import SessionLocal
from app.models.catalog import Category, Product, SpecValueKind, SpecValueSourceType, SpecVerificationStatus
from app.services.product_spec_value_service import ProductSpecValueService, SpecValueInput


@dataclass(frozen=True)
class ParsedSpec:
    key: str
    raw_value: str
    value_kind: str
    value_text: str | None = None
    value_number: Decimal | None = None
    unit: str | None = None
    source_name: str | None = None
    source_type: str = SpecValueSourceType.STORE.value
    source_url: str | None = None


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _manufacturer_source(product: Product):
    entries = sorted(sources_for_product(product), key=lambda item: item.priority)
    for entry in entries:
        if entry.source_type == SpecValueSourceType.MANUFACTURER.value:
            return entry
    return entries[0] if entries else None


def _parse_title_specs(product: Product, source) -> list[ParsedSpec]:
    title = product.name or ""
    source_type = source.source_type if source else SpecValueSourceType.STORE.value
    source_name = source.source_name if source else product.brand
    source_url = source.url if source else None
    specs: list[ParsedSpec] = []

    if match := re.search(r"\b(?:(?:NVIDIA\s+)?GeForce\s+(?:RTX|GTX)\s*[A-Z]?\s*\d{3,4}(?:\s*Ti)?|(?:AMD\s+)?Radeon\s+RX\s*\d{3,4}(?:\s*XT)?)\b", title, re.IGNORECASE):
        value = _clean(match.group(0))
        specs.append(ParsedSpec("chipset", value, SpecValueKind.TEXT.value, value_text=value, source_name=source_name, source_type=source_type, source_url=source_url))

    if match := re.search(r"\b(\d+)\s*GB\s*(GDDR[0-9X]+|DDR[345])\b", title, re.IGNORECASE):
        specs.append(ParsedSpec("vram", f"{match.group(1)} GB", SpecValueKind.NUMBER.value, value_number=Decimal(match.group(1)), unit="GB", source_name=source_name, source_type=source_type, source_url=source_url))
        memory_type = match.group(2).upper()
        specs.append(ParsedSpec("memory_type", memory_type, SpecValueKind.TEXT.value, value_text=memory_type, source_name=source_name, source_type=source_type, source_url=source_url))

    if match := re.search(r"\b(\d{2,4})[-\s]?bit\b", title, re.IGNORECASE):
        specs.append(ParsedSpec("memory_bus", f"{match.group(1)} bit", SpecValueKind.NUMBER.value, value_number=Decimal(match.group(1)), unit="bit", source_name=source_name, source_type=source_type, source_url=source_url))

    if match := re.search(r"\bPCI[-\s]?e\s*(\d(?:\.\d)?)(?:\s*x\s*(\d+))?\b", title, re.IGNORECASE):
        lanes = match.group(2)
        if lanes:
            value = f"PCIe {match.group(1)} x{lanes}"
            specs.append(ParsedSpec("pcie_interface", value, SpecValueKind.TEXT.value, value_text=value, source_name=source_name, source_type=source_type, source_url=source_url))

    return specs


def _parse_source_specs(product: Product, source) -> list[ParsedSpec]:
    if not source:
        return []
    try:
        html = fetch_page(source.url).html
    except RuntimeError:
        return []
    text = normalize_context(html, source.needles, prefer_text=source.prefer_text)
    if not text:
        return []

    specs: list[ParsedSpec] = []
    boost_values = [Decimal(value) for value in re.findall(r"(?:OC mode|Default mode|Boost Clock)[^0-9]{0,40}(\d{3,5})\s*MHz", text, re.IGNORECASE)]
    if boost_values:
        boost = max(boost_values)
        specs.append(
            ParsedSpec(
                "boost_clock",
                f"{int(boost)} MHz",
                SpecValueKind.NUMBER.value,
                value_number=boost,
                unit="MHz",
                source_name=source.source_name,
                source_type=source.source_type,
                source_url=source.url,
            )
        )

    if match := re.search(r"\b(GDDR[0-9X]+)\b", text, re.IGNORECASE):
        memory_type = match.group(1).upper()
        specs.append(ParsedSpec("memory_type", memory_type, SpecValueKind.TEXT.value, value_text=memory_type, source_name=source.source_name, source_type=source.source_type, source_url=source.url))

    return specs


def _upsert_spec(product: Product, service: ProductSpecValueService, definitions: dict[str, object], spec: ParsedSpec, *, force: bool) -> bool:
    definition = definitions.get(spec.key)
    if not definition:
        return False
    service.upsert(
        SpecValueInput(
            product_id=product.id,
            definition_id=definition.id,
            value_kind=spec.value_kind,
            raw_value=spec.raw_value,
            value_text=spec.value_text,
            value_number=spec.value_number,
            unit=spec.unit,
            source_type=spec.source_type,
            source_name=spec.source_name,
            source_url=spec.source_url,
            extraction_method="deterministic_title_source",
            verification_status=SpecVerificationStatus.REVIEW.value,
            force_source_update=force,
        )
    )
    return True


def _dedupe_specs(specs: list[ParsedSpec]) -> list[ParsedSpec]:
    by_key: dict[str, ParsedSpec] = {}
    for spec in specs:
        current = by_key.get(spec.key)
        if current is None:
            by_key[spec.key] = spec
            continue
        current_value = current.raw_value
        if spec.source_type == SpecValueSourceType.MANUFACTURER.value and current.source_type != SpecValueSourceType.MANUFACTURER.value:
            by_key[spec.key] = spec
        elif len(spec.raw_value) > len(current_value):
            by_key[spec.key] = spec
    return list(by_key.values())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-id", type=int, help="Backfill only one product")
    parser.add_argument("--limit", type=int, help="Maximum products to process")
    parser.add_argument("--dry-run", action="store_true", help="Print values without persisting")
    parser.add_argument("--force", action="store_true", help="Allow higher/equal priority source replacement")
    parser.add_argument("--skip-source", action="store_true", help="Only parse product titles; do not fetch source pages")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(Product).options(
            selectinload(Product.category_entity).selectinload(Category.spec_definitions),
            selectinload(Product.offers),
        ).order_by(Product.id)
        if args.product_id:
            query = query.filter(Product.id == args.product_id)
        if args.limit:
            query = query.limit(args.limit)

        touched = 0
        service = ProductSpecValueService(db, auto_commit=False)
        for product in query.all():
            if not product.category_entity:
                continue
            definitions = {definition.key: definition for definition in product.category_entity.spec_definitions}
            source = _manufacturer_source(product)
            parsed = _parse_title_specs(product, source)
            if not args.skip_source:
                parsed += _parse_source_specs(product, source)
            parsed = _dedupe_specs(parsed)
            if not parsed:
                continue
            print(f"#{product.id} {product.name[:70]}")
            for spec in parsed:
                if spec.key not in definitions:
                    continue
                print(f"  {spec.key:16} -> {spec.raw_value} [{spec.source_name or spec.source_type}]")
                if args.dry_run:
                    touched += 1
                elif _upsert_spec(product, service, definitions, spec, force=args.force):
                    touched += 1
            if args.dry_run:
                db.rollback()
            else:
                db.commit()

        print(f"Spec values {'planned' if args.dry_run else 'written'}: {touched}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
