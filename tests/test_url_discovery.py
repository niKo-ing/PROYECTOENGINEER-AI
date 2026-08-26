"""Tests for URL Discovery components."""

from unittest.mock import MagicMock

from app.ingestion.url_discovery import (
    DiscoveredURL,
    DiscoveryFetcher,
    DiscoveryReport,
    FlatSitemapStream,
    SitemapStream,
    batched_urls,
    dedupe_urls,
    normalize_url,
)
from app.ingestion.category import CategoryFilter, CategoryMapper
from app.ingestion.connectors.spdigital.url_discovery import (
    SPDIGITAL_CATEGORY_URLS,
    SPDigitalURLDiscovery,
)
from app.ingestion.connectors.paris.url_discovery import (
    PARIS_CATEGORY_URLS,
    ParisURLDiscovery,
)


# ══════════════════════════════════════════════════════════════════
#  URL NORMALIZATION
# ══════════════════════════════════════════════════════════════════


def test_normalize_trailing_slash():
    assert normalize_url("https://example.com/path/") == "https://example.com/path"
    assert normalize_url("https://example.com/") == "https://example.com/"


def test_normalize_fragment():
    assert normalize_url("https://example.com/path#section") == "https://example.com/path"


def test_normalize_tracking_params():
    url = "https://example.com/path?utm_source=google&id=123&utm_medium=cpc"
    result = normalize_url(url)
    assert "utm_source" not in result
    assert "utm_medium" not in result
    assert "id=123" in result


def test_normalize_http_to_https():
    assert normalize_url("http://example.com/path").startswith("https://")


def test_normalize_lowercase_host():
    assert normalize_url("https://EXAMPLE.COM/path") == "https://example.com/path"


def test_dedup_basic():
    urls = [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/a",
    ]
    unique, dups = dedupe_urls(urls)
    assert len(unique) == 2
    assert dups == 1


def test_dedup_normalized_equal():
    urls = [
        "https://example.com/path/",
        "https://example.com/path",
        "http://example.com/path",
    ]
    unique, dups = dedupe_urls(urls)
    assert len(unique) == 1
    assert dups == 2


def test_dedup_empty():
    unique, dups = dedupe_urls([])
    assert unique == []
    assert dups == 0


# ══════════════════════════════════════════════════════════════════
#  SP DIGITAL URL DISCOVERY (FIXTURES)
# ══════════════════════════════════════════════════════════════════

SPDIGITAL_HTML = """
<html><body>
<div class="product-card">
    <a href="/notebooks/notebook-hp-pavilion-15/p">HP Pavilion 15</a>
</div>
<div class="product-card">
    <a href="/notebooks/notebook-lenovo-ideapad-3/p">Lenovo IdeaPad 3</a>
</div>
<div class="product-item">
    <a href="/notebooks/notebook-dell-inspiron-15/p">Dell Inspiron 15</a>
</div>
<a href="/notebooks/notebook-asus-vivobook-14/p">Asus VivoBook</a>
<a href="/otros/no-es-producto">No producto</a>
</body></html>
"""


class MockFetcher(DiscoveryFetcher):
    def __init__(self, responses=None):
        super().__init__()
        self._responses = responses or {}

    def fetch(self, url, *, headers=None):
        self.request_count += 1
        for pattern, html in self._responses.items():
            if pattern in url:
                return html
        return "<html></html>"


def test_spdigital_discover_category():
    mapper = CategoryMapper.build("www.spdigital.cl", {"Notebooks": "notebooks"})
    cat_filter = CategoryFilter()
    fetcher = MockFetcher({"/notebooks/": SPDIGITAL_HTML})

    discovery = SPDigitalURLDiscovery()
    results = discovery.discover_category(
        source_category="Notebooks",
        category_mapper=mapper,
        category_filter=cat_filter,
        fetcher=fetcher,
        max_urls=10,
    )

    urls = [r.url for r in results]
    assert len(urls) == 4
    assert all("/p" in u for u in urls)
    assert all("www.spdigital.cl" in u for u in urls)
    assert results[0].source_category == "Notebooks"
    assert results[0].mapped_category == "notebooks"


def test_spdigital_unknown_category():
    mapper = CategoryMapper.build("www.spdigital.cl", {"Notebooks": "notebooks"})
    cat_filter = CategoryFilter()
    fetcher = MockFetcher()

    discovery = SPDigitalURLDiscovery()
    results = discovery.discover_category(
        source_category="Fantasía",
        category_mapper=mapper,
        category_filter=cat_filter,
        fetcher=fetcher,
    )
    assert results == []


def test_spdigital_blacklisted_category():
    mapper = CategoryMapper.build("www.spdigital.cl", {"Notebooks": "notebooks"})
    cat_filter = CategoryFilter(blacklist_slugs=frozenset({"notebooks"}))
    fetcher = MockFetcher({"/notebooks/": SPDIGITAL_HTML})

    discovery = SPDigitalURLDiscovery()
    results = discovery.discover_category(
        source_category="Notebooks",
        category_mapper=mapper,
        category_filter=cat_filter,
        fetcher=fetcher,
    )
    assert results == []


def test_spdigital_fetch_error_handled():
    class FailingFetcher(DiscoveryFetcher):
        def fetch(self, url, *, headers=None):
            self.request_count += 1
            raise ConnectionError("network error")

    mapper = CategoryMapper.build("www.spdigital.cl", {"Notebooks": "notebooks"})
    cat_filter = CategoryFilter()
    fetcher = FailingFetcher()

    discovery = SPDigitalURLDiscovery()
    results = discovery.discover_category(
        source_category="Notebooks",
        category_mapper=mapper,
        category_filter=cat_filter,
        fetcher=fetcher,
    )
    assert results == []


def test_spdigital_max_urls_limit():
    html = "<html><body>" + "".join(
        f'<a href="/p-{i}/p">Product {i}</a>' for i in range(50)
    ) + "</body></html>"

    mapper = CategoryMapper.build("www.spdigital.cl", {"Notebooks": "notebooks"})
    cat_filter = CategoryFilter()
    fetcher = MockFetcher({"/notebooks/": html})

    discovery = SPDigitalURLDiscovery()
    results = discovery.discover_category(
        source_category="Notebooks",
        category_mapper=mapper,
        category_filter=cat_filter,
        fetcher=fetcher,
        max_urls=5,
    )
    assert len(results) == 5


# ══════════════════════════════════════════════════════════════════
#  PARIS URL DISCOVERY (FIXTURES)
# ══════════════════════════════════════════════════════════════════

PARIS_HTML = """
<html><body>
<div class="product-card">
    <a href="/camiseta-chile-local-607430.html">Camiseta</a>
</div>
<div class="product-card">
    <a href="/notebook-hp-pavilion-15-607431.html">HP Pavilion</a>
</div>
<div class="product-item">
    <a href="/audifonos-sony-wh-1000xm5-607432.html">Sony WH-1000XM5</a>
</div>
<a href="/consola-ps5-slim-607433.html">PS5</a>
<a href="/not-a-product-link">Other</a>
</body></html>
"""


def test_paris_discover_category():
    mapper = CategoryMapper.build("www.paris.cl", {"Celulares": "celulares"})
    cat_filter = CategoryFilter()
    fetcher = MockFetcher({"celulares": PARIS_HTML})

    discovery = ParisURLDiscovery()
    results = discovery.discover_category(
        source_category="Celulares",
        category_mapper=mapper,
        category_filter=cat_filter,
        fetcher=fetcher,
        max_urls=10,
    )

    urls = [r.url for r in results]
    assert len(urls) == 4
    assert all(".html" in u for u in urls)
    assert all("www.paris.cl" in u for u in urls)
    assert results[0].source_category == "Celulares"
    assert results[0].mapped_category == "celulares"


def test_paris_unknown_category():
    mapper = CategoryMapper.build("www.paris.cl", {"Celulares": "celulares"})
    cat_filter = CategoryFilter()
    fetcher = MockFetcher()

    discovery = ParisURLDiscovery()
    results = discovery.discover_category(
        source_category="Muebles",
        category_mapper=mapper,
        category_filter=cat_filter,
        fetcher=fetcher,
    )
    assert results == []


def test_paris_fetch_error_handled():
    class FailingFetcher(DiscoveryFetcher):
        def fetch(self, url, *, headers=None):
            self.request_count += 1
            raise ConnectionError("network error")

    mapper = CategoryMapper.build("www.paris.cl", {"Celulares": "celulares"})
    cat_filter = CategoryFilter()
    fetcher = FailingFetcher()

    discovery = ParisURLDiscovery()
    results = discovery.discover_category(
        source_category="Celulares",
        category_mapper=mapper,
        category_filter=cat_filter,
        fetcher=fetcher,
    )
    assert results == []


# ══════════════════════════════════════════════════════════════════
#  DISCOVERY ORCHESTRATION
# ══════════════════════════════════════════════════════════════════


def test_discover_dedup_across_categories():
    mapper = CategoryMapper.build("www.spdigital.cl", {
        "Notebooks": "notebooks",
        "Gaming": "notebooks",
    })
    cat_filter = CategoryFilter()
    fetcher = MockFetcher({"/notebooks/": SPDIGITAL_HTML})

    discovery = SPDigitalURLDiscovery()
    report = discovery.discover(
        categories=["Notebooks", "Gaming"],
        category_mapper=mapper,
        category_filter=cat_filter,
        fetcher=fetcher,
    )

    assert report.categories_requested == 2
    assert report.categories_success == 2
    assert report.duplicate_urls > 0


def test_discover_metrics():
    mapper = CategoryMapper.build("www.spdigital.cl", {"Notebooks": "notebooks"})
    cat_filter = CategoryFilter()
    fetcher = MockFetcher({"/notebooks/": SPDIGITAL_HTML})

    discovery = SPDigitalURLDiscovery()
    report = discovery.discover(
        categories=["Notebooks"],
        category_mapper=mapper,
        category_filter=cat_filter,
        fetcher=fetcher,
    )

    assert report.categories_requested == 1
    assert report.categories_success == 1
    assert report.urls_discovered == 4
    assert report.listing_requests > 0
    assert report.duration_ms >= 0


def test_discover_unknown_category_returns_empty():
    mapper = CategoryMapper.build("www.spdigital.cl", {"Notebooks": "notebooks"})
    cat_filter = CategoryFilter()
    fetcher = MockFetcher()

    discovery = SPDigitalURLDiscovery()
    report = discovery.discover(
        categories=["Fantasía"],
        category_mapper=mapper,
        category_filter=cat_filter,
        fetcher=fetcher,
    )

    assert report.categories_requested == 1
    assert report.urls_discovered == 0
    assert len(report.candidates) == 0


def test_discovered_url_fields():
    url = DiscoveredURL(
        url="https://example.com/product.html",
        source="test:source",
        source_category="TestCat",
        mapped_category="test-slug",
        metadata={"key": "value"},
    )
    assert url.url == "https://example.com/product.html"
    assert url.source == "test:source"
    assert url.source_category == "TestCat"
    assert url.mapped_category == "test-slug"
    assert url.metadata == {"key": "value"}
    assert url.discovered_at is not None


def test_spdigital_category_urls_config():
    for slug in ["notebooks", "procesadores", "tarjetas-graficas",
                 "memoria-ram", "almacenamiento-ssd", "monitores",
                 "placas-madre", "pcs-de-escritorio", "celulares", "consolas"]:
        assert slug in SPDIGITAL_CATEGORY_URLS
        assert len(SPDIGITAL_CATEGORY_URLS[slug]) > 0


def test_paris_category_urls_config():
    for slug in ["notebooks", "monitores", "pcs-de-escritorio", "celulares", "consolas"]:
        assert slug in PARIS_CATEGORY_URLS
        assert len(PARIS_CATEGORY_URLS[slug]) > 0


# ══════════════════════════════════════════════════════════════════
#  BATCHED URLS (streaming)
# ══════════════════════════════════════════════════════════════════


def test_batched_urls_empty():
    batches = list(batched_urls([], batch_size=5))
    assert batches == []


def test_batched_urls_exact_batch_size():
    urls = [f"https://example.com/{i}" for i in range(10)]
    batches = list(batched_urls(urls, batch_size=5))
    assert len(batches) == 2
    assert batches[0] == urls[:5]
    assert batches[1] == urls[5:]


def test_batched_urls_partial_last_batch():
    urls = [f"https://example.com/{i}" for i in range(7)]
    batches = list(batched_urls(urls, batch_size=5))
    assert len(batches) == 2
    assert len(batches[0]) == 5
    assert len(batches[1]) == 2


def test_batched_urls_single_batch():
    urls = [f"https://example.com/{i}" for i in range(3)]
    batches = list(batched_urls(urls, batch_size=10))
    assert len(batches) == 1
    assert batches[0] == urls


def test_batched_urls_from_generator():
    def _gen():
        for i in range(8):
            yield f"https://example.com/{i}"

    batches = list(batched_urls(_gen(), batch_size=3))
    assert len(batches) == 3
    assert len(batches[0]) == 3
    assert len(batches[1]) == 3
    assert len(batches[2]) == 2


def test_batched_urls_batch_size_one():
    urls = ["https://a.com", "https://b.com", "https://c.com"]
    batches = list(batched_urls(urls, batch_size=1))
    assert len(batches) == 3
    assert all(len(b) == 1 for b in batches)


# ══════════════════════════════════════════════════════════════════
#  FLAT SITEMAP STREAM
# ══════════════════════════════════════════════════════════════════


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


FLAT_SITEMAP_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.spdigital.cl/notebooks/lenovo/p</loc></url>
  <url><loc>https://www.spdigital.cl/notebooks/hp/p</loc></url>
  <url><loc>https://www.spdigital.cl/celulares/samsung/p</loc></url>
  <url><loc>https://www.spdigital.cl/celulares/apple/p</loc></url>
  <url><loc>https://www.spdigital.cl/monitores/dell/p</loc></url>
</urlset>"""


INDEX_SITEMAP_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex>
  <sitemap><loc>https://www.example.cl/sitemap-child-1.xml</loc></sitemap>
  <sitemap><loc>https://www.example.cl/sitemap-child-2.xml</loc></sitemap>
</sitemapindex>"""

CHILD_SITEMAP_1_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.example.cl/product-1.html</loc></url>
  <url><loc>https://www.example.cl/product-2.html</loc></url>
</urlset>"""

CHILD_SITEMAP_2_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://www.example.cl/product-3.html</loc></url>
</urlset>"""


class TestFlatSitemapStream:
    def test_yields_all_urls(self):
        fetcher = _make_fetcher({"/sitemap.xml": FLAT_SITEMAP_XML})
        stream = FlatSitemapStream(fetcher, "https://www.spdigital.cl/sitemap.xml")
        urls = list(stream)
        assert len(urls) == 5
        assert "https://www.spdigital.cl/notebooks/lenovo/p" in urls

    def test_with_url_filter(self):
        fetcher = _make_fetcher({"/sitemap.xml": FLAT_SITEMAP_XML})
        stream = FlatSitemapStream(
            fetcher,
            "https://www.spdigital.cl/sitemap.xml",
            url_filter=lambda u: "notebooks" in u,
        )
        urls = list(stream)
        assert len(urls) == 2
        assert all("notebooks" in u for u in urls)

    def test_fetch_failure_yields_nothing(self):
        fetcher = _make_fetcher()
        stream = FlatSitemapStream(fetcher, "https://www.spdigital.cl/sitemap.xml")
        urls = list(stream)
        assert urls == []

    def test_caches_xml(self):
        fetcher = _make_fetcher({"/sitemap.xml": FLAT_SITEMAP_XML})
        stream = FlatSitemapStream(fetcher, "https://www.spdigital.cl/sitemap.xml")
        list(stream)
        list(stream)
        assert fetcher.fetch.call_count == 1

    def test_works_with_batched_urls(self):
        fetcher = _make_fetcher({"/sitemap.xml": FLAT_SITEMAP_XML})
        stream = FlatSitemapStream(fetcher, "https://www.spdigital.cl/sitemap.xml")
        batches = list(batched_urls(stream, batch_size=2))
        assert len(batches) == 3
        assert len(batches[0]) == 2
        assert len(batches[1]) == 2
        assert len(batches[2]) == 1


class TestSitemapStream:
    def test_yields_urls_from_child_sitemaps(self):
        fetcher = _make_fetcher({
            "/sitemap_index.xml": INDEX_SITEMAP_XML,
            "/sitemap-child-1.xml": CHILD_SITEMAP_1_XML,
            "/sitemap-child-2.xml": CHILD_SITEMAP_2_XML,
        })
        stream = SitemapStream(fetcher, "https://www.example.cl/sitemap_index.xml")
        urls = list(stream)
        assert len(urls) == 3
        assert "https://www.example.cl/product-1.html" in urls
        assert "https://www.example.cl/product-3.html" in urls

    def test_child_filter(self):
        fetcher = _make_fetcher({
            "/sitemap_index.xml": INDEX_SITEMAP_XML,
            "/sitemap-child-1.xml": CHILD_SITEMAP_1_XML,
        })
        stream = SitemapStream(
            fetcher,
            "https://www.example.cl/sitemap_index.xml",
            child_filter="child-1",
        )
        urls = list(stream)
        assert len(urls) == 2
        assert fetcher.fetch.call_count == 2  # index + child-1 only

    def test_child_fetch_failure_skips(self):
        fetcher = _make_fetcher({
            "/sitemap_index.xml": INDEX_SITEMAP_XML,
            "/sitemap-child-1.xml": CHILD_SITEMAP_1_XML,
        })
        stream = SitemapStream(fetcher, "https://www.example.cl/sitemap_index.xml")
        urls = list(stream)
        assert len(urls) == 2  # child-1 succeeds, child-2 fails

    def test_index_fetch_failure_yields_nothing(self):
        fetcher = _make_fetcher()
        stream = SitemapStream(fetcher, "https://www.example.cl/sitemap_index.xml")
        urls = list(stream)
        assert urls == []

    def test_len_returns_child_count(self):
        fetcher = _make_fetcher({"/sitemap_index.xml": INDEX_SITEMAP_XML})
        stream = SitemapStream(fetcher, "https://www.example.cl/sitemap_index.xml")
        assert len(stream) == 2

    def test_works_with_batched_urls(self):
        fetcher = _make_fetcher({
            "/sitemap_index.xml": INDEX_SITEMAP_XML,
            "/sitemap-child-1.xml": CHILD_SITEMAP_1_XML,
            "/sitemap-child-2.xml": CHILD_SITEMAP_2_XML,
        })
        stream = SitemapStream(fetcher, "https://www.example.cl/sitemap_index.xml")
        batches = list(batched_urls(stream, batch_size=2))
        assert len(batches) == 2
        assert len(batches[0]) == 2
        assert len(batches[1]) == 1


# ══════════════════════════════════════════════════════════════════
#  REQUEST_DELAY per store
# ══════════════════════════════════════════════════════════════════


def test_spdigital_request_delay_is_five():
    discovery = SPDigitalURLDiscovery()
    assert discovery.request_delay == 5.0


def test_paris_request_delay_is_half():
    discovery = ParisURLDiscovery()
    assert discovery.request_delay == 0.5
