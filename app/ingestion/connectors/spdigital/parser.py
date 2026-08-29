"""SP Digital meta tag parser — extracts product data from VTEX standard meta tags."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class RawProductData:
    """Raw extracted data from SP Digital HTML, before NormalizedOffer mapping."""

    name: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    availability: bool | None = None
    brand: str | None = None
    mpn: str | None = None
    sku: str | None = None
    product_id: str | None = None
    product_url: str | None = None
    image_url: str | None = None
    images: list[str] = field(default_factory=list)
    condition: str | None = None


class SPDigitalParser:
    """Parses SP Digital product pages by extracting VTEX meta tags."""

    def parse(self, html: str) -> RawProductData:
        soup = BeautifulSoup(html, "html.parser")
        meta = self._extract_meta_tags(soup)
        return self._map_to_raw(meta, soup)

    def _extract_meta_tags(self, soup: BeautifulSoup) -> dict[str, str]:
        tags: dict[str, str] = {}
        for tag in soup.find_all("meta"):
            name = tag.get("name") or tag.get("property")
            content = tag.get("content")
            if name and content:
                tags[name.lower().strip()] = content.strip()
        return tags

    def _map_to_raw(self, meta: dict[str, str], soup: BeautifulSoup) -> RawProductData:
        name = self._clean_name(meta)
        price = self._parse_price(meta)
        currency = meta.get("product:price:currency") or meta.get("product:price:currency".replace(":", ":"))
        availability = self._parse_availability(meta)
        brand = meta.get("product:brand")
        mpn = meta.get("product:mfr_part_no")
        sku = meta.get("product:retailer_item_id")
        product_id = meta.get("product-id")
        product_url = self._resolve_url(meta)
        image_url = meta.get("og:image")
        images = self._extract_gallery(soup, image_url)
        condition = meta.get("product:condition")

        return RawProductData(
            name=name,
            price=price,
            currency=currency,
            availability=availability,
            brand=brand,
            mpn=mpn,
            sku=sku,
            product_id=product_id,
            product_url=product_url,
            image_url=image_url,
            images=images,
            condition=condition,
        )

    def _extract_gallery(self, soup: BeautifulSoup, og_image: str | None) -> list[str]:
        """Collect the product gallery images and normalize them to a full-size variant.

        SP Digital serves gallery thumbnails (.._thumbnail_256.jpg) plus the og:image
        (.._thumbnail_4096.jpg). Both share the same base path, so every thumbnail is
        upgraded to the 4096 variant.
        """
        pattern = re.compile(r"(https:)?//media\.spdigital\.cl/thumbnails/products/.+?_thumbnail_256\.jpg")
        images: list[str] = []
        for img in soup.find_all("img", src=pattern):
            src = img.get("src")
            if not src:
                continue
            if src.startswith("//"):
                src = f"https:{src}"
            normalized = src.replace("_thumbnail_256.jpg", "_thumbnail_4096.jpg")
            if normalized not in images:
                images.append(normalized)
        if og_image and og_image.startswith("http") and og_image not in images:
            images.insert(0, og_image)
        return images

    def _clean_name(self, meta: dict[str, str]) -> str | None:
        raw = meta.get("og:title") or meta.get("title")
        if not raw:
            return None
        cleaned = re.sub(r"\s*\|\s*SP Digital\s*$", "", raw).strip()
        return cleaned if cleaned else None

    def _parse_price(self, meta: dict[str, str]) -> Decimal | None:
        raw = meta.get("product:price:amount")
        if not raw:
            return None
        normalized = raw.replace(",", "").replace(".", "").strip()
        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None

    def _parse_availability(self, meta: dict[str, str]) -> bool | None:
        raw = meta.get("product:availability")
        if not raw:
            return None
        lower = raw.lower().strip()
        if "in stock" in lower or "in_stock" in lower or "available" in lower:
            return True
        if "out of stock" in lower or "out_of_stock" in lower or "unavailable" in lower:
            return False
        return None

    def _resolve_url(self, meta: dict[str, str]) -> str | None:
        raw = meta.get("og:url")
        if not raw:
            return None
        if raw.startswith("http"):
            return raw
        if raw.startswith("/"):
            return f"https://www.spdigital.cl{raw}"
        return raw
