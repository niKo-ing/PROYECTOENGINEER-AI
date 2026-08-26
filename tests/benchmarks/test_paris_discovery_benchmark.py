"""Benchmark: Category Listing vs Sitemap discovery for Paris.

Compares the two URL discovery strategies for paris.cl across all
configured P0 categories. Run with: pytest -m slow
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pytest

from app.ingestion.category import CategoryFilter, CategoryMapper
from app.ingestion.connectors.paris.url_discovery import (
    PARIS_CATEGORY_URLS,
    ParisURLDiscovery,
)
from app.ingestion.url_discovery import DiscoveryFetcher, dedupe_urls


PARIS_CATEGORY_MAP: dict[str, str] = {
    "Computación": "notebooks",
    "Procesadores": "procesadores",
    "Tarjetas de Video": "tarjetas-graficas",
    "Memoria RAM": "memoria-ram",
    "SSD": "almacenamiento-ssd",
    "Monitores": "monitores",
    "Placas Madre": "placas-madre",
    "Escritorio": "pcs-de-escritorio",
    "Celulares": "celulares",
    "Consolas": "consolas",
}

PARIS_SOURCE_CATEGORIES = list(PARIS_CATEGORY_MAP.keys())


@dataclass
class BenchmarkResult:
    """Metrics for a single discovery strategy run."""

    strategy: str
    urls_discovered: int = 0
    urls_unique: int = 0
    urls_filtered: int = 0
    urls_rejected: int = 0
    errors: int = 0
    duration_ms: int = 0
    requests: int = 0
    categories_covered: int = 0
    duplicates: int = 0
    category_details: dict[str, int] = field(default_factory=dict)


class ParisDiscoveryBenchmark:
    """Orchestrates category-listing vs sitemap benchmark for Paris."""

    def __init__(self):
        self.fetcher = DiscoveryFetcher(request_delay=0.5)
        self.mapper = CategoryMapper.build("www.paris.cl", PARIS_CATEGORY_MAP)
        self.cat_filter = CategoryFilter()
        self.discovery = ParisURLDiscovery()

    def run_category_listing(self) -> BenchmarkResult:
        """Discover URLs by crawling each P0 category listing page."""
        result = BenchmarkResult(strategy="category_listing")
        start = time.monotonic()

        all_urls: list[str] = []
        for source_cat in PARIS_SOURCE_CATEGORIES:
            try:
                candidates = self.discovery.discover_category(
                    source_category=source_cat,
                    category_mapper=self.mapper,
                    category_filter=self.cat_filter,
                    fetcher=self.fetcher,
                    max_urls=50,
                )
                cat_urls = [c.url for c in candidates]
                all_urls.extend(cat_urls)
                result.category_details[source_cat] = len(cat_urls)
                if cat_urls:
                    result.categories_covered += 1
            except Exception:
                result.errors += 1

        result.urls_discovered = len(all_urls)

        unique, dup_count = dedupe_urls(all_urls)
        result.urls_unique = len(unique)
        result.duplicates = dup_count

        categories_without_urls = sum(
            1 for count in result.category_details.values() if count == 0
        )
        result.urls_filtered = len(unique)
        result.urls_rejected = categories_without_urls

        result.requests = self.fetcher.request_count
        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result

    def run_sitemap(self) -> BenchmarkResult:
        """Discover URLs from the product sitemaps."""
        result = BenchmarkResult(strategy="sitemap")
        start = time.monotonic()

        try:
            candidates = self.discovery.discover_from_sitemap(
                fetcher=self.fetcher,
                max_urls=200,
                category_filter=self.cat_filter,
            )
            all_urls = [c.url for c in candidates]
            result.urls_discovered = len(all_urls)

            unique, dup_count = dedupe_urls(all_urls)
            result.urls_unique = len(unique)
            result.duplicates = dup_count
            result.urls_filtered = len(unique)
            result.urls_rejected = 0
            result.categories_covered = 1
            result.category_details["sitemap"] = len(unique)
        except Exception:
            result.errors += 1

        result.requests = self.fetcher.request_count
        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result

    def compare(self) -> dict[str, BenchmarkResult]:
        """Run both strategies and return results keyed by strategy name."""
        category_result = self.run_category_listing()
        sitemap_result = self.run_sitemap()
        return {
            "category_listing": category_result,
            "sitemap": sitemap_result,
        }


def format_benchmark_result(result: BenchmarkResult) -> str:
    """Format a BenchmarkResult as a readable multi-line string."""
    lines = [
        f"Strategy: {result.strategy}",
        f"  URLs discovered:  {result.urls_discovered}",
        f"  URLs unique:      {result.urls_unique}",
        f"  URLs filtered:    {result.urls_filtered}",
        f"  URLs rejected:    {result.urls_rejected}",
        f"  Duplicates:       {result.duplicates}",
        f"  Errors:           {result.errors}",
        f"  Duration (ms):    {result.duration_ms}",
        f"  HTTP requests:    {result.requests}",
        f"  Categories found: {result.categories_covered}",
    ]
    if result.category_details:
        lines.append("  Per-category:")
        for cat, count in result.category_details.items():
            lines.append(f"    {cat}: {count}")
    return "\n".join(lines)


def compare_strategies(
    category_result: BenchmarkResult,
    sitemap_result: BenchmarkResult,
) -> dict[str, str]:
    """Compare two strategy results and return a summary dict."""
    summary: dict[str, str] = {}

    summary["faster_strategy"] = (
        "category_listing"
        if category_result.duration_ms <= sitemap_result.duration_ms
        else "sitemap"
    )
    summary["more_urls"] = (
        "category_listing"
        if category_result.urls_unique >= sitemap_result.urls_unique
        else "sitemap"
    )
    summary["fewer_requests"] = (
        "category_listing"
        if category_result.requests <= sitemap_result.requests
        else "sitemap"
    )
    summary["fewer_errors"] = (
        "category_listing"
        if category_result.errors <= sitemap_result.errors
        else "sitemap"
    )

    cat_score = sum([
        1 if summary["faster_strategy"] == "category_listing" else 0,
        1 if summary["more_urls"] == "category_listing" else 0,
        1 if summary["fewer_requests"] == "category_listing" else 0,
        1 if summary["fewer_errors"] == "category_listing" else 0,
    ])
    sitemap_score = 4 - cat_score
    summary["recommended"] = (
        "category_listing" if cat_score >= sitemap_score else "sitemap"
    )
    summary["category_score"] = str(cat_score)
    summary["sitemap_score"] = str(sitemap_score)

    return summary


@pytest.mark.slow
def test_benchmark_category_listing_vs_sitemap():
    """Run both Paris discovery strategies and compare."""
    benchmark = ParisDiscoveryBenchmark()
    results = benchmark.compare()

    cat_result = results["category_listing"]
    sitemap_result = results["sitemap"]

    print("\n" + "=" * 60)
    print("PARIS DISCOVERY BENCHMARK: Category Listing vs Sitemap")
    print("=" * 60)
    print()
    print(format_benchmark_result(cat_result))
    print()
    print(format_benchmark_result(sitemap_result))
    print()
    print("-" * 60)
    summary = compare_strategies(cat_result, sitemap_result)
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print("=" * 60)

    assert cat_result.duration_ms >= 0
    assert sitemap_result.duration_ms >= 0
    assert cat_result.requests >= 0
    assert sitemap_result.requests >= 0


@pytest.mark.slow
def test_benchmark_determines_better_strategy():
    """Run benchmark and determine which strategy wins per category."""
    benchmark = ParisDiscoveryBenchmark()
    results = benchmark.compare()

    cat_result = results["category_listing"]
    sitemap_result = results["sitemap"]

    print("\n" + "=" * 60)
    print("CATEGORY-LEVEL STRATEGY RECOMMENDATION")
    print("=" * 60)

    for source_cat, slug in PARIS_CATEGORY_MAP.items():
        cat_count = cat_result.category_details.get(source_cat, 0)
        has_listing = slug in PARIS_CATEGORY_URLS
        recommendation = "category_listing" if has_listing else "sitemap"
        print(
            f"  {source_cat:20s} → {slug:20s}  "
            f"listing={cat_count:3d}  has_urls={str(has_listing):5s}  "
            f"→ {recommendation}"
        )

    print()
    summary = compare_strategies(cat_result, sitemap_result)
    print(f"  Overall recommended: {summary['recommended']}")
    print(
        f"  Score: category_listing={summary['category_score']}  "
        f"sitemap={summary['sitemap_score']}"
    )
    print("=" * 60)

    assert cat_result.urls_discovered >= 0
    assert sitemap_result.urls_discovered >= 0
    assert summary["recommended"] in ("category_listing", "sitemap")
