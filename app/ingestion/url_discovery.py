"""URL Discovery — discovers product candidate URLs within store categories.

This module is responsible ONLY for answering:
"¿Qué URLs de productos existen dentro de esta categoría?"

It does NOT persist products. The existing pipeline handles persistence.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
from typing import Any
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import httpx

from app.ingestion.category import CategoryFilter, CategoryMapper


# ── DiscoveredURL DTO ──────────────────────────────────────────────

@dataclass(frozen=True)
class DiscoveredURL:
    """A candidate product URL discovered from a store category page."""

    url: str
    source: str
    source_category: str
    mapped_category: str | None
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


# ── URL normalization ──────────────────────────────────────────────

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "ref_url",
    "source", "spm", "from", "shared", "share_id",
})


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication.

    - Ensures https
    - Removes trailing slash (except root path)
    - Removes tracking query params
    - Removes fragment
    - Normalizes host to lowercase
    """
    parsed = urlparse(url)

    # Force https
    scheme = "https"

    # Normalize host
    host = parsed.hostname or ""
    if host:
        host = host.lower()
        # Re-add port if non-standard
        if parsed.port and parsed.port not in (80, 443):
            host = f"{host}:{parsed.port}"

    # Rebuild netloc
    netloc = host

    # Normalize path
    path = parsed.path or "/"
    # Remove trailing slash (but not for root)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Filter tracking params
    query_params = parse_qs(parsed.query, keep_blank_values=False)
    filtered_params = {
        k: v for k, v in query_params.items()
        if k.lower() not in _TRACKING_PARAMS
    }
    query = urlencode(filtered_params, doseq=True) if filtered_params else ""

    # Rebuild URL (no fragment)
    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    return normalized


def dedupe_urls(urls: list[str]) -> tuple[list[str], int]:
    """Deduplicate URLs by normalized form. Returns (unique_urls, duplicate_count)."""
    seen: dict[str, str] = {}
    unique: list[str] = []
    duplicates = 0

    for url in urls:
        norm = normalize_url(url)
        if norm not in seen:
            seen[norm] = url
            unique.append(url)
        else:
            duplicates += 1

    return unique, duplicates


# ── URL batching (streaming) ───────────────────────────────────────

def batched_urls(
    urls: list[str] | Iterator[str],
    batch_size: int = 500,
) -> Generator[list[str], None, None]:
    """Yield URLs in fixed-size batches without materializing the full list.

    Works with both lists and generators. Used for large sitemaps
    (Paris ~1.9M URLs) to avoid holding everything in memory.

    Args:
        urls: Source of URLs (list or generator).
        batch_size: Number of URLs per batch.

    Yields:
        Lists of up to batch_size URLs.
    """
    batch: list[str] = []
    for url in urls:
        batch.append(url)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def iter_sitemap_urls(
    sitemap_urls: Iterator[str],
    *,
    domain: str = "",
    exclude_patterns: tuple[str, ...] = (),
) -> Generator[str, None, None]:
    """Filter and stream sitemap URLs lazily.

    Args:
        sitemap_urls: Generator yielding raw URLs from sitemap XML.
        domain: Optional domain to enforce (skip URLs from other domains).
        exclude_patterns: URL substrings to skip (e.g. /categories/).

    Yields:
        Filtered URLs one at a time.
    """
    for url in sitemap_urls:
        if domain and not url.startswith(domain):
            continue
        if any(p in url for p in exclude_patterns):
            continue
        yield url


class SitemapStream:
    """Iterates over a sitemap index, yielding URLs from child sitemaps lazily.

    Reads one child sitemap at a time, yielding its URLs before fetching
    the next. This keeps memory constant regardless of total URL count.

    Usage::

        stream = SitemapStream(fetcher, "https://example.com/sitemap_index.xml")
        for batch in batched_urls(stream, batch_size=500):
            process(batch)
    """

    def __init__(
        self,
        fetcher: "DiscoveryFetcher",
        sitemap_index_url: str,
        *,
        child_filter: str | None = None,
    ):
        self.fetcher = fetcher
        self.sitemap_index_url = sitemap_index_url
        self.child_filter = child_filter
        self._child_sitemaps: list[str] | None = None

    def _load_child_sitemaps(self) -> list[str]:
        if self._child_sitemaps is not None:
            return self._child_sitemaps
        try:
            xml = self.fetcher.fetch(self.sitemap_index_url)
            children = parse_sitemap_urls(xml)
            if self.child_filter:
                children = [s for s in children if self.child_filter in s.lower()]
            self._child_sitemaps = children
        except Exception:
            self._child_sitemaps = []
        return self._child_sitemaps

    def __iter__(self) -> Generator[str, None, None]:
        children = self._load_child_sitemaps()
        for child_url in children:
            try:
                xml = self.fetcher.fetch(child_url)
                for url in parse_sitemap_urls(xml):
                    yield url
            except Exception:
                continue

    def __len__(self) -> int:
        return len(self._load_child_sitemaps())


class FlatSitemapStream:
    """Streams URLs from a single flat sitemap.xml without full materialization.

    Uses re.finditer to extract <loc> tags lazily from fetched XML text.
    Memory usage is proportional to XML text size, not URL count.

    Usage::

        stream = FlatSitemapStream(fetcher, "https://example.com/sitemap.xml")
        for batch in batched_urls(stream, batch_size=500):
            process(batch)
    """

    _LOC_RE = re.compile(r"<loc>(.*?)</loc>")

    def __init__(
        self,
        fetcher: "DiscoveryFetcher",
        sitemap_url: str,
        *,
        url_filter: "Callable[[str], bool] | None" = None,
    ):
        self.fetcher = fetcher
        self.sitemap_url = sitemap_url
        self.url_filter = url_filter
        self._xml_text: str | None = None

    def _load_xml(self) -> str:
        if self._xml_text is not None:
            return self._xml_text
        try:
            self._xml_text = self.fetcher.fetch(self.sitemap_url)
        except Exception:
            self._xml_text = ""
        return self._xml_text

    def __iter__(self) -> Generator[str, None, None]:
        xml = self._load_xml()
        if not xml:
            return
        for match in self._LOC_RE.finditer(xml):
            url = match.group(1)
            if self.url_filter is None or self.url_filter(url):
                yield url


# ── Sitemap parsing ────────────────────────────────────────────────

def parse_sitemap_index(xml_text: str) -> list[str]:
    """Parse a sitemap index and return child sitemap URLs."""
    urls = re.findall(r"<loc>(.*?)</loc>", xml_text)
    return [u for u in urls if u.endswith(".xml")]


def parse_sitemap_urls(xml_text: str) -> list[str]:
    """Parse a sitemap and return all listed URLs."""
    return re.findall(r"<loc>(.*?)</loc>", xml_text)


# ── HTTP fetcher for discovery ─────────────────────────────────────

class DiscoveryFetcher:
    """HTTP client with retry, backoff, and rate limiting for discovery."""

    def __init__(
        self,
        request_delay: float = 0.5,
        timeout: float = 15.0,
        max_retries: int = 3,
    ):
        self.request_delay = request_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.request_count = 0
        self._last_request_time: float = 0.0

    def fetch(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        """Fetch URL with retry, backoff, and rate limiting."""
        import time

        # Rate limiting
        elapsed = monotonic() - self._last_request_time
        if elapsed < self.request_delay and self._last_request_time > 0:
            time.sleep(self.request_delay - elapsed)

        default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
        }
        if headers:
            default_headers.update(headers)

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(
                    follow_redirects=True,
                    max_redirects=5,
                    timeout=self.timeout,
                ) as client:
                    response = client.get(url, headers=default_headers)
                    self.request_count += 1
                    self._last_request_time = monotonic()
                    response.raise_for_status()
                    return response.text
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    time.sleep(1.0 * (attempt + 1))

        raise last_exc  # type: ignore[misc]


# ── DiscoveryReport ────────────────────────────────────────────────

@dataclass
class DiscoveryReport:
    """Metrics and results from a URL discovery run."""

    categories_requested: int = 0
    categories_success: int = 0
    urls_discovered: int = 0
    duplicate_urls: int = 0
    rejected_unknown_category: int = 0
    rejected_blacklist: int = 0
    discovery_errors: int = 0
    listing_requests: int = 0
    duration_ms: int = 0
    candidates: list[DiscoveredURL] = field(default_factory=list)


# ── URLDiscovery ABC ───────────────────────────────────────────────

class URLDiscovery(ABC):
    """Base class for URL discovery implementations.

    Each store implements its own discovery strategy (category pages,
    sitemap, API, etc.).
    """

    store_name: str
    store_domain: str
    request_delay: float = 0.5  # seconds between HTTP requests (per robots.txt / Crawl-delay)

    @abstractmethod
    def discover_category(
        self,
        source_category: str,
        category_mapper: CategoryMapper,
        category_filter: CategoryFilter,
        fetcher: DiscoveryFetcher,
        max_urls: int = 20,
    ) -> list[DiscoveredURL]:
        """Discover product URLs for a single category.

        Args:
            source_category: Category name/path as used by the store.
            category_mapper: Maps source categories to internal taxonomy.
            category_filter: Filters by allowed categories.
            fetcher: HTTP client with rate limiting.
            max_urls: Maximum URLs to return per category.

        Returns:
            List of DiscoveredURL candidates.
        """

    def discover(
        self,
        categories: list[str],
        category_mapper: CategoryMapper,
        category_filter: CategoryFilter,
        fetcher: DiscoveryFetcher | None = None,
        max_urls_per_category: int = 20,
    ) -> DiscoveryReport:
        """Discover URLs for multiple categories. Orchestrates the full flow."""
        if fetcher is None:
            fetcher = DiscoveryFetcher()

        start = monotonic()
        report = DiscoveryReport(categories_requested=len(categories))

        for source_cat in categories:
            try:
                candidates = self.discover_category(
                    source_category=source_cat,
                    category_mapper=category_mapper,
                    category_filter=category_filter,
                    fetcher=fetcher,
                    max_urls=max_urls_per_category,
                )
                report.candidates.extend(candidates)
                report.urls_discovered += len(candidates)
                report.categories_success += 1
            except Exception as exc:
                report.discovery_errors += 1
                import logging
                logging.getLogger(__name__).warning(
                    "Discovery error for %s/%s: %s",
                    self.store_domain, source_cat, exc,
                )

        # Global dedup
        all_urls = [c.url for c in report.candidates]
        unique_urls, dup_count = dedupe_urls(all_urls)
        report.duplicate_urls = dup_count

        # Rebuild candidates list with deduped URLs
        if dup_count > 0:
            unique_set = set(normalize_url(u) for u in unique_urls)
            report.candidates = [
                c for c in report.candidates
                if normalize_url(c.url) in unique_set
            ]

        report.listing_requests = fetcher.request_count
        report.duration_ms = int((monotonic() - start) * 1000)

        return report
