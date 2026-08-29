"""Backfill product galleries and store-provided descriptions.

Re-visits the offer URL of every catalog product with the matching store
parser and stores the ordered gallery (products.images) and the
store-provided description (products.description) when missing. Only
updates media, never prices or history.

Usage:
    python -m scripts.backfill_gallery_descriptions [--dry-run]
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.ingestion.connectors import StoreConnector
from app.ingestion.connectors.paris.connector import ParisConnector
from app.ingestion.connectors.paris.parser import RawProductData
from app.ingestion.connectors.spdigital.connector import SPDigitalConnector
from app.ingestion.service import MAX_DESCRIPTION_LENGTH, _clip
from app.models.catalog import Product, StoreOffer


def _connector_for(domain: str) -> type[StoreConnector] | None:
    if domain == "www.paris.cl":
        return ParisConnector
    if domain == "www.spdigital.cl":
        return SPDigitalConnector
    return None


def _fetch_raw(connector_cls: type[StoreConnector], url: str) -> RawProductData | None:
    connector = connector_cls(urls=[url])
    try:
        record = next(connector.extract(), None)
    except Exception:
        return None
    return record["raw"] if record else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print planned updates without persisting")
    args = parser.parse_args()

    db = SessionLocal()
    updated_products = 0
    skipped = 0
    fetched = 0
    try:
        products = db.scalars(
            select(Product)
            .outerjoin(StoreOffer)
            .where(StoreOffer.product_id.is_not(None))
            .group_by(Product.id)
            .order_by(Product.id)
        ).all()

        for product in products:
            if product.images and product.description:
                skipped += 1
                continue
            offers = [o for o in product.offers if o.url]
            if not offers:
                skipped += 1
                continue

            for offer in offers:
                connector_cls = _connector_for(offer.store.domain)
                if connector_cls is None:
                    continue
                try:
                    raw = _fetch_raw(connector_cls, offer.url)
                except Exception:
                    continue
                if raw is None:
                    continue
                fetched += 1
                changed = False
                if not product.images and raw.images:
                    product.images = list(raw.images)
                    changed = True
                raw_description = getattr(raw, "description", None)
                if not product.description and raw_description:
                    product.description = _clip(raw_description)
                    changed = True
                if changed:
                    updated_products += 1
                    print(f"  #{product.id} {product.name[:48]:<50} images={len(product.images) if product.images else 0} desc={'yes' if product.description else 'no'} ({offer.store.domain})")
                break

        if args.dry_run:
            print(f"DRY RUN: would touch {updated_products} products ({fetched} successful fetches, {skipped} skipped)")
            db.rollback()
        else:
            db.commit()
            print(f"Updated {updated_products} products ({fetched} successful fetches, {skipped} skipped)")
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())