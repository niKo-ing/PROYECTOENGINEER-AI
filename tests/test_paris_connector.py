"""Unit tests for Paris connector — no internet required."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.ingestion.connectors.paris.connector import ParisConnector
from app.ingestion.connectors.paris.parser import ParisRSCParser, RawProductData
from app.ingestion.dto import NormalizedOffer
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.service import CatalogIngestionService
from app.models.catalog import Category, PriceHistory, Product, Store, StoreOffer

# ---------------------------------------------------------------------------
# HTML Fixtures — based on real Paris RSC structure
# ---------------------------------------------------------------------------

HTML_FULL_PRODUCT = """
<!DOCTYPE html>
<html>
<head><title>Camiseta</title></head>
<body>
<script>
self.__next_f.push([1,"0:{\\"P\\":null,\\"c\\":[\\"\\",\\"test.html\\"]}"]);
</script>
<script>
self.__next_f.push([1,"{\\"@context\\":\\"https://schema.org/\\",\\"@type\\":\\"Product\\",\\"name\\":\\"Camiseta de F\\u00fatbol Chile 2024 Local\\",\\"brand\\":{\\"@type\\":\\"Brand\\",\\"name\\":\\"Adidas\\"},\\"offers\\":[{\\"@type\\":\\"Offer\\",\\"price\\":59990,\\"priceCurrency\\":\\"CLP\\",\\"availability\\":\\"https://schema.org/InStock\\",\\"seller\\":{\\"@type\\":\\"Organization\\",\\"name\\":\\"Paris\\"},\\"url\\":\\"https://www.paris.cl/camiseta-de-futbol-chile-2024-local-607430.html\\",\\"itemCondition\\":\\"https://schema.org/NewCondition\\"},{\\"@type\\":\\"Offer\\",\\"price\\":23990,\\"priceCurrency\\":\\"CLP\\",\\"availability\\":\\"https://schema.org/InStock\\",\\"seller\\":{\\"@type\\":\\"Organization\\",\\"name\\":\\"Paris\\"},\\"url\\":\\"https://www.paris.cl/camiseta-de-futbol-chile-2024-local-607430.html\\"}],\\"description\\":\\"Camiseta de futbol\\"}"]);
</script>
<script>
self.__next_f.push([1,"2e:[[\\\"$\\\",\\\"$L30\\\",null,{\\\"product\\\":{\\\"id\\\":\\\"b33f2eb4\\\",\\\"key\\\":\\\"607430\\\",\\\"name\\\":\\\"Camiseta de F\\u00fatbol Chile 2024 Local\\\",\\\"slug\\\":\\\"camiseta-de-futbol-chile-2024-local-607430\\\",\\\"brand\\\":\\\"Adidas\\\",\\\"masterVariant\\\":{\\\"id\\\":1,\\\"sku\\\":\\\"607430002\\\",\\\"prices\\\":{\\\"regular\\\":{\\\"value\\\":{\\\"type\\\":\\\"centPrecision\\\",\\\"centAmount\\\":59990,\\\"currencyCode\\\":\\\"CLP\\\",\\\"fractionDigits\\\":0}},\\\"offer\\\":{\\\"value\\\":{\\\"type\\\":\\\"centPrecision\\\",\\\"currencyCode\\\":\\\"CLP\\\",\\\"centAmount\\\":23990,\\\"fractionDigits\\\":0}}},\\\"images\\\":[{\\\"url\\\":\\\"https://cl-dam-resizer.ecomm.cencosud.com/img/607430-0600-001.jpg\\\",\\\"alt\\\":\\\"Camiseta\\\"}]}}}]]"]);
</script>
</body>
</html>
"""

HTML_JSONLD_ONLY = """
<!DOCTYPE html>
<html>
<head><title>Product</title></head>
<body>
<script>
self.__next_f.push([1,"{\\"@context\\":\\"https://schema.org/\\",\\"@type\\":\\"Product\\",\\"name\\":\\"Aud\\u00edfonos Bluetooth\\",\\"brand\\":{\\"@type\\":\\"Brand\\",\\"name\\":\\"Sony\\"},\\"sku\\":\\"WH-1000XM5\\",\\"mpn\\":\\"WH1000XM5\\",\\"offers\\":{\\"@type\\":\\"Offer\\",\\"price\\":199990,\\"priceCurrency\\":\\"CLP\\",\\"availability\\":\\"https://schema.org/InStock\\",\\"url\\":\\"https://www.paris.cl/audifonos-sony\\"}}"]);
</script>
</body>
</html>
"""

HTML_OUT_OF_STOCK = """
<!DOCTYPE html>
<html>
<head><title>Out of stock</title></head>
<body>
<script>
self.__next_f.push([1,"{\\"@context\\":\\"https://schema.org/\\",\\"@type\\":\\"Product\\",\\"name\\":\\"Monitor Dell\\",\\"brand\\":\\"Dell\\",\\"offers\\":{\\"@type\\":\\"Offer\\",\\"price\\":289990,\\"priceCurrency\\":\\"CLP\\",\\"availability\\":\\"https://schema.org/OutOfStock\\",\\"url\\":\\"https://www.paris.cl/monitor-dell\\"}}"]);
</script>
</body>
</html>
"""

HTML_MULTIPLE_OFFERS_BEST = """
<!DOCTYPE html>
<html>
<head><title>Multi offer</title></head>
<body>
<script>
self.__next_f.push([1,"{\\"@context\\":\\"https://schema.org/\\",\\"@type\\":\\"Product\\",\\"name\\":\\"Zapatillas\\",\\"brand\\":\\"Nike\\",\\"offers\\":[{\\"@type\\":\\"Offer\\",\\"price\\":79990,\\"priceCurrency\\":\\"CLP\\",\\"availability\\":\\"https://schema.org/OutOfStock\\"},{\\"@type\\":\\"Offer\\",\\"price\\":65000,\\"priceCurrency\\":\\"CLP\\",\\"availability\\":\\"https://schema.org/InStock\\",\\"url\\":\\"https://www.paris.cl/zap-nike\\"}]}"]);
</script>
</body>
</html>
"""

HTML_NO_AVAILABILITY = """
<!DOCTYPE html>
<html>
<head><title>No avail</title></head>
<body>
<script>
self.__next_f.push([1,"{\\"@context\\":\\"https://schema.org/\\",\\"@type\\":\\"Product\\",\\"name\\":\\"Lampara\\",\\"brand\\":\\"Philips\\",\\"offers\\":{\\"@type\\":\\"Offer\\",\\"price\\":15000,\\"priceCurrency\\":\\"CLP\\",\\"url\\":\\"https://www.paris.cl/lamp\\"}}"]);
</script>
</body>
</html>
"""

HTML_NO_RSC = """
<!DOCTYPE html>
<html>
<head><title>No RSC</title></head>
<body>
<h1>Plain HTML page</h1>
<p>No structured data here.</p>
</body>
</html>
"""

HTML_EMPTY_CHUNKS = """
<!DOCTYPE html>
<html>
<head><title>Empty</title></head>
<body>
<script>
self.__next_f.push([1,""]);
</script>
<script>
self.__next_f.push([1,"0:{\\"P\\":null}"]);
</script>
</body>
</html>
"""

HTML_MALFORMED_JSON = """
<!DOCTYPE html>
<html>
<head><title>Bad JSON</title></head>
<body>
<script>
self.__next_f.push([1,"{\\"@type\\":\\"Product\\",\\"name\\":\\"Bad\\",invalid json here!!!"]);
</script>
</body>
</html>
"""

HTML_CHUNKS_IRRELEVANT = """
<!DOCTYPE html>
<html>
<head><title>Irrelevant</title></head>
<body>
<script>
self.__next_f.push([1,"0:{\\"P\\":null,\\"c\\":[\\"\\",\\"page\\"]}"]);
</script>
<script>
self.__next_f.push([1,"1a:[\\"$\\",\\"body\\",null,{\\"className\\":\\"test\\"}]"]);
</script>
<script>
self.__next_f.push([1,"2a:I[12345,\\"/_next/chunk.js\\"],\\"HydrationBoundary\\""]);
</script>
</body>
</html>
"""

HTML_RSC_PRODUCT_NO_PRICES = """
<!DOCTYPE html>
<html>
<head><title>No prices</title></head>
<body>
<script>
self.__next_f.push([1,"2e:[[{\\"product\\":{\\"key\\":\\"999999\\",\\"name\\":\\"Test Product\\",\\"brand\\":\\"TestBrand\\",\\"slug\\":\\"test-product\\",\\"masterVariant\\":{\\"sku\\":\\"999999001\\",\\"prices\\":{},\\"images\\":[]}}}]]"]);
</script>
</body>
</html>
"""

HTML_PRODUCT_KEY_IN_URL = """
<!DOCTYPE html>
<html>
<head><title>Key URL</title></head>
<body>
<script>
self.__next_f.push([1,"{\\"@context\\":\\"https://schema.org/\\",\\"@type\\":\\"Product\\",\\"name\\":\\"Teclado Mec\\u00e1nico\\",\\"brand\\":\\"Logitech\\",\\"sku\\":\\"920-009280\\",\\"offers\\":{\\"@type\\":\\"Offer\\",\\"price\\":45000,\\"priceCurrency\\":\\"CLP\\",\\"availability\\":\\"https://schema.org/InStock\\",\\"url\\":\\"https://www.paris.cl/teclado-920-009280.html\\"}}"]);
</script>
</body>
</html>
"""

HTML_GTIM_PRODUCT = """
<!DOCTYPE html>
<html>
<head><title>GTIN</title></head>
<body>
<script>
self.__next_f.push([1,"{\\"@context\\":\\"https://schema.org/\\",\\"@type\\":\\"Product\\",\\"name\\":\\"Mouse\\",\\"brand\\":\\"Logitech\\",\\"gtin13\\":\\"5099206104005\\",\\"offers\\":{\\"@type\\":\\"Offer\\",\\"price\\":25000,\\"priceCurrency\\":\\"CLP\\",\\"availability\\":\\"https://schema.org/InStock\\"}}"]);
</script>
</body>
</html>
"""

HTML_SINGLE_OFFER = """
<!DOCTYPE html>
<html>
<head><title>Single</title></head>
<body>
<script>
self.__next_f.push([1,"{\\"@context\\":\\"https://schema.org/\\",\\"@type\\":\\"Product\\",\\"name\\":\\"Impresora HP\\",\\"brand\\":\\"HP\\",\\"offers\\":{\\"@type\\":\\"Offer\\",\\"price\\":189990,\\"priceCurrency\\":\\"CLP\\",\\"availability\\":\\"https://schema.org/InStock\\",\\"url\\":\\"https://www.paris.cl/impresora-hp\\"}}"]);
</script>
</body>
</html>
"""

HTML_IMAGE_IN_ARRAY = """
<!DOCTYPE html>
<html>
<head><title>Img Array</title></head>
<body>
<script>
self.__next_f.push([1,"{\\"@context\\":\\"https://schema.org/\\",\\"@type\\":\\"Product\\",\\"name\\":\\"Tablet\\",\\"brand\\":\\"Samsung\\",\\"image\\":[\\"https://img.paris.cl/tablet1.jpg\\",\\"https://img.paris.cl/tablet2.jpg\\"],\\"offers\\":{\\"@type\\":\\"Offer\\",\\"price\\":399990,\\"priceCurrency\\":\\"CLP\\",\\"availability\\":\\"https://schema.org/InStock\\"}}"]);
</script>
</body>
</html>
"""

HTML_NO_TITLE_CLEAN = """
<!DOCTYPE html>
<html>
<head><title>X</title></head>
<body>
<script>
self.__next_f.push([1,"{\\"@context\\":\\"https://schema.org/\\",\\"@type\\":\\"Product\\",\\"name\\":\\"Simple Product\\",\\"brand\\":\\"BrandX\\",\\"offers\\":{\\"@type\\":\\"Offer\\",\\"price\\":10000,\\"priceCurrency\\":\\"CLP\\",\\"availability\\":\\"https://schema.org/InStock\\"}}"]);
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParisRSCParser:
    def setup_method(self):
        self.parser = ParisRSCParser()

    def test_detects_rsc_chunks(self):
        chunks = self.parser._extract_chunks(HTML_FULL_PRODUCT)
        assert len(chunks) >= 2

    def test_extracts_product_from_jsonld(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.name == "Camiseta de Fútbol Chile 2024 Local"
        assert data.brand == "Adidas"

    def test_extracts_price(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.price == Decimal("23990")

    def test_selects_in_stock_offer_over_out_of_stock(self):
        data = self.parser.parse(HTML_MULTIPLE_OFFERS_BEST)
        assert data.price == Decimal("65000")

    def test_extracts_currency(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.currency == "CLP"

    def test_availability_in_stock(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.availability is True

    def test_availability_out_of_stock(self):
        data = self.parser.parse(HTML_OUT_OF_STOCK)
        assert data.availability is False

    def test_availability_missing(self):
        data = self.parser.parse(HTML_NO_AVAILABILITY)
        assert data.availability is None

    def test_extracts_brand_object(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.brand == "Adidas"

    def test_extracts_brand_string(self):
        data = self.parser.parse(HTML_OUT_OF_STOCK)
        assert data.brand == "Dell"

    def test_extracts_sku_from_jsonld(self):
        data = self.parser.parse(HTML_JSONLD_ONLY)
        assert data.sku == "WH-1000XM5"

    def test_extracts_sku_from_rsc(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.sku == "607430002"

    def test_extracts_gtin(self):
        data = self.parser.parse(HTML_GTIM_PRODUCT)
        assert data.gtin == "5099206104005"

    def test_no_gtin_when_absent(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.gtin is None

    def test_extracts_mpn(self):
        data = self.parser.parse(HTML_JSONLD_ONLY)
        assert data.mpn == "WH1000XM5"

    def test_extracts_image_from_jsonld(self):
        data = self.parser.parse(HTML_IMAGE_IN_ARRAY)
        assert data.image_url == "https://img.paris.cl/tablet1.jpg"

    def test_extracts_image_from_rsc(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.image_url is not None
        assert "607430" in data.image_url

    def test_extracts_url(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.product_url is not None
        assert "paris.cl" in data.product_url

    def test_no_rsc_returns_empty(self):
        data = self.parser.parse(HTML_NO_RSC)
        assert data.name is None
        assert data.price is None

    def test_empty_chunks_returns_empty(self):
        data = self.parser.parse(HTML_EMPTY_CHUNKS)
        assert data.name is None

    def test_malformed_json_returns_empty(self):
        data = self.parser.parse(HTML_MALFORMED_JSON)
        assert data.name is None

    def test_irrelevant_chunks_returns_empty(self):
        data = self.parser.parse(HTML_CHUNKS_IRRELEVANT)
        assert data.name is None

    def test_single_offer_not_list(self):
        data = self.parser.parse(HTML_SINGLE_OFFER)
        assert data.price == Decimal("189990")
        assert data.availability is True

    def test_sources_indicate_origin(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert "json-ld" in data.sources

    def test_rsc_product_no_prices(self):
        data = self.parser.parse(HTML_RSC_PRODUCT_NO_PRICES)
        assert data.name == "Test Product"
        assert data.price is None

    def test_product_key_used_as_id(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.product_id == "607430"

    def test_empty_html(self):
        data = self.parser.parse("")
        assert data.name is None

    def test_junk_html(self):
        data = self.parser.parse("<html><body><<>>not html</body></html>")
        assert data.name is None


# ---------------------------------------------------------------------------
# Connector normalize tests
# ---------------------------------------------------------------------------


class TestParisConnectorNormalize:
    def setup_method(self):
        self.connector = ParisConnector()
        self.parser = ParisRSCParser()

    def _make_record(self, html: str, url: str = "https://www.paris.cl/test.html") -> dict:
        data = self.parser.parse(html)
        return {"url": url, "raw": data}

    def test_normalize_full_product(self):
        record = self._make_record(HTML_FULL_PRODUCT)
        offer = self.connector.normalize(record)
        assert offer.source == "paris:www.paris.cl"
        assert offer.name == "Camiseta de Fútbol Chile 2024 Local"
        assert offer.price == Decimal("23990")
        assert offer.currency == "CLP"
        assert offer.availability is True
        assert offer.brand == "Adidas"
        assert offer.sku == "607430002"
        assert offer.gtin is None
        assert offer.image_url is not None

    def test_external_id_uses_sku(self):
        record = self._make_record(HTML_FULL_PRODUCT)
        offer = self.connector.normalize(record)
        assert offer.external_id == "607430002"

    def test_external_id_fallback_to_product_id(self):
        connector = ParisConnector()
        data = RawProductData(
            name="Test", price=Decimal("100"), currency="CLP",
            availability=True, brand="X", sku=None, product_id="ABC123",
        )
        record = {"url": "https://test.cl/", "raw": data}
        offer = connector.normalize(record)
        assert offer.external_id == "ABC123"

    def test_external_id_fallback_to_brand_mpn(self):
        connector = ParisConnector()
        data = RawProductData(
            name="Test", price=Decimal("100"), currency="CLP",
            availability=True, brand="Y", mpn="MPN-1", sku=None, product_id=None,
        )
        record = {"url": "https://test.cl/", "raw": data}
        offer = connector.normalize(record)
        assert offer.external_id == "Y:MPN-1"

    def test_external_id_none(self):
        connector = ParisConnector()
        data = RawProductData(
            name="Test", price=Decimal("100"), currency="CLP",
            availability=True, brand=None, sku=None, product_id=None, mpn=None,
        )
        record = {"url": "https://test.cl/", "raw": data}
        offer = connector.normalize(record)
        assert offer.external_id is None

    def test_normalize_propagates_mapped_category_slug(self):
        url = "https://www.paris.cl/test.html"
        connector = ParisConnector(
            urls=[url],
            url_category_map={url: "notebooks"},
        )
        data = RawProductData(
            name="Test", price=Decimal("100"), currency="CLP",
            availability=True, brand="X",
        )
        record = connector._record_with_category(url, data)
        offer = connector.normalize(record)
        assert offer.category == "notebooks"

    def test_normalize_category_none_without_url_category_map(self):
        record = self._make_record(HTML_FULL_PRODUCT)
        offer = self.connector.normalize(record)
        assert offer.category is None

    def test_stock_in_stock(self):
        record = self._make_record(HTML_FULL_PRODUCT)
        offer = self.connector.normalize(record)
        assert offer.stock == "in_stock"

    def test_stock_out_of_stock(self):
        record = self._make_record(HTML_OUT_OF_STOCK)
        offer = self.connector.normalize(record)
        assert offer.stock == "out_of_stock"

    def test_stock_unknown(self):
        record = self._make_record(HTML_NO_AVAILABILITY)
        offer = self.connector.normalize(record)
        assert offer.stock == "unknown"

    def test_availability_defaults_true_when_missing(self):
        record = self._make_record(HTML_NO_AVAILABILITY)
        offer = self.connector.normalize(record)
        assert offer.availability is True

    def test_price_decimal(self):
        record = self._make_record(HTML_FULL_PRODUCT)
        offer = self.connector.normalize(record)
        assert isinstance(offer.price, Decimal)

    def test_scraped_at_has_timezone(self):
        record = self._make_record(HTML_FULL_PRODUCT)
        offer = self.connector.normalize(record)
        assert offer.scraped_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Validation integration
# ---------------------------------------------------------------------------


class TestParisValidation:
    def setup_method(self):
        self.connector = ParisConnector()
        self.parser = ParisRSCParser()

    def test_normalized_offer_passes_validation(self):
        from app.ingestion.validation import OfferValidator

        data = self.parser.parse(HTML_FULL_PRODUCT)
        record = {"url": "https://www.paris.cl/test.html", "raw": data}
        offer = self.connector.normalize(record)
        OfferValidator().validate(offer)


# ---------------------------------------------------------------------------
# Pipeline integration tests
# ---------------------------------------------------------------------------

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _reset(db):
    for model in (PriceHistory, StoreOffer, Product, Store, Category):
        db.query(model).delete()
    db.commit()


class _FakeParisConnector(ParisConnector):
    def __init__(self, records: list[dict]):
        super().__init__()
        self._fake_records = records

    def extract(self):
        return iter(self._fake_records)


class TestParisPipelineIntegration:
    def test_full_pipeline_creates_product_store_offer_price_history(self):
        with TestSession() as db:
            _reset(db)
            parser = ParisRSCParser()
            data = parser.parse(HTML_FULL_PRODUCT)
            record = {"url": "https://www.paris.cl/camiseta-607430.html", "raw": data}
            connector = _FakeParisConnector([record])

            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)

            assert not report.errors
            assert len(report.outcomes) == 1

            product = db.query(Product).one()
            assert product.brand == "Adidas"

            offer = db.query(StoreOffer).one()
            assert offer.price == 23990
            assert offer.currency == "CLP"
            assert offer.availability is True
            assert offer.source == "paris:www.paris.cl"
            assert offer.ingestion_status == "success"

            history = db.query(PriceHistory).one()
            assert history.price == 23990

    def test_same_price_no_duplicate_history(self):
        with TestSession() as db:
            _reset(db)
            parser = ParisRSCParser()
            data = parser.parse(HTML_FULL_PRODUCT)
            record = {"url": "https://www.paris.cl/camiseta.html", "raw": data}

            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(_FakeParisConnector([record]))
            assert db.query(PriceHistory).count() == 1

            outcome = IngestionPipeline(service).run(_FakeParisConnector([record])).outcomes[0]
            assert outcome.price_changed is False
            assert db.query(PriceHistory).count() == 1

    def test_price_change_creates_new_history(self):
        with TestSession() as db:
            _reset(db)
            parser = ParisRSCParser()
            data1 = parser.parse(HTML_FULL_PRODUCT)
            record1 = {"url": "https://www.paris.cl/camiseta.html", "raw": data1}

            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(_FakeParisConnector([record1]))
            assert db.query(PriceHistory).count() == 1

            modified = RawProductData(
                name=data1.name, price=Decimal("19990"), currency="CLP",
                availability=True, brand="Adidas", sku="607430002",
                product_url=data1.product_url, image_url=data1.image_url,
            )
            record2 = {"url": "https://www.paris.cl/camiseta.html", "raw": modified}
            outcome = IngestionPipeline(service).run(_FakeParisConnector([record2])).outcomes[0]
            assert outcome.price_changed is True
            assert db.query(PriceHistory).count() == 2

    def test_store_created_correctly(self):
        with TestSession() as db:
            _reset(db)
            parser = ParisRSCParser()
            data = parser.parse(HTML_SINGLE_OFFER)
            record = {"url": "https://www.paris.cl/impresora.html", "raw": data}
            connector = _FakeParisConnector([record])

            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(connector)

            store = db.query(Store).one()
            assert store.name == "Paris"
            assert store.domain == "www.paris.cl"

    def test_multiple_products(self):
        with TestSession() as db:
            _reset(db)
            parser = ParisRSCParser()
            data1 = parser.parse(HTML_FULL_PRODUCT)
            data2 = parser.parse(HTML_OUT_OF_STOCK)
            records = [
                {"url": "https://www.paris.cl/camiseta.html", "raw": data1},
                {"url": "https://www.paris.cl/monitor.html", "raw": data2},
            ]
            connector = _FakeParisConnector(records)

            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)
            assert not report.errors
            assert len(report.outcomes) == 2
            assert db.query(Product).count() == 2
            assert db.query(StoreOffer).count() == 2
