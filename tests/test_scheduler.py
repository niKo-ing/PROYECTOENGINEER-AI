"""Tests for IngestionScheduler — job registration and lifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.ingestion.scheduler import IngestionScheduler
from app.models.catalog import Category, IngestionRun, PriceHistory, Product, Store, StoreOffer

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _reset(db):
    for model in (PriceHistory, StoreOffer, IngestionRun, Product, Store, Category):
        db.query(model).delete()
    db.commit()


def _create_store(db, domain="test.store.cl", sync_enabled=True, interval=30):
    store = Store(
        name=f"Test Store ({domain})",
        domain=domain,
        sync_enabled=sync_enabled,
        sync_interval_min=interval,
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


class TestIngestionScheduler:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_scheduler_registers_jobs_for_enabled_stores(self):
        with TestSession() as db:
            _create_store(db, "store-a.cl", sync_enabled=True, interval=15)
            _create_store(db, "store-b.cl", sync_enabled=True, interval=60)

        callback = MagicMock()
        scheduler = IngestionScheduler(session_factory=TestSession, job_callback=callback)
        scheduler.start()

        jobs = scheduler._scheduler.get_jobs()
        assert len(jobs) == 2

        job_ids = {j.id for j in jobs}
        assert "sync_store-a.cl" in job_ids
        assert "sync_store-b.cl" in job_ids

        scheduler.shutdown()

    def test_scheduler_skips_disabled_stores(self):
        with TestSession() as db:
            _create_store(db, "enabled.cl", sync_enabled=True, interval=30)
            _create_store(db, "disabled.cl", sync_enabled=False, interval=30)

        callback = MagicMock()
        scheduler = IngestionScheduler(session_factory=TestSession, job_callback=callback)
        scheduler.start()

        jobs = scheduler._scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "sync_enabled.cl"

        scheduler.shutdown()

    def test_scheduler_skips_stores_without_interval(self):
        with TestSession() as db:
            _create_store(db, "no-interval.cl", sync_enabled=True, interval=None)

        callback = MagicMock()
        scheduler = IngestionScheduler(session_factory=TestSession, job_callback=callback)
        scheduler.start()

        jobs = scheduler._scheduler.get_jobs()
        assert len(jobs) == 0

        scheduler.shutdown()

    def test_scheduler_runs_callback_with_store_id(self):
        with TestSession() as db:
            store = _create_store(db, "callback.cl", sync_enabled=True, interval=30)

        callback = MagicMock()
        scheduler = IngestionScheduler(session_factory=TestSession, job_callback=callback)
        scheduler.start()

        # Manually trigger the job
        scheduler.run_now(store.id)
        callback.assert_called_once_with(store.id)

        scheduler.shutdown()

    def test_scheduler_start_stop_lifecycle(self):
        with TestSession() as db:
            _create_store(db, "lifecycle.cl", sync_enabled=True, interval=30)

        callback = MagicMock()
        scheduler = IngestionScheduler(session_factory=TestSession, job_callback=callback)
        scheduler.start()
        assert scheduler._scheduler.running

        scheduler.shutdown()
        assert not scheduler._scheduler.running

    def test_scheduler_no_jobs_does_not_start(self):
        callback = MagicMock()
        scheduler = IngestionScheduler(session_factory=TestSession, job_callback=callback)
        scheduler.start()

        assert not scheduler._scheduler.running
        assert len(scheduler._job_ids) == 0
