"""Backfill canonical ProductSpecValue rows from existing Product.specs JSON.

Safe to run repeatedly. Product.specs is not modified.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy.orm import selectinload

from app.catalog.spec_backfill import backfill_product_specs
from app.db import SessionLocal
from app.models.catalog import Category, Product
from app.services.product_spec_value_service import ProductSpecValueService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-id", type=int, help="Backfill only one product")
    parser.add_argument("--limit", type=int, help="Maximum products to process")
    parser.add_argument("--dry-run", action="store_true", help="Report candidates without persisting")
    parser.add_argument("--refresh-provenance", action="store_true", help="Refresh source metadata for existing canonical values")
    args = parser.parse_args()

    db = SessionLocal()
    processed = 0
    written = 0
    skipped = 0
    try:
        query = db.query(Product).options(
            selectinload(Product.category_entity).selectinload(Category.spec_definitions),
        ).filter(Product.specs.isnot(None))
        if args.product_id:
            query = query.filter(Product.id == args.product_id)
        query = query.order_by(Product.id)
        if args.limit:
            query = query.limit(args.limit)

        service = ProductSpecValueService(db, auto_commit=not args.dry_run)
        for product in query.all():
            processed += 1
            if args.dry_run:
                result = backfill_product_specs(product, service, force_source_update=args.refresh_provenance)
                db.rollback()
            else:
                result = backfill_product_specs(product, service, force_source_update=args.refresh_provenance)
                db.commit()
            written += result.created_or_updated
            skipped += result.skipped
            print(f"#{product.id} {product.name[:58]} -> {result.created_or_updated} values, {result.skipped} skipped")
    finally:
        db.close()

    print(f"Processed: {processed}; canonical values touched: {written}; skipped items: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
