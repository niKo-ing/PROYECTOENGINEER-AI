from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import AuthenticatedUser, get_current_user
from app.db import Base, get_db
from app.main import app
from app.models.catalog import Category, PriceHistory, Product, Store, StoreOffer
from app.models.user_profile import UserProfile

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def set_user(user_id: str):
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id)


def reset_database():
    app.dependency_overrides[get_db] = override_get_db
    with TestingSession() as db:
        db.execute(delete(UserProfile))
        db.execute(delete(PriceHistory))
        db.execute(delete(StoreOffer))
        db.execute(delete(Product))
        db.execute(delete(Category))
        db.execute(delete(Store))
        db.commit()


def add_product(name: str, price: int, category: str = "notebook") -> int:
    with TestingSession() as db:
        category_entity = db.scalar(select(Category).where(Category.slug == category)) or Category(name=category, slug=category)
        store = Store(name=f"Tienda {name}", domain=f"{name.lower().replace(' ', '-')}.test")
        product = Product(name=name, category_entity=category_entity, rating=4.5)
        db.add(product)
        db.add(StoreOffer(product=product, store=store, url=f"https://{store.domain}/producto", price=price))
        db.commit()
        db.refresh(product)
        return product.id


def add_profile(user_id: str, name: str):
    with TestingSession() as db:
        db.add(UserProfile(user_id=user_id, display_name=name, favorite_categories=["notebook"], favorite_brands=[], rejected_brands=[], general_preferences={}, shopping_preferences={}))
        db.commit()


def test_search_products_tool_returns_compact_filtered_results():
    reset_database()
    set_user("user-one")
    add_product("Notebook Gamer", 899990)
    add_product("Notebook Económico", 499990)

    response = client.post("/api/v1/ai/tools", json={"tool": "search_products", "parameters": {"query": "notebook", "min_price_clp": 600000, "max_price_clp": 900000}})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["items"][0] == {"id": data["items"][0]["id"], "name": "Notebook Gamer", "category": "notebook", "price_clp": 899990, "rating": 4.5}


def test_get_product_tool_returns_product_summary():
    reset_database()
    set_user("user-one")
    product_id = add_product("Notebook Gamer", 899990)

    response = client.post("/api/v1/ai/tools", json={"tool": "get_product", "parameters": {"product_id": product_id}})
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Notebook Gamer"
    assert "description" not in response.json()["data"]


def test_offer_and_price_history_tools_return_compact_catalog_data():
    reset_database()
    set_user("user-one")
    product_id = add_product("Notebook Gamer", 100000)
    with TestingSession() as db:
        product = db.get(Product, product_id)
        second_store = Store(name="Tienda B", domain="store-b.test")
        db.add(StoreOffer(product=product, store=second_store, url="https://store-b.test/notebook", price=95000))
        first_offer = db.query(StoreOffer).filter_by(product_id=product_id).first()
        db.add(PriceHistory(store_offer=first_offer, price=100000, observed_at=datetime.now(timezone.utc)))
        db.commit()

    offers = client.post("/api/v1/ai/tools", json={"tool": "get_product_offers", "parameters": {"product_id": product_id}})
    history = client.post("/api/v1/ai/tools", json={"tool": "get_price_history", "parameters": {"product_id": product_id}})
    assert offers.status_code == 200
    assert offers.json()["data"]["items"][0]["price"] == 95000
    assert history.status_code == 200
    assert history.json()["data"]["items"][0]["price"] == 100000


def test_get_user_profile_tool_uses_authenticated_identity_only():
    reset_database()
    first_user, second_user = "user-one", "user-two"
    add_profile(first_user, "Ana")
    add_profile(second_user, "Beto")
    set_user(first_user)

    response = client.post("/api/v1/ai/tools", json={"tool": "get_user_profile", "parameters": {"user_id": second_user}})
    assert response.status_code == 200
    assert response.json()["data"]["display_name"] == "Ana"
    assert "user_id" not in response.json()["data"]


def test_unregistered_tool_and_invalid_parameters_are_rejected():
    reset_database()
    set_user("user-one")
    unknown = client.post("/api/v1/ai/tools", json={"tool": "delete_everything", "parameters": {}})
    invalid = client.post("/api/v1/ai/tools", json={"tool": "search_products", "parameters": {"min_price_clp": 900, "max_price_clp": 100}})
    assert unknown.status_code == 404
    assert invalid.status_code == 422


def test_ai_tools_require_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    response = client.post("/api/v1/ai/tools", json={"tool": "search_products", "parameters": {}})
    assert response.status_code == 401
