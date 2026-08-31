from app.catalog.spec_fetch import normalize_context, fetch_page
from app.catalog.spec_sources import SOURCES, SpecSource, sources_for_product, all_urls
from app.catalog.spec_research import (
    ExtractedSpec,
    ResearchOutcome,
    build_prompt,
    cross_validate_outcome,
    evidence_in_context,
    extract_specs,
    extracted_input,
    extracted_input_multi,
    interpret_variant_hints,
    research_input,
    resolve_values,
)
from app.catalog.ai_config import AIResearchConfig
from app.db import Base
from app.models.catalog import (
    Category,
    CategorySpecificationDefinition,
    Product,
    ProductSpecValue,
    SpecValueSourceType,
    SpecVerificationStatus,
)
from app.services.product_spec_value_service import ProductSpecValueService, SpecValueInput
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

CONTEXT = (
    "GeForce RTX 4060 Laptop GPU 3072 @ 1.55 - 2.37 GHz 128 Bit @ 16000 MHz "
    "8 GB GDDR6 Memory 35 - 115 W TGP"
)

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _research_reset(db):
    for model in (ProductSpecValue, Product, CategorySpecificationDefinition, Category):
        db.query(model).delete()
    db.commit()


def _research_fixtures(db):
    _research_reset(db)
    category = Category(name="Notebooks", slug="notebooks")
    product = Product(name="Notebook HP 15-fc HP i5-12450H 8GB", brand="HP")
    gpu = CategorySpecificationDefinition(category=category, key="gpu", label="Tarjeta de video", group="Gráficos", data_type="text")
    vram = CategorySpecificationDefinition(category=category, key="gpu_vram", label="VRAM GPU", group="Gráficos", data_type="integer", unit="GB")
    db.add_all([category, product, gpu, vram])
    db.commit()
    return product, {"gpu": gpu, "gpu_vram": vram}


def _cpu_source():
    return next(s for s in SOURCES if s.kind == "cpu")


def test_extract_specs_keeps_grounded_values_only():
    payload = {
        "values": [
            {"key": "gpu", "value": "GeForce RTX 4060", "evidence": "GeForce RTX 4060 Laptop GPU"},
            {"key": "gpu_vram", "value": "8 GB", "evidence": "8 GB GDDR6"},
        ]
    }
    specs = extract_specs(payload, {"gpu", "gpu_vram", "gpu_type"}, CONTEXT)
    assert {s.key for s in specs} == {"gpu", "gpu_vram"}


def test_extract_specs_rejects_unallowed_and_invented_values():
    # gpu_vram (evidence grounded) and gpu (grounded) kept; unallowed screen_size dropped
    payload = {
        "values": [
            {"key": "gpu_vram", "value": "8 GB", "evidence": "8 GB GDDR6"},  # grounded
            {"key": "screen_size", "value": "15.6", "evidence": "128 Bit"},  # key not allowed for gpu entry
            {"key": "gpu", "value": "GeForce RTX 4060", "evidence": "GeForce RTX 4060 Laptop GPU"},  # grounded & allowed
        ]
    }
    specs = extract_specs(payload, {"gpu", "gpu_vram"}, CONTEXT)
    assert [s.key for s in specs] == ["gpu_vram", "gpu"]
    assert specs[1].value == "GeForce RTX 4060"


def test_extract_specs_raises_when_no_grounded_value():
    payload = {"values": [{"key": "gpu", "value": "GeForce RTX 9999", "evidence": "nothing here"}]}
    try:
        extract_specs(payload, {"gpu"}, CONTEXT)
        raise AssertionError("debería lanzar ValueError")
    except ValueError:
        pass


def test_evidence_in_context_matches_literal():
    assert evidence_in_context("8 GB GDDR6", CONTEXT)
    assert not evidence_in_context("64 GB GDDR6", CONTEXT)


def test_sources_resolve_per_product():
    product = Product(name="Notebook HP Victus i5-12450H RTX 2050 8GB", brand="HP")
    sources = sources_for_product(product)
    kinds = {s.kind for s in sources}
    assert kinds == {"cpu", "gpu"}


def test_generic_i3_not_matched():
    product = Product(name="Notebook Aspire Lite Intel Core i3 8GB", brand="Acer")
    assert sources_for_product(product) == []


def test_all_sources_have_allowed_keys_for_phones():
    for source in SOURCES:
        assert source.url.startswith(("http://", "https://"))
    mobile = [s for s in SOURCES if s.kind == "phone"]
    assert mobile
    for s in mobile:
        assert s.allow_keys is None  # phones use the full category taxonomy


def test_duplicate_urls_share_needles_present_in_page():
    # CPU entries that share the Wikipedia pages must still have specific needles
    meteor = [s for s in SOURCES if s.url == "https://en.wikipedia.org/wiki/Meteor_Lake"]
    assert {s.target for s in meteor} == {"Intel Core Ultra 7 155H", "Intel Core Ultra 9 185H"}
    for s in meteor:
        assert any(needle.casefold() in s.target.casefold() for needle in s.needles)


def test_normalize_context_returns_grounded_plain_text():
    # basic sanity: the reducer never runs on empty needles/liveness
    ctx = normalize_context("<html><body><p>Hello <b>GPU</b></p></body></html>", ("gpu",))
    assert "GPU" in ctx


def test_extracted_input_persists_provenance_and_review_status():
    with Session() as db:
        product, defs = _research_fixtures(db)
        entry = _cpu_source()
        spec = ExtractedSpec(key="gpu_vram", value="8 GB", evidence="8 GB GDDR6")
        service = ProductSpecValueService(db, auto_commit=False)
        incoming = extracted_input(product, defs["gpu_vram"], spec, entry)
        value = service.upsert(incoming)
        db.commit()

        db.refresh(value)
        assert value.value_number == 8
        assert value.unit == "GB"
        assert value.source_type == entry.source_type
        assert value.source_url == entry.url
        assert value.verification_status == SpecVerificationStatus.REVIEW.value
        assert value.extraction_method == "spec_source_fetch:llm_extraction"


def test_research_does_not_overwrite_admin_verified_value():
    with Session() as db:
        product, defs = _research_fixtures(db)
        entry = _cpu_source()

        # seed a verified admin value
        ProductSpecValueService(db, auto_commit=False).upsert(
            SpecValueInput(
                product_id=product.id,
                definition_id=defs["gpu_vram"].id,
                value_kind="number",
                raw_value="8 GB",
                value_number=8,
                unit="GB",
                source_type=SpecValueSourceType.ADMIN.value,
                verification_status=SpecVerificationStatus.VERIFIED.value,
            )
        )
        db.commit()

        spec = ExtractedSpec(key="gpu_vram", value="8 GB", evidence="8 GB GDDR6")
        incoming = extracted_input(product, defs["gpu_vram"], spec, entry)
        value = ProductSpecValueService(db, auto_commit=False).upsert(incoming)
        db.commit()

        db.refresh(value)
        assert value.source_type == SpecValueSourceType.ADMIN.value
        assert value.verification_status == SpecVerificationStatus.VERIFIED.value
        assert value.source_url is None


def _storage_def():
    return CategorySpecificationDefinition(
        category=Category(name="Celulares", slug="celulares"),
        key="storage_capacity",
        label="Capacidad almacenamiento",
        group="Almacenamiento",
        data_type="integer",
        unit="GB",
        filter_type="range",
    )


def _connectivity_def():
    return CategorySpecificationDefinition(
        category=Category(name="Celulares", slug="celulares"),
        key="connectivity",
        label="Conectividad",
        group="Conectividad",
        data_type="text",
        filter_type="multi",
    )


def _specs_128_256_512():
    return [
        ExtractedSpec(key="storage_capacity", value="128 GB", evidence="256GB, 128GB, 512GB internal"),
        ExtractedSpec(key="storage_capacity", value="256 GB", evidence="256GB, 128GB, 512GB internal"),
        ExtractedSpec(key="storage_capacity", value="512 GB", evidence="256GB, 128GB, 512GB internal"),
    ]


def test_build_prompt_includes_product_variant():
    source = next(s for s in SOURCES if s.kind == "cpu")
    prompt = build_prompt("contexto", source, [], product_name="iPhone 15 128GB Negro")
    assert "iPhone 15 128GB Negro" in prompt
    prompt_no_variant = build_prompt("contexto", source, [], product_name=None)
    assert "iPhone 15" not in prompt_no_variant


def test_interpret_variant_hints_extracts_numbers_and_units():
    hints = interpret_variant_hints("iPhone 15 128GB Negro")
    assert (128, "gb") in hints
    hints2 = interpret_variant_hints("HP Victus i5 8GB RAM 512GB SSD 15.6")
    assert (8, "gb") in hints2
    assert (512, "gb") in hints2


def test_resolve_values_picks_variant_capacity():
    storage = _storage_def()
    resolved = resolve_values(_specs_128_256_512(), {"storage_capacity": storage}, product_name="iPhone 15 128GB Negro")
    assert len(resolved) == 1
    assert resolved[0].ambiguous is False
    assert resolved[0].spec is not None
    assert resolved[0].spec.value == "128 GB"


def test_resolve_values_marks_ambiguity_without_picking_arbitrary():
    storage = _storage_def()
    resolved = resolve_values(_specs_128_256_512(), {"storage_capacity": storage}, product_name="iPhone 15 Negro")
    assert resolved[0].ambiguous is True
    assert resolved[0].spec is None  # never picks 128/256/512 arbitrarily
    assert len(resolved[0].candidates) == 3


def test_resolve_values_unique_scalar_is_resolved():
    storage = _storage_def()
    resolved = resolve_values([ExtractedSpec(key="storage_capacity", value="512 GB", evidence="512GB internal")], {"storage_capacity": storage}, product_name="iPhone 15")
    assert resolved[0].spec.value == "512 GB"
    assert resolved[0].ambiguous is False


def test_resolve_values_keeps_multivalue_candidates():
    connectivity = _connectivity_def()
    specs = [
        ExtractedSpec(key="connectivity", value="5G", evidence="5G"),
        ExtractedSpec(key="connectivity", value="Wi-Fi 6", evidence="Wi-Fi 6"),
    ]
    resolved = resolve_values(specs, {"connectivity": connectivity}, product_name="iPhone 15")
    assert resolved[0].ambiguous is False
    assert len(resolved[0].candidates) == 2


def test_extracted_input_multi_persists_value_json():
    with Session() as db:
        _research_reset(db)
        category = Category(name="Celulares", slug="celulares")
        product = Product(name="iPhone 15 128GB", category_entity=category)
        connectivity = CategorySpecificationDefinition(category=category, key="connectivity", label="Conectividad", group="Conectividad", data_type="text", filter_type="multi")
        db.add_all([category, product, connectivity])
        db.commit()
        entry = next(s for s in SOURCES if s.kind == "phone")
        specs = [
            ExtractedSpec(key="connectivity", value="5G", evidence="5G"),
            ExtractedSpec(key="connectivity", value="Wi-Fi 6", evidence="Wi-Fi 6"),
        ]
        incoming = extracted_input_multi(product, connectivity, specs, entry)
        value = ProductSpecValueService(db, auto_commit=False).upsert(incoming)
        db.commit()
        db.refresh(value)
        assert value.value_json == ["5G", "Wi-Fi 6"]
        assert value.source_url == entry.url
        assert value.verification_status == SpecVerificationStatus.REVIEW.value


def test_runner_protects_existing_variant_value():
    from scripts.research_spec_values import _protect_variant_value

    with Session() as db:
        _research_reset(db)
        category = Category(name="Celulares", slug="celulares")
        product = Product(name="iPhone 15 128GB", category_entity=category)
        db.add_all([category, product])
        db.commit()
        storage = CategorySpecificationDefinition(category=category, key="storage_capacity", label="Capacidad almacenamiento", group="Almacenamiento", data_type="integer", unit="GB", filter_type="range")
        db.add(storage)
        db.commit()

        ProductSpecValueService(db, auto_commit=False).upsert(
            SpecValueInput(
                product_id=product.id,
                definition_id=storage.id,
                value_kind="number",
                raw_value="128 GB",
                value_number=128,
                unit="GB",
                source_type=SpecValueSourceType.STORE.value,
                verification_status=SpecVerificationStatus.REVIEW.value,
            )
        )
        db.commit()

        other_variant_spec = ExtractedSpec(key="storage_capacity", value="512 GB", evidence="512GB internal")
        assert _protect_variant_value(db, product, storage, other_variant_spec, product_name=product.name)
        matching_variant_spec = ExtractedSpec(key="storage_capacity", value="128 GB", evidence="128GB internal")
        assert not _protect_variant_value(db, product, storage, matching_variant_spec, product_name=product.name)


def _two_gpu_sources():
    a = next(s for s in SOURCES if s.kind == "gpu")
    b = SpecSource(
        target=a.target,
        kind="gpu",
        aliases=a.aliases,
        url="https://example.com/secondary-specs",
        source_name="SecondarySource",
        allow_keys=a.allow_keys,
        priority=40,
    )
    return a, b


def test_ai_research_source_type_persists():
    with Session() as db:
        _research_reset(db)
        category = Category(name="Notebooks", slug="n2")
        product = Product(name="RTX 4060 Laptop", category_entity=category)
        vram = CategorySpecificationDefinition(category=category, key="gpu_vram", label="VRAM", group="Gráficos", data_type="integer", unit="GB")
        db.add_all([category, product, vram])
        db.commit()
        entry = next(s for s in SOURCES if s.kind == "gpu")
        spec = ExtractedSpec(key="gpu_vram", value="8 GB", evidence="8 GB GDDR6")
        outcome = ResearchOutcome(definition=vram, spec=spec, source=entry)
        incoming = research_input(product, outcome, entry)
        value = ProductSpecValueService(db, auto_commit=False).upsert(incoming)
        db.commit()
        db.refresh(value)
        assert value.source_type == SpecValueSourceType.AI_RESEARCH.value
        assert value.source_url == entry.url
        assert value.verification_status == SpecVerificationStatus.REVIEW.value


def test_cross_validate_variant_resolves_to_single_capacity():
    storage = _storage_def()
    source = next(s for s in SOURCES if s.kind == "phone")
    pairs = [(source, sp) for sp in _specs_128_256_512()]
    outcome = cross_validate_outcome(pairs, storage, AIResearchConfig(), product_name="iPhone 15 128GB Negro")
    assert outcome.spec is not None
    assert outcome.spec.value == "128 GB"
    assert outcome.ambiguous is False


def test_cross_validate_source_agreement_boosts_confidence():
    vram = CategorySpecificationDefinition(category=Category(name="g", slug="g"), key="gpu_vram", label="VRAM", group="Gráficos", data_type="integer", unit="GB")
    a, b = _two_gpu_sources()
    sp1 = ExtractedSpec(key="gpu_vram", value="8 GB", evidence="8 GB GDDR6")
    sp2 = ExtractedSpec(key="gpu_vram", value="8 GB", evidence="8GB GDDR6")
    outcome = cross_validate_outcome([(a, sp1), (b, sp2)], vram, AIResearchConfig())
    assert outcome.source_count == 2
    assert outcome.conflict is False
    assert outcome.spec.value == "8 GB"


def test_cross_validate_source_conflict_marks_review():
    cores = CategorySpecificationDefinition(category=Category(name="g", slug="g"), key="processor_cores", label="Núcleos", group="Procesador", data_type="integer", unit=None)
    a = SpecSource(target="CPU X", kind="cpu", aliases=("cpu x",), url="https://a.example/cpu", source_name="SourceA", priority=10)
    b = SpecSource(target="CPU X", kind="cpu", aliases=("cpu x",), url="https://b.example/cpu", source_name="SourceB", priority=20)
    spA = ExtractedSpec(key="processor_cores", value="16", evidence="16 cores")
    spB = ExtractedSpec(key="processor_cores", value="4", evidence="4 cores")
    outcome = cross_validate_outcome([(a, spA), (b, spB)], cores, AIResearchConfig())
    assert outcome.conflict is True
    assert outcome.note and "Conflicto" in outcome.note
    assert outcome.source is a  # primary (higher trust) kept, but flagged


def test_research_input_never_overwrites_verified_admin():
    with Session() as db:
        _research_reset(db)
        category = Category(name="Notebooks", slug="n3")
        product = Product(name="RTX 4060", category_entity=category)
        vram = CategorySpecificationDefinition(category=category, key="gpu_vram", label="VRAM", group="Gráficos", data_type="integer", unit="GB")
        db.add_all([category, product, vram])
        db.commit()
        ProductSpecValueService(db, auto_commit=False).upsert(
            SpecValueInput(
                product_id=product.id,
                definition_id=vram.id,
                value_kind="number",
                value_number=8,
                unit="GB",
                source_type=SpecValueSourceType.ADMIN.value,
                verification_status=SpecVerificationStatus.VERIFIED.value,
            )
        )
        db.commit()
        entry = next(s for s in SOURCES if s.kind == "gpu")
        spec = ExtractedSpec(key="gpu_vram", value="12 GB", evidence="12 GB GDDR6")
        outcome = ResearchOutcome(definition=vram, spec=spec, source=entry)
        incoming = research_input(product, outcome, entry)
        value = ProductSpecValueService(db, auto_commit=False).upsert(incoming)
        db.commit()
        db.refresh(value)
        assert value.value_number == 8
        assert value.source_type == SpecValueSourceType.ADMIN.value
