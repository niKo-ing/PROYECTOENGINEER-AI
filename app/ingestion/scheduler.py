"""APScheduler wrapper — contains zero business logic.

The scheduler's only job is to call IngestionRunner.run() on a schedule.
All domain logic lives in runner.py and pipeline.py.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler

if TYPE_CHECKING:
    from collections.abc import Callable
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


class IngestionScheduler:
    """Wraps APScheduler to run ingestion jobs on a per-store schedule.

    The scheduler knows nothing about connectors, pipelines, or business rules.
    It only triggers a callback at configured intervals.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        job_callback: Callable[[int], None],
    ) -> None:
        """
        Args:
            session_factory: Callable that returns a new DB session.
            job_callback: Called with store_id when a job fires.
        """
        self._session_factory = session_factory
        self._job_callback = job_callback
        self._scheduler = BackgroundScheduler()
        self._job_ids: list[str] = []

    def start(self) -> None:
        """Read enabled stores from DB and register a job for each."""
        db = self._session_factory()
        try:
            from app.models.catalog import Store
            from sqlalchemy import select

            stores = db.scalars(
                select(Store).where(Store.sync_enabled == True, Store.sync_interval_min.isnot(None))
            ).all()

            for store in stores:
                interval = store.sync_interval_min or 30
                job_id = f"sync_{store.domain}"
                self._scheduler.add_job(
                    self._job_callback,
                    "interval",
                    minutes=interval,
                    args=[store.id],
                    id=job_id,
                    replace_existing=True,
                    max_instances=1,
                )
                self._job_ids.append(job_id)
                log.info("Scheduled sync for %s every %d min", store.domain, interval)

            if self._job_ids:
                self._scheduler.start()
                log.info("Ingestion scheduler started with %d jobs", len(self._job_ids))
            else:
                log.info("No stores with sync_enabled — scheduler not started")
        finally:
            db.close()

    def shutdown(self) -> None:
        """Gracefully shut down the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            log.info("Ingestion scheduler shut down")

    def run_now(self, store_id: int) -> None:
        """Trigger an immediate run for a specific store (manual trigger)."""
        self._job_callback(store_id)
