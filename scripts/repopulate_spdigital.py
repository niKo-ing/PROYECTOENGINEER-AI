"""Repopulate catalog data for SP Digital via curated-URL ingestion.

Replicates the admin endpoint /api/v1/admin/ingestion/run (mode="urls")
for the www.spdigital.cl store, but with the curated URL list + category map
stored in sync_config.urls, so products are assigned to the Notebooks /
Celulares taxonomy slots.

SP Digital's discovery mode is unusable for a small sample: its flat sitemap
(~66K URLs) is ordered alphabetically, so keyword filtering surfaces
accessories (atriles, carcasas, adaptadores). A curated list is the reliable
path.

This is a one-off operational script; safe to delete after use.
"""

from app.db import SessionLocal
from app.ingestion.connectors.spdigital.connector import SPDigitalConnector
from app.ingestion.runner import IngestionRunner
from app.models.catalog import Store
from sqlalchemy import select


def main() -> None:
    domain = "www.spdigital.cl"
    db = SessionLocal()
    try:
        store = db.scalar(select(Store).where(Store.domain == domain))
        if store is None:
            raise SystemExit(f"Store '{domain}' not found")

        config = store.sync_config or {}
        urls = config.get("urls", [])
        if not urls:
            raise SystemExit(f"Store '{domain}' has no URLs configured")

        # Category map: URL -> canonical taxonomy slug (kebab-case).
        # The mapper in _get_category_mapper/www.spdigital.cl maps display
        # names ("Notebooks" -> notebooks, "Celulares" -> celulares); we use
        # the slugs directly here since the service resolves slugs by lookup.
        url_category_map = {url: "notebooks" for url in urls[:5]}
        url_category_map.update({url: "celulares" for url in urls[5:]})

        connector = SPDigitalConnector(urls=urls, url_category_map=url_category_map)

        runner = IngestionRunner()
        run = runner.run(db=db, connector=connector, urls=urls)
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