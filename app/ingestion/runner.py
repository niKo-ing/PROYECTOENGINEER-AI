"""IngestionRunner — executes a single ingestion run and records results in DB.

This is the business logic layer. The scheduler calls runner.run(); the
scheduler itself contains zero business logic.

Supports two modes:
- "urls": Manual URL list (existing behavior)
- "discovery": URL discovery from categories → eligibility → connector → pipeline
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from time import monotonic

from sqlalchemy.orm import Session

from app.ingestion.category import CategoryFilter, check_url_eligibility
from app.ingestion.connectors import StoreConnector
from app.ingestion.limits import get_ingestion_limits
from app.ingestion.pipeline import IngestionPipeline, IngestionReport
from app.ingestion.service import CatalogIngestionService
from app.models.catalog import IngestionRun

log = logging.getLogger(__name__)


class IngestionRunner:
    """Runs one ingestion pass for a connector and persists the run record."""

    def run(
        self,
        db: Session,
        connector: StoreConnector,
        urls: list[str],
    ) -> IngestionRun:
        now = datetime.now(timezone.utc)
        run = IngestionRun(
            store_id=self._resolve_store_id(db, connector),
            source_name=connector.source_name,
            started_at=now,
            status="running",
            urls_total=len(urls),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        start = monotonic()
        try:
            limits = get_ingestion_limits()
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(
                connector, max_products=limits.max_products,
            )

            run.urls_processed = report.urls_processed
            run.products_created = report.products_created
            run.products_updated = report.products_matched
            run.price_changes = report.price_changes
            run.errors_count = len(report.errors)
            if report.errors:
                run.error_messages = json.dumps(report.errors[:20])
            run.duration_ms = report.duration_ms
            run.status = "error" if report.errors and not report.outcomes else "success" if not report.errors else "partial"
        except Exception as exc:
            run.status = "error"
            run.errors_count = 1
            run.error_messages = json.dumps([str(exc)[:500]])
            run.duration_ms = int((monotonic() - start) * 1000)
            log.exception("Ingestion run failed for %s", connector.source_name)

        return self._finalize_run(db, run, start)

    def run_with_discovery(
        self,
        db: Session,
        connector_factory: type[StoreConnector],
        url_discovery: "URLDiscovery",
        category_mapper: "CategoryMapper",
        category_filter: "CategoryFilter",
        categories: list[str],
        store_domain: str,
        max_urls_per_category: int = 20,
    ) -> IngestionRun:
        """Run ingestion in discovery mode: discover URLs → connector → pipeline."""
        from app.ingestion.url_discovery import DiscoveryFetcher, DiscoveryReport

        start = monotonic()
        store_id = self._resolve_store_id_by_domain(db, store_domain)
        connector_name = connector_factory.__name__

        run = IngestionRun(
            store_id=store_id,
            source_name=f"{connector_name.lower().replace('connector', '')}:{store_domain}",
            started_at=datetime.now(timezone.utc),
            status="running",
            urls_total=0,
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        try:
            limits = get_ingestion_limits()

            # Apply dev limits to categories
            effective_categories = categories
            if limits.max_categories > 0:
                effective_categories = categories[: limits.max_categories]
                log.info(
                    "Dev limit: categories capped %d → %d",
                    len(categories), len(effective_categories),
                )

            # Apply dev limit to URLs per category
            effective_max_urls = max_urls_per_category
            if limits.max_urls_per_category > 0:
                effective_max_urls = min(max_urls_per_category, limits.max_urls_per_category)
                log.info(
                    "Dev limit: max_urls_per_category capped %d → %d",
                    max_urls_per_category, effective_max_urls,
                )

            # Phase 1: Discover URLs
            fetcher = DiscoveryFetcher(
                request_delay=getattr(url_discovery, 'request_delay', 0.5),
                timeout=15.0,
            )
            discovery_report = url_discovery.discover(
                categories=effective_categories,
                category_mapper=category_mapper,
                category_filter=category_filter,
                fetcher=fetcher,
                max_urls_per_category=effective_max_urls,
            )

            urls = [c.url for c in discovery_report.candidates]
            run.urls_total = len(urls)

            log.info(
                "Discovery for %s: %d categories, %d URLs (deduped %d)",
                store_domain, len(categories), len(urls), discovery_report.duplicate_urls,
            )

            if not urls:
                run.status = "success"
                run.urls_processed = 0
                run.duration_ms = int((monotonic() - start) * 1000)
                run.finished_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(run)
                return run

            eligible_urls: list[str] = []
            eligibility_rejected = 0
            for url in urls:
                result = check_url_eligibility(url)
                if result.eligible:
                    eligible_urls.append(url)
                else:
                    eligibility_rejected += 1

            log.info(
                "Eligibility for %s: %d eligible, %d rejected",
                store_domain, len(eligible_urls), eligibility_rejected,
            )

            if not eligible_urls:
                run.status = "success"
                run.urls_processed = 0
                run.errors_count = eligibility_rejected
                run.error_messages = json.dumps([f"URL eligibility rejected: {eligibility_rejected} URLs"])
                run.duration_ms = int((monotonic() - start) * 1000)
                run.finished_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(run)
                return run

            # Phase 2: Run connector on eligible URLs
            url_category_map = {
                c.url: c.mapped_category
                for c in discovery_report.candidates
                if c.mapped_category
            }
            connector = connector_factory(
                urls=eligible_urls,
                url_category_map=url_category_map,
            )
            service = CatalogIngestionService(db)
            pipeline_report = IngestionPipeline(service).run(
                connector, max_products=limits.max_products,
            )

            run.urls_processed = pipeline_report.urls_processed
            run.products_created = pipeline_report.products_created
            run.products_updated = pipeline_report.products_matched
            run.price_changes = pipeline_report.price_changes
            run.errors_count = len(pipeline_report.errors)
            if pipeline_report.errors:
                run.error_messages = json.dumps(pipeline_report.errors[:20])
            run.duration_ms = pipeline_report.duration_ms
            run.status = (
                "error" if pipeline_report.errors and not pipeline_report.outcomes
                else "success" if not pipeline_report.errors
                else "partial"
            )

        except Exception as exc:
            run.status = "error"
            run.errors_count = 1
            run.error_messages = json.dumps([str(exc)[:500]])
            run.duration_ms = int((monotonic() - start) * 1000)
            log.exception("Discovery run failed for %s", store_domain)

        return self._finalize_run(db, run, start)

    @staticmethod
    def _finalize_run(db: Session, run: IngestionRun, start: float) -> IngestionRun:
        """Persist the terminal state of an ingestion run.

        Guards against leaving a run stuck in ``running``: if the final commit
        fails (e.g. a stale pooler connection), the transaction is rolled back,
        the run is force-marked ``error`` with the cause appended, and a second
        commit is attempted. Raises only if the database stays unreachable after
        the retry.
        """
        from app.models.catalog import Store

        run.finished_at = datetime.now(timezone.utc)
        store = db.get(Store, run.store_id)
        if store:
            store.sync_last_run_at = run.finished_at

        try:
            db.commit()
            db.refresh(run)
            return run
        except Exception as exc:
            log.exception("Final commit failed for run %s; retrying as error", run.id)
            commit_error = exc

        db.rollback()
        run.status = "error"
        run.errors_count += 1
        prev = json.loads(run.error_messages) if run.error_messages else []
        prev = prev if isinstance(prev, list) else []
        prev.append(f"finalization commit failed: {str(commit_error)[:500]}")
        run.error_messages = json.dumps(prev[:20])
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return run

    @staticmethod
    def _resolve_store_id(db: Session, connector: StoreConnector) -> int:
        from app.models.catalog import Store
        from sqlalchemy import select

        store = db.scalar(select(Store).where(Store.domain == connector.store_domain))
        if store is None:
            store = Store(
                name=connector.store_name,
                domain=connector.store_domain,
                store_type=connector.store_type.value,
            )
            db.add(store)
            db.flush()
        return store.id

    @staticmethod
    def _resolve_store_id_by_domain(db: Session, domain: str) -> int:
        from app.models.catalog import Store
        from sqlalchemy import select

        store = db.scalar(select(Store).where(Store.domain == domain))
        if store is None:
            store = Store(
                name=domain,
                domain=domain,
                store_type="retailer",
            )
            db.add(store)
            db.flush()
        return store.id
