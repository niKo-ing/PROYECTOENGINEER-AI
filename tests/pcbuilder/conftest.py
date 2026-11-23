import pytest

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
