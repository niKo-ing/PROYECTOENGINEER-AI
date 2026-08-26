"""Heuristic platform detection for e-commerce sites."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from app.ingestion.discovery.result import PlatformDetection


class PlatformDetector:
    """Non-invasive heuristic detection of e-commerce platforms."""

    def detect(
        self,
        soup: BeautifulSoup,
        meta_tags: dict[str, str],
        json_ld_data: list[dict[str, Any]],
        response_headers: dict[str, str] | None = None,
    ) -> PlatformDetection | None:
        html_str = str(soup)
        lower_html = html_str.lower()
        signals: list[str] = []
        scores: dict[str, float] = {}

        self._check_shopify(lower_html, meta_tags, response_headers, signals, scores)
        self._check_vtex(lower_html, meta_tags, signals, scores)
        self._check_nextjs(lower_html, soup, meta_tags, signals, scores)
        self._check_woocommerce(lower_html, meta_tags, signals, scores)

        if not scores:
            return None

        best_name = max(scores, key=lambda k: scores[k])
        best_score = min(scores[best_name], 1.0)
        platform_signals = [s for s in signals if best_name.lower() in s.lower()]

        if best_score < 0.3:
            return None

        return PlatformDetection(
            name=best_name, confidence=round(best_score, 2), signals=platform_signals
        )

    def _check_shopify(
        self,
        html: str,
        meta: dict[str, str],
        headers: dict[str, str] | None,
        signals: list[str],
        scores: dict[str, float],
    ) -> float:
        score = 0.0

        if "shopify" in html:
            score += 0.3
            signals.append("Shopify: 'shopify' found in HTML")

        if any("shopify" in v.lower() for v in meta.values()):
            score += 0.2
            signals.append("Shopify: found in meta tags")

        if headers:
            server = headers.get("server", "").lower()
            if "shopify" in server:
                score += 0.3
                signals.append(f"Shopify: server header = '{headers.get('server')}'")
            x_shard = headers.get("x-shopify-stage", "")
            if x_shard:
                score += 0.3
                signals.append(f"Shopify: x-shopify-stage header present")

        if "cdn.shopify.com" in html:
            score += 0.2
            signals.append("Shopify: CDN references found")

        if score > 0:
            scores["Shopify"] = min(score, 1.0)
        return score

    def _check_vtex(
        self,
        html: str,
        meta: dict[str, str],
        signals: list[str],
        scores: dict[str, float],
    ) -> float:
        score = 0.0

        if "vtex" in html.lower():
            score += 0.3
            signals.append("VTEX: 'vtex' found in HTML")

        if "vtexstore" in html.lower() or "vtex-search" in html.lower():
            score += 0.3
            signals.append("VTEX: VTEX-specific scripts found")

        if any("vtex" in v.lower() for v in meta.values()):
            score += 0.2
            signals.append("VTEX: found in meta tags")

        if "/api/catalog_system/" in html or "/api/io/" in html:
            score += 0.2
            signals.append("VTEX: API endpoints detected")

        if score > 0:
            scores["VTEX"] = min(score, 1.0)
        return score

    def _check_nextjs(
        self,
        html: str,
        soup: BeautifulSoup,
        meta: dict[str, str],
        signals: list[str],
        scores: dict[str, float],
    ) -> float:
        score = 0.0

        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data:
            score += 0.5
            signals.append("Next.js: __NEXT_DATA__ script found")

        if "nextjs" in html.lower() or "_next/static" in html:
            score += 0.3
            signals.append("Next.js: Next.js assets detected")

        if meta.get("generator", "").lower().startswith("next"):
            score += 0.3
            signals.append("Next.js: generator meta tag")

        if score > 0:
            scores["Next.js"] = min(score, 1.0)
        return score

    def _check_woocommerce(
        self,
        html: str,
        meta: dict[str, str],
        signals: list[str],
        scores: dict[str, float],
    ) -> float:
        score = 0.0

        if "woocommerce" in html.lower():
            score += 0.3
            signals.append("WooCommerce: 'woocommerce' found in HTML")

        if "wp-content" in html or "wp-includes" in html:
            score += 0.3
            signals.append("WooCommerce: WordPress assets detected")

        if any("woocommerce" in v.lower() for v in meta.values()):
            score += 0.2
            signals.append("WooCommerce: found in meta tags")

        if score > 0:
            scores["WooCommerce"] = min(score, 1.0)
        return score
