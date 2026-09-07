"""Coverage guarantees for the canonical per-category spec definitions.

The goal: each tracked leaf category must define its own complete set of
relevant specification groups so the SpecSheet and /compare produce rich,
comparable fichas (no generic fallback). This test locks the minimum breadth
of the five core categories plus the structural invariants that keep the
taxonomy safe to extend (unique keys, no empty labels/groups/units).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.catalog.taxonomy import CPU_SPECS, GPU_SPECS, INITIAL_TAXONOMY, MONITOR_SPECS, MOBILE_SPECS, MOTHERBOARD_SPECS, NOTEBOOK_SPECS
from app.db import Base
from app.models.catalog import Category, CategorySpecificationDefinition
from app.repositories.category_repository import CategoryRepository
from app.services.category_service import CategoryService

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _reset(db):
    for model in (CategorySpecificationDefinition, Category):
        db.query(model).delete()
    db.commit()


def _seeded(db):
    _reset(db)
    service = CategoryService(db)
    service.seed_initial_taxonomy()
    return db


def _defs(db, slug: str) -> list:
    category = CategoryRepository(db).get_by_slug(slug)
    assert category is not None
    return sorted(category.spec_definitions, key=lambda definition: (definition.group, definition.sort_order))


def test_cpu_specs_are_complete():
    keys = {spec.key for spec in CPU_SPECS}
    assert len(CPU_SPECS) >= 12
    assert {
        "socket",
        "cores",
        "threads",
        "base_frequency",
        "boost_frequency",
        "cache",
        "tdp",
        "integrated_graphics",
        "memory_type",
        "max_memory",
        "pcie_version",
    } <= keys


def test_gpu_specs_are_complete():
    keys = {spec.key for spec in GPU_SPECS}
    assert len(GPU_SPECS) >= 12
    assert {
        "chipset",
        "vram",
        "memory_type",
        "memory_bus",
        "base_clock",
        "boost_clock",
        "cuda_cores",
        "tdp",
        "recommended_psu",
        "power_connector",
        "length",
        "display_ports",
    } <= keys


def test_monitor_specs_are_complete():
    keys = {spec.key for spec in MONITOR_SPECS}
    assert len(MONITOR_SPECS) >= 15
    assert {
        "size",
        "resolution",
        "refresh_rate",
        "panel_type",
        "aspect_ratio",
        "response_time",
        "brightness",
        "hdr",
        "adaptive_sync",
        "ports",
        "vesa_mount",
    } <= keys


def test_notebook_specs_are_complete():
    keys = {spec.key for spec in NOTEBOOK_SPECS}
    assert len(NOTEBOOK_SPECS) >= 28
    assert {
        "processor",
        "processor_base_frequency",
        "processor_boost_frequency",
        "processor_cache",
        "processor_tdp",
        "ram_capacity",
        "ram_type",
        "storage_capacity",
        "storage_type",
        "gpu",
        "gpu_vram",
        "screen_size",
        "screen_resolution",
        "screen_refresh_rate",
        "touchscreen",
        "battery_capacity",
        "weight",
        "webcam",
        "os",
    } <= keys


def test_mobile_specs_are_complete():
    keys = {spec.key for spec in MOBILE_SPECS}
    assert len(MOBILE_SPECS) >= 18
    assert {
        "screen_size",
        "screen_resolution",
        "screen_refresh_rate",
        "panel_type",
        "processor",
        "ram_capacity",
        "ram_type",
        "storage_capacity",
        "storage_type",
        "rear_camera",
        "rear_camera_megapixels",
        "front_camera",
        "battery_capacity",
        "charging_wattage",
        "ip_rating",
        "os",
    } <= keys


def test_seeded_categories_contain_expanded_definitions():
    db = _seeded(Session())
    try:
        assert len(_defs(db, "procesadores")) >= 12
        assert len(_defs(db, "tarjetas-graficas")) >= 12
        assert len(_defs(db, "monitores")) >= 15
        assert len(_defs(db, "notebooks")) >= 28
        assert len(_defs(db, "celulares")) >= 18
    finally:
        db.close()


def test_seed_remains_idempotent_after_expansion():
    db = Session()
    try:
        _reset(db)
        CategoryService(db).seed_initial_taxonomy()
        first = db.query(CategorySpecificationDefinition).count()
        CategoryService(db).seed_initial_taxonomy()
        second = db.query(CategorySpecificationDefinition).count()
        assert first == second
        assert first > 153
    finally:
        db.close()


def test_keys_unique_within_each_category():
    for specs in (CPU_SPECS, GPU_SPECS, MONITOR_SPECS, NOTEBOOK_SPECS, MOBILE_SPECS, MOTHERBOARD_SPECS):
        keys = [spec.key for spec in specs]
        assert len(keys) == len(set(keys)), f"keys duplicadas en {keys}"


def test_motherboard_specs_are_structured_and_complete():
    specs = {spec.key: spec for spec in MOTHERBOARD_SPECS}
    assert len(MOTHERBOARD_SPECS) >= 50
    assert {
        "socket",
        "chipset",
        "form_factor",
        "memory_type",
        "ram_slots",
        "pcie_slots",
        "m2_slots",
        "sata_ports",
        "wifi",
        "bluetooth",
        "ethernet",
    } <= specs.keys()
    required = {spec.key for spec in MOTHERBOARD_SPECS if spec.required}
    assert {"socket", "chipset"} <= required
    for key in ("pcie_slot_list", "m2_slot_list", "rear_ports", "motherboard_power_connector"):
        assert specs[key].data_type == "json", key
        assert specs[key].item_schema, f"{key} sin item_schema"

def test_all_spec_definitions_have_label_group_and_sort_order():
    for specs in (CPU_SPECS, GPU_SPECS, MONITOR_SPECS, NOTEBOOK_SPECS, MOBILE_SPECS, MOTHERBOARD_SPECS):
        for spec in specs:
            assert spec.key, "key vacío"
            assert spec.label, f"label vacío para {spec.key}"
            assert spec.group, f"grupo vacío para {spec.key}"
            assert spec.data_type in {"text", "integer", "decimal", "boolean", "json"}, spec.key
            assert spec.filter_type, f"filter_type vacío para {spec.key}"


def test_sort_orders_are_unique_per_category():
    for specs in (CPU_SPECS, GPU_SPECS, MONITOR_SPECS, NOTEBOOK_SPECS, MOBILE_SPECS):
        orders = [spec.sort_order for spec in specs]
        assert len(orders) == len(set(orders)), f"sort_order duplicados en {orders}"


def _collect_leaves(node):
    leaves = []
    for child in node.children:
        if child.is_group:
            leaves.extend(_collect_leaves(child))
        else:
            leaves.append(child)
    return leaves


def test_p0_leaf_categories_have_spec_definitions():
    db = Session()
    try:
        _reset(db)
        CategoryService(db).seed_initial_taxonomy()
        repo = CategoryRepository(db)
        for leaf in _collect_leaves(INITIAL_TAXONOMY):
            category = repo.get_by_slug(leaf.slug)
            assert category is not None
            if leaf.priority == "P0":
                assert leaf.specs, f"P0 {leaf.slug} no define specs"
                assert len(category.spec_definitions) == len(leaf.specs)
    finally:
        db.close()