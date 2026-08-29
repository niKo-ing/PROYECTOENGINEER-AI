"""Unit tests for SP Digital connector — no internet required."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.ingestion.connectors.spdigital.connector import SPDigitalConnector
from app.ingestion.connectors.spdigital.parser import RawProductData, SPDigitalParser
from app.ingestion.dto import NormalizedOffer
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.service import CatalogIngestionService
from app.models.catalog import Category, CategorySpecificationDefinition, PriceHistory, Product, Store, StoreOffer

# ---------------------------------------------------------------------------
# HTML Fixtures — based on real SP Digital VTEX meta tag structure
# ---------------------------------------------------------------------------

HTML_FULL_PRODUCT = """
<!DOCTYPE html>
<html>
<head>
    <title>Consola PlayStation 5 Slim Edición Digital Sony, Color Blanco  | SP Digital</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <meta name="product-id" content="NA0000081556">
    <meta name="old-web-id" content="139073">
    <meta name="product:mfr_part_no" content="1000039670">
    <meta name="product:catalog_id" content="79154">
    <meta name="product:retailer_item_id" content="79154">
    <meta name="product:brand" content="SONY">
    <meta name="product:condition" content="new">
    <meta name="product:availability" content="in stock">
    <meta name="product:price:currency" content="CLP">
    <meta name="product:price:amount" content="699990">
    <meta property="og:image" content="https://media.spdigital.cl/thumbnails/products/vylqejec_48c4fabb_thumbnail_4096.png">
    <meta property="og:url" content="/consola-playstation-5-slim-edicion-digital-sony-color-blanco/">
    <meta property="og:title" content="Consola PlayStation 5 Slim Edición Digital Sony, Color Blanco  | SP Digital">
    <meta name="language" content="Spanish">
    <meta name="generator" content="Gatsby 4.16.0">
</head>
<body>
    <h1>Consola PlayStation 5 Slim Edición Digital Sony, Color Blanco</h1>
</body>
</html>
"""

HTML_NO_BRAND = """
<!DOCTYPE html>
<html>
<head>
    <title>Teclado Mecánico Generic | SP Digital</title>
    <meta name="product-id" content="NA0000099999">
    <meta name="product:price:currency" content="CLP">
    <meta name="product:price:amount" content="35000">
    <meta name="product:availability" content="in stock">
    <meta property="og:title" content="Teclado Mecánico Generic | SP Digital">
    <meta property="og:url" content="/teclado-mecanico-generic/">
    <meta property="og:image" content="https://media.spdigital.cl/img/teclado.png">
</head>
<body></body>
</html>
"""

HTML_OUT_OF_STOCK = """
<!DOCTYPE html>
<html>
<head>
    <title>Monitor Dell 27" 4K | SP Digital</title>
    <meta name="product:brand" content="DELL">
    <meta name="product:mfr_part_no" content="S2722QC">
    <meta name="product:retailer_item_id" content="55555">
    <meta name="product:price:currency" content="CLP">
    <meta name="product:price:amount" content="289990">
    <meta name="product:availability" content="out of stock">
    <meta property="og:title" content="Monitor Dell 27&quot; 4K | SP Digital">
    <meta property="og:url" content="/monitor-dell-27-4k/">
    <meta property="og:image" content="https://media.spdigital.cl/img/monitor.png">
</head>
<body></body>
</html>
"""

HTML_NO_AVAILABILITY = """
<!DOCTYPE html>
<html>
<head>
    <title>Auriculares Bluetooth X | SP Digital</title>
    <meta name="product-id" content="NA0000066666">
    <meta name="product:brand" content="GENERIC">
    <meta name="product:price:currency" content="CLP">
    <meta name="product:price:amount" content="15000">
    <meta property="og:title" content="Auriculares Bluetooth X | SP Digital">
    <meta property="og:url" content="/auriculares-x/">
    <meta property="og:image" content="https://media.spdigital.cl/img/auri.png">
</head>
<body></body>
</html>
"""

HTML_NO_PRICE = """
<!DOCTYPE html>
<html>
<head>
    <title>Silla Gamer Pro | SP Digital</title>
    <meta name="product-id" content="NA0000055555">
    <meta name="product:brand" content="Secretlab">
    <meta name="product:price:currency" content="CLP">
    <meta property="og:title" content="Silla Gamer Pro | SP Digital">
    <meta property="og:url" content="/silla-gamer/">
</head>
<body></body>
</html>
"""

HTML_INVALID_PRICE = """
<!DOCTYPE html>
<html>
<head>
    <title>Producto Raro | SP Digital</title>
    <meta name="product-id" content="NA0000044444">
    <meta name="product:price:currency" content="CLP">
    <meta name="product:price:amount" content="not-a-price">
    <meta name="product:availability" content="in stock">
    <meta property="og:title" content="Producto Raro | SP Digital">
    <meta property="og:url" content="/producto-raro/">
</head>
<body></body>
</html>
"""

HTML_MINIMAL = """
<!DOCTYPE html>
<html>
<head>
    <title>Producto Mínimo | SP Digital</title>
</head>
<body></body>
</html>
"""

HTML_EMPTY = ""
HTML_JUNK = "<html><body>not html at all <<>> </body></html>"

HTML_ABSOLUTE_OG_URL = """
<!DOCTYPE html>
<html>
<head>
    <title>Mouse Logitech | SP Digital</title>
    <meta name="product-id" content="NA0000033333">
    <meta name="product:brand" content="LOGITECH">
    <meta name="product:mfr_part_no" content="M185">
    <meta name="product:retailer_item_id" content="33333">
    <meta name="product:price:currency" content="CLP">
    <meta name="product:price:amount" content="19990">
    <meta name="product:availability" content="in stock">
    <meta property="og:title" content="Mouse Logitech M185 | SP Digital">
    <meta property="og:url" content="https://www.spdigital.cl/mouse-logitech-m185/">
    <meta property="og:image" content="https://media.spdigital.cl/img/mouse.png">
</head>
<body></body>
</html>
"""

HTML_RICH_BRAND_STRING = """
<!DOCTYPE html>
<html>
<head>
    <title>Cable HDMI 2.1 | SP Digital</title>
    <meta name="product-id" content="NA0000022222">
    <meta name="product:brand" content="Baseus">
    <meta name="product:price:currency" content="CLP">
    <meta name="product:price:amount" content="12990">
    <meta name="product:availability" content="in stock">
    <meta property="og:title" content="Cable HDMI 2.1 | SP Digital">
    <meta property="og:url" content="/cable-hdmi-21/">
    <meta property="og:image" content="https://media.spdigital.cl/img/cable.png">
</head>
<body></body>
</html>
"""

HTML_NO_TITLE_SUFFIX = """
<!DOCTYPE html>
<html>
<head>
    <title>Producto Sin Sufijo</title>
    <meta name="product-id" content="NA0000011111">
    <meta name="product:brand" content="MarcaX">
    <meta name="product:price:currency" content="CLP">
    <meta name="product:price:amount" content="50000">
    <meta property="og:title" content="Producto Sin Sufijo">
    <meta property="og:url" content="/producto-sin-sufijo/">
</head>
<body></body>
</html>
"""

# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestSPDigitalParser:
    def setup_method(self):
        self.parser = SPDigitalParser()

    def test_full_product_extraction(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.name == "Consola PlayStation 5 Slim Edición Digital Sony, Color Blanco"
        assert data.price == Decimal("699990")
        assert data.currency == "CLP"
        assert data.availability is True
        assert data.brand == "SONY"
        assert data.mpn == "1000039670"
        assert data.sku == "79154"
        assert data.product_id == "NA0000081556"
        assert data.image_url == "https://media.spdigital.cl/thumbnails/products/vylqejec_48c4fabb_thumbnail_4096.png"
        assert data.condition == "new"

    def test_price_is_clp(self):
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

    def test_brand(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.brand == "SONY"

    def test_mpn(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.mpn == "1000039670"

    def test_sku_from_retailer_item_id(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.sku == "79154"

    def test_product_url_relative(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.product_url == "https://www.spdigital.cl/consola-playstation-5-slim-edicion-digital-sony-color-blanco/"

    def test_product_url_absolute(self):
        data = self.parser.parse(HTML_ABSOLUTE_OG_URL)
        assert data.product_url == "https://www.spdigital.cl/mouse-logitech-m185/"

    def test_image_url(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.image_url is not None
        assert data.image_url.startswith("https://")

    def test_no_gtin(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert data.gtin is None if hasattr(data, "gtin") else True

    def test_name_cleans_sp_digital_suffix(self):
        data = self.parser.parse(HTML_FULL_PRODUCT)
        assert "SP Digital" not in data.name
        assert "|" not in data.name

    def test_name_preserves_pipe_in_title(self):
        data = self.parser.parse(HTML_NO_TITLE_SUFFIX)
        assert data.name == "Producto Sin Sufijo"

    def test_no_brand(self):
        data = self.parser.parse(HTML_NO_BRAND)
        assert data.brand is None

    def test_no_price(self):
        data = self.parser.parse(HTML_NO_PRICE)
        assert data.price is None

    def test_invalid_price(self):
        data = self.parser.parse(HTML_INVALID_PRICE)
        assert data.price is None

    def test_minimal_html(self):
        data = self.parser.parse(HTML_MINIMAL)
        assert data.name is None
        assert data.price is None

    def test_empty_html(self):
        data = self.parser.parse(HTML_EMPTY)
        assert data.name is None
        assert data.price is None

    def test_junk_html(self):
        data = self.parser.parse(HTML_JUNK)
        assert data.name is None


# ---------------------------------------------------------------------------
# Connector normalize tests
# ---------------------------------------------------------------------------


class TestSPDigitalConnectorNormalize:
    def setup_method(self):
        self.connector = SPDigitalConnector()
        self.parser = SPDigitalParser()

    def _make_record(self, html: str, url: str = "https://www.spdigital.cl/test/") -> dict:
        data = self.parser.parse(html)
        return {"url": url, "raw": data}

    def test_normalize_full_product(self):
        record = self._make_record(HTML_FULL_PRODUCT)
        offer = self.connector.normalize(record)
        assert offer.source == "spdigital:www.spdigital.cl"
        assert offer.name == "Consola PlayStation 5 Slim Edición Digital Sony, Color Blanco"
        assert offer.price == Decimal("699990")
        assert offer.currency == "CLP"
        assert offer.availability is True
        assert offer.brand == "SONY"
        assert offer.mpn == "1000039670"
        assert offer.sku == "79154"
        assert offer.gtin is None
        assert offer.image_url is not None
        assert offer.product_url == "https://www.spdigital.cl/consola-playstation-5-slim-edicion-digital-sony-color-blanco/"
        assert offer.previous_price is None
        assert offer.model is None
        assert offer.category is None
        assert offer.condition == "new"

    def test_external_id_uses_product_id(self):
        record = self._make_record(HTML_FULL_PRODUCT)
        offer = self.connector.normalize(record)
        assert offer.external_id == "NA0000081556"

    def test_external_id_fallback_to_sku(self):
        record = self._make_record(HTML_OUT_OF_STOCK)
        offer = self.connector.normalize(record)
        assert offer.external_id == "55555"

    def test_external_id_fallback_to_brand_mpn(self):
        connector = SPDigitalConnector()
        data = RawProductData(
            name="Test", price=Decimal("100"), currency="CLP",
            availability=True, brand="ACME", mpn="AC-123",
            sku=None, product_id=None,
            product_url="https://test.com", image_url=None, condition=None,
        )
        record = {"url": "https://test.com", "raw": data}
        offer = connector.normalize(record)
        assert offer.external_id == "ACME:AC-123"

    def test_external_id_none_when_no_identifiers(self):
        connector = SPDigitalConnector()
        data = RawProductData(
            name="Test", price=Decimal("100"), currency="CLP",
            availability=None, brand=None, mpn=None,
            sku=None, product_id=None,
            product_url="https://test.com", image_url=None, condition=None,
        )
        record = {"url": "https://test.com", "raw": data}
        offer = connector.normalize(record)
        assert offer.external_id is None

    def test_stock_mapping_in_stock(self):
        record = self._make_record(HTML_FULL_PRODUCT)
        offer = self.connector.normalize(record)
        assert offer.stock == "in_stock"

    def test_stock_mapping_out_of_stock(self):
        record = self._make_record(HTML_OUT_OF_STOCK)
        offer = self.connector.normalize(record)
        assert offer.stock == "out_of_stock"

    def test_stock_mapping_unknown(self):
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


class TestSPDigitalValidation:
    def setup_method(self):
        self.connector = SPDigitalConnector()
        self.parser = SPDigitalParser()

    def test_normalized_offer_passes_validation(self):
        from app.ingestion.validation import OfferValidator

        data = self.parser.parse(HTML_FULL_PRODUCT)
        record = {"url": "https://www.spdigital.cl/test/", "raw": data}
        offer = self.connector.normalize(record)
        OfferValidator().validate(offer)

    def test_empty_html_produces_valid_offer_with_defaults(self):
        data = self.parser.parse(HTML_EMPTY)
        record = {"url": "https://www.spdigital.cl/test/", "raw": data}
        offer = self.connector.normalize(record)
        assert offer.name == "Sin nombre"
        assert offer.price == Decimal("0")
        assert offer.currency == "CLP"


# ---------------------------------------------------------------------------
# Pipeline integration tests
# ---------------------------------------------------------------------------

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _reset(db):
    for model in (PriceHistory, StoreOffer, Product, Store, CategorySpecificationDefinition, Category):
        db.query(model).delete()
    db.commit()


class _FakeSPDigitalConnector(SPDigitalConnector):
    """In-memory connector that returns pre-built records without HTTP."""

    def __init__(self, records: list[dict]):
        super().__init__()
        self._fake_records = records

    def extract(self):
        return iter(self._fake_records)


class TestSPDigitalPipelineIntegration:
    def test_full_pipeline_creates_product_store_offer_price_history(self):
        with TestSession() as db:
            _reset(db)
            parser = SPDigitalParser()
            data = parser.parse(HTML_FULL_PRODUCT)
            record = {"url": "https://www.spdigital.cl/consola-playstation-5-slim/", "raw": data}
            connector = _FakeSPDigitalConnector([record])

            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)

            assert not report.errors
            assert len(report.outcomes) == 1

            product = db.query(Product).one()
            assert product.name == "Consola PlayStation 5 Slim Edición Digital Sony, Color Blanco"
            assert product.brand == "SONY"
            assert product.mpn == "1000039670"

            offer = db.query(StoreOffer).one()
            assert offer.price == 699990
            assert offer.currency == "CLP"
            assert offer.availability is True
            assert offer.external_id == "NA0000081556"
            assert offer.source == "spdigital:www.spdigital.cl"
            assert offer.ingestion_status == "success"

            history = db.query(PriceHistory).one()
            assert history.price == 699990
            assert history.currency == "CLP"

    def test_same_price_no_duplicate_history(self):
        with TestSession() as db:
            _reset(db)
            parser = SPDigitalParser()
            data = parser.parse(HTML_FULL_PRODUCT)
            record = {"url": "https://www.spdigital.cl/consola-ps5/", "raw": data}
            connector = _FakeSPDigitalConnector([record])

            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(connector)
            assert db.query(PriceHistory).count() == 1

            connector2 = _FakeSPDigitalConnector([record])
            outcome = IngestionPipeline(service).run(connector2).outcomes[0]
            assert outcome.price_changed is False
            assert db.query(PriceHistory).count() == 1

    def test_price_change_creates_new_history(self):
        with TestSession() as db:
            _reset(db)
            parser = SPDigitalParser()
            data1 = parser.parse(HTML_FULL_PRODUCT)
            record1 = {"url": "https://www.spdigital.cl/ps5/", "raw": data1}
            connector1 = _FakeSPDigitalConnector([record1])

            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(connector1)
            assert db.query(PriceHistory).count() == 1

            modified = RawProductData(
                name=data1.name, price=Decimal("599990"), currency="CLP",
                availability=True, brand="SONY", mpn="1000039670",
                sku="79154", product_id="NA0000081556",
                product_url=data1.product_url, image_url=data1.image_url,
                condition="new",
            )
            record2 = {"url": "https://www.spdigital.cl/ps5/", "raw": modified}
            connector2 = _FakeSPDigitalConnector([record2])
            outcome = IngestionPipeline(service).run(connector2).outcomes[0]
            assert outcome.price_changed is True
            assert db.query(PriceHistory).count() == 2

    def test_store_created_correctly(self):
        with TestSession() as db:
            _reset(db)
            parser = SPDigitalParser()
            data = parser.parse(HTML_FULL_PRODUCT)
            record = {"url": "https://www.spdigital.cl/test/", "raw": data}
            connector = _FakeSPDigitalConnector([record])

            service = CatalogIngestionService(db)
            IngestionPipeline(service).run(connector)

            store = db.query(Store).one()
            assert store.name == "SP Digital"
            assert store.domain == "www.spdigital.cl"

    def test_multiple_products_different_pages(self):
        with TestSession() as db:
            _reset(db)
            parser = SPDigitalParser()

            data1 = parser.parse(HTML_FULL_PRODUCT)
            data2 = parser.parse(HTML_OUT_OF_STOCK)
            records = [
                {"url": "https://www.spdigital.cl/ps5/", "raw": data1},
                {"url": "https://www.spdigital.cl/monitor-dell/", "raw": data2},
            ]
            connector = _FakeSPDigitalConnector(records)

            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)
            assert not report.errors
            assert len(report.outcomes) == 2
            assert db.query(Product).count() == 2
            assert db.query(StoreOffer).count() == 2
            assert db.query(PriceHistory).count() == 2
