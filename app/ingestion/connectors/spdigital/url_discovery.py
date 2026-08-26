"""SP Digital URL Discovery — discovers product URLs from VTEX category pages.

SP Digital runs on VTEX. Product URLs follow the pattern:
    /{slug}/{slug}/{product-slug}/p

Category pages contain product links that can be extracted from HTML.

Note: Category pages return 403 (VTEX WAF). Discovery uses:
1. Category pages (fallback when available)
2. Sitemap-based discovery (primary: /sitemap.xml is accessible)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app.ingestion.category import CategoryFilter, CategoryMapper
from app.ingestion.url_discovery import (
    DiscoveredURL,
    DiscoveryFetcher,
    FlatSitemapStream,
    URLDiscovery,
    batched_urls,
    dedupe_urls,
    normalize_url,
    parse_sitemap_urls,
)


# VTEX category URL mapping: internal_slug → listing page URLs on spdigital.cl
SPDIGITAL_CATEGORY_URLS: dict[str, list[str]] = {
    "notebooks": [
        "https://www.spdigital.cl/notebooks/",
        "https://www.spdigital.cl/notebooks/notebooks-gaming/",
    ],
    "procesadores": [
        "https://www.spdigital.cl/procesadores/",
        "https://www.spdigital.cl/procesadores/procesadores-amd/",
        "https://www.spdigital.cl/procesadores/procesadores-intel/",
    ],
    "tarjetas-graficas": [
        "https://www.spdigital.cl/tarjetas-de-video/",
        "https://www.spdigital.cl/tarjetas-de-video/tarjetas-de-video-nvidia/",
        "https://www.spdigital.cl/tarjetas-de-video/tarjetas-de-video-amd/",
    ],
    "memoria-ram": [
        "https://www.spdigital.cl/memoria-ram/",
        "https://www.spdigital.cl/memoria-ram/memoria-ram-ddr4/",
        "https://www.spdigital.cl/memoria-ram/memoria-ram-ddr5/",
    ],
    "almacenamiento-ssd": [
        "https://www.spdigital.cl/ssd/",
        "https://www.spdigital.cl/ssd/ssd-nvme/",
        "https://www.spdigital.cl/ssd/ssd-sata/",
    ],
    "monitores": [
        "https://www.spdigital.cl/monitores/",
        "https://www.spdigital.cl/monitores/monitores-gaming/",
    ],
    "placas-madre": [
        "https://www.spdigital.cl/placas-madre/",
        "https://www.spdigital.cl/placas-madre/placas-madre-amd/",
        "https://www.spdigital.cl/placas-madre/placas-madre-intel/",
    ],
    "pcs-de-escritorio": [
        "https://www.spdigital.cl/computadores-de-escritorio/",
    ],
    "celulares": [
        "https://www.spdigital.cl/celulares/",
    ],
    "consolas": [
        "https://www.spdigital.cl/consolas/",
        "https://www.spdigital.cl/consolas/playstation/",
        "https://www.spdigital.cl/consolas/xbox/",
        "https://www.spdigital.cl/consolas/nintendo/",
    ],
}

# Category keywords for sitemap filtering
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "notebooks": ["notebook", "laptop"],
    "procesadores": ["procesador", "amd", "intel", "ryzen", "core", "i3", "i5", "i7", "i9"],
    "tarjetas-graficas": ["tarjeta-de-video", "gpu", "geforce", "radeon", "nvidia", "rtx", "gtx"],
    "memoria-ram": ["memoria-ram", "ddr4", "ddr5"],
    "almacenamiento-ssd": ["ssd", "disco-de-estado", "nvme"],
    "monitores": ["monitor", "pantalla"],
    "placas-madre": ["placa-madre", "motherboard"],
    "pcs-de-escritorio": ["computador-de-escritorio", "pc-de-escritorio"],
    "celulares": ["celular", "telefono", "smartphone", "iphone", "galaxy"],
    "consolas": ["playstation", "xbox", "nintendo", "switch", "consola", "ps5", "ps4"],
}

SPDIGITAL_SITEMAP_URL = "https://www.spdigital.cl/sitemap.xml"


class SPDigitalURLDiscovery(URLDiscovery):
    """Discovers product URLs from SP Digital (VTEX).

    Uses sitemap as primary source (category pages blocked by VTEX WAF).
    Falls back to category pages if accessible.
    """

    store_name: str = "SP Digital"
    store_domain: str = "www.spdigital.cl"
    request_delay: float = 5.0  # robots.txt: Crawl-delay: 5

    def __init__(
        self,
        category_urls: dict[str, list[str]] | None = None,
        category_keywords: dict[str, list[str]] | None = None,
    ):
        self._category_urls = category_urls or SPDIGITAL_CATEGORY_URLS
        self._category_keywords = category_keywords or _CATEGORY_KEYWORDS
        self._sitemap_cache: list[str] | None = None

    def _get_sitemap_urls(self, fetcher: DiscoveryFetcher) -> list[str]:
        """Fetch and parse sitemap.xml (cached, for legacy callers).

        For large-scale discovery, prefer stream_sitemap_batches() which
        yields URLs lazily without holding all URLs in memory.
        """
        if self._sitemap_cache is not None:
            return self._sitemap_cache

        try:
            xml = fetcher.fetch(SPDIGITAL_SITEMAP_URL)
            all_urls = parse_sitemap_urls(xml)
            product_urls = [
                u for u in all_urls
                if u.startswith("https://www.spdigital.cl/")
                and not u.startswith("https://www.spdigital.cl/categories/")
                and u != "https://www.spdigital.cl/"
            ]
            self._sitemap_cache = product_urls
            return product_urls
        except Exception:
            return []

    def stream_sitemap_batches(
        self,
        fetcher: DiscoveryFetcher,
        batch_size: int = 500,
    ) -> "Generator[list[str], None, None]":
        """Yield batches of product URLs from sitemap without full materialization.

        SP Digital has a single flat sitemap.xml with ~66K URLs.
        Streams URLs lazily via FlatSitemapStream.

        Args:
            fetcher: HTTP client.
            batch_size: URLs per batch (default 500).

        Yields:
            Lists of up to batch_size product URLs.
        """
        def _is_product_url(url: str) -> bool:
            return (
                url.startswith("https://www.spdigital.cl/")
                and not url.startswith("https://www.spdigital.cl/categories/")
                and url != "https://www.spdigital.cl/"
            )

        stream = FlatSitemapStream(
            fetcher,
            SPDIGITAL_SITEMAP_URL,
            url_filter=_is_product_url,
        )
        yield from batched_urls(stream, batch_size=batch_size)

    def _filter_by_keywords(
        self,
        urls: list[str],
        category: str,
    ) -> list[str]:
        """Filter URLs by category keywords in the path."""
        keywords = self._category_keywords.get(category, [])
        if not keywords:
            return urls

        filtered: list[str] = []
        for url in urls:
            path = url.lower()
            if any(kw in path for kw in keywords):
                filtered.append(url)
        return filtered

    def discover_category(
        self,
        source_category: str,
        category_mapper: CategoryMapper,
        category_filter: CategoryFilter,
        fetcher: DiscoveryFetcher,
        max_urls: int = 20,
    ) -> list[DiscoveredURL]:
        # Map source category → internal slug
        mapped_slug = category_mapper.map(source_category)
        if mapped_slug is None:
            return []

        # Check filter
        filter_result = category_filter.check(mapped_slug)
        if not filter_result.allowed:
            return []

        # Strategy 1: Sitemap-based (primary for SP Digital)
        sitemap_urls = self._get_sitemap_urls(fetcher)
        if sitemap_urls:
            filtered_urls = self._filter_by_keywords(sitemap_urls, mapped_slug)
            limited = filtered_urls[:max_urls]
            now = datetime.now(timezone.utc)
            return [
                DiscoveredURL(
                    url=url,
                    source="spdigital:sitemap",
                    source_category=source_category,
                    mapped_category=mapped_slug,
                    discovered_at=now,
                    metadata={"sitemap_total": len(sitemap_urls)},
                )
                for url in limited
            ]

        # Strategy 2: Category pages (fallback)
        listing_urls = self._category_urls.get(mapped_slug, [])
        if not listing_urls:
            return []

        all_product_urls: list[str] = []
        last_listing_url = listing_urls[0]

        for listing_url in listing_urls:
            try:
                html = fetcher.fetch(listing_url)
                product_urls = self._extract_product_urls(html)
                all_product_urls.extend(product_urls)
                last_listing_url = listing_url
            except Exception:
                continue

        # Dedupe
        unique_urls, _ = dedupe_urls(all_product_urls)

        # Limit
        limited = unique_urls[:max_urls]

        now = datetime.now(timezone.utc)

        return [
            DiscoveredURL(
                url=url,
                source="spdigital:category_page",
                source_category=source_category,
                mapped_category=mapped_slug,
                discovered_at=now,
                metadata={"listing_url": last_listing_url},
            )
            for url in limited
        ]

    def discover_from_sitemap(
        self,
        fetcher: DiscoveryFetcher,
        max_urls: int = 200,
        category_filter: CategoryFilter | None = None,
    ) -> list[DiscoveredURL]:
        """Discover all product URLs from sitemap (unfiltered or filtered).

        Uses streaming batching to avoid materializing all 66K URLs in memory.
        Stops after collecting max_urls eligible URLs.

        Args:
            fetcher: HTTP client.
            max_urls: Maximum URLs to return (0 = unlimited).
            category_filter: Optional filter to apply.

        Returns:
            List of DiscoveredURL candidates from sitemap.
        """
        collected: list[str] = []
        seen_normalized: set[str] = set()

        for batch in self.stream_sitemap_batches(fetcher, batch_size=500):
            for url in batch:
                if max_urls > 0 and len(collected) >= max_urls:
                    break

                # Dedupe inline
                norm = normalize_url(url)
                if norm in seen_normalized:
                    continue
                seen_normalized.add(norm)

                # Apply category filter if provided
                if category_filter is not None:
                    path = url.replace("https://www.spdigital.cl/", "")
                    slug = path.split("/")[0] if "/" in path else path.replace("/p", "")
                    result = category_filter.check(slug)
                    if not result.allowed:
                        continue

                collected.append(url)
            else:
                continue
            break

        now = datetime.now(timezone.utc)

        return [
            DiscoveredURL(
                url=url,
                source="spdigital:sitemap",
                source_category="all",
                mapped_category=None,
                discovered_at=now,
                metadata={"streaming": True},
            )
            for url in collected
        ]

    @staticmethod
    def _extract_product_urls(html: str) -> list[str]:
        """Extract product URLs from VTEX category page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []

        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if "/p" in href or href.endswith("/p"):
                if href.startswith("/"):
                    full_url = f"https://www.spdigital.cl{href}"
                elif href.startswith("http"):
                    full_url = href
                else:
                    full_url = f"https://www.spdigital.cl/{href}"
                urls.append(full_url)

        # VTEX product grid patterns
        for tag in soup.find_all("div", class_=re.compile(r"product|item|card", re.I)):
            for link in tag.find_all("a", href=True):
                href = link["href"]
                if "/p" in href or href.endswith("/p"):
                    if href.startswith("/"):
                        full_url = f"https://www.spdigital.cl{href}"
                    elif href.startswith("http"):
                        full_url = href
                    else:
                        full_url = f"https://www.spdigital.cl/{href}"
                    urls.append(full_url)

        return urls
