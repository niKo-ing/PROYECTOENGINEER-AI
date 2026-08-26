import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.matching import MatchStatus, ProductMatcher
from app.ingestion.connectors import StoreConnector
from app.ingestion.dto import NormalizedOffer
from app.models.catalog import Category, PriceHistory, Product, Store, StoreOffer
from app.ingestion.validation import OfferValidationError, OfferValidator

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionOutcome:
    product_id: int
    offer_id: int
    price_changed: bool
    is_new: bool


class CatalogIngestionService:
    """The only ingestion layer allowed to write catalog records."""

    def __init__(
        self,
        db: Session,
        validator: OfferValidator | None = None,
        ai_matcher: Any | None = None,
    ):
        self.db = db
        self.validator = validator or OfferValidator()
        self.matcher = ProductMatcher(db)
        self.ai_matcher = ai_matcher

    def ingest(self, connector: StoreConnector, normalized: NormalizedOffer) -> IngestionOutcome:
        self.validator.validate(normalized)
        store = self._get_or_create_store(connector)

        # Check for identity conflicts before matching
        conflict = self.matcher.check_conflict(normalized)
        if conflict:
            log.warning("Identity conflict for %s: %s", normalized.product_url, conflict)

        match_result = self.matcher.match(normalized, ai_matcher=self.ai_matcher)
        if match_result.status == MatchStatus.AMBIGUOUS:
            # Ambiguous: create new product to avoid silent incorrect merges
            product = self._create_product(normalized)
        elif match_result.is_match and match_result.product:
            product = match_result.product
        else:
            product = self._create_product(normalized)
        offer = self._find_offer(store.id, normalized)
        price = self._price_to_int(normalized)
        if offer is None:
            offer = StoreOffer(product=product, store=store, url=normalized.product_url, external_id=normalized.external_id, price=price, original_price=self._previous_price(normalized), currency=normalized.currency.upper(), stock_status=normalized.stock or "unknown", availability=normalized.availability, source=normalized.source, ingestion_status="success", error_count=0, last_checked_at=normalized.scraped_at, last_seen_at=normalized.scraped_at)
            self.db.add(offer)
            self.db.flush()
            self._record_history(offer, normalized)
            is_new = True
            changed = True
        else:
            is_new = False
            changed = offer.price != price
            offer.product = product
            if offer.url != normalized.product_url:
                url_conflict = self.db.scalar(
                    select(StoreOffer).where(
                        StoreOffer.store_id == store.id,
                        StoreOffer.url == normalized.product_url,
                        StoreOffer.id != offer.id,
                    )
                )
                if url_conflict:
                    log.warning(
                        "URL change for offer %d would conflict with offer %d, keeping old URL",
                        offer.id, url_conflict.id,
                    )
                else:
                    offer.url = normalized.product_url
            offer.external_id = normalized.external_id
            offer.original_price = self._previous_price(normalized)
            offer.price = price
            offer.currency = normalized.currency.upper()
            offer.stock_status = normalized.stock or "unknown"
            offer.availability = normalized.availability
            offer.source = normalized.source
            offer.ingestion_status = "success"
            offer.error_count = 0
            offer.last_checked_at = normalized.scraped_at
            offer.last_seen_at = normalized.scraped_at
            if changed:
                self._record_history(offer, normalized)
        self.db.commit()
        self.db.refresh(offer)
        return IngestionOutcome(product_id=product.id, offer_id=offer.id, price_changed=changed, is_new=is_new)

    def record_failure(self, store_id: int, external_id: str | None, product_url: str) -> None:
        offer = self._find_offer(store_id, NormalizedOffer(source="failure", external_id=external_id, product_url=product_url, name="failure", brand=None, model=None, mpn=None, gtin=None, sku=None, price=0, previous_price=None, currency="CLP", availability=False, stock=None, image_url=None, category=None, scraped_at=self._now()))
        if offer:
            offer.ingestion_status = "error"
            offer.error_count += 1
            self.db.commit()

    def _get_or_create_store(self, connector: StoreConnector) -> Store:
        store = self.db.scalar(select(Store).where(Store.domain == connector.store_domain))
        if store:
            return store
        store = Store(name=connector.store_name, domain=connector.store_domain, store_type=connector.store_type.value)
        self.db.add(store)
        self.db.flush()
        return store

    def _create_product(self, offer: NormalizedOffer) -> Product:
        category = self._get_or_create_category(offer.category) if offer.category else None
        product = Product(name=offer.name, brand=offer.brand, model=offer.model, mpn=offer.mpn, gtin=offer.gtin, manufacturer_sku=offer.sku, image_url=offer.image_url, category_entity=category)
        self.db.add(product)
        self.db.flush()
        return product

    def _get_or_create_category(self, name: str) -> Category:
        category = self.db.scalar(select(Category).where(Category.name == name))
        if category:
            return category
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "sin-categoria"
        suffix, candidate = 2, slug
        while self.db.scalar(select(Category.id).where(Category.slug == candidate)):
            candidate = f"{slug}-{suffix}"
            suffix += 1
        category = Category(name=name, slug=candidate)
        self.db.add(category)
        self.db.flush()
        return category

    def _find_offer(self, store_id: int, normalized: NormalizedOffer) -> StoreOffer | None:
        statement = select(StoreOffer).where(StoreOffer.store_id == store_id)
        if normalized.external_id:
            offer = self.db.scalar(statement.where(StoreOffer.external_id == normalized.external_id))
            if offer is not None:
                return offer
        return self.db.scalar(statement.where(StoreOffer.url == normalized.product_url))

    @staticmethod
    def _price_to_int(offer: NormalizedOffer) -> int:
        if offer.price != offer.price.to_integral_value():
            raise ValueError("El modelo actual de StoreOffer requiere precios enteros")
        return int(offer.price)

    @staticmethod
    def _previous_price(offer: NormalizedOffer) -> int | None:
        return int(offer.previous_price) if offer.previous_price is not None else None

    def _record_history(self, offer: StoreOffer, normalized: NormalizedOffer) -> None:
        self.db.add(PriceHistory(store_offer=offer, price=offer.price, original_price=offer.original_price, currency=offer.currency, observed_at=normalized.scraped_at))

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
