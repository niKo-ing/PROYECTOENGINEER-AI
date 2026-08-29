"""Repopulate catalog data for Paris via discovery ingestion.

Replicates the admin endpoint /api/v1/admin/ingestion/run (mode=discovery)
for the www.paris.cl store. Authorized rerun after the manual DELETE cleared
products/store_offers/price_history.

This is a one-off operational script; safe to delete after use.
"""

from app.db import SessionLocal
from app.ingestion.runner import IngestionRunner
from app.main import _get_connector_class, _get_url_discovery, _get_category_mapper
from app.ingestion.category import CategoryFilter
from app.models.catalog import Store
from sqlalchemy import select


def main() -> None:
    domain = "www.paris.cl"
    db = SessionLocal()
    try:
        store = db.scalar(select(Store).where(Store.domain == domain))
        if store is None:
            raise SystemExit(f"Store '{domain}' not found")

        config = store.sync_config or {}
        categories = config.get("categories", [])
        max_urls = config.get("max_urls_per_category", 20)
        if not categories:
            raise SystemExit(f"Store '{domain}' has no categories configured")

        connector_cls = _get_connector_class(domain)
        url_discovery = _get_url_discovery(domain)
        mapper = _get_category_mapper(domain)
        category_filter = CategoryFilter()

        runner = IngestionRunner()
        run = runner.run_with_discovery(
            db=db,
            connector_factory=connector_cls,
            url_discovery=url_discovery,
            category_mapper=mapper,
            category_filter=category_filter,
            categories=categories,
            store_domain=domain,
            max_urls_per_category=max_urls,
        )
        print("Run id:", run.id)
        print("status:", run.status)
        print("urls_total:", run.urls_total, "urls_processed:", run.urls_processed)
        print("products_created:", run.products_created)
        print("products_updated:", run.products_updated)
        print("price_changes:", run.price_changes)
        print("errors_count:", run.errors_count)
        if run.error_messages:
            print("errors:", run.error_messages)
        print("duration_ms:", run.duration_ms)
    finally:
        db.close()


if __name__ == "__main__":
    main()
