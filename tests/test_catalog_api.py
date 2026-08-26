from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models.catalog import Category, PriceHistory, Product, Store, StoreOffer

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)
client = TestClient(app)


def override_get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


def use_catalog_db():
    app.dependency_overrides[get_db] = override_get_db


def reset_catalog():
    with Session() as db:
        for model in (PriceHistory, StoreOffer, Product, Store, Category):
            db.execute(delete(model))
        db.commit()


def add_comparison_product() -> int:
    reset_catalog()
    with Session() as db:
        category = Category(name="Notebooks", slug="notebooks")
        product = Product(name="Producto X", brand="Marca X", model="X-1", category_entity=category)
        store_a = Store(name="Tienda A", domain="a.test")
        store_b = Store(name="Tienda B", domain="b.test")
        store_c = Store(name="Tienda C", domain="c.test")
        db.add_all([product, StoreOffer(product=product, store=store_a, url="https://a.test/x", price=100000), StoreOffer(product=product, store=store_b, url="https://b.test/x", price=95000), StoreOffer(product=product, store=store_c, url="https://c.test/x", price=110000)])
        db.commit()
        db.refresh(product)
        best_offer = next(offer for offer in product.offers if offer.store.name == "Tienda B")
        db.add_all([PriceHistory(store_offer=best_offer, price=99000, observed_at=datetime.now(timezone.utc) - timedelta(days=1)), PriceHistory(store_offer=best_offer, price=95000, observed_at=datetime.now(timezone.utc))])
        db.commit()
        return product.id


def test_product_endpoints_derive_lowest_price_and_order_offers():
    use_catalog_db()
    product_id = add_comparison_product()

    product = client.get(f"/api/v1/products/{product_id}")
    offers = client.get(f"/api/v1/products/{product_id}/offers")
    assert product.status_code == 200
    assert product.json()["lowest_price"] == 95000
    assert product.json()["lowest_price_store"] == "Tienda B"
    assert product.json()["offer_count"] == 3
    assert [item["price"] for item in offers.json()] == [95000, 100000, 110000]
    assert offers.json()[0]["store"]["name"] == "Tienda B"


def test_catalog_filters_categories_and_price_history_are_public():
    use_catalog_db()
    product_id = add_comparison_product()

    filtered = client.get("/api/v1/products", params={"query": "Producto", "category": "Notebooks", "brand": "Marca X", "min_price_clp": 90000, "max_price_clp": 100000})
    categories = client.get("/api/v1/categories")
    history = client.get(f"/api/v1/products/{product_id}/price-history")
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["lowest_price"] == 95000
    assert categories.status_code == 200
    assert categories.json()[0]["name"] == "Notebooks"
    assert [item["price"] for item in history.json()] == [99000, 95000]
