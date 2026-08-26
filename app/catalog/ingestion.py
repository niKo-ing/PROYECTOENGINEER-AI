from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.ingestion.dto import NormalizedOffer
from app.models.catalog import IngestionSourceType


@dataclass(frozen=True)
class NormalizedProduct:
    name: str
    brand: str | None = None
    model: str | None = None
    mpn: str | None = None
    gtin: str | None = None
    manufacturer_sku: str | None = None
    category_slug: str | None = None
    description: str | None = None
    image_url: str | None = None
    specifications: dict[str, str] = field(default_factory=dict)


class ProductSource(ABC):
    """Future API/feed/scraper adapters return normalized records only."""

    source_type: IngestionSourceType

    @abstractmethod
    def fetch(self) -> list[tuple[NormalizedProduct, NormalizedOffer]]:
        raise NotImplementedError


class ApiProductSource(ProductSource):
    source_type = IngestionSourceType.API


class FeedProductSource(ProductSource):
    source_type = IngestionSourceType.FEED


class AffiliateFeedProductSource(ProductSource):
    source_type = IngestionSourceType.AFFILIATE_FEED


class ScraperProductSource(ProductSource):
    source_type = IngestionSourceType.SCRAPER
