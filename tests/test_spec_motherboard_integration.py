"""Integration tests: realistic motherboard variants (ASUS / MSI / Gigabyte / ASRock).

Validates the Fase 3.5 structured spec pipeline end-to-end against real-world
spec strings: PCIe, M.2, fan headers, power connectors, USB and SATA, plus the
absent-vs-missing boolean rule and manufacturer provenance.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.catalog.spec_backfill import backfill_product_specs
from app.catalog.spec_normalizer import normalize_fan_headers, normalize_pcie_slots, normalize_sata_speed, normalize_to_json, scan_usb_ports
from app.catalog.spec_research import ExtractedSpec, extract_specs
from app.catalog.spec_sources import sources_for_product
from app.catalog.taxonomy import MOTHERBOARD_SPECS
from app.db import Base
from app.models.catalog import Category, CategorySpecificationDefinition, Product, ProductSpecValue, ProductSpecValueHistory
from app.services.product_spec_value_service import ProductSpecValueService

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


@pytest.fixture()
def db():
    with Session() as session:
        yield session


def _reset(db):
    for model in (ProductSpecValueHistory, ProductSpecValue, Product, CategorySpecificationDefinition, Category):
        db.query(model).delete()
    db.commit()


def _seed_motherboard(db, name, spec_json):
    category = Category(name="Placas madre", slug="placas-madre")
    db.add(category)
    db.flush()
    for definition in MOTHERBOARD_SPECS:
        db.add(
            CategorySpecificationDefinition(
                category=category,
                key=definition.key,
                label=definition.label,
                group=definition.group,
                data_type=definition.data_type,
                unit=definition.unit,
                filter_type=definition.filter_type,
                required=definition.required,
                comparable=definition.comparable,
                facetable=definition.facetable,
                applicability=definition.applicability,
                sort_order=definition.sort_order,
                options=list(definition.options) if definition.options else None,
                item_schema=definition.item_schema,
            )
        )
    product = Product(
        name=name,
        brand="ASUS",
        category_entity=category,
        specs={"sections": [{"title": title, "items": items} for title, items in spec_json.items()]},
    )
    db.add(product)
    db.commit()
    return product, {definition.key: definition for definition in product.category_entity.spec_definitions}


def _get_value(db, product, key):
    return db.query(ProductSpecValue).join(ProductSpecValue.definition).filter(
        ProductSpecValue.product_id == product.id,
        CategorySpecificationDefinition.key == key,
    ).one_or_none()


# --------------------------------------------------------------------------- #
# 1. Real-world PCIe / M.2 / SATA / USB / video variations (req #4)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1 x PCIe 5.0 x16", [{"type": "PCIe x16", "generation": "5.0", "lanes": 16, "count": 1}]),
        ("1x PCIe 4.0 x16", [{"type": "PCIe x16", "generation": "4.0", "lanes": 16, "count": 1}]),
        ("PCIe 5.0 x16, PCIe 4.0 x4", [{"type": "PCIe x16", "generation": "5.0", "lanes": 16, "count": 1}, {"type": "PCIe x4", "generation": "4.0", "lanes": 4, "count": 1}]),
        ("1 × PCI Express 5.0 x16", [{"type": "PCIe x16", "generation": "5.0", "lanes": 16, "count": 1}]),
        ("PCIe x16 Gen 5", [{"type": "PCIe x16", "generation": "5.0", "lanes": 16, "count": 1}]),
    ],
)
def test_pcie_variants(raw, expected):
    assert normalize_to_json("pcie_slot_list", raw) == expected


def test_pcie_counts_accumulate():
    result = normalize_to_json("pcie_slot_list", "1x PCIe 5.0 x16, 2x PCIe 4.0 x1, 1x PCIe 3.0 x1")
    assert result == [
        {"type": "PCIe x16", "generation": "5.0", "lanes": 16, "count": 1},
        {"type": "PCIe x1", "generation": "4.0", "lanes": 1, "count": 2},
        {"type": "PCIe x1", "generation": "3.0", "lanes": 1, "count": 1},
    ]


def test_m2_never_invents_interface():
    # "3 x M.2" carries no interface/generation -> must NOT be guessed
    result = normalize_to_json("m2_slot_list", "3 x M.2")
    assert result == [{"interface": None, "generation": None, "lanes": None, "form_factors": []}]
    # full detail still captured when present
    detailed = normalize_to_json("m2_slot_list", "1 x M.2 2280 PCIe 5.0 x4, 1 x M.2 22110 SATA")
    assert detailed[0] == {"interface": "PCIe", "generation": "5.0", "lanes": 4, "form_factors": ["2280"]}
    assert detailed[1]["interface"] == "SATA"


def test_sata_speed_canonicalization():
    assert normalize_sata_speed("4 x SATA 6Gb/s") == "SATA 3.0 6 Gb/s"
    assert normalize_sata_speed("4 SATA III") == "SATA 3.0 6 Gb/s"
    assert normalize_sata_speed("SATA 6 Gbps ×4") == "SATA 3.0 6 Gb/s"


def test_usb_scan_detects_type_c_and_version():
    result = scan_usb_ports("2x USB 3.2 Gen 2 Type-C, 4x USB 3.2 Gen 1")
    assert result == [
        {"kind": "USB", "version": "3.2 Gen 2", "connector": "Type-C", "count": 2},
        {"kind": "USB", "version": "3.2 Gen 1", "connector": None, "count": 4},
    ]


def test_video_preserves_version_and_count():
    assert normalize_to_json("displayport", "2 x DisplayPort 1.4") == [{"version": "1.4", "count": 2}]
    assert normalize_to_json("hdmi", "1 x HDMI 2.1") == [{"version": "2.1", "count": 1}]


def test_power_connector_counts_vs_pins():
    assert normalize_to_json("motherboard_power_connector", "24-pin") == [{"type": "ATX", "pins": 24, "count": 1}]
    assert normalize_to_json("cpu_power_connector_types", "2x 8-pin EPS") == [{"type": "EPS", "pins": 8, "count": 2}]
    # 8+4-pin sums pins without confusing them for the connector count
    assert normalize_to_json("cpu_power_connector_types", "1x 8+4-pin CPU") == [{"type": "ATX12V", "pins": 12, "count": 1}]


def test_fan_header_list_structured():
    result = normalize_fan_headers("1 x CPU_FAN, 1 x CPU_OPT, 3 x CHA_FAN, 2 x AIO_PUMP")
    assert result == [
        {"name": "CPU_FAN", "count": 1},
        {"name": "CPU_OPT", "count": 1},
        {"name": "CHA_FAN", "count": 3},
        {"name": "AIO_PUMP", "count": 2},
    ]


# --------------------------------------------------------------------------- #
# 2. End-to-end backfill of a realistic ASUS Prime B650M-A (req #3)
# --------------------------------------------------------------------------- #

def test_backfill_asus_b650m_structured(db):
    _reset(db)
    product, defs = _seed_motherboard(
        db,
        "ASUS Prime B650M-A II-CSM",
        {
            "Expansión": [{"label": "Detalle slots PCIe", "value": "1 x PCIe 5.0 x16, 1 x PCIe 4.0 x1"}],
            "Almacenamiento": [{"label": "Detalle slots M.2", "value": "2 x M.2"}, {"label": "Puertos SATA", "value": "4 x SATA 6Gb/s"}],
            "Alimentación": [{"label": "Tipos conector CPU", "value": "1 x 8-pin EPS"}],
            "Refrigeración": [{"label": "Detalle headers ventilador", "value": "1 x CPU_FAN, 1 x CPU_OPT, 3 x CHA_FAN"}],
        },
    )
    backfill_product_specs(product, ProductSpecValueService(db, auto_commit=False))
    db.commit()

    pcie = _get_value(db, product, "pcie_slot_list").value_json
    assert pcie[0] == {"type": "PCIe x16", "generation": "5.0", "lanes": 16, "count": 1}
    assert pcie[1] == {"type": "PCIe x1", "generation": "4.0", "lanes": 1, "count": 1}

    m2 = _get_value(db, product, "m2_slot_list").value_json
    assert m2 == [{"interface": None, "generation": None, "lanes": None, "form_factors": []}]

    sata = _get_value(db, product, "sata_ports")
    assert sata.value_number == 4
    fan = _get_value(db, product, "fan_header_list").value_json
    assert {item["name"] for item in fan} == {"CPU_FAN", "CPU_OPT", "CHA_FAN"}


# --------------------------------------------------------------------------- #
# 3. Taxonomy correctness: groups, applicability, no invented keys (req #11)
# --------------------------------------------------------------------------- #

def test_taxonomy_groups_and_applicability():
    keys = {s.key: s for s in MOTHERBOARD_SPECS}
    assert keys["dimensions"].group == "Dimensiones"
    assert keys["weight"].group == "Dimensiones"
    assert keys["rear_ports"].group == "Panel trasero"
    assert keys["fan_header_list"].data_type == "json"
    required = {s.key for s in MOTHERBOARD_SPECS if s.applicability == "required"}
    assert {"socket", "chipset", "memory_type", "ram_slots"} <= required
    conditional = {s.key for s in MOTHERBOARD_SPECS if s.applicability == "conditional"}
    assert {"sli_support", "wifi_standard", "thunderbolt_header"} <= conditional
    # manufacturer/model are product identity, not specs: must not be duplicated
    assert "manufacturer" not in keys and "model" not in keys


def test_taxonomy_facetable_flags():
    by_key = {s.key: s for s in MOTHERBOARD_SPECS}
    # free-text fields must not be facetable
    for key in ("ethernet_controller", "wifi_controller", "audio_codec", "rgb_software", "pcie_lane_configuration", "cpu_compatibility"):
        assert by_key[key].facetable is False, key


# --------------------------------------------------------------------------- #
# 4. Absent vs missing boolean rule (req #6) + manufacturer provenance (req #8)
# --------------------------------------------------------------------------- #

ASUS_NETWORK_CONTEXT = (
    "Conectividad: 1x Realtek 2.5Gb Ethernet, 1x Intel Wi-Fi 6E AX211, Bluetooth 5.3. "
    "Audio: Realtek ALC897, 7.1 Surround High Definition Audio"
)


def test_extract_specs_grounds_false_with_section_evidence():
    payload = {
        "values": [
            {"key": "optical_spdif", "value": "false", "evidence": "Audio: Realtek ALC897, 7.1 Surround High Definition Audio"},
        ]
    }
    specs = extract_specs(payload, {"optical_spdif", "wifi"}, ASUS_NETWORK_CONTEXT)
    assert [s.key for s in specs] == ["optical_spdif"]
    assert specs[0].value == "false"


def test_extract_specs_rejects_unverified_false():
    # "false" with no grounding evidence in the page must be DISCARDED
    payload = {
        "values": [
            {"key": "wifi", "value": "false", "evidence": "no mention anywhere"},
        ]
    }
    with pytest.raises(ValueError):
        extract_specs(payload, {"wifi"}, ASUS_NETWORK_CONTEXT)


def test_sources_for_asus_product_are_manufacturer():
    product = Product(name="ASUS Prime B650M-A II-CSM", brand="ASUS")
    sources = sources_for_product(product)
    assert sources, "debería resolver la fuente ASUS"
    assert all(source.source_name == "ASUS" for source in sources)
    assert all(source.source_type == "manufacturer" for source in sources)


def test_fan_header_list_allowed_key():
    from app.catalog.spec_sources import MOTHERBOARD_ALLOWED_KEYS
    assert "fan_header_list" in MOTHERBOARD_ALLOWED_KEYS
