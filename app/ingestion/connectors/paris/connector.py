"""Paris StoreConnector — HTTP + RSC payload extraction for Next.js pages."""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.ingestion.connectors import StoreConnector
from app.ingestion.connectors.paris.parser import ParisRSCParser, RawProductData
from app.ingestion.dto import NormalizedOffer
from app.models.catalog import StoreType


class ParisConnector(StoreConnector):
    """Extracts product data from Paris (Next.js RSC) via HTTP + payload parsing."""

    store_name: str = "Paris"
    store_domain: str = "www.paris.cl"
    source_name: str = "paris:www.paris.cl"
    store_type: StoreType = StoreType.RETAILER
    max_concurrent: int = 2
    request_delay: float = 1.0

    def __init__(self, urls: list[str] | None = None) -> None:
        self._urls = urls or []
        self._parser = ParisRSCParser()

    def extract(self) -> Iterable[Mapping[str, Any]]:
        for i, url in enumerate(self._urls):
            if i > 0 and self.request_delay > 0:
                time.sleep(self.request_delay)
            record = self._fetch_and_parse(url)
            if record is not None:
                yield record

    def normalize(self, record: Mapping[str, Any]) -> NormalizedOffer:
        data: RawProductData = record["raw"]
        now = datetime.now(timezone.utc)

        return NormalizedOffer(
            source=self.source_name,
            external_id=self._resolve_external_id(data),
            product_url=data.product_url or record.get("url", ""),
            name=data.name or "Sin nombre",
            brand=data.brand,
            model=None,
            mpn=data.mpn,
            gtin=data.gtin,
            sku=data.sku,
            price=data.price or Decimal("0"),
            previous_price=None,
            currency=data.currency or "CLP",
            availability=data.availability if data.availability is not None else True,
            stock=self._map_stock(data.availability),
            image_url=data.image_url,
            category=None,
            scraped_at=now,
        )

    def _fetch_and_parse(self, url: str) -> Mapping[str, Any] | None:
        try:
            html = self._fetch_html(url)
        except Exception:
            return None

        data = self._parser.parse(html)
        if data.name is None or data.price is None:
            return None

        return {"url": url, "raw": data}

    @staticmethod
    def _resolve_external_id(data: RawProductData) -> str | None:
        if data.sku:
            return data.sku
        if data.product_id:
            return data.product_id
        if data.mpn and data.brand:
            return f"{data.brand}:{data.mpn}"
        return None

    @staticmethod
    def _map_stock(availability: bool | None) -> str:
        if availability is True:
            return "in_stock"
        if availability is False:
            return "out_of_stock"
        return "unknown"
