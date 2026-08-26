"""HTML extractors for the Discovery Tool: JSON-LD, embedded JSON, metadata."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_PRODUCT_TYPES = {"Product", "https://schema.org/Product", "ProductModel"}
_OFFER_TYPES = {"Offer", "https://schema.org/Offer", "AggregateOffer"}


class JSONLDExtractor:
    """Extracts and parses JSON-LD structured data from HTML."""

    def extract(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for script in soup.find_all("script", type="application/ld+json"):
            raw = script.string
            if not raw or not raw.strip():
                continue
            parsed = self._parse(raw.strip())
            if parsed is None:
                continue
            if isinstance(parsed, list):
                results.extend(parsed)
            else:
                results.append(parsed)
        return results

    def _parse(self, raw: str) -> Any:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            logger.debug("JSON-LD parse failed, skipping block")
            return None

    def find_products(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [i for i in items if self._is_product(i)]

    def find_offers(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        offers: list[dict[str, Any]] = []
        for item in items:
            offers.extend(self._extract_offers_from_item(item))
        return offers

    def _is_product(self, item: dict[str, Any]) -> bool:
        t = item.get("@type", "")
        if isinstance(t, list):
            return any(x in _PRODUCT_TYPES for x in t)
        return t in _PRODUCT_TYPES

    def _extract_offers_from_item(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        offers: list[dict[str, Any]] = []
        raw_offers = item.get("offers")
        if raw_offers is None:
            return offers
        if isinstance(raw_offers, dict):
            t = raw_offers.get("@type", "")
            if isinstance(t, list):
                is_offer = any(x in _OFFER_TYPES for x in t)
            else:
                is_offer = t in _OFFER_TYPES
            if is_offer:
                offers.append(raw_offers)
        elif isinstance(raw_offers, list):
            for o in raw_offers:
                if isinstance(o, dict):
                    t = o.get("@type", "")
                    if isinstance(t, list):
                        is_offer = any(x in _OFFER_TYPES for x in t)
                    else:
                        is_offer = t in _OFFER_TYPES
                    if is_offer:
                        offers.append(o)
        return offers


class EmbeddedJSONExtractor:
    """Conservatively extracts JSON embedded in script tags (not application/ld+json)."""

    _SUPPORTED_TYPES = {"application/json", "application/hydration-json"}

    def extract(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for script in soup.find_all("script"):
            t = script.get("type", "")
            if t in self._SUPPORTED_TYPES:
                results.extend(self._parse_scripts([script]))
                continue
            if not t and script.string:
                results.extend(self._parse_inline(script.string))
        return results

    def _parse_scripts(self, scripts: list) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for script in scripts:
            raw = script.string
            if not raw or not raw.strip():
                continue
            try:
                data = json.loads(raw.strip())
                if isinstance(data, dict):
                    results.append(data)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            results.append(item)
            except (json.JSONDecodeError, ValueError):
                continue
        return results

    def _parse_inline(self, raw: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        patterns = [
            r"window\.__INITIAL_STATE__\s*=\s*({.+?});",
            r"window\.__NEXT_DATA__\s*=\s*({.+?});",
            r"window\.__NUXT__\s*=\s*({.+?});",
        ]
        for pattern in patterns:
            match = re.search(pattern, raw, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    if isinstance(data, dict):
                        results.append(data)
                except (json.JSONDecodeError, ValueError):
                    continue
        return results


class MetadataExtractor:
    """Extracts OpenGraph and standard meta tags from HTML."""

    def extract(self, soup: BeautifulSoup) -> dict[str, str]:
        meta_tags: dict[str, str] = {}
        for tag in soup.find_all("meta"):
            self._extract_property(tag, meta_tags)
            self._extract_name(tag, meta_tags)
        self._extract_title(soup, meta_tags)
        return meta_tags

    def _extract_property(self, tag: dict, meta_tags: dict[str, str]) -> None:
        prop = tag.get("property") or tag.get("name")
        content = tag.get("content")
        if prop and content:
            meta_tags[prop.lower()] = content

    def _extract_name(self, tag: dict, meta_tags: dict[str, str]) -> None:
        name = tag.get("name")
        content = tag.get("content")
        if name and content and name.lower() not in meta_tags:
            meta_tags[name.lower()] = content

    def _extract_title(self, soup: BeautifulSoup, meta_tags: dict[str, str]) -> None:
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            meta_tags["title"] = title_tag.string.strip()
