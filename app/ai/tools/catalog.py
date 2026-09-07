from sqlalchemy.orm import Session

from app.ai.schemas.tools import CompareProductsInput, GetPriceHistoryInput, GetProductInput, GetProductOffersInput, ProductToolResult, SearchProductsInput
from app.models.catalog import Product
from app.services.product_service import ProductService


def _project(product: Product) -> dict:
    return ProductToolResult(
        id=product.id,
        name=product.name,
        category=product.category,
        price_clp=product.price_clp,
        rating=float(product.rating) if product.rating is not None else None,
        brand=product.brand,
        lowest_price=product.lowest_price,
        lowest_price_store=product.lowest_price_store,
        offer_count=product.offer_count,
    ).model_dump()


def _flatten_specs(product: Product) -> dict[str, str]:
    """Return a flat label->value map from the canonical spec sheet, LLM-friendly."""
    sheet = getattr(product, "canonical_specs", None)
    if not sheet:
        return {}
    flattened: dict[str, str] = {}
    for section in sheet.get("sections") or []:
        for item in section.get("items") or []:
            label = item.get("label")
            value = item.get("value")
            if label and value:
                flattened[label] = value
    return flattened


def _rich_project(product: Product) -> dict:
    return {
        **_project(product),
        "specs": _flatten_specs(product),
    }


class SearchProductsTool:
    def __init__(self, db: Session):
        self.service = ProductService(db)

    def execute(self, params: SearchProductsInput) -> dict:
        products, total = self.service.search(
            query=params.query,
            category=params.category,
            brand=params.brand,
            min_price_clp=params.min_price_clp,
            max_price_clp=params.max_price_clp,
            limit=params.limit,
            offset=0,
        )
        return {"items": [_project(item) for item in products], "total": total}


class GetProductTool:
    def __init__(self, db: Session):
        self.service = ProductService(db)

    def execute(self, params: GetProductInput) -> dict:
        product = self.service.get(params.product_id)
        return _rich_project(product)


class CompareProductsTool:
    def __init__(self, db: Session):
        self.service = ProductService(db)

    def execute(self, params: CompareProductsInput) -> dict:
        products = []
        for product_id in params.product_ids:
            try:
                products.append(_rich_project(self.service.get(product_id)))
            except Exception:
                products.append({"error": {"product_id": product_id, "detail": "Producto no encontrado"}})
        valid = [p for p in products if "error" not in p]
        return {
            "products": products,
            "count": len(products),
            "comparison": build_product_comparison(valid) if valid else {},
        }


def _to_float(value: str) -> float | None:
    import re

    if not value:
        return None
    cleaned = value.replace(".", "").replace(",", ".").strip()
    match = re.search(r"[-+]?[\d]+(?:[.,]\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def build_product_comparison(products: list[dict]) -> dict:
    """Build a category-agnostic structured comparison from rich product data.

    It compares every spec label that appears in at least one product and
    reports, per dimension, which products carry the value and which are
    missing it — suitable for phones, GPUs, notebooks, etc.
    """
    specs_by_id: dict[int, dict[str, str]] = {}
    for product in products:
        specs_by_id[product.get("id")] = dict(product.get("specs") or {})

    all_labels: set[str] = set()
    for specs in specs_by_id.values():
        all_labels.update(specs.keys())

    dimensions: dict[str, dict] = {}
    for label in sorted(all_labels):
        present: dict[int, str] = {}
        missing: list[int] = []
        for pid, specs in specs_by_id.items():
            value = specs.get(label)
            if value:
                present[pid] = value
            else:
                missing.append(pid)
        dimensions[label] = {
            "present": {str(pid): value for pid, value in present.items()},
            "missing": missing,
        }

    common_labels = [label for label, dim in dimensions.items() if not dim["missing"]]

    advantages: dict[int, list[str]] = {}
    for product in products:
        pid = product.get("id")
        advantages[str(pid)] = []
        for label, dim in dimensions.items():
            if str(pid) not in dim["present"]:
                continue
            value = dim["present"][str(pid)]
            competitors = [dim["present"][other] for other in dim["present"] if other != str(pid)]
            if not competitors:
                continue
            number = _to_float(value)
            if number is None:
                continue
            other_numbers = [n for n in (_to_float(c) for c in competitors) if n is not None]
            if other_numbers and all(number > n for n in other_numbers):
                advantages[str(pid)].append(label)

    missing_specs: list[str] = [label for label, dim in dimensions.items() if len(dim["missing"]) > 0]

    price_rows: dict[str, str] = {}
    for product in products:
        pid = product.get("id")
        price_rows[str(pid)] = product.get("lowest_price") if product.get("lowest_price") is not None else "Sin precio"
        if product.get("lowest_price_store"):
            price_rows[str(pid)] = f"{product.get('lowest_price')} ({product.get('lowest_price_store')})"

    return {
        "dimensions": dimensions,
        "common_specs": common_labels,
        "advantages": advantages,
        "missing_specs": missing_specs,
        "price": price_rows,
        "count": len(products),
    }


class GetProductOffersTool:
    def __init__(self, db: Session):
        self.service = ProductService(db)

    def execute(self, params: GetProductOffersInput) -> dict:
        offers = self.service.offers(params.product_id)
        return {"items": [{"store": offer.store.name, "price": offer.price, "currency": offer.currency, "availability": offer.availability, "stock_status": offer.stock_status, "url": offer.url, "seller_name": offer.seller_name} for offer in offers[: params.limit]], "total": len(offers)}


class GetPriceHistoryTool:
    def __init__(self, db: Session):
        self.service = ProductService(db)

    def execute(self, params: GetPriceHistoryInput) -> dict:
        history = self.service.price_history(params.product_id)
        return {"items": [{"price": item.price, "original_price": item.original_price, "currency": item.currency, "observed_at": item.observed_at.isoformat()} for item in history[-params.limit :]], "total": len(history)}