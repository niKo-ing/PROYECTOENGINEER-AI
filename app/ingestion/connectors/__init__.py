from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from app.ingestion.dto import NormalizedOffer
from app.models.catalog import StoreType


class StoreConnector(ABC):
    """Extracts and normalizes store data without importing repositories or SQLAlchemy."""

    store_name: str
    store_domain: str
    source_name: str
    store_type: StoreType = StoreType.RETAILER
    max_concurrent: int = 1
    request_delay: float = 0.0

    @abstractmethod
    def extract(self) -> Iterable[Mapping[str, Any]]:
        """Return connector-local records. Never persist raw HTML in the catalog."""

    @abstractmethod
    def normalize(self, record: Mapping[str, Any]) -> NormalizedOffer:
        """Convert one extracted record to the portable ingestion DTO."""

    def normalized_offers(self) -> Iterable[NormalizedOffer]:
        for record in self.extract():
            yield self.normalize(record)

    def _fetch_html(self, url: str, *, timeout: float = 15.0) -> str:
        """Shared HTTP fetch with retry and backoff."""
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                with httpx.Client(
                    follow_redirects=True,
                    max_redirects=5,
                    timeout=timeout,
                    headers={"User-Agent": "SoloTodo-Ingestion/1.0", "Accept": "text/html"},
                ) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    return response.text
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < 2:
                    import time
                    time.sleep(1.0 * (attempt + 1))
        raise last_exc  # type: ignore[misc]


class MockStoreConnector(StoreConnector):
    """Test-only connector; it demonstrates the connector contract without network I/O."""

    def __init__(self, *, store_name: str, store_domain: str, price: int, external_id: str):
        self.store_name = store_name
        self.store_domain = store_domain
        self.source_name = f"mock:{store_domain}"
        self._price = price
        self._external_id = external_id

    def extract(self) -> Iterable[Mapping[str, Any]]:
        return [{"price": self._price, "external_id": self._external_id}]

    def normalize(self, record: Mapping[str, Any]) -> NormalizedOffer:
        return NormalizedOffer(
            source=self.source_name,
            external_id=str(record["external_id"]),
            product_url=f"https://{self.store_domain}/producto-a",
            name="Producto A",
            brand="Marca A",
            model="A-1",
            mpn="MPN-A-1",
            gtin="7501234567890",
            sku="SKU-A-1",
            price=Decimal(str(record["price"])),
            previous_price=None,
            currency="CLP",
            availability=True,
            stock="in_stock",
            image_url=None,
            category="Notebooks",
            scraped_at=datetime.now(timezone.utc),
        )
