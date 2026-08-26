"""Paris URL Discovery — discovers product URLs from Next.js category pages.

Paris uses Next.js with RSC. Category pages contain product cards
with links to product detail pages (/slug.html or /slug-key.html).

Strategy:
1. Fetch category listing page HTML (primary)
2. Sitemap-based discovery (alternative/complement)
3. Deduplicate and limit
"""

from __future__ import annotations

import re
from collections.abc import Generator
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app.ingestion.category import CategoryFilter, CategoryMapper
from app.ingestion.url_discovery import (
    DiscoveredURL,
    DiscoveryFetcher,
    SitemapStream,
    URLDiscovery,
    batched_urls,
    dedupe_urls,
    normalize_url,
    parse_sitemap_urls,
)


# Paris category URL mapping: internal_slug → listing page URLs on paris.cl
# Validated: all URLs return HTTP 200
PARIS_CATEGORY_URLS: dict[str, list[str]] = {
    "notebooks": [
        "https://www.paris.cl/tecnologia/computadores/notebooks/",
    ],
    "monitores": [
        "https://www.paris.cl/tecnologia/gamer/monitores/",
    ],
    "pcs-de-escritorio": [
        "https://www.paris.cl/tecnologia/computadores/torres/",
    ],
    "celulares": [
        "https://www.paris.cl/tecnologia/celulares/",
    ],
    "consolas": [
        "https://www.paris.cl/tecnologia/consolas-videojuegos/consolas/",
        "https://www.paris.cl/tecnologia/consolas-videojuegos/consolas-playstation/",
        "https://www.paris.cl/tecnologia/consolas-videojuegos/consolas-xbox/",
        "https://www.paris.cl/tecnologia/consolas-videojuegos/consolas-nintendo/",
    ],
}

# Regex for product URLs on Paris: ends with .html
_PARIS_PRODUCT_URL_RE = re.compile(r'href="(/[a-zA-Z0-9_-]+(?:-[a-zA-Z0-9_-]+)*\.html)"')


class ParisURLDiscovery(URLDiscovery):
    """Discovers product URLs from Paris (Next.js).

    Uses category pages as primary source (accessible, ~20-40 URLs each).
    Sitemap available as complement (1.9M URLs but flat, no category info).
    """

    store_name: str = "Paris"
    store_domain: str = "www.paris.cl"
    request_delay: float = 0.5

    def __init__(
        self,
        category_urls: dict[str, list[str]] | None = None,
    ):
        self._category_urls = category_urls or PARIS_CATEGORY_URLS
        self._sitemap_cache: list[str] | None = None

    def _get_sitemap_urls(self, fetcher: DiscoveryFetcher) -> list[str]:
        """Fetch and parse product sitemaps (cached, for legacy callers).

        For large-scale discovery, prefer stream_sitemap_batches() which
        yields URLs lazily without holding 1.9M URLs in memory.
        """
        if self._sitemap_cache is not None:
            return self._sitemap_cache

        try:
            index_xml = fetcher.fetch("https://www.paris.cl/sitemap_index.xml")
            child_sitemaps = parse_sitemap_urls(index_xml)
            product_sitemaps = [
                s for s in child_sitemaps
                if "product" in s.lower() or "page" in s.lower()
            ]
            all_urls: list[str] = []
            for sitemap_url in product_sitemaps:
                try:
                    xml = fetcher.fetch(sitemap_url)
                    urls = parse_sitemap_urls(xml)
                    all_urls.extend(urls)
                except Exception:
                    continue
            product_urls = [u for u in all_urls if u.endswith(".html")]
            self._sitemap_cache = product_urls
            return product_urls
        except Exception:
            return []

    def stream_sitemap_batches(
        self,
        fetcher: DiscoveryFetcher,
        batch_size: int = 500,
    ) -> "Generator[list[str], None, None]":
        """Yield batches of product URLs from sitemaps without full materialization.

        Paris has 38 product sitemaps with ~1.9M URLs. This streams them
        one child sitemap at a time, yielding batches of batch_size URLs.

        Args:
            fetcher: HTTP client.
            batch_size: URLs per batch (default 500).

        Yields:
            Lists of up to batch_size product URLs.
        """
        stream = SitemapStream(
            fetcher,
            "https://www.paris.cl/sitemap_index.xml",
            child_filter="product",
        )
        def _filtered() -> "Generator[str, None, None]":
            for url in stream:
                if url.endswith(".html"):
                    yield url

        yield from batched_urls(_filtered(), batch_size=batch_size)

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

        # Get category listing URLs
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
                source="paris:category_page",
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
        """Discover product URLs from sitemap (unfiltered or filtered).

        Uses streaming batching to avoid materializing all 1.9M URLs in memory.
        Stops after collecting max_urls eligible URLs.

        Note: Paris sitemaps are flat (no category info in URL path).
        Category filtering is approximate based on URL slug keywords.
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
                    path = url.replace("https://www.paris.cl/", "")
                    slug = path.split("-")[0] if "-" in path else path.replace(".html", "")
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
                source="paris:sitemap",
                source_category="all",
                mapped_category=None,
                discovered_at=now,
                metadata={"streaming": True},
            )
            for url in collected
        ]

    @staticmethod
    def _extract_product_urls(html: str) -> list[str]:
        """Extract product URLs from Paris category page HTML."""
        urls: list[str] = []

        # Method 1: Standard HTML links to .html pages
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            if re.search(r'/[a-zA-Z0-9_-]+(?:-[a-zA-Z0-9_-]+)*\.html$', href):
                if href.startswith("/"):
                    full_url = f"https://www.paris.cl{href}"
                elif href.startswith("http"):
                    full_url = href
                else:
                    continue
                urls.append(full_url)

        # Method 2: RSC chunks may contain product URLs
        for match in re.finditer(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html):
            chunk = match.group(1)
            # Unescape JS string
            chunk = chunk.replace('\\"', '"').replace("\\\\", "\\")
            for url_match in re.finditer(r'/(?:[a-zA-Z0-9_-]+-)?\d+\.html', chunk):
                url_path = url_match.group(0)
                full_url = f"https://www.paris.cl{url_path}"
                urls.append(full_url)

        return urls
