"""Paris RSC parser — extracts product data from Next.js React Server Component payloads."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class RawProductData:
    """Raw extracted data from Paris RSC payload."""

    name: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    availability: bool | None = None
    brand: str | None = None
    sku: str | None = None
    gtin: str | None = None
    mpn: str | None = None
    product_id: str | None = None
    product_url: str | None = None
    image_url: str | None = None
    images: list[str] = field(default_factory=list)
    description: str | None = None
    seller: str | None = None
    sources: list[str] = field(default_factory=list)


class ParisRSCParser:
    """Parses Paris product pages by extracting JSON-LD from Next.js RSC payloads."""

    _RSC_CHUNK_RE = re.compile(
        r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', re.DOTALL
    )
    _SCHEMA_PRODUCT = re.compile(r'"@type"\s*:\s*"Product"')
    _MASTER_VARIANT_RE = re.compile(r'"masterVariant"\s*:\s*\{')
    _PRODUCT_KEY_RE = re.compile(r'"key"\s*:\s*"(\d+)"')

    def parse(self, html: str) -> RawProductData:
        chunks = self._extract_chunks(html)
        jsonld = self._find_jsonld_product(chunks)
        rsc_product = self._find_rsc_product(chunks)

        if jsonld is not None:
            result = self._from_jsonld(jsonld)
            if rsc_product is not None:
                rsc = self._from_rsc_product(rsc_product)
                return self._merge(result, rsc)
            return result

        if rsc_product is not None:
            return self._from_rsc_product(rsc_product)

        return RawProductData()

    def _extract_chunks(self, html: str) -> list[str]:
        chunks: list[str] = []
        for match in self._RSC_CHUNK_RE.finditer(html):
            raw = match.group(1)
            chunks.append(self._unescape_js(raw))
        return chunks

    @staticmethod
    def _unescape_js(s: str) -> str:
        result: list[str] = []
        i = 0
        length = len(s)
        while i < length:
            if s[i] == "\\" and i + 1 < length:
                c = s[i + 1]
                if c == '"':
                    result.append('"')
                    i += 2
                elif c == "\\":
                    result.append("\\")
                    i += 2
                elif c == "n":
                    result.append("\n")
                    i += 2
                elif c == "t":
                    result.append("\t")
                    i += 2
                elif c == "r":
                    result.append("\r")
                    i += 2
                elif c == "u" and i + 5 < length:
                    hex_part = s[i + 2 : i + 6]
                    try:
                        result.append(chr(int(hex_part, 16)))
                        i += 6
                    except ValueError:
                        result.append(s[i])
                        i += 1
                else:
                    result.append(s[i + 1])
                    i += 2
            else:
                result.append(s[i])
                i += 1
        return "".join(result)

    @staticmethod
    def _merge(primary: RawProductData, secondary: RawProductData) -> RawProductData:
        return RawProductData(
            name=primary.name or secondary.name,
            price=primary.price or secondary.price,
            currency=primary.currency or secondary.currency,
            availability=primary.availability
            if primary.availability is not None
            else secondary.availability,
            brand=primary.brand or secondary.brand,
            sku=primary.sku or secondary.sku,
            gtin=primary.gtin or secondary.gtin,
            mpn=primary.mpn or secondary.mpn,
            product_id=primary.product_id or secondary.product_id,
            product_url=primary.product_url or secondary.product_url,
            image_url=primary.image_url or secondary.image_url,
            images=ParisRSCParser._dedupe(primary.images + secondary.images),
            description=primary.description or secondary.description,
            seller=primary.seller or secondary.seller,
            sources=primary.sources + secondary.sources,
        )

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _find_jsonld_product(self, chunks: list[str]) -> dict[str, Any] | None:
        for chunk in chunks:
            if not self._SCHEMA_PRODUCT.search(chunk):
                continue
            try:
                data = json.loads(chunk)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
        return None

    def _find_rsc_product(self, chunks: list[str]) -> dict[str, Any] | None:
        for chunk in chunks:
            if not self._MASTER_VARIANT_RE.search(chunk):
                continue
            product = self._extract_product_from_rsc(chunk)
            if product is not None:
                return product
        return None

    def _extract_product_from_rsc(self, chunk: str) -> dict[str, Any] | None:
        match = re.search(r'"product"\s*:\s*(\{)', chunk)
        if not match:
            return None
        start = match.start(1)
        depth = 0
        for i in range(start, len(chunk)):
            if chunk[i] == "{":
                depth += 1
            elif chunk[i] == "}":
                depth -= 1
                if depth == 0:
                    raw = chunk[start : i + 1]
                    try:
                        return json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        return None
        return None

    def _from_jsonld(self, data: dict[str, Any]) -> RawProductData:
        name = data.get("name")
        brand = self._extract_brand(data)
        offers = data.get("offers", [])
        if isinstance(offers, dict):
            offers = [offers]

        price, currency, availability, seller, offer_url = self._best_offer(offers)
        gtin = self._extract_gtin(data)
        mpn = data.get("mpn")
        sku = data.get("sku") or data.get("productID")
        image_url = self._extract_image(data)
        images = self._extract_images(data)
        product_url = offer_url or data.get("url")
        description = data.get("description")

        return RawProductData(
            name=name,
            price=price,
            currency=currency,
            availability=availability,
            brand=brand,
            sku=sku,
            gtin=gtin,
            mpn=mpn,
            product_id=sku,
            product_url=product_url,
            image_url=image_url,
            images=images,
            description=description,
            seller=seller,
            sources=["json-ld"],
        )

    def _from_rsc_product(self, data: dict[str, Any]) -> RawProductData:
        name = data.get("name")
        brand = data.get("brand")
        sku = None
        price = None
        currency = None
        image_url = None
        image_urls: list[str] = []

        mv = data.get("masterVariant", {})
        if isinstance(mv, dict):
            sku = mv.get("sku")
            prices = mv.get("prices", {})
            if isinstance(prices, dict):
                offer_price = prices.get("offer", {})
                regular = prices.get("regular", {})
                price_obj = offer_price if offer_price else regular
                value = price_obj.get("value", {}) if isinstance(price_obj, dict) else {}
                cent = value.get("centAmount")
                if cent is not None:
                    try:
                        price = Decimal(str(cent))
                    except (InvalidOperation, ValueError):
                        pass
                currency = value.get("currencyCode")
            images = mv.get("images", [])
            if isinstance(images, list):
                for image in images:
                    if isinstance(image, dict) and isinstance(image.get("url"), str):
                        image_urls.append(image["url"])
            image_url = image_urls[0] if image_urls else None

        product_url = None
        slug = data.get("slug")
        key = data.get("key")
        if slug and key:
            product_url = f"https://www.paris.cl/{slug}-{key}.html"
        elif slug:
            product_url = f"https://www.paris.cl/{slug}.html"

        availability = True if price is not None else None

        return RawProductData(
            name=name,
            price=price,
            currency=currency or "CLP",
            availability=availability,
            brand=brand,
            sku=sku,
            product_id=key or sku,
            product_url=product_url,
            image_url=image_url,
            images=image_urls,
            sources=["rsc-product"],
        )

    def _best_offer(
        self, offers: list[dict[str, Any]]
    ) -> tuple[Decimal | None, str | None, bool | None, str | None, str | None]:
        if not offers:
            return None, None, None, None, None

        in_stock = [
            o
            for o in offers
            if "InStock" in str(o.get("availability", ""))
        ]
        candidates = in_stock if in_stock else offers

        best = candidates[0]
        best_price = self._parse_price(best.get("price"))
        for o in candidates[1:]:
            price = self._parse_price(o.get("price"))
            if price is not None and (best_price is None or price < best_price):
                best = o
                best_price = price

        price = self._parse_price(best.get("price"))
        currency = best.get("priceCurrency")
        avail_raw = str(best.get("availability", ""))
        availability = "InStock" in avail_raw if avail_raw else None
        seller_obj = best.get("seller", {})
        seller = seller_obj.get("name") if isinstance(seller_obj, dict) else None
        url = best.get("url")

        return price, currency, availability, seller, url

    def _extract_brand(self, data: dict[str, Any]) -> str | None:
        brand = data.get("brand")
        if isinstance(brand, str):
            return brand
        if isinstance(brand, dict):
            return brand.get("name")
        return None

    def _extract_gtin(self, data: dict[str, Any]) -> str | None:
        for key in ("gtin", "gtin8", "gtin12", "gtin13", "gtin14", "ean", "isbn"):
            val = data.get(key)
            if val:
                return str(val)
        return None

    def _extract_image(self, data: dict[str, Any]) -> str | None:
        img = data.get("image")
        if isinstance(img, str):
            return img
        if isinstance(img, list) and img:
            return img[0] if isinstance(img[0], str) else None
        images = data.get("images", [])
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                return first.get("url")
            if isinstance(first, str):
                return first
        return None

    def _extract_images(self, data: dict[str, Any]) -> list[str]:
        images: list[str] = []
        img = data.get("image")
        if isinstance(img, str):
            images.append(img)
        elif isinstance(img, list):
            images.extend(u for u in img if isinstance(u, str))
        for item in data.get("images", []):
            if isinstance(item, str):
                images.append(item)
            elif isinstance(item, dict):
                url = item.get("url")
                if isinstance(url, str):
                    images.append(url)
        return self._dedupe(images)

    def _parse_price(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
