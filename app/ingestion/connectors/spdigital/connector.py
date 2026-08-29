"""SP Digital StoreConnector — HTTP + meta tag extraction for VTEX pages."""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.ingestion.connectors import StoreConnector
from app.ingestion.connectors.spdigital.parser import RawProductData, SPDigitalParser
from app.ingestion.dto import NormalizedOffer
from app.models.catalog import StoreType


class SPDigitalConnector(StoreConnector):
    """Extracts product data from SP Digital (VTEX) via HTTP + meta tags."""

    store_name: str = "SP Digital"
    store_domain: str = "www.spdigital.cl"
    source_name: str = "spdigital:www.spdigital.cl"
    store_type: StoreType = StoreType.RETAILER
    max_concurrent: int = 3
    request_delay: float = 0.5

    def __init__(self, urls: list[str] | None = None, url_category_map: dict[str, str] | None = None) -> None:
        super().__init__()
        self._urls = urls or []
        self._parser = SPDigitalParser()
        if url_category_map:
            self.set_url_category_map(url_category_map)

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
        url = data.product_url or record.get("url", "")

        return NormalizedOffer(
            source=self.source_name,
            external_id=self._resolve_external_id(data),
            product_url=url,
            name=data.name or "Sin nombre",
            brand=data.brand,
            model=None,
            mpn=data.mpn,
            gtin=None,
            sku=data.sku,
            price=data.price or Decimal("0"),
            previous_price=None,
            currency=data.currency or "CLP",
            availability=data.availability if data.availability is not None else True,
            stock=self._map_stock(data.availability),
            image_url=data.image_url,
            images=data.images or None,
            description=None,
            category=record.get("category"),
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

        return self._record_with_category(url, data)

    @staticmethod
    def _resolve_external_id(data: RawProductData) -> str | None:
        if data.product_id:
            return data.product_id
        if data.sku:
            return data.sku
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
