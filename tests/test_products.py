from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models.catalog import Category, CategorySpecificationDefinition, PriceHistory, Product, ProductSpecValue, ProductSpecValueHistory, Store, StoreOffer

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def setup_function():
    app.dependency_overrides[get_db] = override_get_db
    with TestingSession() as db:
        for model in (PriceHistory, StoreOffer, ProductSpecValueHistory, ProductSpecValue, Product, Store, CategorySpecificationDefinition, Category):
            db.execute(delete(model))
        db.commit()


def teardown_function():
    app.dependency_overrides.pop(get_db, None)


def test_create_and_filter_products():
    created = client.post("/api/v1/products", json={"name": "Notebook Gamer", "brand": "Solo", "category": "notebook", "price_clp": 899990, "rating": 4.5})
    assert created.status_code == 201

    result = client.get("/api/v1/products", params={"query": "gamer", "max_price_clp": 900000})
    assert result.status_code == 200
    assert result.json()["total"] == 1
    assert result.json()["items"][0]["name"] == "Notebook Gamer"


def test_product_not_found():
    response = client.get("/api/v1/products/9999")
    assert response.status_code == 404
