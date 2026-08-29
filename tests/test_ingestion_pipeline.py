from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.ingestion.connectors import MockStoreConnector, StoreConnector
from app.ingestion.dto import NormalizedOffer
from app.ingestion.pipeline import IngestionPipeline, IngestionReport
from app.ingestion.service import CatalogIngestionService
from app.ingestion.validation import OfferValidationError, OfferValidator
from app.models.catalog import Category, PriceHistory, Product, Store, StoreOffer

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def reset(db):
    for model in (PriceHistory, StoreOffer, Product, Store, Category):
        db.query(model).delete()
    db.commit()


def test_mock_connectors_match_one_product_and_preserve_price_history_on_same_price():
    with Session() as db:
        reset(db)
        service = CatalogIngestionService(db)
        connectors = [
            MockStoreConnector(store_name="Tienda A", store_domain="a.mock", price=100000, external_id="a-product-a"),
            MockStoreConnector(store_name="Tienda B", store_domain="b.mock", price=95000, external_id="b-product-a"),
            MockStoreConnector(store_name="Tienda C", store_domain="c.mock", price=110000, external_id="c-product-a"),
        ]
        for connector in connectors:
            report = IngestionPipeline(service).run(connector)
            assert not report.errors
            assert len(report.outcomes) == 1

        product = db.query(Product).one()
        assert db.query(StoreOffer).count() == 3
        assert product.lowest_price == 95000
        assert product.lowest_price_store == "Tienda B"
        assert db.query(PriceHistory).count() == 3

        outcome = IngestionPipeline(service).run(connectors[1]).outcomes[0]
        assert outcome.price_changed is False
        assert db.query(PriceHistory).count() == 3

        changed = MockStoreConnector(store_name="Tienda B", store_domain="b.mock", price=90000, external_id="b-product-a")
        outcome = IngestionPipeline(service).run(changed).outcomes[0]
        assert outcome.price_changed is True
        assert product.lowest_price == 90000
        assert db.query(PriceHistory).count() == 4
        offer = db.query(StoreOffer).filter_by(external_id="b-product-a").one()
        assert offer.source == "mock:b.mock"
        assert offer.ingestion_status == "success"
        assert offer.error_count == 0
        assert offer.last_checked_at is not None and offer.last_seen_at is not None


def test_validator_rejects_invalid_normalized_offers_without_writing_catalog():
    invalid = NormalizedOffer(source="mock", external_id=None, product_url="not-a-url", name="Producto", brand=None, model=None, mpn=None, gtin=None, sku=None, price=-1, previous_price=None, currency="CL", availability=True, stock=None, image_url=None, category=None, scraped_at=datetime.now(timezone.utc))
    try:
        OfferValidator().validate(invalid)
    except OfferValidationError:
        pass
    else:
        raise AssertionError("La oferta inválida debía ser rechazada")


def test_product_image_persisted_on_create():
    with Session() as db:
        reset(db)
        service = CatalogIngestionService(db)
        connector = MockStoreConnector(
            store_name="Tienda A", store_domain="a.mock", price=100000,
            external_id="a-product-a", image_url="https://cdn.example.com/a.jpg",
        )
        report = IngestionPipeline(service).run(connector)
        assert not report.errors
        assert len(report.outcomes) == 1
        assert report.outcomes[0].product_created
        product = db.query(Product).one()
        assert product.image_url == "https://cdn.example.com/a.jpg"


def test_product_image_backfilled_on_match_when_missing():
    with Session() as db:
        reset(db)
        service = CatalogIngestionService(db)
        first = MockStoreConnector(store_name="Tienda A", store_domain="a.mock", price=100000, external_id="a-product-a")
        IngestionPipeline(service).run(first)
        product = db.query(Product).one()
        assert product.image_url is None

        second = MockStoreConnector(
            store_name="Tienda B", store_domain="b.mock", price=98000,
            external_id="b-product-a", image_url="https://cdn.example.com/b.jpg",
        )
        report = IngestionPipeline(service).run(second)
        assert not report.errors
        assert report.outcomes[0].product_matched
        db.refresh(product)
        assert db.query(Product).count() == 1
        assert product.image_url == "https://cdn.example.com/b.jpg"


def test_product_image_not_overwritten_on_match():
    with Session() as db:
        reset(db)
        service = CatalogIngestionService(db)
        first = MockStoreConnector(
            store_name="Tienda A", store_domain="a.mock", price=100000,
            external_id="a-product-a", image_url="https://cdn.example.com/original.jpg",
        )
        IngestionPipeline(service).run(first)
        product = db.query(Product).one()
        assert product.image_url == "https://cdn.example.com/original.jpg"

        second = MockStoreConnector(
            store_name="Tienda B", store_domain="b.mock", price=98000,
            external_id="b-product-a", image_url="https://cdn.example.com/changed.jpg",
        )
        report = IngestionPipeline(service).run(second)
        assert not report.errors
        assert report.outcomes[0].product_matched
        db.refresh(product)
        assert product.image_url == "https://cdn.example.com/original.jpg"


def test_product_image_stays_null_when_offer_has_none():
    with Session() as db:
        reset(db)
        service = CatalogIngestionService(db)
        first = MockStoreConnector(store_name="Tienda A", store_domain="a.mock", price=100000, external_id="a-product-a")
        IngestionPipeline(service).run(first)
        second = MockStoreConnector(store_name="Tienda B", store_domain="b.mock", price=98000, external_id="b-product-a")
        report = IngestionPipeline(service).run(second)
        assert not report.errors
        product = db.query(Product).one()
        assert product.image_url is None
