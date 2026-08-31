from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import AuthenticatedUser, get_current_user
from app.db import Base, get_db
from app.main import app
from app.models.catalog import Category, CategorySpecificationDefinition, Product, ProductSpecValue, ProductSpecValueHistory, Store, StoreOffer

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
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="admin-user", email="admin@example.com")
    with Session() as db:
        for model in (ProductSpecValueHistory, ProductSpecValue, StoreOffer, Product, Store, CategorySpecificationDefinition, Category):
            db.execute(delete(model))
        db.commit()


def teardown_function():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def _add_pending_spec() -> int:
    with Session() as db:
        category = Category(name="Notebooks", slug="notebooks")
        product = Product(name="Notebook Admin", brand="Lenovo", category_entity=category)
        definition = CategorySpecificationDefinition(category=category, key="ram_capacity", label="Capacidad RAM", group="Memoria", data_type="integer", unit="GB")
        store = Store(name="Tienda Admin", domain="admin.test")
        db.add_all([category, product, definition, store, StoreOffer(product=product, store=store, url="https://admin.test/notebook", price=100000)])
        db.flush()
        value = ProductSpecValue(product=product, definition=definition, value_kind="number", value_number=16, unit="GB", raw_value="16 GB", source_type="ai", source_name="Product.specs JSON", extraction_method="product_specs_json", verification_status="review", conflict_status="none")
        db.add(value)
        db.commit()
        return value.id


def test_admin_lists_spec_values_for_review():
    _add_pending_spec()

    response = client.get("/api/v1/admin/spec-values/review")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["product_name"] == "Notebook Admin"
    assert item["label"] == "Capacidad RAM"
    assert item["value"] == "16 GB"
    assert item["verification_status"] == "review"


def test_admin_verifies_spec_value():
    value_id = _add_pending_spec()

    response = client.post(f"/api/v1/admin/spec-values/{value_id}/verify", json={"note": "ok"})

    assert response.status_code == 200
    assert response.json()["verification_status"] == "verified"
    with Session() as db:
        value = db.get(ProductSpecValue, value_id)
        assert value is not None
        assert value.verified_by == "admin@example.com"
        assert db.query(ProductSpecValueHistory).count() == 1


def test_admin_verifies_spec_value_with_correction():
    value_id = _add_pending_spec()

    response = client.post(
        f"/api/v1/admin/spec-values/{value_id}/verify",
        json={"note": "5500 MB/s es etiqueta de la tienda; la velocidad documentada es LPDDR5-5500", "value_kind": "number", "raw_value": "5500 MB/s", "value_text": "5500", "value_number": 5500, "unit": "MT/s", "source_type": "admin", "source_name": "Revisión manual"},
    )

    assert response.status_code == 200
    assert response.json()["verification_status"] == "verified"
    with Session() as db:
        value = db.get(ProductSpecValue, value_id)
        assert value.value_number == 5500
        assert value.unit == "MT/s"
        assert value.conflict_status == "resolved"
        assert value.verified_by == "admin@example.com"


def test_admin_dashboard_returns_real_metrics_and_activity():
    value_id = _add_pending_spec()
    client.post(f"/api/v1/admin/spec-values/{value_id}/verify", json={"note": "ok"})
    with Session() as db:
        category = db.query(Category).filter_by(slug="notebooks").one()
        db.add(Product(name="Notebook sin specs", category_entity=category))
        db.commit()

    response = client.get("/api/v1/admin/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["products"] == 2
    assert body["metrics"]["offers"] == 1
    assert body["metrics"]["stores"] == 1
    assert body["metrics"]["specs_pending"] == 0
    assert body["metrics"]["conflicts"] == 0
    assert body["metrics"]["products_without_specs"] == 1
    assert body["metrics"]["products_verified"] == 1
    assert body["recent_activity"][0]["action"] == "verified"
    assert body["recent_activity"][0]["product_name"] == "Notebook Admin"


def test_admin_catalog_quality_reports_completeness_and_missing_specs():
    with Session() as db:
        category = Category(name="Notebooks", slug="notebooks")
        product = Product(name="Notebook incompleto", brand="Lenovo", category_entity=category)
        empty_product = Product(name="Notebook sin specs", category_entity=category)
        processor = CategorySpecificationDefinition(category=category, key="processor", label="Procesador", group="Procesador", data_type="text")
        ram = CategorySpecificationDefinition(category=category, key="ram_capacity", label="Capacidad RAM", group="Memoria", data_type="integer", unit="GB")
        screen = CategorySpecificationDefinition(category=category, key="screen_size", label="Tamaño pantalla", group="Pantalla", data_type="decimal", unit='"')
        db.add_all([category, product, empty_product, processor, ram, screen])
        db.flush()
        db.add_all([
            ProductSpecValue(product=product, definition=processor, value_kind="text", value_text="Intel Core i5", raw_value="Intel Core i5", source_type="ai", verification_status="review"),
            ProductSpecValue(product=product, definition=ram, value_kind="number", value_number=16, unit="GB", raw_value="16 GB", source_type="ai", verification_status="review"),
        ])
        db.commit()

    response = client.get("/api/v1/admin/catalog/quality")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["products"] == 2
    assert body["summary"]["spec_values"] == 2
    assert body["summary"]["products_without_specs"] == 1
    assert body["categories"] == [{"category": "Notebooks", "products": 2}]
    incomplete = {item["name"]: item for item in body["products_incomplete"]}
    assert incomplete["Notebook sin specs"]["score"] < incomplete["Notebook incompleto"]["score"]
    assert "Tamaño pantalla" in incomplete["Notebook incompleto"]["missing"]
    assert {item["key"] for item in body["definitions_used"]} == {"processor", "ram_capacity"}
    assert body["definitions_always_empty"][0]["key"] == "screen_size"
    assert body["sources"] == [{"source_type": "ai", "values": 2}]
    assert body["verification"] == [{"status": "review", "values": 2}]
