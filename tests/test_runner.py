"""Tests for IngestionRunner — execution tracking and DB persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
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
