"""Tests for sitemap-based URL discovery."""

from unittest.mock import MagicMock

from app.ingestion.url_discovery import (
    DiscoveryFetcher,
    DiscoveryReport,
    parse_sitemap_index,
    parse_sitemap_urls,
)
from app.ingestion.category import CategoryFilter, CategoryMapper
from app.ingestion.connectors.spdigital.url_discovery import SPDigitalURLDiscovery
from app.ingestion.connectors.paris.url_discovery import ParisURLDiscovery


SPDIGITAL_SITEMAP_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.spdigital.cl/notebooks/lenovo/p</loc></url>
  <url><loc>https://www.spdigital.cl/notebooks/hp/p</loc></url>
  <url><loc>https://www.spdigital.cl/celulares/samsung/p</loc></url>
  <url><loc>https://www.spdigital.cl/celulares/apple/p</loc></url>
  <url><loc>https://www.spdigital.cl/categories/notebooks</loc></url>
</urlset>"""

PARIS_SITEMAP_INDEX_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex>
  <sitemap><loc>https://www.paris.cl/sitemap-product-1.xml</loc></sitemap>
  <sitemap><loc>https://www.paris.cl/sitemap-category-1.xml</loc></sitemap>
</sitemapindex>"""

PARIS_SITEMAP_PRODUCTS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.paris.cl/notebook-hp-123.html</loc></url>
  <url><loc>https://www.paris.cl/celular-samsung-456.html</loc></url>
  <url><loc>https://www.paris.cl/notebook-lenovo-789.html</loc></url>
  <url><loc>https://www.paris.cl/audifonos-sony-012.html</loc></url>
</urlset>"""


def _make_fetcher(responses=None):
    responses = responses or {}
    fetcher = MagicMock(spec=DiscoveryFetcher)
    fetcher.request_count = 0

    def _fetch(url, *, headers=None):
        fetcher.request_count += 1
        for pattern, body in responses.items():
            if pattern in url:
                return body
        raise ConnectionError(f"no mock for {url}")

    fetcher.fetch.side_effect = _fetch
    return fetcher


def _make_mapper(source, target):
    return CategoryMapper.build("test.store.cl", {source: target})


def _make_filter(allowed_slugs):
    return CategoryFilter(whitelist_slugs=frozenset(allowed_slugs))


class TestSitemapXmlParsing:
    def test_parse_sitemap_index_returns_child_sitemaps(self):
        result = parse_sitemap_index(PARIS_SITEMAP_INDEX_XML)
        assert result == [
            "https://www.paris.cl/sitemap-product-1.xml",
            "https://www.paris.cl/sitemap-category-1.xml",
        ]

    def test_parse_sitemap_index_excludes_non_xml_locs(self):
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex>
  <sitemap><loc>https://example.com/sitemap-1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/page/1</loc></sitemap>
</sitemapindex>"""
        result = parse_sitemap_index(xml)
        assert result == ["https://example.com/sitemap-1.xml"]

    def test_parse_sitemap_index_empty(self):
        assert parse_sitemap_index("") == []

    def test_parse_sitemap_urls_returns_all_locs(self):
        result = parse_sitemap_urls(SPDIGITAL_SITEMAP_XML)
        assert len(result) == 5
        assert "https://www.spdigital.cl/notebooks/lenovo/p" in result
        assert "https://www.spdigital.cl/celulares/samsung/p" in result
        assert "https://www.spdigital.cl/categories/notebooks" in result

    def test_parse_sitemap_urls_empty(self):
        assert parse_sitemap_urls("") == []


class TestSPDigitalSitemapDiscovery:
    def _make_discovery(self):
        return SPDigitalURLDiscovery(category_keywords={
            "notebooks": ["notebook"],
            "celulares": ["celular", "samsung", "apple"],
        })

    def test_get_sitemap_urls_caching(self):
        fetcher = _make_fetcher({"/sitemap.xml": SPDIGITAL_SITEMAP_XML})
        discovery = self._make_discovery()

        first = discovery._get_sitemap_urls(fetcher)
        second = discovery._get_sitemap_urls(fetcher)

        assert first == second
        assert len(first) == 4
        assert fetcher.fetch.call_count == 1

    def test_filter_by_keywords(self):
        discovery = self._make_discovery()
        urls = [
            "https://www.spdigital.cl/notebooks/lenovo/p",
            "https://www.spdigital.cl/notebooks/hp/p",
            "https://www.spdigital.cl/celulares/samsung/p",
            "https://www.spdigital.cl/celulares/apple/p",
            "https://www.spdigital.cl/monitores/dell/p",
        ]

        notebooks = discovery._filter_by_keywords(urls, "notebooks")
        assert len(notebooks) == 2
        assert all("notebooks" in u for u in notebooks)

        celulares = discovery._filter_by_keywords(urls, "celulares")
        assert len(celulares) == 2
        assert all("celulares" in u for u in celulares)

    def test_filter_by_keywords_unknown_category_returns_all(self):
        discovery = self._make_discovery()
        urls = ["https://www.spdigital.cl/a/b/p"]
        assert discovery._filter_by_keywords(urls, "unknown-slug") == urls

    def test_discover_category_prefers_sitemap(self):
        fetcher = _make_fetcher({"/sitemap.xml": SPDIGITAL_SITEMAP_XML})
        mapper = _make_mapper("Notebooks", "notebooks")
        cat_filter = _make_filter({"notebooks"})
        discovery = self._make_discovery()

        results = discovery.discover_category(
            source_category="Notebooks",
            category_mapper=mapper,
            category_filter=cat_filter,
            fetcher=fetcher,
            max_urls=10,
        )

        assert len(results) == 2
        assert all(r.source == "spdigital:sitemap" for r in results)
        assert all(r.mapped_category == "notebooks" for r in results)
        assert fetcher.fetch.call_count == 1

    def test_discover_category_max_urls_applied(self):
        fetcher = _make_fetcher({"/sitemap.xml": SPDIGITAL_SITEMAP_XML})
        mapper = _make_mapper("Celulares", "celulares")
        cat_filter = _make_filter({"celulares"})
        discovery = self._make_discovery()

        results = discovery.discover_category(
            source_category="Celulares",
            category_mapper=mapper,
            category_filter=cat_filter,
            fetcher=fetcher,
            max_urls=1,
        )

        assert len(results) == 1

    def test_sitemap_fetch_failure_returns_empty(self):
        fetcher = _make_fetcher()
        discovery = self._make_discovery()

        result = discovery._get_sitemap_urls(fetcher)
        assert result == []

    def test_discover_from_sitemap_max_urls_zero_returns_all(self):
        fetcher = _make_fetcher({"/sitemap.xml": SPDIGITAL_SITEMAP_XML})
        discovery = self._make_discovery()

        results = discovery.discover_from_sitemap(fetcher, max_urls=0)
        assert len(results) == 4

    def test_discover_from_sitemap_category_filter(self):
        fetcher = _make_fetcher({"/sitemap.xml": SPDIGITAL_SITEMAP_XML})
        cat_filter = _make_filter({"notebooks"})
        discovery = self._make_discovery()

        results = discovery.discover_from_sitemap(
            fetcher, max_urls=0, category_filter=cat_filter,
        )
        assert len(results) == 2
        assert all("notebooks" in r.url for r in results)

    def test_discover_from_sitemap_fetch_failure(self):
        fetcher = _make_fetcher()
        discovery = self._make_discovery()

        results = discovery.discover_from_sitemap(fetcher)
        assert results == []


class TestParisSitemapDiscovery:
    def _build_fetcher(self):
        return _make_fetcher({
            "/sitemap_index.xml": PARIS_SITEMAP_INDEX_XML,
            "/sitemap-product-1.xml": PARIS_SITEMAP_PRODUCTS_XML,
        })

    def test_discover_from_sitemap_max_urls_limit(self):
        fetcher = self._build_fetcher()
        discovery = ParisURLDiscovery()

        results = discovery.discover_from_sitemap(fetcher, max_urls=2)
        assert len(results) == 2

    def test_discover_from_sitemap_category_filter(self):
        fetcher = self._build_fetcher()
        cat_filter = MagicMock(spec=CategoryFilter)
        discovery = ParisURLDiscovery()

        def _check(slug):
            from app.ingestion.category import FilterResult
            if slug in ("notebook",):
                return FilterResult(allowed=True, slug=slug)
            return FilterResult(allowed=False, slug=slug)

        cat_filter.check.side_effect = _check

        results = discovery.discover_from_sitemap(
            fetcher, max_urls=0, category_filter=cat_filter,
        )
        urls = [r.url for r in results]
        assert len(results) == 2
        assert all("notebook" in u for u in urls)

    def test_discover_from_sitemap_fetch_failure(self):
        fetcher = _make_fetcher()
        discovery = ParisURLDiscovery()

        results = discovery.discover_from_sitemap(fetcher)
        assert results == []


class TestDiscoveryReportListingRequests:
    def test_listing_requests_field_exists(self):
        report = DiscoveryReport()
        assert hasattr(report, "listing_requests")
        assert report.listing_requests == 0

    def test_listing_requests_set_after_discover(self):
        responses = {
            "/sitemap.xml": SPDIGITAL_SITEMAP_XML,
            "/notebooks/": "<html><body></body></html>",
        }
        fetcher = _make_fetcher(responses)
        mapper = _make_mapper("Notebooks", "notebooks")
        cat_filter = _make_filter({"notebooks"})

        discovery = SPDigitalURLDiscovery()
        report = discovery.discover(
            categories=["Notebooks"],
            category_mapper=mapper,
            category_filter=cat_filter,
            fetcher=fetcher,
        )

        assert report.listing_requests == fetcher.request_count
        assert report.listing_requests > 0
