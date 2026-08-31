import json as jsonlib
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models.catalog import Category, CategorySpecificationDefinition, PriceHistory, Product, ProductSpecValue, ProductSpecValueHistory, Store, StoreOffer

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


def setup_function():
    app.dependency_overrides[get_db] = override_get_db
    with Session() as db:
        for model in (PriceHistory, StoreOffer, ProductSpecValueHistory, ProductSpecValue, Product, Store, CategorySpecificationDefinition, Category):
            db.execute(delete(model))
        db.commit()


def teardown_function():
    app.dependency_overrides.pop(get_db, None)


def _seed_catalog() -> None:
    with Session() as db:
        tecnologia = Category(name="Tecnología", slug="tecnologia", is_group=True, priority="P0")
        computadores = Category(name="Computadores", slug="computadores", parent=tecnologia, is_group=True, priority="P0")
        pc = Category(name="PC y Componentes", slug="pc-y-componentes", parent=tecnologia, is_group=True, priority="P0")
        notebooks = Category(name="Notebooks", slug="notebooks", parent=computadores, priority="P0")
        procesadores = Category(name="Procesadores", slug="procesadores", parent=pc, priority="P0")
        db.add_all([tecnologia, computadores, pc, notebooks, procesadores])

        ram_def = CategorySpecificationDefinition(category=notebooks, key="ram_capacity", label="Capacidad RAM", group="Memoria", data_type="integer", unit="GB", filter_type="range", sort_order=5)
        brand_def = CategorySpecificationDefinition(category=notebooks, key="screen_resolution", label="Resolución", group="Pantalla", data_type="text", filter_type="multi", sort_order=10)
        db.add_all([ram_def, brand_def])

        stores = [Store(name=f"Tienda {index}", domain=f"t{index}.test") for index in range(1, 4)]
        db.add_all(stores)

        fixtures = [
            ("Notebook Gama Alta", "Lenovo", 800000, "16 GB", 16, "2560 × 1440"),
            ("Notebook Gama Media", "Lenovo", 550000, "8 GB", 8, "1920 × 1080"),
            ("Notebook Económico", "HP", 320000, "8 GB", 8, "1366 × 768"),
            ("Notebook Pro", "Apple", 1500000, "32 GB", 32, "2560 × 1600"),
        ]
        products: dict[str, Product] = {}
        for name, brand, price, raw_ram, ram_number, screen in fixtures:
            product = Product(name=name, brand=brand, category_entity=notebooks)
            db.add(product)
            db.flush()
            products[name] = product
            db.add(StoreOffer(product=product, store=stores[0], url=f"https://t1.test/{product.id}", price=price))
            db.add(ProductSpecValue(product=product, definition=ram_def, value_kind="number", value_number=ram_number, unit="GB", raw_value=raw_ram, value_text=raw_ram, source_type="store", verification_status="review"))
            db.add(ProductSpecValue(product=product, definition=brand_def, value_kind="text", value_text=screen, source_type="store", verification_status="review"))
        db.commit()


def test_categories_include_counts_and_group_flags():
    _seed_catalog()

    response = client.get("/api/v1/categories")

    assert response.status_code == 200
    tree = response.json()
    tecnologia = tree[0]
    assert tecnologia["name"] == "Tecnología"
    assert tecnologia["is_group"] is True
    assert tecnologia["total_products"] == 4
    computadores = next(item for item in tecnologia["children"] if item["slug"] == "computadores")
    assert computadores["total_products"] == 4
    notebooks = computadores["children"][0]
    assert notebooks["product_count"] == 4
    assert notebooks["sort_order"] == 0
    assert notebooks["enabled"] is True
    assert notebooks["spec_definitions"][0]["key"] == "ram_capacity"


def test_category_by_slug_returns_subtree():
    _seed_catalog()

    response = client.get("/api/v1/categories/by-slug/notebooks")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Notebooks"
    assert body["total_products"] == 4

    missing = client.get("/api/v1/categories/by-slug/no-existe")
    assert missing.status_code == 404


def test_search_accepts_group_slug_and_includes_subtree_products():
    _seed_catalog()

    response = client.get("/api/v1/products", params={"category": "computadores"})

    assert response.status_code == 200
    assert response.json()["total"] == 4

    empty = client.get("/api/v1/products", params={"category": "procesadores"})
    assert empty.json()["total"] == 0


def test_search_spec_filters_and_ranges():
    _seed_catalog()

    filtered = client.get("/api/v1/products", params={"category": "notebooks", "spec_ranges": jsonlib.dumps({"ram_capacity": "16-32"})})
    assert filtered.json()["total"] == 2

    exact = client.get("/api/v1/products", params={"category": "notebooks", "spec_filters": jsonlib.dumps({"screen_resolution": "1920 × 1080"})})
    assert exact.json()["total"] == 1

    multi = client.get("/api/v1/products", params={"category": "notebooks", "spec_filters": jsonlib.dumps({"screen_resolution": "1920 × 1080,1366 × 768"})})
    assert multi.json()["total"] == 2


def test_search_sort_options():
    _seed_catalog()

    asc = client.get("/api/v1/products", params={"category": "notebooks", "sort": "price_asc"})
    desc = client.get("/api/v1/products", params={"category": "notebooks", "sort": "price_desc"})
    cheapest = [item["name"] for item in asc.json()["items"]]
    priciest = [item["name"] for item in desc.json()["items"]]
    assert cheapest[0] == "Notebook Económico"
    assert priciest[0] == "Notebook Pro"
    assert cheapest == list(reversed(priciest))

    names = client.get("/api/v1/products", params={"category": "notebooks", "sort": "name", "limit": 100})
    name_list = [item["name"] for item in names.json()["items"]]
    assert name_list == sorted(name_list)


def test_search_by_ids():
    _seed_catalog()
    with Session() as db:
        lenovo_ids = [product.id for product in db.query(Product).filter_by(brand="Lenovo").all()][:2]

    response = client.get("/api/v1/products", params={"ids": ",".join(str(item) for item in lenovo_ids)})

    assert response.status_code == 200
    result = response.json()
    assert result["total"] == len(lenovo_ids)
    assert {item["id"] for item in result["items"]} == set(lenovo_ids)


def test_search_single_and_multi_brand():
    _seed_catalog()

    single = client.get("/api/v1/products", params={"category": "notebooks", "brand": "Lenovo"})
    assert single.json()["total"] == 2

    multi = client.get("/api/v1/products", params={"category": "notebooks", "brand": "Lenovo,Apple"})
    assert multi.json()["total"] == 3

    all_brands = client.get("/api/v1/products", params={"category": "notebooks", "brand": "Lenovo,HP,Apple"})
    assert all_brands.json()["total"] == 4


def test_facets_endpoint_returns_aggregations():
    _seed_catalog()

    response = client.get("/api/v1/products/facets", params={"category": "notebooks"})

    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "notebooks"
    assert body["total"] == 4
    assert {option["value"] for option in body["brands"]} == {"Lenovo", "HP", "Apple"}
    assert body["price_range"]["minimum"] == 320000
    assert body["price_range"]["maximum"] == 1500000
    ram = next(spec for spec in body["specs"] if spec["key"] == "ram_capacity")
    assert ram["kind"] == "range"
    assert ram["range"] == {"minimum": 8, "maximum": 32}
    res = next(spec for spec in body["specs"] if spec["key"] == "screen_resolution")
    assert res["kind"] == "options"
    assert {option["value"] for option in res["options"]} == {"2560 × 1440", "1920 × 1080", "1366 × 768", "2560 × 1600"}

    missing = client.get("/api/v1/products/facets", params={"category": "nada"})
    assert missing.status_code == 404


def test_facets_by_group_slug():
    _seed_catalog()

    response = client.get("/api/v1/products/facets", params={"category": "computadores"})

    assert response.status_code == 200
    assert response.json()["total"] == 4