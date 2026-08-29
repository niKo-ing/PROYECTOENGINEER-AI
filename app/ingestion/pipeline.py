import decimal
import time
from dataclasses import dataclass, field

from app.ingestion.category import (
    CategoryFilter,
    check_eligibility,
)
from app.ingestion.connectors import StoreConnector
from app.ingestion.service import CatalogIngestionService, IngestionOutcome
from app.ingestion.validation import OfferValidationError


@dataclass
class IngestionReport:
    """Metrics from a single ingestion pipeline run.

    Answers: "What did we manage to process?"
    """

    urls_processed: int = 0
    offers_created: int = 0
    offers_updated: int = 0
    price_changes: int = 0
    products_created: int = 0
    products_matched: int = 0
    extraction_errors: int = 0
    validation_errors: int = 0
    eligibility_rejected: int = 0
    outcomes: list[IngestionOutcome] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0

    # AI matching metrics (separate from deterministic)
    ai_candidates_generated: int = 0
    ai_calls: int = 0
    ai_cache_hits: int = 0
    ai_matches: int = 0
    ai_no_matches: int = 0
    ai_unresolved: int = 0
    ai_errors: int = 0

    @property
    def urls_total(self) -> int:
        return self.urls_processed

    @property
    def ai_total_resolved(self) -> int:
        return self.ai_matches + self.ai_no_matches


class IngestionPipeline:
    def __init__(
        self,
        catalog_service: CatalogIngestionService,
        category_filter: CategoryFilter | None = None,
        eligibility_enabled: bool = False,
    ):
        self.catalog_service = catalog_service
        self.category_filter = category_filter
        self.eligibility_enabled = eligibility_enabled

    def run(self, connector: StoreConnector, max_products: int = 0) -> IngestionReport:
        report = IngestionReport()
        start = time.monotonic()

        for record in connector.extract():
            report.urls_processed += 1
            try:
                normalized = connector.normalize(record)

                if self.eligibility_enabled:
                    eligibility = check_eligibility(
                        category_slug=normalized.category,
                        name=normalized.name,
                        url=normalized.product_url,
                        price=int(normalized.price) if normalized.price else None,
                        gtin=normalized.gtin,
                        mpn=normalized.mpn,
                        brand=normalized.brand,
                        sku=normalized.sku,
                        product_id=None,
                        category_filter=self.category_filter,
                    )

                    if not eligibility.eligible:
                        report.eligibility_rejected += 1
                        continue

                outcome = self.catalog_service.ingest(connector, normalized)
                report.outcomes.append(outcome)
                if outcome.is_new:
                    report.offers_created += 1
                else:
                    report.offers_updated += 1
                if outcome.product_created:
                    report.products_created += 1
                if outcome.product_matched:
                    report.products_matched += 1
                if max_products > 0 and len(report.outcomes) >= max_products:
                    break
            except OfferValidationError as error:
                report.errors.append(str(error))
                report.validation_errors += 1
            except (ValueError, KeyError, decimal.InvalidOperation) as error:
                report.errors.append(str(error))
                report.extraction_errors += 1

        report.price_changes = sum(
            1 for o in report.outcomes if o.price_changed and not o.is_new
        )
        report.duration_ms = int((time.monotonic() - start) * 1000)
        return report


class PipelineReport(IngestionReport):
    """Backward-compatible alias. Deprecated: use IngestionReport."""

    pass
