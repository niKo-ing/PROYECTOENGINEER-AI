from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.catalog.synonyms import expand_query, expand_token, normalize_spanish
from app.core.security import AuthenticatedUser, get_current_user
from app.db import Base, get_db
from app.main import app
from app.models.catalog import Category, Product, Store, StoreOffer

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


def reset_catalog():
    app.dependency_overrides[get_db] = override_get_db
    with Session() as db:
        for model in (StoreOffer, Product, Category, Store):
            db.execute(delete(model))
        db.commit()


def add_product(name: str, category: str, price: int = 500000) -> int:
    with Session() as db:
        category_entity = db.scalar(select(Category).where(Category.name == category)) or Category(name=category, slug=category.lower())
        store = Store(name=f"Tienda {name}", domain=f"{name.lower().replace(' ', '-')}.test")
        product = Product(name=name, category_entity=category_entity)
        db.add(product)
        db.add(StoreOffer(product=product, store=store, url=f"https://{store.domain}/p", price=price))
        db.commit()
        db.refresh(product)
        return product.id


def seed_catalog():
    reset_catalog()
    add_product("iPhone 15 128GB Negro", "Celulares", 849990)
    add_product("Smartphone Galaxy A57 5G Navy", "Celulares", 499990)
    add_product("Celular Xiaomi Poco M8 5G", "Celulares", 259990)
    add_product("Notebook Aspire Lite i3", "Notebooks", 399990)
    add_product("Notebook Gamer ROG Ultra 9", "Notebooks", 2599990)
    add_product("Notebook HP 15 Ryzen 5", "Notebooks", 529990)


def search(query: str, **params):
    return client.get("/api/v1/products", params={"query": query, **params}).json()


# ── Unit tests: expansión de términos ──────────────────────────────


def test_normalize_spanish_strips_accents():
    assert normalize_spanish("Audífonos") == "audifonos"
    assert normalize_spanish("TELEFONO") == "telefono"


def test_expand_token_groups_equivalent_terms():
    expansion = expand_token("celulares")
    assert {"celulares", "celular", "smartphone", "smartphones", "telefono"} <= expansion


def test_expand_token_handles_singular_and_accented_input():
    assert {"celular", "celulares", "smartphone"} <= expand_token("celular")
    assert "auricular" in expand_token("audífonos")


def test_expand_token_notebook_family():
    expansion = expand_token("notebooks")
    assert {"notebook", "notebooks", "laptop", "portatil"} <= expansion


def test_expand_query_splits_tokens_and_filters_stopwords():
    groups = expand_query("Busca un notebook para gaming")
    assert len(groups) == 2
    assert {"notebook", "notebooks", "laptop"} <= set(groups[0])
    assert "gaming" in groups[1]


def test_expand_query_keeps_short_and_stopword_free():
    assert expand_query("el de") == []
    assert "hp" in expand_query("notebook hp")[1]


def test_expand_query_deduplicates_tokens():
    groups = expand_query("notebook notebook")
    assert len(groups) == 1


# ── Integration: búsqueda por categoría y sinónimos ────────────────


def test_search_finds_products_by_category_for_celulares():
    seed_catalog()
    data = search("celulares")
    assert data["total"] == 3
    assert all(item["category"] == "Celulares" for item in data["items"])


def test_search_smartphones_matches_celulares_category():
    seed_catalog()
    data = search("smartphones")
    assert data["total"] == 3
    assert all(item["category"] == "Celulares" for item in data["items"])


def test_search_singular_and_phone_alias_match_the_category():
    seed_catalog()
    assert search("celular")["total"] == 3
    assert search("telefono")["total"] == 3


def test_search_laptop_matches_notebook_products():
    seed_catalog()
    data = search("laptop")
    assert data["total"] == 3
    assert all(item["category"] == "Notebooks" for item in data["items"])


def test_search_multitoken_uses_and_semantics():
    seed_catalog()
    data = search("notebook hp")
    assert data["total"] == 1
    assert "HP 15" in data["items"][0]["name"]


def test_search_brand_term_does_not_over_expand_category():
    seed_catalog()
    data = search("galaxy")
    assert data["total"] == 1
    assert "Galaxy" in data["items"][0]["name"]


def test_search_empty_terms_returns_all_without_crashing():
    seed_catalog()
    assert search("para que")["total"] == 6


def test_ai_search_tool_uses_same_category_expansion():
    seed_catalog()
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="search-synonyms-user")
    try:
        response = client.post("/api/v1/ai/tools", json={"tool": "search_products", "parameters": {"query": "celulares", "limit": 10}})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 3
    assert all(item["category"] == "Celulares" for item in data["items"])