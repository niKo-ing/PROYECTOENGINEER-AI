"""StoreDiscovery — orchestrates URL analysis for structured product data."""

from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

from app.ingestion.discovery.extractors import (
    EmbeddedJSONExtractor,
    JSONLDExtractor,
    MetadataExtractor,
)
from app.ingestion.discovery.fetcher import FetchResult, HTTPFetcher
from app.ingestion.discovery.platform import PlatformDetector
from app.ingestion.discovery.result import DiscoveryResult
from app.ingestion.discovery.security import URLValidationError

logger = logging.getLogger(__name__)


class StoreDiscovery:
    """Analyzes a public product URL and extracts structured data signals."""

    def __init__(self) -> None:
        self._fetcher = HTTPFetcher()
        self._jsonld = JSONLDExtractor()
        self._embedded = EmbeddedJSONExtractor()
        self._metadata = MetadataExtractor()
        self._platform = PlatformDetector()

    def discover(self, url: str) -> DiscoveryResult:
        """Run full discovery pipeline on a URL."""
        try:
            fetch_result = self._fetcher.fetch(url)
        except URLValidationError as exc:
            return DiscoveryResult(
                url=url,
                errors=[str(exc)],
            )

        return self._analyze(url, fetch_result)

    def discover_html(self, url: str, html: str) -> DiscoveryResult:
        """Analyze pre-fetched HTML (for testing or when fetch is done externally)."""
        fetch_result = FetchResult(
            html=html,
            final_url=url,
            http_status=200,
            content_type="text/html",
        )
        return self._analyze(url, fetch_result)

    def _analyze(self, url: str, fetch_result: FetchResult) -> DiscoveryResult:
        warnings: list[str] = []
        errors: list[str] = list(fetch_result.errors) if hasattr(fetch_result, 'errors') else []

        if fetch_result.http_status >= 400:
            errors.append(f"HTTP {fetch_result.http_status}")

        if "text/html" not in fetch_result.content_type and "xhtml" not in fetch_result.content_type:
            warnings.append(
                f"Content-Type inesperado: {fetch_result.content_type!r}. "
                "Es posible que la página requiera JavaScript."
            )

        soup = BeautifulSoup(fetch_result.html, "html.parser")

        requires_js = self._detect_requires_js(soup, fetch_result.html)
        if requires_js:
            warnings.append(
                "La página probablemente requiere JavaScript para mostrar contenido completo."
            )

        json_ld_items = self._jsonld.extract(soup)
        json_ld_products = self._jsonld.find_products(json_ld_items)
        json_ld_offers = self._jsonld.find_offers(json_ld_items)

        embedded_items = self._embedded.extract(soup)
        meta_tags = self._metadata.extract(soup)

        platform = self._platform.detect(
            soup, meta_tags, json_ld_items, None
        )

        title = meta_tags.get("title")

        product_data = self._merge_product_data(
            json_ld_products, json_ld_offers, embedded_items, meta_tags
        )

        structured_sources: list[str] = []
        if json_ld_items:
            structured_sources.append("json-ld")
        if embedded_items:
            structured_sources.append("embedded-json")
        if meta_tags:
            structured_sources.append("meta-tags")

        return DiscoveryResult(
            url=url,
            final_url=fetch_result.final_url,
            http_status=fetch_result.http_status,
            content_type=fetch_result.content_type,
            title=title,
            detected_platform=platform,
            json_ld_found=bool(json_ld_items),
            json_ld_product_found=bool(json_ld_products),
            json_ld_offer_found=bool(json_ld_offers),
            embedded_json_found=bool(embedded_items),
            meta_data_found=bool(meta_tags),
            price_found=product_data.get("price") is not None,
            currency_found=product_data.get("currency") is not None,
            availability_found=product_data.get("availability") is not None,
            sku_found=product_data.get("sku") is not None,
            gtin_found=product_data.get("gtin") is not None,
            mpn_found=product_data.get("mpn") is not None,
            brand_found=product_data.get("brand") is not None,
            product_name_found=product_data.get("name") is not None,
            image_found=product_data.get("image") is not None,
            product_url_found=product_data.get("url") is not None,
            structured_sources=structured_sources,
            warnings=warnings,
            errors=errors,
            json_ld_data=json_ld_items,
            embedded_json_data=embedded_items,
            meta_tags=meta_tags,
        )

    def _merge_product_data(
        self,
        json_ld_products: list[dict[str, Any]],
        json_ld_offers: list[dict[str, Any]],
        embedded_items: list[dict[str, Any]],
        meta_tags: dict[str, str],
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}

        # Priority 1: JSON-LD product
        if json_ld_products:
            product = json_ld_products[0]
            self._fill_from_product(merged, product)

        # Priority 2: JSON-LD offers (fill gaps)
        if json_ld_offers:
            offer = json_ld_offers[0]
            self._fill_from_offer(merged, offer)

        # Priority 3: Embedded JSON (fill gaps)
        for item in embedded_items:
            self._fill_from_embedded(merged, item)
            if all(merged.get(k) is not None for k in ("name", "price", "currency")):
                break

        # Priority 4: Meta tags (fill remaining gaps)
        self._fill_from_meta(merged, meta_tags)

        return merged

    def _fill_from_product(self, target: dict[str, Any], product: dict[str, Any]) -> None:
        self._set_if_none(target, "name", product.get("name"))
        self._set_if_none(target, "sku", self._first_non_none(product, "sku", "productID"))
        self._set_if_none(target, "gtin", self._resolve_gtin(product))
        self._set_if_none(target, "mpn", product.get("mpn"))
        self._set_if_none(target, "brand", self._resolve_brand(product))
        self._set_if_none(target, "image", self._resolve_image(product))
        self._set_if_none(target, "url", product.get("url"))

    def _fill_from_offer(self, target: dict[str, Any], offer: dict[str, Any]) -> None:
        self._set_if_none(target, "price", self._resolve_price(offer))
        self._set_if_none(target, "currency", offer.get("priceCurrency"))
        avail = offer.get("availability")
        if avail is not None and target.get("availability") is None:
            target["availability"] = self._normalize_availability(avail)

    def _fill_from_embedded(self, target: dict[str, Any], item: dict[str, Any]) -> None:
        if "name" in item and target.get("name") is None:
            target["name"] = item["name"]
        if "price" in item and target.get("price") is None:
            target["price"] = item["price"]
        if "sku" in item and target.get("sku") is None:
            target["sku"] = item["sku"]
        if "brand" in item and target.get("brand") is None:
            target["brand"] = item["brand"]

    def _fill_from_meta(self, target: dict[str, Any], meta: dict[str, str]) -> None:
        if target.get("name") is None:
            self._set_if_none(target, "name", meta.get("og:title") or meta.get("title"))
        self._set_if_none(target, "price", self._parse_meta_price(meta))
        self._set_if_none(target, "currency", meta.get("product:price:currency"))
        self._set_if_none(target, "image", meta.get("og:image"))
        self._set_if_none(target, "url", meta.get("og:url") or meta.get("canonical"))
        self._set_if_none(target, "brand", meta.get("product:brand"))

    def _resolve_gtin(self, product: dict[str, Any]) -> str | None:
        for key in ("gtin", "gtin8", "gtin12", "gtin13", "gtin14", "ean", "isbn"):
            val = product.get(key)
            if val:
                return str(val)
        return None

    def _resolve_brand(self, product: dict[str, Any]) -> str | None:
        brand = product.get("brand")
        if isinstance(brand, str):
            return brand
        if isinstance(brand, dict):
            return brand.get("name")
        return None

    def _resolve_image(self, product: dict[str, Any]) -> str | None:
        img = product.get("image")
        if isinstance(img, str):
            return img
        if isinstance(img, list) and img:
            return img[0] if isinstance(img[0], str) else None
        return None

    def _resolve_price(self, offer: dict[str, Any]) -> Any:
        price = offer.get("price")
        if price is not None:
            return price
        low = offer.get("lowPrice")
        if low is not None:
            return low
        return None

    def _normalize_availability(self, value: str | bool) -> str:
        if isinstance(value, bool):
            return "in_stock" if value else "out_of_stock"
        lower = str(value).lower()
        if "instock" in lower or "in_stock" in lower or "available" in lower:
            return "in_stock"
        if "outofstock" in lower or "out_of_stock" in lower or "unavailable" in lower:
            return "out_of_stock"
        if "preorder" in lower:
            return "preorder"
        return lower

    def _parse_meta_price(self, meta: dict[str, str]) -> Any:
        raw = meta.get("product:price:amount")
        if raw is None:
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return raw

    def _detect_requires_js(self, soup: BeautifulSoup, html: str) -> bool:
        noscript_tags = soup.find_all("noscript")
        if len(noscript_tags) >= 3:
            return True
        return False

    @staticmethod
    def _set_if_none(d: dict, key: str, value: Any) -> None:
        if key not in d or d[key] is None:
            d[key] = value

    @staticmethod
    def _first_non_none(d: dict, *keys: str) -> Any:
        for k in keys:
            v = d.get(k)
            if v is not None:
                return v
        return None
