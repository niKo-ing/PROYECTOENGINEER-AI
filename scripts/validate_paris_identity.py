"""Validation: Paris numeric-SKU identity fix, faithful second-pass re-ingestion.

Reproduces EXACTLY the scope of run 6 for www.paris.cl:
- Honors the .env dev limits via get_ingestion_limits():
    INGESTION_MAX_CATEGORIES=2
    INGESTION_MAX_URLS_PER_CATEGORY=5
    INGESTION_MAX_PRODUCTS=10
- Discovery capped the same way runner.run_with_discovery caps it.
- The pipeline runs with max_products=limits.max_products (10).
- To guarantee we only re-check the 10 ORIGINAL run-6 products (ids 28-37),
  normalized offers are restricted to the original-10 SKU set loaded from DB.
  Nothing outside that set is written, so products_created must be 0 and no
  new Product can appear for those SKUs.

Read-only relative to catalog data EXCEPT the pipeline re-ingestion, which only
INSERTs new rows / reuses existing (never DELETEs). No DELETE/TRUNCATE anywhere.
"""

from __future__ import annotations

from collections import Counter

from app.db import SessionLocal
from app.ingestion.category import CategoryFilter, check_url_eligibility
from app.ingestion.connectors import StoreConnector
from app.ingestion.limits import get_ingestion_limits
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.service import CatalogIngestionService
from app.main import _get_connector_class, _get_url_discovery, _get_category_mapper
from app.models.catalog import Product, Store, StoreOffer, PriceHistory
from sqlalchemy import select, func


ORIGINAL_IDS = list(range(28, 38))  # 28..37 = run-6 original products


class _PassthroughConnector(StoreConnector):
    """Yields pre-normalized offers without re-fetching the network."""

    store_name = "Paris"
    store_domain = "www.paris.cl"
    source_name = "paris:www.paris.cl"

    def __init__(self, normalized):
        self._normalized = normalized

    def extract(self):
        for n in self._normalized:
            yield n

    def normalize(self, record):
        return record


def main() -> None:
    domain = "www.paris.cl"
    limits = get_ingestion_limits()
    print("LIMITS:", {
        "max_categories": limits.max_categories,
        "max_urls_per_category": limits.max_urls_per_category,
        "max_products": limits.max_products,
    })

    db = SessionLocal()
    try:
        store = db.scalar(select(Store).where(Store.domain == domain))
        config = store.sync_config or {}
        categories = config.get("categories", [])
        max_urls = config.get("max_urls_per_category", 20)

        # Faithful to runner.run_with_discovery: cap categories & URLs by dev limits
        effective_categories = categories
        if limits.max_categories > 0:
            effective_categories = categories[: limits.max_categories]
        effective_max_urls = max_urls
        if limits.max_urls_per_category > 0:
            effective_max_urls = min(max_urls, limits.max_urls_per_category)
        print("EFFECTIVE_SCOPE:", {"categories": effective_categories, "max_urls_per_category": effective_max_urls})

        def counts():
            return {
                "products": db.query(func.count(Product.id)).scalar(),
                "offers": db.query(func.count(StoreOffer.id)).scalar(),
                "price_history": db.query(func.count(PriceHistory.id)).scalar(),
            }

        before = counts()
        print("STATE_BEFORE:", before)

        # Original-10 SKU set + their URLs, loaded from DB
        originals = db.execute(
            select(StoreOffer.external_id, StoreOffer.url)
            .where(StoreOffer.product_id.in_(ORIGINAL_IDS))
        ).all()
        original_skus = {o.external_id for o in originals if o.external_id}
        original_urls = {o.url for o in originals}
        print("ORIGINAL_10_SKUS:", sorted(original_skus))
        print("ORIGINAL_10_URLS:", len(original_urls))

        url_discovery = _get_url_discovery(domain)
        category_mapper = _get_category_mapper(domain)
        category_filter = CategoryFilter()

        from app.ingestion.url_discovery import DiscoveryFetcher
        fetcher = DiscoveryFetcher(request_delay=0.5, timeout=15.0)
        discovery_report = url_discovery.discover(
            categories=effective_categories,
            category_mapper=category_mapper,
            category_filter=category_filter,
            fetcher=fetcher,
            max_urls_per_category=effective_max_urls,
        )
        urls = [c.url for c in discovery_report.candidates]
        print("DISCOVERED_URLS:", len(urls))

        eligible = []
        for u in urls:
            res = check_url_eligibility(u)
            if res.eligible:
                eligible.append(u)
        print("ELIGIBLE_URLS:", len(eligible))

        url_category_map = {
            c.url: c.mapped_category
            for c in discovery_report.candidates
            if c.mapped_category
        }

        connector_cls = _get_connector_class(domain)
        connector = connector_cls(urls=eligible, url_category_map=url_category_map)
        records = [r for r in connector.extract()]
        print("FETCHED_RECORDS:", len(records))

        normalized_all = [connector.normalize(r) for r in records]

        # Restrict to the ORIGINAL-10 SKUs only (safety against listing drift).
        normalized = [n for n in normalized_all if n.sku in original_skus]
        print("NORMALIZED_IN_ORIGINAL_10:", len(normalized))
        if len(normalized) != len(ORIGINAL_IDS):
            missing = original_skus - {n.sku for n in normalized}
            print("WARNING_NOT_ALL_ORIGINALS_FOUND:", sorted(missing))

        # Matching breakdown against existing Supabase products
        from app.catalog.matching import MatchStatus, ProductMatcher
        matcher = ProductMatcher(db)
        status_counter = Counter()
        strategy_counter = Counter()
        matched_ids = []
        for n in normalized:
            print("  offer sku=", n.sku, "sku_is_identity=", n.sku_is_identity, "brand=", n.brand)
            result = matcher.match(n)
            status_counter[result.status.value] += 1
            if result.strategy:
                strategy_counter[result.strategy] += 1
            if result.is_match and result.product:
                matched_ids.append(result.product.id)
            if n.sku == "502788999":
                print("   [502788999] result:", result.status, "strategy:", result.strategy,
                      "product_id:", result.product.id if result.product else None)
        print("MATCH_BREAKDOWN:", dict(status_counter))
        print("MATCH_STRATEGIES:", dict(strategy_counter))
        print("MATCHED_PRODUCT_IDS:", sorted(set(matched_ids)))

        # Real re-ingestion restricted to original-10 normalized offers,
        # with max_products honored.
        service = CatalogIngestionService(db)
        passthrough = _PassthroughConnector(normalized)
        report = IngestionPipeline(service).run(passthrough, max_products=limits.max_products)

        print("REPORT:")
        print("  products_created:", report.products_created)
        print("  products_matched:", report.products_matched)
        print("  offers_created:", report.offers_created)
        print("  offers_updated:", report.offers_updated)
        print("  price_changes:", report.price_changes)
        print("  urls_processed:", report.urls_processed)
        print("  errors:", report.errors)

        after = counts()
        print("STATE_AFTER:", after)
        after_ids = db.execute(select(Product.id).order_by(Product.id)).scalars().all()
        print("PRODUCT_IDS_AFTER:", after_ids)
        after_skus = db.execute(
            select(StoreOffer.external_id)
            .where(StoreOffer.product_id.in_(ORIGINAL_IDS))
        ).scalars().all()
        print("ORIGINAL_10_OFFERS_AFTER:", sorted(after_skus))

        print("VERDICT:")
        print("  products delta:", after["products"] - before["products"])
        print("  offers delta:", after["offers"] - before["offers"])
        print("  price_history delta:", after["price_history"] - before["price_history"])
        print("  no_new_for_original_skus:", not (set(after_ids) - set(ORIGINAL_IDS)))
    finally:
        db.close()


if __name__ == "__main__":
    main()
