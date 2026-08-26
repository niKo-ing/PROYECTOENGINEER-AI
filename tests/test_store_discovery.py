"""Unit tests for the Store Discovery Tool.

All tests use local HTML fixtures — no internet required.
"""

from __future__ import annotations

import json

import pytest
from bs4 import BeautifulSoup

from app.ingestion.discovery.discovery import StoreDiscovery
from app.ingestion.discovery.extractors import (
    EmbeddedJSONExtractor,
    JSONLDExtractor,
    MetadataExtractor,
)
from app.ingestion.discovery.fetcher import HTTPFetcher
from app.ingestion.discovery.platform import PlatformDetector
from app.ingestion.discovery.result import DiscoveryResult
from app.ingestion.discovery.security import URLValidationError, validate_url

# ---------------------------------------------------------------------------
# Fixtures: HTML snippets
# ---------------------------------------------------------------------------

HTML_JSONLD_PRODUCT = """
<!DOCTYPE html>
<html>
<head>
    <title>MacBook Pro 14 M3 — TiendaX</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "MacBook Pro 14 M3",
        "sku": "MBP14-M3-2024",
        "gtin13": "194253945612",
        "mpn": "MNW73LA/A",
        "brand": {"@type": "Brand", "name": "Apple"},
        "image": "https://cdn.tiendax.com/img/mbp14.jpg",
        "url": "https://tiendax.com/productos/macbook-pro-14-m3",
        "offers": {
            "@type": "Offer",
            "price": "1299990",
            "priceCurrency": "CLP",
            "availability": "https://schema.org/InStock",
            "url": "https://tiendax.com/productos/macbook-pro-14-m3"
        }
    }
    </script>
</head>
<body>
    <h1>MacBook Pro 14 M3</h1>
    <p>Price: $1.299.990</p>
</body>
</html>
"""

HTML_JSONLD_AGGREGATE_OFFER = """
<!DOCTYPE html>
<html>
<head>
    <title>Samsung Galaxy S24 — Comparador</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Samsung Galaxy S24",
        "gtin13": "8806095350001",
        "brand": "Samsung",
        "offers": {
            "@type": "AggregateOffer",
            "lowPrice": "599990",
            "highPrice": "799990",
            "priceCurrency": "CLP",
            "offerCount": "5"
        }
    }
    </script>
</head>
<body><h1>Samsung Galaxy S24</h1></body>
</html>
"""

HTML_JSONLD_ARRAY = """
<!DOCTYPE html>
<html>
<head>
    <title>Multi Product</title>
    <script type="application/ld+json">
    [
        {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Product A",
            "sku": "SKU-A",
            "offers": {"@type": "Offer", "price": "1000", "priceCurrency": "USD"}
        },
        {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Product B",
            "sku": "SKU-B",
            "offers": {"@type": "Offer", "price": "2000", "priceCurrency": "USD"}
        }
    ]
    </script>
</head>
<body></body>
</html>
"""

HTML_SKU_ONLY = """
<!DOCTYPE html>
<html>
<head>
    <title>SKU Product</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Keyboard MX Keys",
        "sku": "920-009280"
    }
    </script>
</head>
<body></body>
</html>
"""

HTML_GTIM_ONLY = """
<!DOCTYPE html>
<html>
<head>
    <title>GTIN Product</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Logitech Mouse",
        "gtin": "5099206104005"
    }
    </script>
</head>
<body></body>
</html>
"""

HTML_MPN_ONLY = """
<!DOCTYPE html>
<html>
<head>
    <title>MPN Product</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Dell Monitor",
        "mpn": "S2722QC"
    }
    </script>
</head>
<body></body>
</html>
"""

HTML_BRAND_ONLY = """
<!DOCTYPE html>
<html>
<head>
    <title>Brand Product</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "USB Cable",
        "brand": {"@type": "Brand", "name": "Baseus"}
    }
    </script>
</head>
<body></body>
</html>
"""

HTML_PRICE_CURRENCY = """
<!DOCTYPE html>
<html>
<head>
    <title>Priced Product</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Webcam HD",
        "offers": {
            "@type": "Offer",
            "price": "29990",
            "priceCurrency": "CLP",
            "availability": "https://schema.org/InStock"
        }
    }
    </script>
</head>
<body></body>
</html>
"""

HTML_OPENGGRAPH = """
<!DOCTYPE html>
<html>
<head>
    <title>OG Product</title>
    <meta property="og:title" content="iPhone 15 Pro Max">
    <meta property="og:url" content="https://tienda.com/iphone-15-pro-max">
    <meta property="og:image" content="https://tienda.com/img/iphone15.jpg">
    <meta property="product:price:amount" content="1199990">
    <meta property="product:price:currency" content="CLP">
    <meta property="product:brand" content="Apple">
</head>
<body><h1>iPhone 15 Pro Max</h1></body>
</html>
"""

HTML_EMBEDDED_JSON = """
<!DOCTYPE html>
<html>
<head><title>Embedded Product</title></head>
<body>
    <div id="app"></div>
    <script>
    window.__INITIAL_STATE__ = {"product": {"name": "RTX 4080", "price": 899990, "sku": "RTX4080-FE"}};
    </script>
</body>
</html>
"""

HTML_NO_STRUCTURED_DATA = """
<!DOCTYPE html>
<html>
<head><title>Plain Page</title></head>
<body>
    <h1>No structured data here</h1>
    <p>Just plain text content.</p>
</body>
</html>
"""

HTML_INVALID_HTML = """
<!DOCTYPE html>
<html>
<head><title>Broken</title></head>
<body>
    <unclosed-tag>
    <script type="application/ld+json">
    {invalid json here!!!
    </script>
</body>
</html>
"""

HTML_PLATFORM_SHOPIFY = """
<!DOCTYPE html>
<html>
<head>
    <title>Shopify Store</title>
    <meta property="og:title" content="Product">
    <script>
    Shopify.theme = {"name": "Dawn"};
    </script>
</head>
<body>
    <link href="https://cdn.shopify.com/s/files/1/0001/style.css" rel="stylesheet">
</body>
</html>
"""

HTML_PLATFORM_VTEX = """
<!DOCTYPE html>
<html>
<head><title>VTEX Store</title></head>
<body>
    <script src="https://io.vtex.com.br/vtex.js/3.10.0/vtex.min.js"></script>
    <div class="vtex-store-components-0-x-productSummary"></div>
</body>
</html>
"""

HTML_PLATFORM_NEXTJS = """
<!DOCTYPE html>
<html>
<head><title>Next.js Store</title></head>
<body>
    <script id="__NEXT_DATA__" type="application/json">{"props": {"pageProps": {}}}</script>
</body>
</html>
"""

HTML_PLATFORM_WOOCOMMERCE = """
<!DOCTYPE html>
<html>
<head><title>WooCommerce Store</title></head>
<body>
    <link rel="stylesheet" href="https://example.com/wp-content/themes/store/style.css">
    <div class="woocommerce-product-gallery"></div>
</body>
</html>
"""

HTML_REQUIRES_JS = """
<!DOCTYPE html>
<html>
<head><title>SPA</title></head>
<body>
    <noscript>Enable JavaScript to run this app.</noscript>
    <noscript>Please enable JavaScript.</noscript>
    <noscript>This app requires JavaScript.</noscript>
    <div id="root"></div>
</body>
</html>
"""

HTML_MULTIPLE_SOURCES = """
<!DOCTYPE html>
<html>
<head>
    <title>Multi Source Product</title>
    <meta property="og:title" content="iPad Air">
    <meta property="product:price:amount" content="699990">
    <meta property="product:price:currency" content="CLP">
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "iPad Air M2",
        "brand": "Apple",
        "offers": {
            "@type": "Offer",
            "price": "749990",
            "priceCurrency": "CLP",
            "availability": "https://schema.org/InStock"
        }
    }
    </script>
</head>
<body></body>
</html>
"""

HTML_BRAND_STRING = """
<!DOCTYPE html>
<html>
<head>
    <title>Brand String</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Mouse",
        "brand": "Logitech",
        "offers": {"@type": "Offer", "price": "25000", "priceCurrency": "CLP"}
    }
    </script>
</head>
<body></body>
</html>
"""

HTML_GTIM8 = """
<!DOCTYPE html>
<html>
<head>
    <title>GTIN8</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Small Product",
        "gtin8": "12345670"
    }
    </script>
</head>
<body></body>
</html>
"""

HTML_OFFER_OUT_OF_STOCK = """
<!DOCTYPE html>
<html>
<head>
    <title>Out of Stock</title>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Unavailable Widget",
        "offers": {
            "@type": "Offer",
            "price": "50000",
            "priceCurrency": "CLP",
            "availability": "https://schema.org/OutOfStock"
        }
    }
    </script>
</head>
<body></body>
</html>
"""

HTML_HYDRATION_JSON = """
<!DOCTYPE html>
<html>
<head><title>Hydration</title></head>
<body>
    <script type="application/json">
    {"product": {"name": "Hydrated Product", "price": 15000, "currency": "CLP"}}
    </script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Security tests
# ---------------------------------------------------------------------------


class TestURLValidation:
    def test_rejects_empty_url(self):
        with pytest.raises(URLValidationError, match="vacía"):
            validate_url("")

    def test_rejects_ftp(self):
        with pytest.raises(URLValidationError, match="Esquema no permitido"):
            validate_url("ftp://example.com/file")

    def test_rejects_file_scheme(self):
        with pytest.raises(URLValidationError, match="Esquema no permitido"):
            validate_url("file:///etc/passwd")

    def test_rejects_localhost(self):
        with pytest.raises(URLValidationError, match="localhost"):
            validate_url("http://localhost/product")

    def test_rejects_localhost_with_port(self):
        with pytest.raises(URLValidationError, match="localhost"):
            validate_url("http://localhost:8080/product")

    def test_rejects_loopback_ip(self):
        with pytest.raises(URLValidationError, match="loopback"):
            validate_url("http://127.0.0.1/product")

    def test_rejects_private_ip_10(self):
        with pytest.raises(URLValidationError, match="privada"):
            validate_url("http://10.0.0.1/product")

    def test_rejects_private_ip_172(self):
        with pytest.raises(URLValidationError, match="privada"):
            validate_url("http://172.16.0.1/product")

    def test_rejects_private_ip_192(self):
        with pytest.raises(URLValidationError, match="privada"):
            validate_url("http://192.168.1.1/product")

    def test_rejects_link_local(self):
        with pytest.raises(URLValidationError, match="link-local"):
            validate_url("http://169.254.1.1/product")

    def test_rejects_local_domain(self):
        with pytest.raises(URLValidationError, match="no permitido"):
            validate_url("http://myserver.local/product")

    def test_accepts_valid_https(self):
        result = validate_url("https://www.falabella.com/falabella-cl/product/123")
        assert result.hostname == "www.falabella.com"

    def test_accepts_valid_http(self):
        result = validate_url("http://example.com/product")
        assert result.scheme == "http"

    def test_rejects_javascript_scheme(self):
        with pytest.raises(URLValidationError, match="Esquema no permitido"):
            validate_url("javascript:alert(1)")


# ---------------------------------------------------------------------------
# JSON-LD tests
# ---------------------------------------------------------------------------


class TestJSONLDExtractor:
    def setup_method(self):
        self.extractor = JSONLDExtractor()

    def test_product(self):
        soup = BeautifulSoup(HTML_JSONLD_PRODUCT, "html.parser")
        items = self.extractor.extract(soup)
        products = self.extractor.find_products(items)
        assert len(products) == 1
        assert products[0]["name"] == "MacBook Pro 14 M3"
        assert products[0]["sku"] == "MBP14-M3-2024"

    def test_offer(self):
        soup = BeautifulSoup(HTML_JSONLD_PRODUCT, "html.parser")
        items = self.extractor.extract(soup)
        offers = self.extractor.find_offers(items)
        assert len(offers) == 1
        assert offers[0]["price"] == "1299990"
        assert offers[0]["priceCurrency"] == "CLP"

    def test_aggregate_offer(self):
        soup = BeautifulSoup(HTML_JSONLD_AGGREGATE_OFFER, "html.parser")
        items = self.extractor.extract(soup)
        offers = self.extractor.find_offers(items)
        assert len(offers) == 1
        assert offers[0]["@type"] == "AggregateOffer"
        assert offers[0]["lowPrice"] == "599990"

    def test_array(self):
        soup = BeautifulSoup(HTML_JSONLD_ARRAY, "html.parser")
        items = self.extractor.extract(soup)
        products = self.extractor.find_products(items)
        assert len(products) == 2
        assert products[0]["name"] == "Product A"
        assert products[1]["name"] == "Product B"

    def test_invalid_json_ld(self):
        soup = BeautifulSoup(HTML_INVALID_HTML, "html.parser")
        items = self.extractor.extract(soup)
        assert items == []

    def test_empty_script(self):
        html = '<html><head><script type="application/ld+json"></script></head></html>'
        soup = BeautifulSoup(html, "html.parser")
        items = self.extractor.extract(soup)
        assert items == []


class TestJSONLDSKU:
    def setup_method(self):
        self.extractor = JSONLDExtractor()

    def test_sku(self):
        soup = BeautifulSoup(HTML_SKU_ONLY, "html.parser")
        items = self.extractor.extract(soup)
        products = self.extractor.find_products(items)
        assert products[0]["sku"] == "920-009280"


class TestJSONLDGTIN:
    def setup_method(self):
        self.extractor = JSONLDExtractor()

    def test_gtin(self):
        soup = BeautifulSoup(HTML_GTIM_ONLY, "html.parser")
        items = self.extractor.extract(soup)
        products = self.extractor.find_products(items)
        assert products[0]["gtin"] == "5099206104005"

    def test_gtin13(self):
        soup = BeautifulSoup(HTML_JSONLD_PRODUCT, "html.parser")
        items = self.extractor.extract(soup)
        products = self.extractor.find_products(items)
        assert products[0]["gtin13"] == "194253945612"

    def test_gtin8(self):
        soup = BeautifulSoup(HTML_GTIM8, "html.parser")
        items = self.extractor.extract(soup)
        products = self.extractor.find_products(items)
        assert products[0]["gtin8"] == "12345670"


class TestJSONLDMPN:
    def setup_method(self):
        self.extractor = JSONLDExtractor()

    def test_mpn(self):
        soup = BeautifulSoup(HTML_MPN_ONLY, "html.parser")
        items = self.extractor.extract(soup)
        products = self.extractor.find_products(items)
        assert products[0]["mpn"] == "S2722QC"


class TestJSONLDBrand:
    def setup_method(self):
        self.extractor = JSONLDExtractor()

    def test_brand_object(self):
        soup = BeautifulSoup(HTML_JSONLD_PRODUCT, "html.parser")
        items = self.extractor.extract(soup)
        products = self.extractor.find_products(items)
        assert isinstance(products[0]["brand"], dict)
        assert products[0]["brand"]["name"] == "Apple"

    def test_brand_string(self):
        soup = BeautifulSoup(HTML_BRAND_STRING, "html.parser")
        items = self.extractor.extract(soup)
        products = self.extractor.find_products(items)
        assert products[0]["brand"] == "Logitech"


class TestJSONLDPrice:
    def setup_method(self):
        self.extractor = JSONLDExtractor()

    def test_price(self):
        soup = BeautifulSoup(HTML_PRICE_CURRENCY, "html.parser")
        items = self.extractor.extract(soup)
        offers = self.extractor.find_offers(items)
        assert offers[0]["price"] == "29990"
        assert offers[0]["priceCurrency"] == "CLP"


class TestJSONLDCurrency:
    def setup_method(self):
        self.extractor = JSONLDExtractor()

    def test_currency(self):
        soup = BeautifulSoup(HTML_PRICE_CURRENCY, "html.parser")
        items = self.extractor.extract(soup)
        offers = self.extractor.find_offers(items)
        assert offers[0]["priceCurrency"] == "CLP"


class TestJSONLDAvailability:
    def setup_method(self):
        self.extractor = JSONLDExtractor()

    def test_in_stock(self):
        soup = BeautifulSoup(HTML_PRICE_CURRENCY, "html.parser")
        items = self.extractor.extract(soup)
        offers = self.extractor.find_offers(items)
        assert "InStock" in offers[0]["availability"]

    def test_out_of_stock(self):
        soup = BeautifulSoup(HTML_OFFER_OUT_OF_STOCK, "html.parser")
        items = self.extractor.extract(soup)
        offers = self.extractor.find_offers(items)
        assert "OutOfStock" in offers[0]["availability"]


# ---------------------------------------------------------------------------
# Embedded JSON tests
# ---------------------------------------------------------------------------


class TestEmbeddedJSONExtractor:
    def setup_method(self):
        self.extractor = EmbeddedJSONExtractor()

    def test_initial_state(self):
        soup = BeautifulSoup(HTML_EMBEDDED_JSON, "html.parser")
        items = self.extractor.extract(soup)
        assert len(items) >= 1
        found = any(
            "product" in item or item.get("name") == "RTX 4080"
            for item in items
        )
        assert found

    def test_hydration_json(self):
        soup = BeautifulSoup(HTML_HYDRATION_JSON, "html.parser")
        items = self.extractor.extract(soup)
        assert len(items) >= 1

    def test_no_scripts(self):
        soup = BeautifulSoup(HTML_NO_STRUCTURED_DATA, "html.parser")
        items = self.extractor.extract(soup)
        assert items == []


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------


class TestMetadataExtractor:
    def setup_method(self):
        self.extractor = MetadataExtractor()

    def test_opengraph(self):
        soup = BeautifulSoup(HTML_OPENGGRAPH, "html.parser")
        meta = self.extractor.extract(soup)
        assert meta.get("og:title") == "iPhone 15 Pro Max"
        assert meta.get("og:url") == "https://tienda.com/iphone-15-pro-max"
        assert meta.get("og:image") == "https://tienda.com/img/iphone15.jpg"
        assert meta.get("product:price:amount") == "1199990"
        assert meta.get("product:price:currency") == "CLP"
        assert meta.get("product:brand") == "Apple"

    def test_title_tag(self):
        soup = BeautifulSoup(HTML_OPENGGRAPH, "html.parser")
        meta = self.extractor.extract(soup)
        assert meta.get("title") == "OG Product"

    def test_no_meta(self):
        soup = BeautifulSoup(HTML_NO_STRUCTURED_DATA, "html.parser")
        meta = self.extractor.extract(soup)
        assert "og:title" not in meta


# ---------------------------------------------------------------------------
# Platform detection tests
# ---------------------------------------------------------------------------


class TestPlatformDetector:
    def setup_method(self):
        self.detector = PlatformDetector()

    def test_shopify(self):
        soup = BeautifulSoup(HTML_PLATFORM_SHOPIFY, "html.parser")
        result = self.detector.detect(soup, {}, [])
        assert result is not None
        assert result.name == "Shopify"
        assert result.confidence > 0.3

    def test_vtex(self):
        soup = BeautifulSoup(HTML_PLATFORM_VTEX, "html.parser")
        result = self.detector.detect(soup, {}, [])
        assert result is not None
        assert result.name == "VTEX"

    def test_nextjs(self):
        soup = BeautifulSoup(HTML_PLATFORM_NEXTJS, "html.parser")
        result = self.detector.detect(soup, {}, [])
        assert result is not None
        assert result.name == "Next.js"

    def test_woocommerce(self):
        soup = BeautifulSoup(HTML_PLATFORM_WOOCOMMERCE, "html.parser")
        result = self.detector.detect(soup, {}, [])
        assert result is not None
        assert result.name == "WooCommerce"

    def test_no_platform(self):
        soup = BeautifulSoup(HTML_NO_STRUCTURED_DATA, "html.parser")
        result = self.detector.detect(soup, {}, [])
        assert result is None


# ---------------------------------------------------------------------------
# StoreDiscovery orchestrator tests
# ---------------------------------------------------------------------------


class TestStoreDiscovery:
    def setup_method(self):
        self.discovery = StoreDiscovery()

    def test_full_product(self):
        result = self.discovery.discover_html(
            "https://example.com/product", HTML_JSONLD_PRODUCT
        )
        assert result.json_ld_found is True
        assert result.json_ld_product_found is True
        assert result.json_ld_offer_found is True
        assert result.price_found is True
        assert result.currency_found is True
        assert result.availability_found is True
        assert result.sku_found is True
        assert result.gtin_found is True
        assert result.mpn_found is True
        assert result.brand_found is True
        assert result.product_name_found is True
        assert result.image_found is True
        assert result.product_url_found is True
        assert result.http_status == 200
        assert result.errors == []

    def test_opengraph_fallback(self):
        result = self.discovery.discover_html(
            "https://example.com/og-product", HTML_OPENGGRAPH
        )
        assert result.meta_data_found is True
        assert result.product_name_found is True
        assert result.price_found is True
        assert result.currency_found is True
        assert result.image_found is True
        assert result.brand_found is True

    def test_no_structured_data(self):
        result = self.discovery.discover_html(
            "https://example.com/plain", HTML_NO_STRUCTURED_DATA
        )
        assert result.json_ld_found is False
        assert result.embedded_json_found is False
        assert result.price_found is False
        assert result.sku_found is False
        assert result.brand_found is False
        assert result.gtin_found is False
        assert result.mpn_found is False
        assert result.availability_found is False
        assert result.image_found is False

    def test_invalid_html(self):
        result = self.discovery.discover_html(
            "https://example.com/broken", HTML_INVALID_HTML
        )
        assert result.json_ld_found is False
        assert result.errors == []

    def test_requires_js(self):
        result = self.discovery.discover_html(
            "https://example.com/spa", HTML_REQUIRES_JS
        )
        assert any("JavaScript" in w for w in result.warnings)

    def test_multiple_sources(self):
        result = self.discovery.discover_html(
            "https://example.com/multi", HTML_MULTIPLE_SOURCES
        )
        assert result.json_ld_found is True
        assert result.meta_data_found is True
        assert "json-ld" in result.structured_sources
        assert "meta-tags" in result.structured_sources
        assert result.price_found is True

    def test_invalid_url(self):
        result = self.discovery.discover("not-a-url")
        assert len(result.errors) > 0

    def test_localhost_url(self):
        result = self.discovery.discover("http://localhost/admin")
        assert len(result.errors) > 0

    def test_private_ip(self):
        result = self.discovery.discover("http://192.168.1.1/admin")
        assert len(result.errors) > 0


class TestStoreDiscoveryPlatform:
    def setup_method(self):
        self.discovery = StoreDiscovery()

    def test_shopify_detection(self):
        result = self.discovery.discover_html(
            "https://shop.example.com", HTML_PLATFORM_SHOPIFY
        )
        assert result.detected_platform is not None
        assert result.detected_platform.name == "Shopify"

    def test_vtex_detection(self):
        result = self.discovery.discover_html(
            "https://store.example.com", HTML_PLATFORM_VTEX
        )
        assert result.detected_platform is not None
        assert result.detected_platform.name == "VTEX"


class TestStoreDiscoveryAggregateOffer:
    def setup_method(self):
        self.discovery = StoreDiscovery()

    def test_aggregate_offer(self):
        result = self.discovery.discover_html(
            "https://example.com/compare", HTML_JSONLD_AGGREGATE_OFFER
        )
        assert result.json_ld_offer_found is True
        assert result.price_found is True
        assert result.currency_found is True


class TestStoreDiscoveryEmbeddedJSON:
    def setup_method(self):
        self.discovery = StoreDiscovery()

    def test_embedded_json(self):
        result = self.discovery.discover_html(
            "https://example.com/spa-product", HTML_EMBEDDED_JSON
        )
        assert result.embedded_json_found is True


class TestStoreDiscoveryBrandOnly:
    def setup_method(self):
        self.discovery = StoreDiscovery()

    def test_brand_only(self):
        result = self.discovery.discover_html(
            "https://example.com/cable", HTML_BRAND_ONLY
        )
        assert result.brand_found is True
        assert result.product_name_found is True


class TestStoreDiscoveryOfferOutOfStock:
    def setup_method(self):
        self.discovery = StoreDiscovery()

    def test_out_of_stock(self):
        result = self.discovery.discover_html(
            "https://example.com/unavailable", HTML_OFFER_OUT_OF_STOCK
        )
        assert result.availability_found is True
        assert result.price_found is True


# ---------------------------------------------------------------------------
# Admin API endpoint tests
# ---------------------------------------------------------------------------


class TestAdminDiscoverEndpoint:
    def setup_method(self):
        from fastapi.testclient import TestClient

        from app.core.security import AuthenticatedUser, get_current_user
        from app.main import create_app

        self.app = create_app()
        self.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id="test-admin"
        )
        self.client = TestClient(self.app)

    def test_discover_endpoint(self):
        response = self.client.post(
            "/api/v1/admin/ingestion/discover",
            json={"url": "https://httpbin.org/html"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "json_ld_found" in data
        assert "price_found" in data

    def test_discover_requires_auth(self):
        from fastapi.testclient import TestClient

        from app.core.security import get_current_user

        self.app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(self.app)
        response = client.post(
            "/api/v1/admin/ingestion/discover",
            json={"url": "https://example.com"},
        )
        assert response.status_code in (401, 403)

    def test_discover_invalid_url(self):
        response = self.client.post(
            "/api/v1/admin/ingestion/discover",
            json={"url": "not-a-url"},
        )
        assert response.status_code == 422

    def test_discover_localhost_blocked(self):
        response = self.client.post(
            "/api/v1/admin/ingestion/discover",
            json={"url": "http://localhost/secret"},
        )
        data = response.json()
        assert response.status_code == 200
        assert len(data.get("errors", [])) > 0
