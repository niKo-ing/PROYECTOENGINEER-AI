from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.catalog.ingestion import NormalizedProduct
from app.catalog.matching import ProductMatcher
from app.catalog.taxonomy import INITIAL_TAXONOMY
from app.db import Base
from app.models.catalog import Category, CategorySpecificationDefinition, Product, ProductSpecification, Store, StoreOffer
from app.repositories.product_repository import ProductRepository
from app.repositories.store_offer_repository import StoreOfferRepository
from app.schemas.product import ProductCreate
from app.services.category_service import CategoryService

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def reset_catalog(db):
    for model in (ProductSpecification, StoreOffer, Product, Store, CategorySpecificationDefinition, Category):
        db.query(model).delete()
    db.commit()


def test_initial_taxonomy_is_hierarchical_and_idempotent():
    with Session() as db:
        reset_catalog(db)
        CategoryService(db).seed_initial_taxonomy()
        CategoryService(db).seed_initial_taxonomy()

        computers = db.query(Category).filter_by(slug="computadores").one()
        notebooks = db.query(Category).filter_by(slug="notebooks").one()
        tech = db.query(Category).filter_by(slug="tecnologia").one()
        assert computers.parent_id == tech.id
        assert notebooks.parent_id == computers.id
        # 8 groups (Tecnología + 7 branches) + 36 leaves = 44
        assert db.query(Category).count() == 44


def test_product_price_is_derived_from_store_offers_and_history_is_separate():
    with Session() as db:
        reset_catalog(db)
        product = ProductRepository(db).create(ProductCreate(name="Notebook de prueba", category="Notebooks", price_clp=800000, brand="Marca", rating=4.5))
        offer = StoreOfferRepository(db).get_for_product(product.id)[0]
        history = StoreOfferRepository(db).record_price(offer, price=offer.price, original_price=None)
        db.commit()

        assert product.price_clp == 800000
        assert offer.product_id == product.id
        assert history.store_offer_id == offer.id
        assert not hasattr(Product, "price")


def test_matcher_prioritizes_strong_identifiers_before_brand_and_model():
    with Session() as db:
        reset_catalog(db)
        category = Category(name="Notebooks", slug="notebooks")
        exact = Product(name="ASUS ROG Strix G16", brand="ASUS", model="G16", mpn="G614", gtin="1234567890123", category_entity=category)
        similar = Product(name="ASUS ROG Strix G16 variante", brand="ASUS", model="G16")
        db.add_all([exact, similar])
        db.commit()

        result = ProductMatcher(db).match(NormalizedProduct(name="Notebook ASUS", brand="ASUS", model="G16", mpn="G614"))
        assert result is not None
        assert result.product is not None
        assert result.product.id == exact.id
