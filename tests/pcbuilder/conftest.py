import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models.catalog import Category
from app.pcbuilder.catalog import seed_pc_parts
from app.pcbuilder.catalog_data import PARTS
from app.pcbuilder.parts import Part


def catalog_parts() -> list[Part]:
    return [Part(slot=d["slot"], name=f"{d['brand']} {d['model']}", specs=d["pc"], product_id=i + 1, price_clp=d.get("price"), brand=d["brand"], legacy=bool(d.get("legacy")))
            for i, d in enumerate(PARTS)]


@pytest.fixture()
def catalog() -> list[Part]:
    return catalog_parts()


@pytest.fixture()
def by_name(catalog):
    def find(fragment: str) -> Part:
        matches = [p for p in catalog if fragment.lower() in p.name.lower()]
        assert matches, fragment
        return matches[0]
    return find


@pytest.fixture()
def env(monkeypatch):
    """Cliente de la API con una base en memoria sembrada con las piezas del armador."""
    for name in ("AUTH_RATE_LIMIT_PER_MINUTE", "PC_RATE_LIMIT_PER_MINUTE", "PC_AI_RATE_LIMIT_PER_MINUTE"):
        monkeypatch.setenv(name, "1000")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add(Category(name="PC y Componentes", slug="pc-y-componentes", is_group=True))
        db.commit()
        seed_pc_parts(db)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    yield client, Session
    app.dependency_overrides.pop(get_db, None)
