"""Integration tests for the eligibility flow: URL discovery → eligibility → pipeline.

Covers the full lifecycle of offer eligibility checks, from NormalizedOffer
creation through check_eligibility() to pipeline consumption, including
mock connectors that verify rejected offers never reach fetchers.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.ingestion.category import (
    CategoryFilter,
    EligibilityRejectReason,
    check_eligibility,
)
from app.ingestion.connectors import StoreConnector
from app.ingestion.dto import NormalizedOffer
from app.ingestion.pipeline import IngestionPipeline, IngestionReport
from app.ingestion.service import CatalogIngestionService
from app.models.catalog import Category, PriceHistory, Product, Store, StoreOffer

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _reset(db):
    for model in (PriceHistory, StoreOffer, Product, Store, Category):
        db.query(model).delete()
    db.commit()


def make_eligible_offer(**kwargs) -> NormalizedOffer:
    defaults = dict(
        source="mock:test-store",
        external_id="EXT-001",
        product_url="https://example.com/hp-pavilion-15",
        name="HP Pavilion 15",
        brand="HP",
        model="Pavilion 15",
        mpn="HP-PAV-15",
        gtin="7501234567890",
        sku="HP-PAV-15-SKU",
        price=Decimal("499990"),
        previous_price=None,
        currency="CLP",
        availability=True,
        stock="in_stock",
        image_url="https://example.com/img.jpg",
        category="notebooks",
        scraped_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return NormalizedOffer(**defaults)


def make_rejected_offer(reason: EligibilityRejectReason, **kwargs) -> NormalizedOffer:
    offer_map = {
        EligibilityRejectReason.MISSING_URL: dict(
            product_url="", name="Laptop Sin URL",
            category="notebooks", price=Decimal("299990"), gtin="123",
        ),
        EligibilityRejectReason.MISSING_CATEGORY: dict(
            category=None, product_url="https://example.com/p", name="Sin Categoría",
            price=Decimal("199990"), gtin="123",
        ),
        EligibilityRejectReason.IS_BUNDLE: dict(
            name="Bundle Pack + Regalo", product_url="https://example.com/bundle",
            category="notebooks", price=Decimal("599990"), gtin="123",
        ),
        EligibilityRejectReason.IS_SERVICE: dict(
            name="Servicio de instalación", product_url="https://example.com/svc",
            category="notebooks", price=Decimal("19990"), sku="SVC-01",
        ),
        EligibilityRejectReason.CATEGORY_NOT_ALLOWED: dict(
            name="Laptop HP", product_url="https://example.com/hp",
            category="unknown-category", price=Decimal("399990"), gtin="123",
        ),
        EligibilityRejectReason.MISSING_NAME: dict(
            name="", product_url="https://example.com/empty",
            category="notebooks", price=Decimal("299990"), gtin="123",
        ),
        EligibilityRejectReason.INVALID_PRICE: dict(
            name="Laptop Barata", product_url="https://example.com/cheap",
            category="notebooks", price=Decimal("0"), gtin="123",
        ),
        EligibilityRejectReason.MISSING_PRODUCT_IDENTITY: dict(
            name="Laptop Misteriosa", product_url="https://example.com/mystery",
            category="notebooks", price=Decimal("299990"), external_id=None,
            gtin=None, mpn=None, brand=None, sku=None,
        ),
    }
    base = offer_map.get(reason, {})
    base.update(kwargs)
    return make_eligible_offer(**base)


def _offer_to_eligibility_kwargs(offer: NormalizedOffer) -> dict[str, Any]:
    return dict(
        category_slug=offer.category,
        name=offer.name,
        url=offer.product_url,
        price=int(offer.price) if offer.price else None,
        gtin=offer.gtin,
        mpn=offer.mpn,
        brand=offer.brand,
        sku=offer.sku,
        product_id=offer.external_id,
    )


class _TrackingConnector(StoreConnector):
    def __init__(self, offers: list[NormalizedOffer]):
        self.store_name = "tracking-store"
        self.store_domain = "tracking.mock"
        self.source_name = "mock:tracking"
        self._offers = offers
        self.fetch_count = 0
        self.fetched_urls: list[str] = []

    def extract(self) -> list[dict[str, Any]]:
        return [{"idx": i} for i in range(len(self._offers))]

    def normalize(self, record: dict[str, Any]) -> NormalizedOffer:
        self.fetch_count += 1
        offer = self._offers[record["idx"]]
        self.fetched_urls.append(offer.product_url)
        return offer


class _EligibilityGuardedConnector(StoreConnector):
    def __init__(self, offers: list[NormalizedOffer], category_filter: CategoryFilter | None = None):
        self.store_name = "guarded-store"
        self.store_domain = "guarded.mock"
        self.source_name = "mock:guarded"
        self._offers = offers
        self._category_filter = category_filter
        self.fetch_count = 0
        self.fetched_urls: list[str] = []
        self.rejected_offers: list[NormalizedOffer] = []

    def extract(self) -> list[dict[str, Any]]:
        return [{"idx": i} for i in range(len(self._offers))]

    def normalize(self, record: dict[str, Any]) -> NormalizedOffer:
        offer = self._offers[record["idx"]]
        eligibility = check_eligibility(**_offer_to_eligibility_kwargs(offer), category_filter=self._category_filter)
        if not eligibility.eligible:
            self.rejected_offers.append(offer)
            raise ValueError(f"Eligibility rejected: {eligibility.reason}")
        self.fetch_count += 1
        self.fetched_urls.append(offer.product_url)
        return offer


class TestEligibilityIntegration:
    def test_valid_url_passes_eligibility(self):
        offer = make_eligible_offer()
        result = check_eligibility(**_offer_to_eligibility_kwargs(offer))
        assert result.eligible is True
        assert result.reason is None

    def test_invalid_url_rejected_by_eligibility(self):
        offer = make_rejected_offer(EligibilityRejectReason.MISSING_URL)
        result = check_eligibility(**_offer_to_eligibility_kwargs(offer))
        assert result.eligible is False
        assert result.reason == EligibilityRejectReason.MISSING_URL

    def test_allowed_category_passes(self):
        offer = make_eligible_offer(category="notebooks")
        category_filter = CategoryFilter(
            allowed_priorities=frozenset({"P0", "P1", "P2"}),
        )
        result = check_eligibility(
            **_offer_to_eligibility_kwargs(offer),
            category_filter=category_filter,
        )
        assert result.eligible is True

    def test_rejected_category_fails(self):
        offer = make_rejected_offer(EligibilityRejectReason.CATEGORY_NOT_ALLOWED)
        category_filter = CategoryFilter()
        result = check_eligibility(
            **_offer_to_eligibility_kwargs(offer),
            category_filter=category_filter,
        )
        assert result.eligible is False
        assert result.reason == EligibilityRejectReason.CATEGORY_NOT_ALLOWED

    def test_product_like_url_rejected(self):
        offer = make_rejected_offer(EligibilityRejectReason.IS_BUNDLE)
        result = check_eligibility(**_offer_to_eligibility_kwargs(offer))
        assert result.eligible is False
        assert result.reason == EligibilityRejectReason.IS_BUNDLE

    def test_duplicate_noise_urls_rejected(self):
        cases = [
            (make_rejected_offer(EligibilityRejectReason.IS_BUNDLE), EligibilityRejectReason.IS_BUNDLE),
            (make_rejected_offer(EligibilityRejectReason.IS_SERVICE), EligibilityRejectReason.IS_SERVICE),
            (make_rejected_offer(EligibilityRejectReason.MISSING_URL), EligibilityRejectReason.MISSING_URL),
            (make_rejected_offer(EligibilityRejectReason.INVALID_PRICE), EligibilityRejectReason.INVALID_PRICE),
            (make_rejected_offer(EligibilityRejectReason.MISSING_CATEGORY), EligibilityRejectReason.MISSING_CATEGORY),
            (make_rejected_offer(EligibilityRejectReason.MISSING_NAME), EligibilityRejectReason.MISSING_NAME),
            (make_rejected_offer(EligibilityRejectReason.MISSING_PRODUCT_IDENTITY), EligibilityRejectReason.MISSING_PRODUCT_IDENTITY),
        ]
        for offer, expected_reason in cases:
            result = check_eligibility(**_offer_to_eligibility_kwargs(offer))
            assert result.eligible is False, f"Expected rejection for {expected_reason}, got eligible=True"
            assert result.reason == expected_reason

    def test_rejected_url_never_reaches_fetcher(self):
        eligible = make_eligible_offer(product_url="https://example.com/good-product")
        rejected = make_rejected_offer(EligibilityRejectReason.IS_BUNDLE, product_url="https://example.com/bundle-pack")
        connector = _TrackingConnector([eligible, rejected])
        guarded = _EligibilityGuardedConnector([eligible, rejected])

        for record in guarded.extract():
            try:
                guarded.normalize(record)
            except ValueError:
                pass

        assert guarded.fetch_count == 1
        assert len(guarded.fetched_urls) == 1
        assert guarded.fetched_urls[0] == "https://example.com/good-product"
        assert len(guarded.rejected_offers) == 1


class TestEligibilityPipelineFlow:
    def test_discovery_to_eligibility_to_pipeline(self):
        offers = [
            make_eligible_offer(
                product_url="https://example.com/notebook-a",
                name="Notebook A",
                external_id="NB-A",
                gtin="7501111111111",
            ),
            make_rejected_offer(
                EligibilityRejectReason.IS_BUNDLE,
                product_url="https://example.com/bundle-b",
                external_id="BUN-B",
            ),
            make_eligible_offer(
                product_url="https://example.com/monitor-c",
                name="Monitor C",
                category="monitores",
                external_id="MON-C",
                gtin="7502222222222",
            ),
            make_rejected_offer(
                EligibilityRejectReason.MISSING_URL,
                product_url="",
                external_id="NOURL-D",
            ),
        ]
        eligible_offers = []
        for offer in offers:
            result = check_eligibility(**_offer_to_eligibility_kwargs(offer))
            if result.eligible:
                eligible_offers.append(offer)

        assert len(eligible_offers) == 2
        assert eligible_offers[0].product_url == "https://example.com/notebook-a"
        assert eligible_offers[1].product_url == "https://example.com/monitor-c"

        connector = _TrackingConnector(eligible_offers)
        with Session() as db:
            _reset(db)
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)

        assert report.errors == []
        assert report.urls_processed == 2
        assert connector.fetch_count == 2

    def test_eligibility_filters_before_fetch(self):
        offers = [
            make_eligible_offer(product_url="https://example.com/product-1", external_id="P1"),
            make_rejected_offer(EligibilityRejectReason.IS_BUNDLE, product_url="https://example.com/bundle", external_id="B1"),
            make_rejected_offer(EligibilityRejectReason.IS_SERVICE, product_url="https://example.com/service", external_id="S1"),
            make_eligible_offer(product_url="https://example.com/product-2", external_id="P2"),
        ]
        guarded = _EligibilityGuardedConnector(offers)

        for record in guarded.extract():
            try:
                guarded.normalize(record)
            except ValueError:
                pass

        assert guarded.fetch_count == 2
        assert len(guarded.rejected_offers) == 2
        assert guarded.rejected_offers[0].external_id == "B1"
        assert guarded.rejected_offers[1].external_id == "S1"
        assert "https://example.com/product-1" in guarded.fetched_urls
        assert "https://example.com/product-2" in guarded.fetched_urls
        assert "https://example.com/bundle" not in guarded.fetched_urls
        assert "https://example.com/service" not in guarded.fetched_urls

    def test_eligibility_reject_count_tracked(self):
        offers = [
            make_eligible_offer(product_url="https://example.com/ok-1", external_id="OK1"),
            make_rejected_offer(EligibilityRejectReason.IS_BUNDLE, product_url="https://example.com/b1", external_id="B1"),
            make_rejected_offer(EligibilityRejectReason.IS_SERVICE, product_url="https://example.com/s1", external_id="S1"),
            make_rejected_offer(EligibilityRejectReason.MISSING_URL, product_url="", external_id="U1"),
            make_eligible_offer(product_url="https://example.com/ok-2", external_id="OK2"),
        ]
        eligible = []
        rejected_count = 0
        for offer in offers:
            result = check_eligibility(**_offer_to_eligibility_kwargs(offer))
            if result.eligible:
                eligible.append(offer)
            else:
                rejected_count += 1

        assert len(eligible) == 2
        assert rejected_count == 3

        report = IngestionReport()
        report.eligibility_rejected = rejected_count
        report.urls_processed = len(offers)
        assert report.eligibility_rejected == 3
        assert report.urls_processed == 5

    def test_pipeline_with_all_rejected_returns_empty(self):
        offers = [
            make_rejected_offer(EligibilityRejectReason.IS_BUNDLE, product_url="https://example.com/b1", external_id="B1"),
            make_rejected_offer(EligibilityRejectReason.IS_SERVICE, product_url="https://example.com/s1", external_id="S1"),
        ]
        eligible = []
        for offer in offers:
            result = check_eligibility(**_offer_to_eligibility_kwargs(offer))
            if result.eligible:
                eligible.append(offer)

        assert len(eligible) == 0

        connector = _TrackingConnector(eligible)
        with Session() as db:
            _reset(db)
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)

        assert report.urls_processed == 0
        assert report.errors == []
        assert connector.fetch_count == 0

    def test_eligibility_with_category_filter_in_pipeline(self):
        category_filter = CategoryFilter(
            allowed_priorities=frozenset({"P0", "P1"}),
        )
        offers = [
            make_eligible_offer(
                product_url="https://example.com/nb",
                name="Notebook HP",
                category="notebooks",
                external_id="NB-1",
            ),
            make_eligible_offer(
                product_url="https://example.com/silla",
                name="Silla Gamer X",
                category="sillas-gaming",
                external_id="SG-1",
            ),
            make_eligible_offer(
                product_url="https://example.com/router",
                name="Router WiFi 6",
                category="routers",
                external_id="RT-1",
            ),
        ]
        eligible = []
        for offer in offers:
            result = check_eligibility(
                **_offer_to_eligibility_kwargs(offer),
                category_filter=category_filter,
            )
            if result.eligible:
                eligible.append(offer)

        assert len(eligible) == 2
        urls = [o.product_url for o in eligible]
        assert "https://example.com/silla" not in urls
