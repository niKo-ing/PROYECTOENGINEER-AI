from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import Category, CategorySpecificationDefinition, Product, ProductSpecValue, Store, StoreOffer


@dataclass(frozen=True)
class ProductCompleteness:
    product_id: int
    name: str
    category: str | None
    score: int
    spec_values_count: int
    missing: list[str]
    present: list[str]
    verification_status: str


NOTEBOOK_RELEVANT_KEYS = (
    "processor",
    "processor_cores",
    "processor_threads",
    "ram_capacity",
    "ram_type",
    "storage_capacity",
    "storage_type",
    "gpu",
    "screen_size",
    "screen_resolution",
    "screen_refresh_rate",
    "panel_type",
    "ports",
    "wireless",
    "battery_capacity",
    "battery",
    "weight",
)

GPU_RELEVANT_KEYS = (
    "chipset",
    "vram",
    "memory_type",
    "memory_bus",
    "tdp",
    "length",
    "power_connector",
)

RAM_RELEVANT_KEYS = (
    "capacity",
    "type",
    "speed",
    "modules",
    "latency",
)

MOBILE_RELEVANT_KEYS = (
    "screen",
    "processor",
    "ram",
    "storage",
    "rear_camera",
    "battery",
    "connectivity",
)

MONITOR_RELEVANT_KEYS = (
    "size",
    "resolution",
    "refresh_rate",
    "panel_type",
    "response_time",
    "brightness",
    "hdr",
    "adaptive_sync",
    "ports",
    "vesa_mount",
)

MOTHERBOARD_RELEVANT_KEYS = (
    "socket",
    "chipset",
    "form_factor",
    "memory_type",
    "ram_slots",
    "max_memory",
    "pcie_slots",
    "m2_slots",
    "sata_ports",
    "ethernet",
)

CATEGORY_PROFILES = {
    "notebooks": NOTEBOOK_RELEVANT_KEYS,
    "pcs-de-escritorio": NOTEBOOK_RELEVANT_KEYS,
    "mini-pcs": NOTEBOOK_RELEVANT_KEYS,
    "tarjetas-graficas": GPU_RELEVANT_KEYS,
    "memoria-ram": RAM_RELEVANT_KEYS,
    "celulares": MOBILE_RELEVANT_KEYS,
    "tablets": MOBILE_RELEVANT_KEYS,
    "monitores": MONITOR_RELEVANT_KEYS,
    "smart-tvs": MONITOR_RELEVANT_KEYS,
    "placas-madre": MOTHERBOARD_RELEVANT_KEYS,
}


class CatalogQualityService:
    def __init__(self, db: Session):
        self.db = db

    def build_report(self) -> dict:
        products = self._products()
        values = self._values()
        product_scores = [self._score_product(product) for product in products]
        categories = Counter(product.category for product in products)
        definitions_used = Counter(value.definition.key for value in values if value.definition)
        source_counts = Counter(value.source_type for value in values)
        source_name_counts = Counter(value.source_name or "Sin nombre" for value in values)
        extraction_counts = Counter(value.extraction_method or "Sin método" for value in values)
        verification_counts = Counter(value.verification_status for value in values)
        category_definition_usage = self._category_definition_usage(products)

        total_products = len(products)
        products_with_values = {value.product_id for value in values}
        conflicts = [value for value in values if value.conflict_status == "pending"]
        incomplete = sorted(product_scores, key=lambda item: (item.score, item.spec_values_count, item.name))
        complete = sorted(product_scores, key=lambda item: (-item.score, -item.spec_values_count, item.name))

        return {
            "summary": {
                "products": total_products,
                "offers": self.db.scalar(select(func.count(StoreOffer.id))) or 0,
                "stores": self.db.scalar(select(func.count(Store.id))) or 0,
                "spec_values": len(values),
                "products_without_specs": total_products - len(products_with_values),
                "specs_pending": verification_counts.get("review", 0) + verification_counts.get("auto", 0),
                "specs_verified": verification_counts.get("verified", 0),
                "conflicts": len(conflicts),
                "average_completeness": round(sum(item.score for item in product_scores) / total_products) if total_products else 0,
            },
            "categories": [{"category": category or "Sin categoría", "products": count} for category, count in categories.most_common()],
            "products": [self._product_score_to_dict(item) for item in product_scores],
            "products_incomplete": [self._product_score_to_dict(item) for item in incomplete[:20]],
            "products_complete": [self._product_score_to_dict(item) for item in complete[:20]],
            "definitions_used": [
                {"key": key, "values": count}
                for key, count in definitions_used.most_common()
            ],
            "definitions_always_empty": self._definitions_always_empty(category_definition_usage),
            "definitions_low_coverage": self._definitions_low_coverage(category_definition_usage),
            "sources": [{"source_type": source, "values": count} for source, count in source_counts.most_common()],
            "source_names": [{"source_name": source, "values": count} for source, count in source_name_counts.most_common()],
            "extraction_methods": [{"extraction_method": method, "values": count} for method, count in extraction_counts.most_common()],
            "provenance_summary": {
                "ai": source_counts.get("ai", 0),
                "store": source_counts.get("store", 0),
                "manufacturer": source_counts.get("manufacturer", 0),
                "external": source_counts.get("external", 0),
                "scraper": source_counts.get("scraper", 0),
                "ingestion": source_counts.get("ingestion", 0),
                "admin": source_counts.get("admin", 0),
                "unknown": source_counts.get("unknown", 0),
            },
            "verification": [{"status": status, "values": count} for status, count in verification_counts.most_common()],
            "conflicts_by_source": [
                {"source_type": source, "conflicts": count}
                for source, count in Counter(value.source_type for value in conflicts).most_common()
            ],
            "conflicts": [self._conflict_to_dict(value) for value in conflicts],
        }

    def _products(self) -> list[Product]:
        return list(
            self.db.scalars(
                select(Product)
                .options(
                    selectinload(Product.category_entity).selectinload(Category.spec_definitions),
                    selectinload(Product.spec_values).selectinload(ProductSpecValue.definition),
                )
                .order_by(Product.id)
            )
        )

    def _values(self) -> list[ProductSpecValue]:
        return list(
            self.db.scalars(
                select(ProductSpecValue)
                .options(selectinload(ProductSpecValue.product), selectinload(ProductSpecValue.definition))
                .order_by(ProductSpecValue.id)
            )
        )

    def _score_product(self, product: Product) -> ProductCompleteness:
        definitions = {definition.key: definition for definition in (product.category_entity.spec_definitions if product.category_entity else [])}
        relevant_keys = self._relevant_keys(product.category_entity, definitions)
        present_keys = {value.definition.key for value in product.spec_values if value.definition and self._has_value(value)}
        relevant_present = [key for key in relevant_keys if key in present_keys]
        missing = [definitions[key].label for key in relevant_keys if key not in present_keys and key in definitions]

        identity_score = self._identity_score(product)
        spec_score = round((len(relevant_present) / len(relevant_keys)) * 85) if relevant_keys else 0
        score = min(100, identity_score + spec_score)
        verification_status = self._product_verification_status(product)
        return ProductCompleteness(
            product_id=product.id,
            name=product.name,
            category=product.category,
            score=score,
            spec_values_count=len(product.spec_values),
            missing=missing,
            present=[definitions[key].label for key in relevant_present if key in definitions],
            verification_status=verification_status,
        )

    def _relevant_keys(self, category: Category | None, definitions: dict[str, CategorySpecificationDefinition]) -> tuple[str, ...]:
        if not category:
            return ()
        profile = CATEGORY_PROFILES.get(category.slug)
        if profile:
            return tuple(key for key in profile if key in definitions)
        required = tuple(key for key, definition in definitions.items() if definition.required)
        return required or tuple(definitions.keys())

    def _identity_score(self, product: Product) -> int:
        score = 5 if product.name else 0
        if product.brand:
            score += 4
        if product.model:
            score += 3
        if product.mpn or product.gtin or product.manufacturer_sku:
            score += 3
        return score

    def _product_verification_status(self, product: Product) -> str:
        if not product.spec_values:
            return "missing"
        if any(value.conflict_status == "pending" for value in product.spec_values):
            return "conflict"
        if all(value.verification_status == "verified" for value in product.spec_values):
            return "verified"
        return "unverified"

    def _has_value(self, value: ProductSpecValue) -> bool:
        return value.value_text is not None or value.value_number is not None or value.value_boolean is not None or value.value_json is not None or bool(value.raw_value)

    def _category_definition_usage(self, products: list[Product]) -> list[dict]:
        products_by_category: dict[int, list[Product]] = defaultdict(list)
        for product in products:
            if product.category_id:
                products_by_category[product.category_id].append(product)

        rows = []
        for category_id, category_products in products_by_category.items():
            category = category_products[0].category_entity
            if not category:
                continue
            product_count = len(category_products)
            for definition in category.spec_definitions:
                product_ids_with_value = {
                    product.id
                    for product in category_products
                    for value in product.spec_values
                    if value.definition_id == definition.id and self._has_value(value)
                }
                rows.append(
                    {
                        "category": category.name,
                        "category_slug": category.slug,
                        "key": definition.key,
                        "label": definition.label,
                        "group": definition.group,
                        "data_type": definition.data_type,
                        "applicability": definition.applicability,
                        "products": product_count,
                        "products_with_value": len(product_ids_with_value),
                        "coverage": round((len(product_ids_with_value) / product_count) * 100) if product_count else 0,
                    }
                )
        return rows

    def _definitions_always_empty(self, rows: list[dict]) -> list[dict]:
        return [row for row in rows if row["products_with_value"] == 0]

    def _definitions_low_coverage(self, rows: list[dict]) -> list[dict]:
        return sorted(
            [row for row in rows if 0 < row["products_with_value"] < row["products"]],
            key=lambda row: (row["coverage"], row["category"], row["key"]),
        )

    def _conflict_to_dict(self, value: ProductSpecValue) -> dict:
        return {
            "product_id": value.product_id,
            "product_name": value.product.name if value.product else f"Producto #{value.product_id}",
            "category": value.product.category if value.product else None,
            "definition_key": value.definition.key if value.definition else "unknown",
            "label": value.definition.label if value.definition else "Especificación",
            "raw_value": value.raw_value,
            "source_type": value.source_type,
            "verification_status": value.verification_status,
            "conflict_status": value.conflict_status,
        }

    def _product_score_to_dict(self, item: ProductCompleteness) -> dict:
        return {
            "product_id": item.product_id,
            "name": item.name,
            "category": item.category,
            "score": item.score,
            "spec_values_count": item.spec_values_count,
            "missing": item.missing,
            "present": item.present,
            "verification_status": item.verification_status,
        }
