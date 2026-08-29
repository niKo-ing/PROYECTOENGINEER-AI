"""Tests for taxonomy seed and ingestion category components.

Covers:
- Taxonomy structure and idempotency
- CategoryMapper (deterministic per-store)
- CategoryFilter (priority whitelist/blacklist)
- EligibilityCheck (identity, name, URL, price, bundles)
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.catalog.taxonomy import INITIAL_TAXONOMY, TaxonomyNode
from app.ingestion.category import (
    CategoryFilter,
    CategoryMapper,
    CategoryMapping,
    EligibilityRejectReason,
    RejectReason,
    check_eligibility,
    get_group_slugs,
    get_leaf_slugs,
    get_taxonomy_node,
)
from app.models.catalog import Category, CategorySpecificationDefinition, PriceHistory, Product, Store, StoreOffer
from app.repositories.category_repository import CategoryRepository
from app.services.category_service import CategoryService

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _reset(db):
    for model in (PriceHistory, StoreOffer, Product, Store, CategorySpecificationDefinition, Category):
        db.query(model).delete()
    db.commit()


# ══════════════════════════════════════════════════════════════════
#  TAXONOMY STRUCTURE
# ══════════════════════════════════════════════════════════════════


def test_root_is_tecnologia():
    assert INITIAL_TAXONOMY.name == "Tecnología"
    assert INITIAL_TAXONOMY.slug == "tecnologia"
    assert INITIAL_TAXONOMY.is_group is True


def test_root_has_children():
    assert len(INITIAL_TAXONOMY.children) > 0


def test_all_leaf_nodes_have_priority():
    leaves = get_leaf_slugs()
    for slug in leaves:
        node = get_taxonomy_node(slug)
        assert node is not None
        assert node.priority in ("P0", "P1", "P2")
        assert node.is_group is False


def test_all_groups_are_is_group():
    groups = get_group_slugs()
    for slug in groups:
        node = get_taxonomy_node(slug)
        assert node is not None
        assert node.is_group is True


def test_leaf_count_matches_design():
    leaves = get_leaf_slugs()
    assert len(leaves) == 36


def test_all_slugs_unique():
    leaves = get_leaf_slugs()
    groups = get_group_slugs()
    all_slugs = leaves + groups
    assert len(all_slugs) == len(set(all_slugs))


def test_get_taxonomy_node_existing():
    node = get_taxonomy_node("notebooks")
    assert node is not None
    assert node.name == "Notebooks"


def test_get_taxonomy_node_missing():
    assert get_taxonomy_node("nonexistent-slug") is None


# ══════════════════════════════════════════════════════════════════
#  TAXONOMY SEED IDEMPOTENCY
# ══════════════════════════════════════════════════════════════════


def test_seed_creates_all_categories():
    with Session() as db:
        _reset(db)
        service = CategoryService(db)
        service.seed_initial_taxonomy()
        all_cats = CategoryRepository(db).list_all()
        # 8 groups (Tecnología + 7 branches) + 36 leaves = 44
        assert len(all_cats) == 44


def test_seed_twice_no_duplicates():
    with Session() as db:
        _reset(db)
        service = CategoryService(db)
        service.seed_initial_taxonomy()
        count_first = len(CategoryRepository(db).list_all())

        service.seed_initial_taxonomy()
        count_second = len(CategoryRepository(db).list_all())

        assert count_first == count_second == 44


def test_tecnologia_is_group_in_db():
    with Session() as db:
        _reset(db)
        service = CategoryService(db)
        service.seed_initial_taxonomy()
        tech = CategoryRepository(db).get_by_name_and_parent("Tecnología", None)
        assert tech is not None
        assert tech.is_group is True
        assert tech.priority == "P0"


def test_leaf_categories_have_correct_priority():
    with Session() as db:
        _reset(db)
        service = CategoryService(db)
        service.seed_initial_taxonomy()
        repo = CategoryRepository(db)

        tech = repo.get_by_name_and_parent("Tecnología", None)
        assert tech is not None

        computadores = repo.get_by_name_and_parent("Computadores", tech.id)
        assert computadores is not None

        notebooks = repo.get_by_name_and_parent("Notebooks", computadores.id)
        assert notebooks is not None
        assert notebooks.priority == "P0"
        assert notebooks.is_group is False

        gaming = repo.get_by_name_and_parent("Gaming", tech.id)
        assert gaming is not None

        sillas = repo.get_by_name_and_parent("Sillas gaming", gaming.id)
        assert sillas is not None
        assert sillas.priority == "P2"
        assert sillas.is_group is False


def test_category_spec_definitions_seeded_by_category():
    with Session() as db:
        _reset(db)
        service = CategoryService(db)
        service.seed_initial_taxonomy()

        cpu = CategoryRepository(db).get_by_slug("procesadores")
        gpu = CategoryRepository(db).get_by_slug("tarjetas-graficas")
        notebooks = CategoryRepository(db).get_by_slug("notebooks")

        assert cpu is not None
        assert gpu is not None
        assert notebooks is not None
        assert {spec.key for spec in cpu.spec_definitions} >= {"socket", "cores", "threads", "tdp", "integrated_graphics"}
        assert {spec.key for spec in gpu.spec_definitions} >= {"vram", "memory_type", "memory_bus", "tdp"}
        assert {spec.key for spec in notebooks.spec_definitions} >= {"processor", "ram", "storage", "gpu", "screen"}


def test_category_spec_definitions_are_idempotent():
    with Session() as db:
        _reset(db)
        service = CategoryService(db)
        service.seed_initial_taxonomy()
        first = db.query(CategorySpecificationDefinition).count()

        service.seed_initial_taxonomy()
        second = db.query(CategorySpecificationDefinition).count()

        assert first == second
        assert first > 0


def test_seed_preserves_products():
    with Session() as db:
        _reset(db)
        service = CategoryService(db)
        service.seed_initial_taxonomy()
        assert len(CategoryRepository(db).list_all()) == 44


def test_seed_deletes_obsolete_empty_categories():
    with Session() as db:
        _reset(db)
        obsolete = Category(name="Computación", slug="computacion", priority="P0", is_group=True)
        db.add(obsolete)
        db.commit()

        CategoryService(db).seed_initial_taxonomy()

        assert CategoryRepository(db).get_by_slug("computacion") is None
        assert len(CategoryRepository(db).list_all()) == 44


# ══════════════════════════════════════════════════════════════════
#  CATEGORY MAPPER
# ══════════════════════════════════════════════════════════════════


def test_mapper_correct():
    mapper = CategoryMapper.build("spdigital.cl", {
        "Tarjetas de Video": "tarjetas-graficas",
        "Notebooks": "notebooks",
    })
    assert mapper.map("Tarjetas de Video") == "tarjetas-graficas"
    assert mapper.map("Notebooks") == "notebooks"


def test_mapper_unknown_returns_none():
    mapper = CategoryMapper.build("spdigital.cl", {
        "Tarjetas de Video": "tarjetas-graficas",
    })
    assert mapper.map("Categoría Fantasma") is None


def test_mapper_different_store_independent():
    m1 = CategoryMapper.build("spdigital.cl", {"TV": "smart-tvs"})
    m2 = CategoryMapper.build("paris.cl", {"Computación": "notebooks"})
    assert m1.map("TV") == "smart-tvs"
    assert m1.map("Computación") is None
    assert m2.map("Computación") == "notebooks"
    assert m2.map("TV") is None


def test_mapper_case_insensitive():
    mapper = CategoryMapper.build("spdigital.cl", {
        "tarjetas de video": "tarjetas-graficas",
    })
    assert mapper.map("Tarjetas de Video") == "tarjetas-graficas"
    assert mapper.map("TARJETAS DE VIDEO") == "tarjetas-graficas"


def test_mapper_whitespace_trimmed():
    mapper = CategoryMapper.build("spdigital.cl", {
        "  Notebooks  ": "notebooks",
    })
    assert mapper.map("  Notebooks  ") == "notebooks"


def test_mapper_register_runtime():
    mapper = CategoryMapper("spdigital.cl")
    mapper.register("Monitores", "monitores")
    assert mapper.map("Monitores") == "monitores"


def test_mapper_mapped_slugs_unique():
    mapper = CategoryMapper.build("spdigital.cl", {
        "TV A": "smart-tvs",
        "TV B": "smart-tvs",
        "Notebooks": "notebooks",
    })
    assert sorted(mapper.mapped_slugs()) == ["notebooks", "smart-tvs"]


def test_category_mapping_frozen():
    m = CategoryMapping(source_category="Notebooks", target_slug="notebooks")
    assert m.source_category == "Notebooks"
    assert m.target_slug == "notebooks"


# ══════════════════════════════════════════════════════════════════
#  CATEGORY FILTER
# ══════════════════════════════════════════════════════════════════


def test_filter_p0_allowed():
    f = CategoryFilter()
    assert f.check("notebooks").allowed is True


def test_filter_p1_allowed():
    f = CategoryFilter()
    assert f.check("routers").allowed is True


def test_filter_p2_allowed():
    f = CategoryFilter()
    assert f.check("sillas-gaming").allowed is True


def test_filter_unknown_rejected():
    f = CategoryFilter()
    result = f.check("nonexistent-slug")
    assert result.allowed is False
    assert result.reason == RejectReason.UNKNOWN_CATEGORY


def test_filter_blacklist_rejected():
    f = CategoryFilter(blacklist_slugs=frozenset({"sillas-gaming"}))
    result = f.check("sillas-gaming")
    assert result.allowed is False
    assert result.reason == RejectReason.BLACKLISTED


def test_filter_whitelist_only_allowed():
    f = CategoryFilter(whitelist_slugs=frozenset({"notebooks", "consolas"}))
    assert f.check("notebooks").allowed is True
    assert f.check("routers").allowed is False
    assert f.check("routers").reason == RejectReason.NOT_IN_WHITELIST


def test_filter_group_node_rejected():
    f = CategoryFilter()
    result = f.check("computadores")
    assert result.allowed is False
    assert result.reason == RejectReason.IS_GROUP_NODE


def test_filter_priority_rejects_p2():
    f = CategoryFilter(allowed_priorities=frozenset({"P0", "P1"}))
    result = f.check("sillas-gaming")
    assert result.allowed is False
    assert result.reason == RejectReason.NOT_IN_WHITELIST


def test_filter_empty_whitelist_rejects_all():
    f = CategoryFilter(whitelist_slugs=frozenset())
    assert f.check("notebooks").allowed is False


def test_filter_blacklist_takes_precedence():
    f = CategoryFilter(
        whitelist_slugs=frozenset({"notebooks"}),
        blacklist_slugs=frozenset({"notebooks"}),
    )
    result = f.check("notebooks")
    assert result.allowed is False
    assert result.reason == RejectReason.BLACKLISTED


# ══════════════════════════════════════════════════════════════════
#  ELIGIBILITY CHECK
# ══════════════════════════════════════════════════════════════════


def test_eligible_with_gtin():
    result = check_eligibility(
        category_slug="notebooks", name="HP Pavilion 15",
        url="https://example.com/hp-15", price=499990, gtin="1234567890123",
    )
    assert result.eligible is True
    assert result.reason is None


def test_eligible_with_mpn_and_brand():
    result = check_eligibility(
        category_slug="notebooks", name="Lenovo IdeaPad 3",
        url="https://example.com/lenovo", price=399990,
        mpn="82SF00D4CL", brand="Lenovo",
    )
    assert result.eligible is True


def test_eligible_with_sku():
    result = check_eligibility(
        category_slug="notebooks", name="Dell Inspiron",
        url="https://example.com/dell", price=549990, sku="DELL-INS-15",
    )
    assert result.eligible is True


def test_eligible_with_product_id():
    result = check_eligibility(
        category_slug="notebooks", name="Asus VivoBook",
        url="https://example.com/asus", price=449990, product_id="ASUS-VB-14",
    )
    assert result.eligible is True


def test_rejected_no_identity():
    result = check_eligibility(
        category_slug="notebooks", name="Laptop Misteriosa",
        url="https://example.com/mystery", price=299990,
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.MISSING_PRODUCT_IDENTITY


def test_rejected_no_category():
    result = check_eligibility(
        category_slug=None, name="Laptop", url="https://example.com/laptop",
        price=299990, gtin="123",
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.MISSING_CATEGORY


def test_rejected_no_name():
    result = check_eligibility(
        category_slug="notebooks", name=None, url="https://example.com/laptop",
        price=299990, gtin="123",
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.MISSING_NAME


def test_rejected_empty_name():
    result = check_eligibility(
        category_slug="notebooks", name="   ", url="https://example.com/laptop",
        price=299990, gtin="123",
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.MISSING_NAME


def test_rejected_no_url():
    result = check_eligibility(
        category_slug="notebooks", name="Laptop", url=None,
        price=299990, gtin="123",
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.MISSING_URL


def test_rejected_zero_price():
    result = check_eligibility(
        category_slug="notebooks", name="Laptop", url="https://example.com/laptop",
        price=0, gtin="123",
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.INVALID_PRICE


def test_rejected_negative_price():
    result = check_eligibility(
        category_slug="notebooks", name="Laptop", url="https://example.com/laptop",
        price=-100, gtin="123",
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.INVALID_PRICE


def test_rejected_none_price():
    result = check_eligibility(
        category_slug="notebooks", name="Laptop", url="https://example.com/laptop",
        price=None, gtin="123",
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.INVALID_PRICE


def test_rejected_bundle():
    result = check_eligibility(
        category_slug="notebooks", name="Pack Notebooks + Mouse + Alfombrilla",
        url="https://example.com/pack", price=599990, gtin="123",
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.IS_BUNDLE


def test_rejected_combo():
    result = check_eligibility(
        category_slug="notebooks", name="Combo Teclado + Mouse Gamer",
        url="https://example.com/combo", price=79990, sku="COMBO-01",
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.IS_BUNDLE


def test_rejected_service():
    result = check_eligibility(
        category_slug="notebooks", name="Servicio de instalación",
        url="https://example.com/svc", price=19990, sku="SVC-01",
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.IS_SERVICE


def test_rejected_garantia():
    result = check_eligibility(
        category_slug="notebooks", name="Garantía extendida 2 años",
        url="https://example.com/gar", price=29990, sku="GAR-01",
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.IS_SERVICE


def test_rejected_gift_card():
    result = check_eligibility(
        category_slug="notebooks", name="Gift Card $50.000",
        url="https://example.com/gc", price=50000, sku="GC-50",
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.IS_SERVICE


def test_eligible_with_filter_passes():
    f = CategoryFilter(whitelist_slugs=frozenset({"notebooks"}))
    result = check_eligibility(
        category_slug="notebooks", name="Laptop HP",
        url="https://example.com/hp", price=499990, gtin="123",
        category_filter=f,
    )
    assert result.eligible is True


def test_eligible_with_filter_rejects():
    f = CategoryFilter(whitelist_slugs=frozenset({"consolas"}))
    result = check_eligibility(
        category_slug="notebooks", name="Laptop HP",
        url="https://example.com/hp", price=499990, gtin="123",
        category_filter=f,
    )
    assert result.eligible is False
    assert result.reason == EligibilityRejectReason.CATEGORY_NOT_ALLOWED
