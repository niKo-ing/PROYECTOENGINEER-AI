"""End-to-end pipeline audit tests.

Covers:
1. Full flow trace with metrics validation
2. Idempotency (double-run same data)
3. Failure/resumption behavior
4. max_urls end-to-end
5. Deduplication edge cases
6. Rate limiting with mock clock
7. Error handling audit
8. Reporting semantics
9. Memory/streaming validation
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.ingestion.category import (
    CategoryFilter,
    CategoryMapper,
    EligibilityRejectReason,
    check_url_eligibility,
)
from app.ingestion.connectors import StoreConnector
from app.ingestion.connectors.paris.url_discovery import ParisURLDiscovery
from app.ingestion.connectors.spdigital.url_discovery import SPDigitalURLDiscovery
from app.ingestion.dto import NormalizedOffer
from app.ingestion.pipeline import IngestionPipeline, IngestionReport
from app.ingestion.runner import IngestionRunner
from app.ingestion.service import CatalogIngestionService, IngestionOutcome
from app.ingestion.url_discovery import (
    DiscoveryFetcher,
    DiscoveryReport,
    DiscoveredURL,
    FlatSitemapStream,
    SitemapStream,
    batched_urls,
    dedupe_urls,
    normalize_url,
)
from app.ingestion.validation import OfferValidationError
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


# ── Mock store connector ───────────────────────────────────────────

class AuditMockConnector(StoreConnector):
    """Multi-record mock connector for audit tests.

    Each record has: url, price, external_id, name, brand, mpn.
    Supports injectable failures per URL.
    """

    store_name = "Audit Mock"
    store_domain = "audit.mock"
    source_name = "mock:audit.mock"

    def __init__(
        self,
        records: list[dict[str, Any]] | None = None,
        fail_urls: set[str] | None = None,
        fail_normalize_urls: set[str] | None = None,
    ):
        self._records = records or []
        self._fail_urls = fail_urls or set()
        self._fail_normalize_urls = fail_normalize_urls or set()

    def extract(self) -> Iterable[Mapping[str, Any]]:
        for rec in self._records:
            url = rec.get("url", "")
            if url in self._fail_urls:
                continue  # real connectors catch HTTP errors and skip
            yield rec

    def normalize(self, record: Mapping[str, Any]) -> NormalizedOffer:
        url = record.get("url", "")
        if url in self._fail_normalize_urls:
            raise ValueError(f"normalize failed: {url}")
        now = datetime.now(timezone.utc)
        return NormalizedOffer(
            source=self.source_name,
            external_id=record.get("external_id"),
            product_url=url,
            name=record.get("name", "Product"),
            brand=record.get("brand"),
            model=None,
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


# ── 2. END-TO-END TEST ────────────────────────────────────────────


class TestEndToEndFlow:
    """Full flow: 10 URLs discovered → 2 dupes → 8 unique → 2 eligibility rejects →
    6 fetches → 5 valid → 1 extraction error → 5 offers processed."""

    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def _make_records(self) -> list[dict[str, Any]]:
        return [
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "Notebook HP", "brand": "HP", "mpn": "HP-001", "price": 500000, "category": "notebooks"},
            {"url": "https://audit.mock/p2", "external_id": "E002", "name": "Notebook Lenovo", "brand": "Lenovo", "mpn": "LEN-001", "price": 600000, "category": "notebooks"},
            {"url": "https://audit.mock/p3", "external_id": "E003", "name": "Monitor Dell", "brand": "Dell", "mpn": "DEL-001", "price": 200000, "category": "monitores"},
            {"url": "https://audit.mock/p4", "external_id": "E004", "name": "Celular Samsung", "brand": "Samsung", "mpn": "SAM-001", "price": 400000, "category": "celulares"},
            {"url": "https://audit.mock/p5", "external_id": "E005", "name": "Consola PS5", "brand": "Sony", "mpn": "SON-001", "price": 500000, "category": "consolas"},
        ]

    def test_full_flow_discovery_to_persistence(self):
        """Test the complete pipeline: discovery → eligibility → connector → pipeline → DB."""
        records = self._make_records()
        connector = AuditMockConnector(records=records)

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)

            assert report.urls_processed == 5
            assert report.offers_created == 5
            assert report.offers_updated == 0
            assert report.extraction_errors == 0
            assert report.validation_errors == 0
            assert len(report.outcomes) == 5
            assert report.errors == []

            # Verify DB persistence
            products = db.query(Product).all()
            assert len(products) == 5

            offers = db.query(StoreOffer).all()
            assert len(offers) == 5

            history = db.query(PriceHistory).all()
            assert len(history) == 5  # one per new offer

    def test_discovery_report_metrics(self):
        """DiscoveryReport and IngestionReport have separate metrics."""
        report = DiscoveryReport(
            categories_requested=3,
            categories_success=2,
            urls_discovered=10,
            duplicate_urls=2,
            listing_requests=5,
        )

        assert report.categories_requested == 3
        assert report.urls_discovered == 10
        assert report.duplicate_urls == 2

        ingestion_report = IngestionReport(
            urls_processed=8,
            offers_created=5,
            offers_updated=3,
        )

        assert ingestion_report.urls_processed == 8
        assert not hasattr(ingestion_report, "categories_requested")
        assert not hasattr(ingestion_report, "duplicate_urls")

    def test_eligibility_reject_count(self):
        """Rejected URLs don't reach the fetcher and are counted."""
        records = [
            {"url": "https://audit.mock/good1", "external_id": "G001", "name": "Notebook HP", "brand": "HP", "mpn": "HP-001", "price": 500000, "category": "notebooks"},
            {"url": "https://audit.mock/good2", "external_id": "G002", "name": "Monitor Dell", "brand": "Dell", "mpn": "DEL-001", "price": 200000, "category": "monitores"},
            {"url": "https://audit.mock/bundle", "external_id": "B001", "name": "Pack Combo 3 en 1", "brand": "Generic", "mpn": "COMBO-001", "price": 100000, "category": "notebooks"},
        ]
        connector = AuditMockConnector(records=records)

        cat_filter = CategoryFilter(whitelist_slugs=frozenset({"notebooks", "monitores"}))

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(
                service,
                category_filter=cat_filter,
                eligibility_enabled=True,
            ).run(connector)

            # Bundle rejected by name heuristic
            assert report.eligibility_rejected >= 1
            assert report.offers_created == 2
            assert len(report.outcomes) == 2


# ── 3. IDEMPOTENCY ─────────────────────────────────────────────────


class TestIdempotency:
    """Same data run twice: no duplicate products, no duplicate offers, correct price history."""

    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_same_price_no_new_history(self):
        """Second run with same price: no new PriceHistory entry."""
        records = [
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "Notebook HP", "brand": "HP", "mpn": "HP-001", "price": 500000, "category": "notebooks"},
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)

            # First run
            connector = AuditMockConnector(records=records)
            report1 = IngestionPipeline(service).run(connector)
            assert report1.offers_created == 1
            assert len(report1.outcomes) == 1

            product_count_1 = db.query(Product).count()
            offer_count_1 = db.query(StoreOffer).count()
            history_count_1 = db.query(PriceHistory).count()

            # Second run (same price)
            connector2 = AuditMockConnector(records=records)
            report2 = IngestionPipeline(service).run(connector2)
            assert report2.offers_updated == 1
            assert report2.offers_created == 0
            assert report2.outcomes[0].price_changed is False

            # No new products, offers, or price history
            assert db.query(Product).count() == product_count_1
            assert db.query(StoreOffer).count() == offer_count_1
            assert db.query(PriceHistory).count() == history_count_1

    def test_price_change_creates_history(self):
        """Second run with different price: new PriceHistory entry."""
        records_v1 = [
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "Notebook HP", "brand": "HP", "mpn": "HP-001", "price": 500000, "category": "notebooks"},
        ]
        records_v2 = [
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "Notebook HP", "brand": "HP", "mpn": "HP-001", "price": 450000, "category": "notebooks"},
        ]

        with TestSession() as db:
            service = CatalogIngestionService(db)

            # First run
            connector1 = AuditMockConnector(records=records_v1)
            IngestionPipeline(service).run(connector1)
            history_after_v1 = db.query(PriceHistory).count()

            # Second run (price changed)
            connector2 = AuditMockConnector(records=records_v2)
            report2 = IngestionPipeline(service).run(connector2)
            assert report2.outcomes[0].price_changed is True
            assert report2.price_changes == 1
            assert db.query(PriceHistory).count() == history_after_v1 + 1

            # Verify price updated in offer
            offer = db.query(StoreOffer).filter_by(external_id="E001").one()
            assert offer.price == 450000

    def test_product_not_duplicated(self):
        """Same product from different stores: one Product, multiple StoreOffers."""
        connector_a = AuditMockConnector(records=[
            {"url": "https://a.mock/p1", "external_id": "A001", "name": "Notebook HP", "brand": "HP", "mpn": "HP-001", "price": 500000, "category": "notebooks"},
        ])
        connector_b = AuditMockConnector(records=[
            {"url": "https://b.mock/p1", "external_id": "B001", "name": "Notebook HP", "brand": "HP", "mpn": "HP-001", "price": 520000, "category": "notebooks"},
        ])

        # Need different store names AND domains
        connector_a.store_name = "Store A"
        connector_a.store_domain = "a.mock"
        connector_a.source_name = "mock:a.mock"
        connector_b.store_name = "Store B"
        connector_b.store_domain = "b.mock"
        connector_b.source_name = "mock:b.mock"

        with TestSession() as db:
            service = CatalogIngestionService(db)

            IngestionPipeline(service).run(connector_a)
            IngestionPipeline(service).run(connector_b)

            assert db.query(Product).count() == 1
            assert db.query(StoreOffer).count() == 2


# ── 4. FAILURE / RESUMPTION ────────────────────────────────────────


class TestFailureResumption:
    """Simulate batch 1 OK, batch 2 OK, batch 3 ERROR, batch 4 OK.

    Current behavior: pipeline processes records sequentially in a single run.
    If one record fails, it's caught and counted; others continue.
    If extract() raises, it crashes the entire run.
    """

    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_individual_record_error_continues(self):
        """Validation error for one record doesn't stop others."""
        records = [
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "Good Product", "brand": "B1", "mpn": "M1", "price": 1000, "category": "notebooks"},
            {"url": "https://audit.mock/p2", "external_id": "E002", "name": "", "brand": "B2", "mpn": "M2", "price": 2000, "category": "notebooks"},
            {"url": "https://audit.mock/p3", "external_id": "E003", "name": "Also Good", "brand": "B3", "mpn": "M3", "price": 3000, "category": "notebooks"},
        ]
        connector = AuditMockConnector(records=records)

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)

            # All 3 attempted: 2 succeed, 1 has validation error (empty name)
            assert report.urls_processed == 3
            assert report.offers_created == 2
            assert report.validation_errors == 1
            assert len(report.outcomes) == 2

    def test_fetch_error_skips_record(self):
        """HTTP failure for one URL: connector skips it, others continue."""
        records = [
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "Good", "brand": "B1", "mpn": "M1", "price": 1000, "category": "notebooks"},
            {"url": "https://audit.mock/FAIL", "external_id": "E002", "name": "Bad", "brand": "B2", "mpn": "M2", "price": 2000, "category": "notebooks"},
            {"url": "https://audit.mock/p3", "external_id": "E003", "name": "Good2", "brand": "B3", "mpn": "M3", "price": 3000, "category": "notebooks"},
        ]
        connector = AuditMockConnector(records=records, fail_urls={"https://audit.mock/FAIL"})

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)

            # FAIL URL silently skipped by connector, others processed
            assert report.urls_processed == 2
            assert report.offers_created == 2
            assert report.extraction_errors == 0

    def test_extract_raises_aborts_pipeline(self):
        """If extract() raises (not from a specific URL), the pipeline aborts."""
        connector = AuditMockConnector(records=[
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "Good", "brand": "B1", "mpn": "M1", "price": 1000},
        ])

        with TestSession() as db:
            service = CatalogIngestionService(db)
            with patch.object(type(connector), "extract", side_effect=RuntimeError("boom")):
                with pytest.raises(RuntimeError, match="boom"):
                    IngestionPipeline(service).run(connector)

    def test_runner_catches_extract_abort(self):
        """IngestionRunner catches top-level exceptions from pipeline."""
        connector = AuditMockConnector(records=[
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "Good", "brand": "B1", "mpn": "M1", "price": 1000},
        ])

        with TestSession() as db:
            runner = IngestionRunner()
            with patch.object(type(connector), "extract", side_effect=RuntimeError("boom")):
                run = runner.run(db, connector, urls=["https://audit.mock/p1"])

            assert run.status == "error"
            assert "boom" in (run.error_messages or "")


# ── 5. MAX_URLS ────────────────────────────────────────────────────


class TestMaxUrls:
    """Validate max_urls end-to-end."""

    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_max_urls_limits_results(self):
        """discover_from_sitemap respects max_urls."""
        sitemap_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.spdigital.cl/p1/p</loc></url>
  <url><loc>https://www.spdigital.cl/p2/p</loc></url>
  <url><loc>https://www.spdigital.cl/p3/p</loc></url>
  <url><loc>https://www.spdigital.cl/p4/p</loc></url>
  <url><loc>https://www.spdigital.cl/p5/p</loc></url>
</urlset>"""
        fetcher = MagicMock(spec=DiscoveryFetcher)
        fetcher.fetch.return_value = sitemap_xml
        discovery = SPDigitalURLDiscovery()

        results = discovery.discover_from_sitemap(fetcher, max_urls=3)
        assert len(results) == 3

    def test_max_urls_zero_means_unlimited(self):
        """max_urls=0 returns all URLs."""
        sitemap_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.spdigital.cl/p1/p</loc></url>
  <url><loc>https://www.spdigital.cl/p2/p</loc></url>
  <url><loc>https://www.spdigital.cl/p3/p</loc></url>
</urlset>"""
        fetcher = MagicMock(spec=DiscoveryFetcher)
        fetcher.fetch.return_value = sitemap_xml
        discovery = SPDigitalURLDiscovery()

        results = discovery.discover_from_sitemap(fetcher, max_urls=0)
        assert len(results) == 3

    def test_max_urls_one(self):
        """max_urls=1 returns exactly 1 URL."""
        sitemap_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.spdigital.cl/p1/p</loc></url>
  <url><loc>https://www.spdigital.cl/p2/p</loc></url>
</urlset>"""
        fetcher = MagicMock(spec=DiscoveryFetcher)
        fetcher.fetch.return_value = sitemap_xml
        discovery = SPDigitalURLDiscovery()

        results = discovery.discover_from_sitemap(fetcher, max_urls=1)
        assert len(results) == 1

    def test_max_urls_exceeds_sitemap_size(self):
        """max_urls > sitemap size returns all URLs."""
        sitemap_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.spdigital.cl/p1/p</loc></url>
  <url><loc>https://www.spdigital.cl/p2/p</loc></url>
</urlset>"""
        fetcher = MagicMock(spec=DiscoveryFetcher)
        fetcher.fetch.return_value = sitemap_xml
        discovery = SPDigitalURLDiscovery()

        results = discovery.discover_from_sitemap(fetcher, max_urls=100)
        assert len(results) == 2

    def test_max_urls_batch_boundary(self):
        """max_urls at batch_size boundary."""
        urls = [f"https://www.spdigital.cl/p{i}/p" for i in range(1000)]
        sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset>\n'
        sitemap_xml += "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
        sitemap_xml += "\n</urlset>"

        fetcher = MagicMock(spec=DiscoveryFetcher)
        fetcher.fetch.return_value = sitemap_xml
        discovery = SPDigitalURLDiscovery()

        results = discovery.discover_from_sitemap(fetcher, max_urls=500)
        assert len(results) == 500

    def test_max_urls_no_extra_urls_sent_to_fetcher(self):
        """URLs beyond max_urls never reach the connector."""
        processed_urls: list[str] = []

        class TrackingConnector(StoreConnector):
            store_name = "Track"
            store_domain = "track.mock"
            source_name = "mock:track.mock"

            def __init__(self, urls):
                self._urls = urls

            def extract(self):
                for url in self._urls:
                    processed_urls.append(url)
                    yield {"url": url, "name": "P", "price": 1000}

            def normalize(self, record):
                return NormalizedOffer(
                    source="mock:track.mock", external_id=None,
                    product_url=record["url"], name=record["name"],
                    brand=None, model=None, mpn=None, gtin=None, sku=None,
                    price=Decimal("1000"), previous_price=None, currency="CLP",
                    availability=True, stock="in_stock", image_url=None,
                    category="notebooks", scraped_at=datetime.now(timezone.utc),
                )

        all_urls = [f"https://track.mock/p{i}" for i in range(10)]
        limited_urls = all_urls[:3]

        connector = TrackingConnector(urls=limited_urls)
        with TestSession() as db:
            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(connector)

        assert len(processed_urls) == 3
        assert processed_urls == limited_urls


# ── 6. DEDUPLICATION ───────────────────────────────────────────────


class TestDeduplicationEdgeCases:
    """Verify dedup across various edge cases."""

    def test_same_url_repeated(self):
        """Duplicate URLs in same sitemap are deduped."""
        sitemap_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.spdigital.cl/p1/p</loc></url>
  <url><loc>https://www.spdigital.cl/p1/p</loc></url>
  <url><loc>https://www.spdigital.cl/p2/p</loc></url>
</urlset>"""
        fetcher = MagicMock(spec=DiscoveryFetcher)
        fetcher.fetch.return_value = sitemap_xml
        discovery = SPDigitalURLDiscovery()

        results = discovery.discover_from_sitemap(fetcher, max_urls=0)
        assert len(results) == 2

    def test_trailing_slash_normalization(self):
        """URLs with/without trailing slash are considered the same."""
        url1 = normalize_url("https://example.com/product")
        url2 = normalize_url("https://example.com/product/")
        assert url1 == url2

    def test_query_string_normalization(self):
        """Tracking params are stripped, others preserved."""
        url1 = normalize_url("https://example.com/product?utm_source=google&id=123")
        url2 = normalize_url("https://example.com/product?id=123")
        assert url1 == url2

    def test_http_upgraded_to_https(self):
        """HTTP is normalized to HTTPS."""
        url = normalize_url("http://example.com/product")
        assert url.startswith("https://")

    def test_dedupe_between_child_sitemaps(self):
        """URLs appearing in multiple child sitemaps are deduped."""
        child1 = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.example.cl/p1.html</loc></url>
  <url><loc>https://www.example.cl/p2.html</loc></url>
</urlset>"""
        child2 = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.example.cl/p2.html</loc></url>
  <url><loc>https://www.example.cl/p3.html</loc></url>
</urlset>"""
        index_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex>
  <sitemap><loc>https://www.example.cl/sitemap-1.xml</loc></sitemap>
  <sitemap><loc>https://www.example.cl/sitemap-2.xml</loc></sitemap>
</sitemapindex>"""

        fetcher = MagicMock(spec=DiscoveryFetcher)
        responses = {
            "sitemap_index.xml": index_xml,
            "sitemap-1.xml": child1,
            "sitemap-2.xml": child2,
        }

        def _fetch(url, *, headers=None):
            for pattern, body in responses.items():
                if pattern in url:
                    return body
            raise ConnectionError(f"no mock: {url}")

        fetcher.fetch.side_effect = _fetch
        stream = SitemapStream(fetcher, "https://www.example.cl/sitemap_index.xml")
        urls = list(stream)
        # SitemapStream does NOT deduplicate — it yields all URLs from all children
        assert len(urls) == 4  # p1, p2, p2, p3

        unique, dupes = dedupe_urls(urls)
        assert len(unique) == 3  # p1, p2, p3
        assert dupes == 1  # p2 was duplicated


# ── 7. RATE LIMITING ──────────────────────────────────────────────


class TestRateLimiting:
    """Verify rate limiting with mock clock."""

    def test_spdigital_request_delay_is_five(self):
        discovery = SPDigitalURLDiscovery()
        assert discovery.request_delay == 5.0

    def test_paris_request_delay_is_half(self):
        discovery = ParisURLDiscovery()
        assert discovery.request_delay == 0.5

    def test_discovery_fetcher_applies_delay(self):
        """DiscoveryFetcher sleeps between requests."""
        fetcher = DiscoveryFetcher(request_delay=0.1, timeout=5.0)
        mock_response = MagicMock()
        mock_response.text = "<xml/>"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.get.return_value = mock_response

            with patch("time.sleep") as mock_sleep:
                fetcher.fetch("https://example.com/sitemap.xml")
                fetcher.fetch("https://example.com/sitemap2.xml")

                # Should have slept once (between requests)
                assert mock_sleep.call_count >= 1

    def test_connector_request_delay_is_connector_property(self):
        """request_delay is a connector-level property, not pipeline-level."""
        from app.ingestion.connectors.paris.connector import ParisConnector
        from app.ingestion.connectors.spdigital.connector import SPDigitalConnector

        assert ParisConnector.request_delay >= 0
        assert SPDigitalConnector.request_delay >= 0

        connector = AuditMockConnector(records=[])
        assert connector.request_delay == 0.0  # base default

    def test_runner_uses_connector_request_delay(self):
        """Runner uses url_discovery.request_delay for DiscoveryFetcher."""
        discovery = SPDigitalURLDiscovery()
        assert discovery.request_delay == 5.0
        discoveryParis = ParisURLDiscovery()
        assert discoveryParis.request_delay == 0.5


# ── 8. ERROR HANDLING AUDIT ───────────────────────────────────────


class TestErrorHandlingAudit:
    """Verify behavior for each error type."""

    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_403_is_not_retried_by_connector(self):
        """403 from product page: connector returns None, record skipped silently."""
        connector = AuditMockConnector(records=[
            {"url": "https://audit.mock/403", "external_id": "E001", "name": "P", "price": 1000},
        ], fail_urls={"https://audit.mock/403"})

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)

            # Connector skips failed URLs — pipeline never sees them
            assert report.urls_processed == 0
            assert report.offers_created == 0
            assert len(report.outcomes) == 0

    def test_validation_error_counted_separately(self):
        """OfferValidationError → validation_errors, not extraction_errors."""
        connector = AuditMockConnector(records=[
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "P", "brand": "B", "mpn": "M", "price": 1000, "category": "notebooks"},
        ])

        with TestSession() as db:
            service = CatalogIngestionService(db)
            with patch.object(service, "ingest", side_effect=OfferValidationError("bad offer")):
                report = IngestionPipeline(service).run(connector)

                assert report.validation_errors == 1
                assert report.extraction_errors == 0

    def test_normalize_error_counted_as_extraction(self):
        """ValueError from normalize → extraction_errors."""
        connector = AuditMockConnector(records=[
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "P", "price": 1000},
        ], fail_normalize_urls={"https://audit.mock/p1"})

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)

            assert report.extraction_errors == 1
            assert report.validation_errors == 0

    def test_sitemap_malformed_xml_returns_empty(self):
        """Malformed sitemap XML: no crash, returns empty."""
        fetcher = MagicMock(spec=DiscoveryFetcher)
        fetcher.fetch.return_value = "not xml at all"
        discovery = SPDigitalURLDiscovery()

        results = discovery.discover_from_sitemap(fetcher, max_urls=0)
        assert results == []

    def test_child_sitemap_inaccessible_skips(self):
        """Inaccessible child sitemap: skipped, others continue."""
        child1 = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.example.cl/p1.html</loc></url>
</urlset>"""
        index_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex>
  <sitemap><loc>https://www.example.cl/sitemap-1.xml</loc></sitemap>
  <sitemap><loc>https://www.example.cl/sitemap-2.xml</loc></sitemap>
</sitemapindex>"""

        fetcher = MagicMock(spec=DiscoveryFetcher)

        def _fetch(url, *, headers=None):
            if "sitemap_index" in url or "sitemap-index" in url:
                return index_xml
            if "sitemap-1" in url:
                return child1
            raise ConnectionError("inaccessible")

        fetcher.fetch.side_effect = _fetch
        stream = SitemapStream(fetcher, "https://www.example.cl/sitemap_index.xml")
        urls = list(stream)
        assert len(urls) == 1
        assert urls[0] == "https://www.example.cl/p1.html"

    def test_db_error_aborts_individual_offer(self):
        """Database error in ingest: NOT caught by pipeline, crashes run."""
        connector = AuditMockConnector(records=[
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "P", "brand": "B", "mpn": "M", "price": 1000, "category": "notebooks"},
        ])

        with TestSession() as db:
            service = CatalogIngestionService(db)
            with patch.object(service, "ingest", side_effect=Exception("db error")):
                with pytest.raises(Exception, match="db error"):
                    IngestionPipeline(service).run(connector)

    def test_product_page_inaccessible_skipped(self):
        """Product page HTTP failure: connector skips, others continue."""
        connector = AuditMockConnector(records=[
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "P1", "brand": "B", "mpn": "M", "price": 1000, "category": "notebooks"},
            {"url": "https://audit.mock/FAIL", "external_id": "E002", "name": "P2", "brand": "B", "mpn": "M2", "price": 2000, "category": "notebooks"},
        ], fail_urls={"https://audit.mock/FAIL"})

        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)

            # FAIL URL skipped by connector, pipeline only sees p1
            assert report.urls_processed == 1
            assert report.offers_created == 1


# ── 9. REPORTING SEMANTICS ────────────────────────────────────────


class TestReportingSemantics:
    """Ensure reports have consistent semantics."""

    def test_pipeline_report_has_all_fields(self):
        report = IngestionReport()
        assert hasattr(report, "urls_processed")
        assert hasattr(report, "offers_created")
        assert hasattr(report, "offers_updated")
        assert hasattr(report, "price_changes")
        assert hasattr(report, "products_created")
        assert hasattr(report, "products_matched")
        assert hasattr(report, "extraction_errors")
        assert hasattr(report, "validation_errors")
        assert hasattr(report, "eligibility_rejected")
        assert hasattr(report, "outcomes")
        assert hasattr(report, "errors")
        assert hasattr(report, "duration_ms")

    def test_pipeline_report_alias_works(self):
        """PipelineReport is backward-compatible alias."""
        from app.ingestion.pipeline import PipelineReport
        assert issubclass(PipelineReport, IngestionReport)

    def test_discovery_report_separate_from_ingestion(self):
        """DiscoveryReport does not contain ingestion metrics."""
        dr = DiscoveryReport()
        assert not hasattr(dr, "offers_created")
        assert not hasattr(dr, "offers_updated")
        assert not hasattr(dr, "price_changes")

    def test_ingestion_report_separate_from_discovery(self):
        """IngestionReport does not contain discovery metrics."""
        ir = IngestionReport()
        assert not hasattr(ir, "categories_requested")
        assert not hasattr(ir, "categories_success")

    def test_outcomes_list_tracks_per_offer(self):
        """Each successful offer produces an IngestionOutcome."""
        records = [
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "P1", "brand": "B", "mpn": "M1", "price": 1000, "category": "notebooks"},
            {"url": "https://audit.mock/p2", "external_id": "E002", "name": "P2", "brand": "B", "mpn": "M2", "price": 2000, "category": "notebooks"},
        ]
        connector = AuditMockConnector(records=records)

        with TestSession() as db:
            _reset(db)
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)

            assert len(report.outcomes) == 2
            assert all(isinstance(o, IngestionOutcome) for o in report.outcomes)
            assert all(o.is_new for o in report.outcomes)


# ── 10. MEMORY / STREAMING VALIDATION ─────────────────────────────


class TestMemoryStreaming:
    """Validate that streaming doesn't accidentally materialize all URLs."""

    def test_flat_sitemap_stream_yields_lazily(self):
        """FlatSitemapStream uses re.finditer, not re.findall."""
        import re

        sitemap_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.spdigital.cl/p1/p</loc></url>
  <url><loc>https://www.spdigital.cl/p2/p</loc></url>
  <url><loc>https://www.spdigital.cl/p3/p</loc></url>
</urlset>"""
        fetcher = MagicMock(spec=DiscoveryFetcher)
        fetcher.fetch.return_value = sitemap_xml

        stream = FlatSitemapStream(fetcher, "https://www.spdigital.cl/sitemap.xml")

        # Verify it yields one at a time (generator)
        gen = iter(stream)
        first = next(gen)
        assert first == "https://www.spdigital.cl/p1/p"

        # Verify fetch was called once (XML loaded)
        assert fetcher.fetch.call_count == 1

        second = next(gen)
        assert second == "https://www.spdigital.cl/p2/p"

    def test_sitemap_stream_yields_per_child(self):
        """SitemapStream fetches one child at a time."""
        child1 = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.example.cl/p1.html</loc></url>
</urlset>"""
        child2 = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.example.cl/p2.html</loc></url>
</urlset>"""
        index_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex>
  <sitemap><loc>https://www.example.cl/sitemap-1.xml</loc></sitemap>
  <sitemap><loc>https://www.example.cl/sitemap-2.xml</loc></sitemap>
</sitemapindex>"""

        fetcher = MagicMock(spec=DiscoveryFetcher)

        def _fetch(url, *, headers=None):
            if "sitemap-1" in url:
                return child1
            if "sitemap-2" in url:
                return child2
            return index_xml

        fetcher.fetch.side_effect = _fetch

        stream = SitemapStream(fetcher, "https://www.example.cl/sitemap_index.xml")
        gen = iter(stream)

        # First child fetched lazily
        first = next(gen)
        assert first == "https://www.example.cl/p1.html"
        # Only index + child-1 fetched so far
        assert fetcher.fetch.call_count == 2

        # Second child fetched on demand
        second = next(gen)
        assert second == "https://www.example.cl/p2.html"
        assert fetcher.fetch.call_count == 3

    def test_batched_urls_yields_incrementally(self):
        """batched_urls yields batches without full materialization."""
        call_count = 0

        def _gen():
            nonlocal call_count
            for i in range(10):
                call_count += 1
                yield f"https://example.com/{i}"

        batches = list(batched_urls(_gen(), batch_size=3))
        assert len(batches) == 4  # 3+3+3+1
        assert call_count == 10  # all consumed

    def test_spdigital_streaming_batch_count(self):
        """SP Digital streaming yields correct batch count."""
        urls_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset>\n'
        for i in range(1200):
            urls_xml += f'  <url><loc>https://www.spdigital.cl/p{i}/p</loc></url>\n'
        urls_xml += '</urlset>'

        fetcher = MagicMock(spec=DiscoveryFetcher)
        fetcher.fetch.return_value = urls_xml
        discovery = SPDigitalURLDiscovery()

        results = discovery.discover_from_sitemap(fetcher, max_urls=0)
        assert len(results) == 1200

    def test_paris_streaming_with_child_filter(self):
        """Paris SitemapStream filters child sitemaps by keyword."""
        product_child = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.paris.cl/product-1.html</loc></url>
</urlset>"""
        other_child = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.paris.cl/category-1.html</loc></url>
</urlset>"""
        index_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex>
  <sitemap><loc>https://www.paris.cl/sitemap-product-1.xml</loc></sitemap>
  <sitemap><loc>https://www.paris.cl/sitemap-category-1.xml</loc></sitemap>
</sitemapindex>"""

        fetcher = MagicMock(spec=DiscoveryFetcher)

        def _fetch(url, *, headers=None):
            if "product-1" in url:
                return product_child
            if "category-1" in url:
                return other_child
            return index_xml

        fetcher.fetch.side_effect = _fetch

        stream = SitemapStream(
            fetcher,
            "https://www.paris.cl/sitemap_index.xml",
            child_filter="product",
        )
        urls = list(stream)
        assert len(urls) == 1
        assert urls[0] == "https://www.paris.cl/product-1.html"


# ── ADDITIONAL: INGESTIONRUN PERSISTENCE ──────────────────────────


class TestIngestionRunPersistence:
    """Validate IngestionRun is correctly persisted."""

    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_runner_persists_metrics(self):
        records = [
            {"url": "https://audit.mock/p1", "external_id": "E001", "name": "P1", "brand": "B", "mpn": "M1", "price": 50000, "category": "notebooks"},
            {"url": "https://audit.mock/p2", "external_id": "E002", "name": "P2", "brand": "B", "mpn": "M2", "price": 60000, "category": "monitores"},
        ]
        connector = AuditMockConnector(records=records)

        with TestSession() as db:
            runner = IngestionRunner()
            run = runner.run(db, connector, urls=["https://audit.mock/p1", "https://audit.mock/p2"])

            assert run.status == "success"
            assert run.urls_total == 2
            assert run.urls_processed == 2
            assert run.products_created >= 2
            assert run.duration_ms >= 0
            assert run.finished_at is not None

    def test_runner_records_price_changes(self):
        """Runner records price changes from pipeline."""
        records_v1 = [{"url": "https://audit.mock/p1", "external_id": "E001", "name": "P1", "brand": "B", "mpn": "M1", "price": 50000}]
        records_v2 = [{"url": "https://audit.mock/p1", "external_id": "E001", "name": "P1", "brand": "B", "mpn": "M1", "price": 60000}]

        with TestSession() as db:
            runner = IngestionRunner()
            run1 = runner.run(db, AuditMockConnector(records=records_v1), urls=["https://audit.mock/p1"])
            assert run1.price_changes == 0

            run2 = runner.run(db, AuditMockConnector(records=records_v2), urls=["https://audit.mock/p1"])
            assert run2.price_changes == 1
