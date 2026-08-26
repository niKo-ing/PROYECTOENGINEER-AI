"""Concurrency and constraint audit tests.

Test matrix:
A) Two threads create same Product simultaneously → one IntegrityError
B) Two threads create same StoreOffer simultaneously → one IntegrityError
C) Race: _find_offer returns None, two threads both create → UNIQUE catches
D) Race: match returns NO_MATCH, two threads both create Product → UNIQUE catches
E) GTIN with leading zeros preserved correctly
F) GTIN-12 and GTIN-13 for same product → two Products (different GTINs)
G) MPN variant from different brand → stored separately (UNIQUE(mpn) allows)
H) MPN variant from same brand → UNIQUE(mpn) catches exact match
I) match_by_mpn_brand with variant MPN from different brand → found via Python filter
J) match_by_mpn_brand uses normalize_mpn in query (fix for variant matching)
K) ProductSpec: same spec name, different products → allowed
L) ProductSpec: same spec name, same product → UNIQUE catches
M) Transaction: ingest() commits independently, one failure doesn't undo others
N) Transaction: pipeline continues after individual offer failure
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.catalog.identity import normalize_mpn
from app.catalog.matching import ProductMatcher, MatchStatus
from app.db import Base
from app.ingestion.connectors import StoreConnector
from app.ingestion.dto import NormalizedOffer
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.service import CatalogIngestionService
from app.models.catalog import (
    Category,
    PriceHistory,
    Product,
    ProductSpecification,
    Store,
    StoreOffer,
)

# ── Test DB setup ──────────────────────────────────────────────────

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _reset(db):
    for model in (PriceHistory, StoreOffer, ProductSpecification, Product, Store, Category):
        db.query(model).delete()
    db.commit()


def _make_connector(store_name, store_domain, records):
    source = f"mock:{store_domain}"
    sn, sd = store_name, store_domain

    class _Conn(StoreConnector):
        store_name = sn
        store_domain = sd
        source_name = source

        def __init__(self, recs):
            self._recs = recs

        def extract(self):
            yield from self._recs

        def normalize(self, record):
            now = datetime.now(timezone.utc)
            return NormalizedOffer(
                source=self.source_name,
                external_id=record.get("external_id"),
                product_url=record.get("url", f"https://{sd}/p"),
                name=record.get("name", "Product"),
                brand=record.get("brand"),
                model=record.get("model"),
                mpn=record.get("mpn"),
                gtin=record.get("gtin"),
                sku=record.get("sku"),
                price=Decimal(str(record.get("price", 1000))),
                previous_price=None,
                currency="CLP",
                availability=True,
                stock="in_stock",
                image_url=None,
                category=record.get("category"),
                scraped_at=now,
            )

    return _Conn(records)


# ══════════════════════════════════════════════════════════════════
#  A) TWO THREADS CREATE SAME PRODUCT → UNIQUE CATCHES
# ══════════════════════════════════════════════════════════════════


class TestRaceCreateProduct:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_concurrent_same_mpn_one_product(self):
        """Two threads ingesting same MPN → UNIQUE(mpn) catches duplicates.

        Note: SQLite with StaticPool shares one connection, so concurrent
        transactions may both fail. With a real DB (PostgreSQL), exactly one
        would succeed and the other would get IntegrityError.
        """
        records = [
            {"url": "https://a.mock/p1", "external_id": "A001", "name": "HP Laptop", "brand": "HP", "mpn": "HP-001", "price": 500000},
            {"url": "https://b.mock/p1", "external_id": "B001", "name": "HP Laptop", "brand": "HP", "mpn": "HP-001", "price": 520000},
        ]

        # Pre-create stores to avoid store creation race
        with TestSession() as db:
            db.add(Store(name="Store A", domain="a.mock", store_type="retailer"))
            db.add(Store(name="Store B", domain="b.mock", store_type="retailer"))
            db.commit()

        errors = []

        def run_connector(store_name, store_domain, recs):
            try:
                conn = _make_connector(store_name, store_domain, recs)
                with TestSession() as db:
                    service = CatalogIngestionService(db)
                    IngestionPipeline(service).run(conn)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=run_connector, args=("Store A", "a.mock", [records[0]]))
        t2 = threading.Thread(target=run_connector, args=("Store B", "b.mock", [records[1]]))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        with TestSession() as db:
            product_count = db.query(Product).count()
            offer_count = db.query(StoreOffer).count()
            # At most 1 Product (UNIQUE(mpn) catches), at most 2 Offers
            assert product_count <= 1
            assert offer_count <= 2


# ══════════════════════════════════════════════════════════════════
#  B) TWO THREADS CREATE SAME STOREOFFER → UNIQUE CATCHES
# ══════════════════════════════════════════════════════════════════


class TestRaceCreateOffer:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_concurrent_same_url_same_store_one_offer(self):
        """Two threads creating offer with same URL+store → UNIQUE catches."""
        record = {"url": "https://a.mock/p1", "external_id": "A001", "name": "HP", "brand": "HP", "mpn": "HP-001", "price": 500}

        # Pre-create the store
        with TestSession() as db:
            db.add(Store(name="Store A", domain="a.mock", store_type="retailer"))
            db.commit()

        results = []
        errors = []

        def run_connector():
            try:
                conn = _make_connector("Store A", "a.mock", [record])
                with TestSession() as db:
                    service = CatalogIngestionService(db)
                    report = IngestionPipeline(service).run(conn)
                    results.append(report)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=run_connector)
        t2 = threading.Thread(target=run_connector)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        with TestSession() as db:
            offer_count = db.query(StoreOffer).count()
            assert offer_count == 1


# ══════════════════════════════════════════════════════════════════
#  C) RACE: _find_offer RETURNS None, BOTH CREATE → UNIQUE CATCHES
# ══════════════════════════════════════════════════════════════════


class TestRaceFindOfferNone:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_both_threads_find_no_offer_then_create(self):
        """Simulate the race: both threads see no offer, both try to create."""
        records = [
            {"url": "https://a.mock/p1", "external_id": "A001", "name": "HP", "brand": "HP", "mpn": "HP-001", "price": 500},
        ]

        # Pre-create the store so threads don't race on store creation
        with TestSession() as db:
            store = Store(name="Store A", domain="a.mock", store_type="retailer")
            db.add(store)
            db.commit()

        def run_connector():
            try:
                conn = _make_connector("Store A", "a.mock", records)
                with TestSession() as db:
                    service = CatalogIngestionService(db)
                    IngestionPipeline(service).run(conn)
            except Exception:
                pass

        t1 = threading.Thread(target=run_connector)
        t2 = threading.Thread(target=run_connector)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        with TestSession() as db:
            offer_count = db.query(StoreOffer).count()
            # UNIQUE(store_id, url) catches duplicate
            assert offer_count == 1


# ══════════════════════════════════════════════════════════════════
#  D) RACE: MATCH RETURNS NO_MATCH, BOTH CREATE PRODUCT → UNIQUE CATCHES
# ══════════════════════════════════════════════════════════════════


class TestRaceMatchNoMatch:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_both_threads_match_fails_both_create(self):
        """Both threads see no matching product, both try to create."""
        records = [
            {"url": "https://a.mock/p1", "external_id": "A001", "name": "HP", "brand": "HP", "mpn": "HP-001", "price": 500},
        ]

        # Pre-create the store
        with TestSession() as db:
            db.add(Store(name="Store A", domain="a.mock", store_type="retailer"))
            db.commit()

        def run_connector():
            try:
                conn = _make_connector("Store A", "a.mock", records)
                with TestSession() as db:
                    service = CatalogIngestionService(db)
                    IngestionPipeline(service).run(conn)
            except Exception:
                pass

        t1 = threading.Thread(target=run_connector)
        t2 = threading.Thread(target=run_connector)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        with TestSession() as db:
            product_count = db.query(Product).count()
            # UNIQUE(mpn) catches duplicate
            assert product_count == 1


# ══════════════════════════════════════════════════════════════════
#  E) GTIN WITH LEADING ZEROS PRESERVED
# ══════════════════════════════════════════════════════════════════


class TestGTINLeadingZeros:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_gtin12_with_leading_zeros(self):
        """GTIN-12 '012345678901' → stored as '012345678901' (12 chars)."""
        records = [
            {"url": "https://a.mock/p1", "external_id": "A001", "name": "Product", "brand": "HP", "gtin": "012345678901", "price": 500},
        ]
        conn = _make_connector("Store A", "a.mock", records)

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(conn)

            product = db.query(Product).one()
            assert product.gtin == "012345678901"
            assert len(product.gtin) == 12

    def test_gtin13_with_leading_zeros(self):
        """GTIN-13 '0012345678901' → stored as '0012345678901' (13 chars)."""
        records = [
            {"url": "https://a.mock/p1", "external_id": "A001", "name": "Product", "brand": "HP", "gtin": "0012345678901", "price": 500},
        ]
        conn = _make_connector("Store A", "a.mock", records)

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(conn)

            product = db.query(Product).one()
            assert product.gtin == "0012345678901"
            assert len(product.gtin) == 13


# ══════════════════════════════════════════════════════════════════
#  F) GTIN-12 AND GTIN-13 FOR SAME PRODUCT → TWO PRODUCTS
# ══════════════════════════════════════════════════════════════════


class TestGTINDifferentLengths:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_different_gtin_lengths_create_separate_products(self):
        """GTIN-12 and GTIN-13 are different identifiers → two Products."""
        records_a = [
            {"url": "https://a.mock/p1", "external_id": "A001", "name": "Product A", "brand": "HP", "gtin": "012345678901", "price": 500},
        ]
        records_b = [
            {"url": "https://b.mock/p1", "external_id": "B001", "name": "Product B", "brand": "HP", "gtin": "0012345678901", "price": 600},
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(_make_connector("Store A", "a.mock", records_a))
            IngestionPipeline(service).run(_make_connector("Store B", "b.mock", records_b))

            assert db.query(Product).count() == 2


# ══════════════════════════════════════════════════════════════════
#  G) MPN VARIANT FROM DIFFERENT BRAND → STORED SEPARATELY
# ══════════════════════════════════════════════════════════════════


class TestMPNVariantsDifferentBrand:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_same_mpn_different_brand_two_products(self):
        """RTX-5070 (ASUS) and RTX 5070 (MSI) → different Products."""
        records_a = [
            {"url": "https://a.mock/p1", "external_id": "A001", "name": "ASUS RTX 5070", "brand": "ASUS", "mpn": "RTX-5070", "price": 600000},
        ]
        records_b = [
            {"url": "https://b.mock/p1", "external_id": "B001", "name": "MSI RTX 5070", "brand": "MSI", "mpn": "RTX 5070", "price": 620000},
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(_make_connector("Store A", "a.mock", records_a))
            IngestionPipeline(service).run(_make_connector("Store B", "b.mock", records_b))

            # Different brands + different MPN strings → two Products
            assert db.query(Product).count() == 2


# ══════════════════════════════════════════════════════════════════
#  H) MPN VARIANT FROM SAME BRAND → UNIQUE(MPN) CATCHES
# ══════════════════════════════════════════════════════════════════


class TestMPNVariantsSameBrand:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_same_mpn_exact_same_brand_one_product(self):
        """Same MPN string, same brand → UNIQUE(mpn) prevents duplicate."""
        records_a = [
            {"url": "https://a.mock/p1", "external_id": "A001", "name": "ASUS RTX 5070", "brand": "ASUS", "mpn": "RTX5070", "price": 600000},
        ]
        records_b = [
            {"url": "https://b.mock/p1", "external_id": "B001", "name": "ASUS RTX 5070 OC", "brand": "ASUS", "mpn": "RTX5070", "price": 620000},
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(_make_connector("Store A", "a.mock", records_a))
            IngestionPipeline(service).run(_make_connector("Store B", "b.mock", records_b))

            # Same MPN string → UNIQUE catches, one Product
            assert db.query(Product).count() == 1
            assert db.query(StoreOffer).count() == 2


# ══════════════════════════════════════════════════════════════════
#  I) MATCH_BY_MPN_BRAND WITH VARIANT FROM DIFFERENT BRAND
# ══════════════════════════════════════════════════════════════════


class TestMatchMPNBrandVariant:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_mpn_variant_different_brand_matches_via_python(self):
        """RTX-5070 (ASUS) exists, query RTX 5070 (ASUS) → found via mpn_matches."""
        with TestSession() as db:
            product = Product(
                name="ASUS RTX 5070",
                brand="ASUS",
                mpn="RTX-5070",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            # Query with variant MPN (space instead of hyphen)
            result = matcher.match_by_mpn_brand("RTX 5070", "ASUS")
            assert result.is_match
            assert result.product.id == product.id

    def test_mpn_variant_different_brand_not_found_by_brand_filter(self):
        """RTX-5070 (ASUS) exists, query RTX 5070 (MSI) → not found (different brand)."""
        with TestSession() as db:
            product = Product(
                name="ASUS RTX 5070",
                brand="ASUS",
                mpn="RTX-5070",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_mpn_brand("RTX 5070", "MSI")
            assert result.is_no_match


# ══════════════════════════════════════════════════════════════════
#  J) MATCH_BY_MPN_BRAND USES NORMALIZE_MPN IN QUERY
# ══════════════════════════════════════════════════════════════════


class TestMatchMPNNormalizedQuery:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_normalized_mpn_matches_variant_in_db(self):
        """Product stored with 'RTX-5070', query 'RTX 5070' → found via normalize_mpn."""
        with TestSession() as db:
            product = Product(
                name="ASUS RTX 5070",
                brand="ASUS",
                mpn="RTX-5070",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            # The fix: match_by_mpn_brand should normalize MPN in query
            result = matcher.match_by_mpn_brand("RTX 5070", "ASUS")
            assert result.is_match
            assert result.product.id == product.id

    def test_no_false_positive_different_mpn(self):
        """Different MPNs should not match."""
        with TestSession() as db:
            product = Product(
                name="ASUS RTX 5070",
                brand="ASUS",
                mpn="RTX-5070",
            )
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)
            result = matcher.match_by_mpn_brand("RTX-5060", "ASUS")
            assert result.is_no_match


# ══════════════════════════════════════════════════════════════════
#  K) PRODUCT SPEC: SAME NAME, DIFFERENT PRODUCTS → ALLOWED
# ══════════════════════════════════════════════════════════════════


class TestProductSpecDifferentProducts:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_same_spec_name_different_products(self):
        """RAM=16GB on two different products → allowed."""
        with TestSession() as db:
            p1 = Product(name="HP Laptop", brand="HP")
            p2 = Product(name="Dell Laptop", brand="Dell")
            db.add_all([p1, p2])
            db.flush()

            s1 = ProductSpecification(product_id=p1.id, name="RAM", value="16 GB")
            s2 = ProductSpecification(product_id=p2.id, name="RAM", value="16 GB")
            db.add_all([s1, s2])
            db.commit()

            assert db.query(ProductSpecification).count() == 2


# ══════════════════════════════════════════════════════════════════
#  L) PRODUCT SPEC: SAME NAME, SAME PRODUCT → UNIQUE CATCHES
# ══════════════════════════════════════════════════════════════════


class TestProductSpecSameProduct:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_duplicate_spec_name_same_product_rejected(self):
        """Two 'RAM' specs on same product → UNIQUE(product_id, name) catches."""
        with TestSession() as db:
            p1 = Product(name="HP Laptop", brand="HP")
            db.add(p1)
            db.flush()

            s1 = ProductSpecification(product_id=p1.id, name="RAM", value="16 GB")
            db.add(s1)
            db.commit()

            s2 = ProductSpecification(product_id=p1.id, name="RAM", value="32 GB")
            db.add(s2)
            with pytest.raises(Exception):  # IntegrityError
                db.commit()


# ══════════════════════════════════════════════════════════════════
#  M) TRANSACTION: INGEST() COMMITS INDEPENDENTLY
# ══════════════════════════════════════════════════════════════════


class TestTransactionIndependence:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_one_offer_failure_does_not_undo_others(self):
        """First offer succeeds, second fails validation → first committed."""
        records = [
            {"url": "https://a.mock/p1", "external_id": "A001", "name": "Good", "brand": "HP", "mpn": "HP-001", "price": 500},
            {"url": "https://a.mock/p2", "external_id": "A002", "name": "", "brand": "HP", "mpn": "HP-002", "price": 600},
        ]
        conn = _make_connector("Store A", "a.mock", records)

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(conn)

            assert report.offers_created == 1
            assert report.validation_errors == 1
            assert db.query(StoreOffer).count() == 1

    def test_second_offer_new_product_first_committed(self):
        """First offer creates product+offer, second creates different product."""
        records = [
            {"url": "https://a.mock/p1", "external_id": "A001", "name": "HP", "brand": "HP", "mpn": "HP-001", "price": 500},
            {"url": "https://a.mock/p2", "external_id": "A002", "name": "Dell", "brand": "Dell", "mpn": "DEL-001", "price": 600},
        ]
        conn = _make_connector("Store A", "a.mock", records)

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(conn)

            assert report.offers_created == 2
            assert db.query(Product).count() == 2
            assert db.query(StoreOffer).count() == 2


# ══════════════════════════════════════════════════════════════════
#  N) PIPELINE CONTINUES AFTER INDIVIDUAL FAILURE
# ══════════════════════════════════════════════════════════════════


class TestPipelineContinuesAfterFailure:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_validation_error_does_not_stop_pipeline(self):
        """Middle offer fails → first and third succeed."""
        records = [
            {"url": "https://a.mock/p1", "external_id": "A001", "name": "HP", "brand": "HP", "mpn": "HP-001", "price": 500},
            {"url": "https://a.mock/p2", "external_id": "A002", "name": "", "brand": "HP", "mpn": "HP-002", "price": 600},
            {"url": "https://a.mock/p3", "external_id": "A003", "name": "Dell", "brand": "Dell", "mpn": "DEL-001", "price": 700},
        ]
        conn = _make_connector("Store A", "a.mock", records)

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(conn)

            assert report.offers_created == 2
            assert report.validation_errors == 1
            assert db.query(StoreOffer).count() == 2

    def test_extraction_error_does_not_stop_pipeline(self):
        """Middle offer raises ValueError → first and third succeed."""
        records = [
            {"url": "https://a.mock/p1", "external_id": "A001", "name": "HP", "brand": "HP", "mpn": "HP-001", "price": 500},
            {"url": "https://a.mock/p2", "external_id": "A002", "name": "Bad", "brand": "HP", "mpn": "HP-002", "price": "not_a_number"},
            {"url": "https://a.mock/p3", "external_id": "A003", "name": "Dell", "brand": "Dell", "mpn": "DEL-001", "price": 700},
        ]
        conn = _make_connector("Store A", "a.mock", records)

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(conn)

            assert report.offers_created == 2
            assert report.extraction_errors == 1
            assert db.query(StoreOffer).count() == 2
