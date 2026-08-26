"""Store Offer + PriceHistory robustness audit tests.

Test matrix:
A) Primera oferta
B) Segunda ingestión idéntica
C) Cambio de precio
D) Precio vuelve al valor anterior
E) Stock cambia sin cambio de precio
F) URL cambia
G) Seller cambia
H) Currency conflict (invalid currency rejected)
I) Precio inválido (negative, zero)
J) Product existente (matched by MPN)
K) Product nuevo
L) Múltiples tiendas mismo Product
M) Múltiples ofertas same store (different URLs)
N) DB transaction rollback
O) Unique constraint conflict
P) Concurrent ingestion simulation
Q) IngestionReport correcto
R) IngestionRun correcto
S) _find_offer fallback (external_id → URL)
T) URL conflict guard
U) PriceHistory temporal sequence
V) Original price tracking
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.ingestion.connectors import StoreConnector
from app.ingestion.dto import NormalizedOffer
from app.ingestion.pipeline import IngestionPipeline, IngestionReport
from app.ingestion.runner import IngestionRunner
from app.ingestion.service import CatalogIngestionService, IngestionOutcome
from app.ingestion.validation import OfferValidationError, OfferValidator
from app.models.catalog import (
    Category,
    IngestionRun,
    PriceHistory,
    Product,
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
    for model in (PriceHistory, StoreOffer, IngestionRun, Product, Store, Category):
        db.query(model).delete()
    db.commit()


# ── Mock connector ────────────────────────────────────────────────


class RobustMockConnector(StoreConnector):
    store_name = "Robust Mock"
    store_domain = "robust.mock"
    source_name = "mock:robust.mock"

    def __init__(self, records=None):
        self._records = records or []

    def extract(self):
        yield from self._records

    def normalize(self, record):
        now = datetime.now(timezone.utc)
        return NormalizedOffer(
            source=self.source_name,
            external_id=record.get("external_id"),
            product_url=record.get("url", "https://robust.mock/p"),
            name=record.get("name", "Product"),
            brand=record.get("brand"),
            model=record.get("model"),
            mpn=record.get("mpn"),
            gtin=record.get("gtin"),
            sku=record.get("sku"),
            price=Decimal(str(record.get("price", 1000))),
            previous_price=Decimal(str(record["previous_price"])) if record.get("previous_price") is not None else None,
            currency=record.get("currency", "CLP"),
            availability=record.get("availability", True),
            stock=record.get("stock", "in_stock"),
            image_url=None,
            category=record.get("category"),
            scraped_at=record.get("scraped_at", now),
        )


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
                previous_price=Decimal(str(record["previous_price"])) if record.get("previous_price") is not None else None,
                currency=record.get("currency", "CLP"),
                availability=record.get("availability", True),
                stock=record.get("stock", "in_stock"),
                image_url=None,
                category=record.get("category"),
                scraped_at=record.get("scraped_at", now),
            )

    return _Conn(records)


# ══════════════════════════════════════════════════════════════════
#  A) FIRST OFFER
# ══════════════════════════════════════════════════════════════════


class TestFirstOffer:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_first_offer_creates_product_offer_history(self):
        records = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "Notebook HP", "brand": "HP", "mpn": "HP-001", "price": 500000}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(RobustMockConnector(records))

            assert report.offers_created == 1
            assert db.query(Product).count() == 1
            assert db.query(StoreOffer).count() == 1
            assert db.query(PriceHistory).count() == 1

            offer = db.query(StoreOffer).one()
            assert offer.price == 500000
            assert offer.url == "https://robust.mock/p1"
            assert offer.external_id == "E001"
            assert offer.currency == "CLP"

            ph = db.query(PriceHistory).one()
            assert ph.price == 500000
            assert ph.currency == "CLP"


# ══════════════════════════════════════════════════════════════════
#  B) SECOND IDENTICAL INGESTION
# ══════════════════════════════════════════════════════════════════


class TestIdempotentIngestion:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_same_data_no_duplicates(self):
        records = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "Notebook HP", "brand": "HP", "mpn": "HP-001", "price": 500000}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records))

            p1 = db.query(Product).count()
            o1 = db.query(StoreOffer).count()
            h1 = db.query(PriceHistory).count()

            report2 = IngestionPipeline(service).run(RobustMockConnector(records))

            assert db.query(Product).count() == p1
            assert db.query(StoreOffer).count() == o1
            assert db.query(PriceHistory).count() == h1
            assert report2.offers_created == 0
            assert report2.offers_updated == 1
            assert report2.outcomes[0].price_changed is False
            assert report2.outcomes[0].is_new is False


# ══════════════════════════════════════════════════════════════════
#  C) PRICE CHANGE
# ══════════════════════════════════════════════════════════════════


class TestPriceChange:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_price_change_creates_history(self):
        records_v1 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "Notebook HP", "brand": "HP", "mpn": "HP-001", "price": 500000}]
        records_v2 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "Notebook HP", "brand": "HP", "mpn": "HP-001", "price": 450000}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records_v1))

            h1 = db.query(PriceHistory).count()
            report2 = IngestionPipeline(service).run(RobustMockConnector(records_v2))

            assert report2.outcomes[0].price_changed is True
            assert report2.price_changes == 1
            assert db.query(PriceHistory).count() == h1 + 1

            offer = db.query(StoreOffer).filter_by(external_id="E001").one()
            assert offer.price == 450000

            ph_last = db.query(PriceHistory).order_by(PriceHistory.id.desc()).first()
            assert ph_last.price == 450000


# ══════════════════════════════════════════════════════════════════
#  D) PRICE RETURNS TO PREVIOUS VALUE
# ══════════════════════════════════════════════════════════════════


class TestPriceReturns:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_price_sequence_preserved(self):
        records_v1 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 100}]
        records_v2 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 90}]
        records_v3 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 100}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records_v1))
            IngestionPipeline(service).run(RobustMockConnector(records_v2))
            IngestionPipeline(service).run(RobustMockConnector(records_v3))

            history = db.query(PriceHistory).order_by(PriceHistory.observed_at.asc()).all()
            assert len(history) == 3
            assert [h.price for h in history] == [100, 90, 100]


# ══════════════════════════════════════════════════════════════════
#  E) STOCK CHANGE WITHOUT PRICE CHANGE
# ══════════════════════════════════════════════════════════════════


class TestStockChangeNoPriceChange:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_stock_change_no_price_history(self):
        records_v1 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500, "stock": "in_stock", "availability": True}]
        records_v2 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500, "stock": "out_of_stock", "availability": False}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records_v1))
            h1 = db.query(PriceHistory).count()

            report = IngestionPipeline(service).run(RobustMockConnector(records_v2))

            assert db.query(PriceHistory).count() == h1
            assert report.price_changes == 0
            assert report.outcomes[0].price_changed is False

            offer = db.query(StoreOffer).filter_by(external_id="E001").one()
            assert offer.stock_status == "out_of_stock"
            assert offer.availability is False


# ══════════════════════════════════════════════════════════════════
#  F) URL CHANGES
# ══════════════════════════════════════════════════════════════════


class TestURLChange:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_url_update_no_price_history(self):
        records_v1 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500}]
        records_v2 = [{"url": "https://robust.mock/p1-new", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records_v1))
            h1 = db.query(PriceHistory).count()

            IngestionPipeline(service).run(RobustMockConnector(records_v2))

            assert db.query(PriceHistory).count() == h1
            offer = db.query(StoreOffer).filter_by(external_id="E001").one()
            assert offer.url == "https://robust.mock/p1-new"


# ══════════════════════════════════════════════════════════════════
#  G) SELLER CHANGES
# ══════════════════════════════════════════════════════════════════


class TestSellerChange:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_seller_update_no_price_history(self):
        records_v1 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500}]
        records_v2 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500, "seller": "Seller B"}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records_v1))
            h1 = db.query(PriceHistory).count()

            IngestionPipeline(service).run(RobustMockConnector(records_v2))

            assert db.query(PriceHistory).count() == h1


# ══════════════════════════════════════════════════════════════════
#  H) CURRENCY CONFLICT (invalid currency rejected)
# ══════════════════════════════════════════════════════════════════


class TestCurrencyValidation:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_invalid_currency_rejected(self):
        records = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500, "currency": "CL"}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(RobustMockConnector(records))

            assert report.validation_errors == 1
            assert report.offers_created == 0

    def test_valid_currency_accepted(self):
        records = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500, "currency": "USD"}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(RobustMockConnector(records))

            assert report.validation_errors == 0
            assert report.offers_created == 1

    def test_currency_case_insensitive(self):
        records = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500, "currency": "clp"}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(RobustMockConnector(records))

            assert report.offers_created == 1
            offer = db.query(StoreOffer).one()
            assert offer.currency == "CLP"


# ══════════════════════════════════════════════════════════════════
#  I) INVALID PRICES
# ══════════════════════════════════════════════════════════════════


class TestInvalidPrices:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_negative_price_rejected(self):
        records = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": -100}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(RobustMockConnector(records))

            assert report.validation_errors == 1
            assert report.offers_created == 0

    def test_zero_price_rejected(self):
        records = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 0}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(RobustMockConnector(records))

            assert report.validation_errors == 1
            assert report.offers_created == 0


# ══════════════════════════════════════════════════════════════════
#  J) PRODUCT EXISTENT (matched by MPN)
# ══════════════════════════════════════════════════════════════════


class TestExistingProductMatch:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_same_mpn_matches_existing_product(self):
        records_a = [{"url": "https://a.mock/p1", "external_id": "A001", "name": "Notebook HP Pavilion", "brand": "HP", "mpn": "HP-001", "price": 500000}]
        records_b = [{"url": "https://b.mock/p1", "external_id": "B001", "name": "HP Pavilion 15", "brand": "HP", "mpn": "HP-001", "price": 520000}]

        conn_a = _make_connector("Store A", "a.mock", records_a)
        conn_b = _make_connector("Store B", "b.mock", records_b)

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(conn_a)
            IngestionPipeline(service).run(conn_b)

            assert db.query(Product).count() == 1
            assert db.query(StoreOffer).count() == 2


# ══════════════════════════════════════════════════════════════════
#  K) NEW PRODUCT
# ══════════════════════════════════════════════════════════════════


class TestNewProduct:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_different_mpn_creates_new_product(self):
        records_a = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "Notebook HP", "brand": "HP", "mpn": "HP-001", "price": 500000}]
        records_b = [{"url": "https://robust.mock/p2", "external_id": "E002", "name": "Monitor Dell", "brand": "Dell", "mpn": "DEL-001", "price": 200000}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records_a + records_b))

            assert db.query(Product).count() == 2
            assert db.query(StoreOffer).count() == 2


# ══════════════════════════════════════════════════════════════════
#  L) MULTIPLE STORES SAME PRODUCT
# ══════════════════════════════════════════════════════════════════


class TestMultipleStoresSameProduct:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_two_stores_one_product(self):
        conn_a = _make_connector("Store A", "a.mock", [{"url": "https://a.mock/p1", "external_id": "A001", "name": "HP Laptop", "brand": "HP", "mpn": "HP-001", "price": 500000}])
        conn_b = _make_connector("Store B", "b.mock", [{"url": "https://b.mock/p1", "external_id": "B001", "name": "HP Laptop", "brand": "HP", "mpn": "HP-001", "price": 520000}])

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(conn_a)
            IngestionPipeline(service).run(conn_b)

            product = db.query(Product).one()
            assert product.lowest_price == 500000
            assert db.query(StoreOffer).count() == 2


# ══════════════════════════════════════════════════════════════════
#  M) MULTIPLE OFFERS SAME STORE (different URLs)
# ══════════════════════════════════════════════════════════════════


class TestMultipleOffersSameStore:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_different_urls_different_offers(self):
        records = [
            {"url": "https://robust.mock/seller-a/p1", "external_id": "SA001", "name": "HP Laptop", "brand": "HP", "mpn": "HP-001", "price": 500000},
            {"url": "https://robust.mock/seller-b/p1", "external_id": "SB001", "name": "HP Laptop", "brand": "HP", "mpn": "HP-001", "price": 520000},
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records))

            assert db.query(Product).count() == 1
            assert db.query(StoreOffer).count() == 2


# ══════════════════════════════════════════════════════════════════
#  N) DB TRANSACTION ROLLBACK
# ══════════════════════════════════════════════════════════════════


class TestTransactionRollback:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_individual_offer_error_does_not_affect_others(self):
        records = [
            {"url": "https://robust.mock/p1", "external_id": "E001", "name": "Good", "brand": "HP", "mpn": "HP-001", "price": 500},
            {"url": "https://robust.mock/p2", "external_id": "E002", "name": "", "brand": "HP", "mpn": "HP-002", "price": 600},
            {"url": "https://robust.mock/p3", "external_id": "E003", "name": "Also Good", "brand": "Dell", "mpn": "DEL-001", "price": 700},
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(RobustMockConnector(records))

            assert report.offers_created == 2
            assert report.validation_errors == 1
            assert db.query(StoreOffer).count() == 2


# ══════════════════════════════════════════════════════════════════
#  O) UNIQUE CONSTRAINT CONFLICT
# ══════════════════════════════════════════════════════════════════


class TestUniqueConstraint:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_same_external_id_same_store_idempotent(self):
        records = [
            {"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500},
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records))
            report2 = IngestionPipeline(service).run(RobustMockConnector(records))

            assert report2.offers_updated == 1
            assert db.query(StoreOffer).count() == 1


# ══════════════════════════════════════════════════════════════════
#  P) CONCURRENT INGESTION SIMULATION
# ══════════════════════════════════════════════════════════════════


class TestConcurrentIngestion:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_sequential_runs_same_data_no_duplicates(self):
        records = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            for _ in range(5):
                IngestionPipeline(service).run(RobustMockConnector(records))

            assert db.query(Product).count() == 1
            assert db.query(StoreOffer).count() == 1
            assert db.query(PriceHistory).count() == 1


# ══════════════════════════════════════════════════════════════════
#  Q) INGESTION REPORT CORRECTNESS
# ══════════════════════════════════════════════════════════════════


class TestIngestionReport:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_report_fields_correct_after_first_run(self):
        records = [
            {"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500},
            {"url": "https://robust.mock/p2", "external_id": "E002", "name": "P2", "brand": "Dell", "mpn": "DEL-001", "price": 600},
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(RobustMockConnector(records))

            assert report.urls_processed == 2
            assert report.offers_created == 2
            assert report.offers_updated == 0
            assert report.price_changes == 0
            assert report.extraction_errors == 0
            assert report.validation_errors == 0
            assert len(report.outcomes) == 2
            assert all(o.is_new for o in report.outcomes)

    def test_report_fields_correct_after_price_change(self):
        records_v1 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500}]
        records_v2 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 600}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records_v1))
            report = IngestionPipeline(service).run(RobustMockConnector(records_v2))

            assert report.offers_created == 0
            assert report.offers_updated == 1
            assert report.price_changes == 1
            assert report.outcomes[0].is_new is False
            assert report.outcomes[0].price_changed is True

    def test_report_counts_validation_errors_separately(self):
        records = [
            {"url": "https://robust.mock/p1", "external_id": "E001", "name": "Good", "brand": "HP", "mpn": "HP-001", "price": 500},
            {"url": "https://robust.mock/p2", "external_id": "E002", "name": "", "brand": "HP", "mpn": "HP-002", "price": 600},
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(RobustMockConnector(records))

            assert report.validation_errors == 1
            assert report.extraction_errors == 0
            assert report.offers_created == 1


# ══════════════════════════════════════════════════════════════════
#  R) INGESTION RUN CORRECTNESS
# ══════════════════════════════════════════════════════════════════


class TestIngestionRun:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_runner_persists_correct_metrics(self):
        records = [
            {"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 50000},
        ]

        with TestSession() as db:
            runner = IngestionRunner()
            run = runner.run(db, RobustMockConnector(records), urls=["https://robust.mock/p1"])

            assert run.status == "success"
            assert run.urls_total == 1
            assert run.urls_processed == 1
            assert run.duration_ms >= 0
            assert run.finished_at is not None

    def test_runner_records_price_changes(self):
        records_v1 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 50000}]
        records_v2 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 60000}]

        with TestSession() as db:
            runner = IngestionRunner()
            run1 = runner.run(db, RobustMockConnector(records_v1), urls=["https://robust.mock/p1"])
            assert run1.price_changes == 0

            run2 = runner.run(db, RobustMockConnector(records_v2), urls=["https://robust.mock/p1"])
            assert run2.price_changes == 1


# ══════════════════════════════════════════════════════════════════
#  S) _find_offer FALLBACK
# ══════════════════════════════════════════════════════════════════


class TestFindOfferFallback:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_find_offer_falls_back_to_url(self):
        """Offer created by URL (no external_id), then found by external_id on re-ingestion."""
        records_v1 = [{"url": "https://robust.mock/p1", "external_id": None, "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500}]
        records_v2 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records_v1))

            assert db.query(StoreOffer).count() == 1

            report2 = IngestionPipeline(service).run(RobustMockConnector(records_v2))

            assert db.query(StoreOffer).count() == 1
            assert report2.offers_updated == 1
            offer = db.query(StoreOffer).one()
            assert offer.external_id == "E001"

    def test_find_offer_falls_back_to_url_when_external_id_not_found(self):
        """external_id doesn't match any offer, falls back to URL match."""
        records_v1 = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500}]
        records_v2 = [{"url": "https://robust.mock/p1", "external_id": "E002", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 600}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records_v1))
            report2 = IngestionPipeline(service).run(RobustMockConnector(records_v2))

            assert db.query(StoreOffer).count() == 1
            assert report2.outcomes[0].price_changed is True
            offer = db.query(StoreOffer).one()
            assert offer.external_id == "E002"


# ══════════════════════════════════════════════════════════════════
#  T) URL CONFLICT GUARD
# ══════════════════════════════════════════════════════════════════


class TestURLConflictGuard:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_url_change_conflict_keeps_old_url(self):
        """If URL change would conflict with another offer, keep old URL."""
        records_a = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500}]
        records_b = [{"url": "https://robust.mock/p2", "external_id": "E002", "name": "P2", "brand": "Dell", "mpn": "DEL-001", "price": 600}]
        records_a_new_url = [{"url": "https://robust.mock/p2", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records_a))
            IngestionPipeline(service).run(RobustMockConnector(records_b))

            offer_a = db.query(StoreOffer).filter_by(external_id="E001").one()
            assert offer_a.url == "https://robust.mock/p1"

            IngestionPipeline(service).run(RobustMockConnector(records_a_new_url))

            offer_a = db.query(StoreOffer).filter_by(external_id="E001").one()
            assert offer_a.url == "https://robust.mock/p1"


# ══════════════════════════════════════════════════════════════════
#  U) PRICE HISTORY TEMPORAL SEQUENCE
# ══════════════════════════════════════════════════════════════════


class TestPriceHistorySequence:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_temporal_order_preserved(self):
        now = datetime.now(timezone.utc)
        from datetime import timedelta

        runs = [
            [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 100, "scraped_at": now}],
            [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 90, "scraped_at": now + timedelta(hours=1)}],
            [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 95, "scraped_at": now + timedelta(hours=2)}],
            [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 100, "scraped_at": now + timedelta(hours=3)}],
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            for batch in runs:
                IngestionPipeline(service).run(RobustMockConnector(batch))

            history = db.query(PriceHistory).order_by(PriceHistory.observed_at.asc()).all()
            assert len(history) == 4
            assert [h.price for h in history] == [100, 90, 95, 100]
            assert [h.observed_at for h in history] == sorted([h.observed_at for h in history])


# ══════════════════════════════════════════════════════════════════
#  V) ORIGINAL PRICE TRACKING
# ══════════════════════════════════════════════════════════════════


class TestOriginalPrice:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_original_price_stored_on_offer(self):
        records = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500, "previous_price": 600}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records))

            offer = db.query(StoreOffer).one()
            assert offer.price == 500
            assert offer.original_price == 600

    def test_original_price_none_when_absent(self):
        records = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records))

            offer = db.query(StoreOffer).one()
            assert offer.original_price is None

    def test_original_price_recorded_in_price_history(self):
        records = [{"url": "https://robust.mock/p1", "external_id": "E001", "name": "P1", "brand": "HP", "mpn": "HP-001", "price": 500, "previous_price": 600}]

        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(RobustMockConnector(records))

            ph = db.query(PriceHistory).one()
            assert ph.price == 500
            assert ph.original_price == 600
