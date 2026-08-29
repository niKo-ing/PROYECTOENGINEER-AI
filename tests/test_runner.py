"""Tests for IngestionRunner — execution tracking and DB persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.ingestion.connectors import MockStoreConnector
from app.ingestion.runner import IngestionRunner
from app.models.catalog import (
    Category,
    IngestionRun,
    PriceHistory,
    Product,
    Store,
    StoreOffer,
)

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _reset(db):
    for model in (PriceHistory, StoreOffer, IngestionRun, Product, Store, Category):
        db.query(model).delete()
    db.commit()


class TestIngestionRunner:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_runner_creates_ingestion_run_record(self):
        connector = MockStoreConnector(
            store_name="Mock Store",
            store_domain="mock.test",
            price=10000,
            external_id="MOCK-001",
        )
        with TestSession() as db:
            runner = IngestionRunner()
            run = runner.run(db, connector, urls=["https://mock.test/product"])

            assert run.id is not None
            assert run.source_name == "mock:mock.test"
            assert run.status == "success"
            assert run.urls_total == 1
            assert run.urls_processed == 1
            assert run.errors_count == 0
            assert run.finished_at is not None
            assert run.duration_ms is not None
            assert run.duration_ms >= 0

    def test_runner_persists_run_to_db(self):
        connector = MockStoreConnector(
            store_name="Mock Store",
            store_domain="mock.test",
            price=10000,
            external_id="MOCK-001",
        )
        with TestSession() as db:
            runner = IngestionRunner()
            run = runner.run(db, connector, urls=["https://mock.test/product"])

            persisted = db.get(IngestionRun, run.id)
            assert persisted is not None
            assert persisted.status == "success"
            assert persisted.store_id is not None

    def test_runner_creates_store_if_missing(self):
        connector = MockStoreConnector(
            store_name="New Store",
            store_domain="new.store.test",
            price=5000,
            external_id="NEW-001",
        )
        with TestSession() as db:
            runner = IngestionRunner()
            run = runner.run(db, connector, urls=["https://new.store.test/p"])

            store = db.get(Store, run.store_id)
            assert store is not None
            assert store.name == "New Store"
            assert store.domain == "new.store.test"

    def test_runner_updates_store_sync_last_run_at(self):
        connector = MockStoreConnector(
            store_name="Mock Store",
            store_domain="mock.test",
            price=10000,
            external_id="MOCK-001",
        )
        with TestSession() as db:
            runner = IngestionRunner()
            run = runner.run(db, connector, urls=["https://mock.test/product"])

            store = db.get(Store, run.store_id)
            assert store.sync_last_run_at is not None

    def test_runner_records_error_on_exception(self):
        connector = MockStoreConnector(
            store_name="Fail Store",
            store_domain="fail.test",
            price=10000,
            external_id="FAIL-001",
        )

        with TestSession() as db:
            runner = IngestionRunner()
            with patch.object(
                type(connector),
                "extract",
                side_effect=RuntimeError("boom"),
            ):
                run = runner.run(db, connector, urls=["https://fail.test/p"])

            assert run.status == "error"
            assert run.errors_count == 1
            assert "boom" in (run.error_messages or "")

    def test_runner_counts_products_created(self):
        connector = MockStoreConnector(
            store_name="Mock Store",
            store_domain="mock.test",
            price=10000,
            external_id="MOCK-002",
        )
        with TestSession() as db:
            runner = IngestionRunner()
            run = runner.run(db, connector, urls=["https://mock.test/p"])

            assert run.products_created >= 1

    def test_runner_with_empty_urls(self):
        connector = MockStoreConnector(
            store_name="Empty Store",
            store_domain="empty.test",
            price=10000,
            external_id="E-001",
        )
        with TestSession() as db:
            runner = IngestionRunner()
            run = runner.run(db, connector, urls=[])

            assert run.urls_total == 0
            assert run.status == "success"


class TestIngestionReportFields:
    def test_report_has_duration_and_urls(self):
        from app.ingestion.connectors import MockStoreConnector
        from app.ingestion.pipeline import IngestionPipeline, IngestionReport
        from app.ingestion.service import CatalogIngestionService

        connector = MockStoreConnector(
            store_name="Test",
            store_domain="test.local",
            price=1000,
            external_id="T-1",
        )
        with TestSession() as db:
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)

            assert isinstance(report, IngestionReport)
            assert report.urls_processed == 1
            assert report.duration_ms >= 0
            assert len(report.outcomes) == 1


class TestRunnerDiscoveryMode:
    """End-to-end run_with_discovery: candidates → connector → pipeline → run record.

    Regression test for the NameError on `Store` in run_with_discovery
    when a run reaches the success path that updates sync_last_run_at.
    """

    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_run_with_discovery_completes_and_sets_store_timestamp(self):
        from app.ingestion.category import CategoryFilter, CategoryMapper
        from app.ingestion.runner import IngestionRunner
        from app.ingestion.url_discovery import DiscoveredURL, DiscoveryReport
        from datetime import datetime, timezone

        class FakeDiscovery:
            request_delay = 0.0

            def discover(self, *, categories, category_mapper, category_filter, fetcher, max_urls_per_category):
                now = datetime.now(timezone.utc)
                candidates = [
                    DiscoveredURL(
                        url=f"https://mock.test/products/product-{i}.html",
                        source="mock:category",
                        source_category="Computación",
                        mapped_category="notebooks",
                        discovered_at=now,
                    )
                    for i in range(3)
                ]
                return DiscoveryReport(
                    categories_requested=len(categories),
                    categories_success=1,
                    urls_discovered=len(candidates),
                    duplicate_urls=0,
                    candidates=candidates,
                )

        class FakeConnector(MockStoreConnector):
            def __init__(self, *, urls=None, url_category_map=None):
                super().__init__(
                    store_name="Mock Store",
                    store_domain="mock.test",
                    price=9999,
                    external_id="REG-001",
                )
                self._urls = urls or []
                self.set_url_category_map(url_category_map or {})

        with TestSession() as db:
            runner = IngestionRunner()
            run = runner.run_with_discovery(
                db=db,
                connector_factory=FakeConnector,
                url_discovery=FakeDiscovery(),
                category_mapper=CategoryMapper("mock.test"),
                category_filter=CategoryFilter(),
                categories=["Computación"],
                store_domain="mock.test",
                max_urls_per_category=3,
            )

            assert run.status == "success"
            assert run.urls_total == 3
            assert run.products_created == 1
            store = db.get(Store, run.store_id)
            assert store is not None
            assert store.sync_last_run_at is not None


class TestRunnerFinalizationRobustness:
    """A failing terminal commit must never leave a run stuck as 'running'."""

    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    @staticmethod
    def _fail_first_terminal_commit(db, error):
        """Patch commit to raise once, only when finalizing (run status set)."""
        original = db.commit
        fired = {"done": False}

        def commit():
            pending = any(
                isinstance(obj, IngestionRun) and obj.status != "running"
                for obj in db
            )
            if pending and not fired["done"]:
                fired["done"] = True
                raise error
            return original()

        db.commit = commit  # type: ignore[method-assign]

    def test_run_final_commit_failure_forces_error_not_running(self):
        connector = MockStoreConnector(
            store_name="Mock Store",
            store_domain="mock.test",
            price=10000,
            external_id="FLK-001",
        )
        with TestSession() as db:
            self._fail_first_terminal_commit(
                db, OperationalError("statement", {}, Exception("pooler hiccup"))
            )
            runner = IngestionRunner()
            run = runner.run(db, connector, urls=["https://mock.test/p"])

            assert run.status == "error"
            assert run.finished_at is not None
            persisted = db.get(IngestionRun, run.id)
            assert persisted is not None
            assert persisted.status == "error"
            assert persisted.finished_at is not None
            assert persisted.errors_count >= 1
            assert "finalization commit failed" in (persisted.error_messages or "")

    def test_discovery_final_commit_failure_forces_error_not_running(self):
        from app.ingestion.category import CategoryFilter, CategoryMapper
        from app.ingestion.url_discovery import DiscoveredURL, DiscoveryReport

        class FakeDiscovery:
            request_delay = 0.0

            def discover(self, **kwargs):
                now = datetime.now(timezone.utc)
                return DiscoveryReport(
                    categories_requested=1,
                    categories_success=1,
                    urls_discovered=1,
                    duplicate_urls=0,
                    candidates=[
                        DiscoveredURL(
                            url="https://mock.test/products/p-flkx.html",
                            source="mock:category",
                            source_category="Computación",
                            mapped_category="notebooks",
                            discovered_at=now,
                        )
                    ],
                )

        class FakeConnector(MockStoreConnector):
            def __init__(self, *, urls=None, url_category_map=None):
                super().__init__(
                    store_name="Mock Store",
                    store_domain="mock.test",
                    price=9999,
                    external_id="REG-FLK",
                )
                self._urls = urls or []
                self.set_url_category_map(url_category_map or {})

        with TestSession() as db:
            self._fail_first_terminal_commit(
                db, OperationalError("statement", {}, Exception("pooler hiccup"))
            )
            runner = IngestionRunner()
            run = runner.run_with_discovery(
                db=db,
                connector_factory=FakeConnector,
                url_discovery=FakeDiscovery(),
                category_mapper=CategoryMapper("mock.test"),
                category_filter=CategoryFilter(),
                categories=["Computación"],
                store_domain="mock.test",
                max_urls_per_category=1,
            )

            assert run.status == "error"
            assert run.finished_at is not None
            persisted = db.get(IngestionRun, run.id)
            assert persisted is not None
            assert persisted.status == "error"
            assert persisted.finished_at is not None
            assert persisted.errors_count >= 1
            assert "finalization commit failed" in (persisted.error_messages or "")


class TestDiscoveryCategoryAssignment:
    """Discovery propagates the mapped internal category slug to Product.category_id."""

    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def _run_discovery(self, db, mapped_category):
        from app.ingestion.category import CategoryFilter, CategoryMapper
        from app.ingestion.url_discovery import DiscoveredURL, DiscoveryReport
        from datetime import datetime, timezone as tz

        class FakeDiscovery:
            request_delay = 0.0

            def discover(self, **kwargs):
                now = datetime.now(tz.utc)
                return DiscoveryReport(
                    categories_requested=1,
                    categories_success=1,
                    urls_discovered=1,
                    duplicate_urls=0,
                    candidates=[
                        DiscoveredURL(
                            url="https://mock.test/products/p-cat.html",
                            source="mock:category",
                            source_category="Computación",
                            mapped_category=mapped_category,
                            discovered_at=now,
                        )
                    ],
                )

        from app.ingestion.dto import NormalizedOffer

        class FakeConnector(MockStoreConnector):
            def __init__(self, *, urls=None, url_category_map=None):
                super().__init__(
                    store_name="Mock Store",
                    store_domain="mock.test",
                    price=9999,
                    external_id="CAT-001",
                )
                self._urls = urls or []
                self.set_url_category_map(url_category_map or {})

            def extract(self):
                for url in self._urls:
                    yield self._record_with_category(
                        url, {"price": self._price, "external_id": self._external_id}
                    )

            def normalize(self, record):
                data = record["raw"]
                return NormalizedOffer(
                    source=self.source_name,
                    external_id=str(data["external_id"]),
                    product_url=record.get("url", "https://mock.test/producto-a"),
                    name="Producto A",
                    brand="Marca A",
                    model="A-1",
                    mpn="MPN-A-1",
                    gtin="7501234567890",
                    sku="SKU-A-1",
                    price=Decimal(str(data["price"])),
                    previous_price=None,
                    currency="CLP",
                    availability=True,
                    stock="in_stock",
                    image_url=None,
                    category=record.get("category"),
                    scraped_at=datetime.now(timezone.utc),
                )

        runner = IngestionRunner()
        return runner.run_with_discovery(
            db=db,
            connector_factory=FakeConnector,
            url_discovery=FakeDiscovery(),
            category_mapper=CategoryMapper("mock.test"),
            category_filter=CategoryFilter(),
            categories=["Computación"],
            store_domain="mock.test",
            max_urls_per_category=1,
        )

    def test_discovery_assigns_category_by_slug(self):
        with TestSession() as db:
            run = self._run_discovery(db, "notebooks")
            assert run.status == "success"
            product = db.query(Product).filter_by(manufacturer_sku="SKU-A-1").one_or_none()
            assert product is not None
            assert product.category_id is not None
            assert product.category_entity.slug == "notebooks"
            assert product.category_entity.name == "Notebooks"

    def test_discovery_reuses_existing_category(self):
        with TestSession() as db:
            existing = Category(name="Notebooks", slug="notebooks")
            db.add(existing)
            db.commit()
            existing_id = existing.id

            self._run_discovery(db, "notebooks")

            assert db.query(Category).filter_by(slug="notebooks").count() == 1
            product = db.query(Product).filter_by(manufacturer_sku="SKU-A-1").one()
            assert product.category_id == existing_id
            assert db.query(Category).count() == 1

    def test_mapped_category_none_leaves_category_id_null(self):
        with TestSession() as db:
            self._run_discovery(db, None)
            product = db.query(Product).filter_by(manufacturer_sku="SKU-A-1").one_or_none()
            assert product is not None
            assert product.category_id is None
            assert db.query(Category).count() == 0

    def test_slug_category_helper_is_idempotent(self):
        from app.ingestion.service import CatalogIngestionService

        with TestSession() as db:
            service = CatalogIngestionService(db)
            first = service._get_or_create_category_by_slug("almacenamiento-ssd")
            second = service._get_or_create_category_by_slug("almacenamiento-ssd")
            assert first.id == second.id
            assert db.query(Category).filter_by(slug="almacenamiento-ssd").count() == 1
            assert first.name == "Almacenamiento Ssd"

    def test_manual_mode_resolves_category_by_name(self):
        from app.ingestion.connectors import MockStoreConnector

        connector = MockStoreConnector(
            store_name="Mock Store",
            store_domain="mock.test",
            price=5000,
            external_id="MAN-001",
        )
        with TestSession() as db:
            run = IngestionRunner().run(db, connector, urls=["https://mock.test/manual"])
            assert run.status == "success"
            product = db.query(Product).filter_by(manufacturer_sku="SKU-A-1").one()
            assert product.category_id is not None
            assert product.category_entity.name == "Notebooks"
            assert product.category_entity.slug == "notebooks"
