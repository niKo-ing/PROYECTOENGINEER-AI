"""Tests for the structured spec normalizer (M.2, PCIe, ports, power connectors)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.catalog.spec_backfill import backfill_product_specs
from app.catalog.spec_normalizer import normalize_m2_slots, normalize_pcie_slots, normalize_power_connectors, normalize_rear_ports, normalize_to_json
from app.db import Base
from app.models.catalog import Category, CategorySpecificationDefinition, Product, ProductSpecValue, ProductSpecValueHistory, SpecValueKind
from app.services.product_spec_value_service import ProductSpecValueService

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _reset(db):
    for model in (ProductSpecValueHistory, ProductSpecValue, Product, CategorySpecificationDefinition, Category):
        db.query(model).delete()
    db.commit()


def test_normalize_pcie_slots_parses_compact_list():
    result = normalize_to_json("pcie_slot_list", "1x PCIe 5.0 x16, 2x PCIe 4.0 x1")
    assert result == [
        {"type": "PCIe x16", "generation": "5.0", "lanes": 16, "count": 1},
        {"type": "PCIe x1", "generation": "4.0", "lanes": 1, "count": 2},
    ]


def test_normalize_m2_slots_parses_form_factors_and_interface():
    result = normalize_to_json("m2_slot_list", "1x M.2 2280 (PCIe 5.0 x4), 1x M.2 2280 (SATA)")
    assert result[0]["interface"] == "PCIe"
    assert result[0]["generation"] == "5.0"
    assert result[0]["lanes"] == 4
    assert result[0]["form_factors"] == ["2280"]
    assert result[1]["interface"] == "SATA"


def test_normalize_rear_ports_detects_versions():
    result = normalize_to_json("rear_ports", "2x USB 3.2 Gen 1, 1x HDMI 2.1, 1x DisplayPort 1.4")
    kinds = [(p["kind"], p["version"], p["count"]) for p in result]
    assert ("USB", "3.2 Gen 1", 2) in kinds
    assert ("HDMI", "2.1", 1) in kinds
    assert ("DisplayPort", "1.4", 1) in kinds


def test_normalize_power_connectors_detects_pins_and_types():
    atx = normalize_to_json("motherboard_power_connector", "24-pin")
    assert atx == [{"type": "ATX", "pins": 24, "count": 1}]
    cpu = normalize_to_json("cpu_power_connector_types", "1x 8-pin EPS + 1x 4-pin")
    assert cpu[0]["type"] == "EPS"
    assert cpu[0]["pins"] == 8


def test_normalize_video_keeps_version():
    assert normalize_to_json("hdmi", "1x HDMI 2.1") == [{"version": "2.1", "count": 1}]


def _add_motherboard(db):
    category = Category(name="Motherboards", slug="motherboards")
    defs = [
        CategorySpecificationDefinition(category=category, key="pcie_slot_list", label="Detalle slots PCIe", group="Expansión", data_type="json", item_schema={"type": "string", "generation": "string", "lanes": "number", "count": "number"}, facetable=False),
        CategorySpecificationDefinition(category=category, key="m2_slot_list", label="Detalle slots M.2", group="Almacenamiento", data_type="json", item_schema={"interface": "string", "generation": "string", "lanes": "number", "form_factors": ["string"]}, facetable=False),
    ]
    product = Product(
        name="ASUS Prime B650M-A II",
        brand="ASUS",
        category_entity=category,
        specs={
            "sections": [
                {"title": "Expansión", "items": [{"label": "Detalle slots PCIe", "value": "1x PCIe 5.0 x16, 1x PCIe 4.0 x1"}]},
                {"title": "Almacenamiento", "items": [{"label": "Detalle slots M.2", "value": "1x M.2 2280 (PCIe 5.0 x4)"}]},
            ],
        },
    )
    db.add_all([category, product, *defs])
    db.commit()
    return product


def test_backfill_stores_structured_json_for_motherboard():
    with Session() as db:
        _reset(db)
        product = _add_motherboard(db)

        backfill_product_specs(product, ProductSpecValueService(db, auto_commit=False))
        db.commit()

        pcie = db.query(ProductSpecValue).filter(ProductSpecValue.definition.has(key="pcie_slot_list")).one()
        assert pcie.value_kind == SpecValueKind.JSON.value
        assert pcie.value_json == [
            {"type": "PCIe x16", "generation": "5.0", "lanes": 16, "count": 1},
            {"type": "PCIe x1", "generation": "4.0", "lanes": 1, "count": 1},
        ]
        m2 = db.query(ProductSpecValue).filter(ProductSpecValue.definition.has(key="m2_slot_list")).one()
        assert m2.value_json[0]["interface"] == "PCIe"
        assert m2.value_json[0]["form_factors"] == ["2280"]
