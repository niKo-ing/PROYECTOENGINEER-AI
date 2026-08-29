from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models.catalog import (
    Category,
    CategorySpecificationDefinition,
    Product,
    ProductSpecValue,
    ProductSpecValueHistory,
    SpecConflictStatus,
    SpecValueHistoryAction,
    SpecValueKind,
    SpecValueSourceType,
    SpecVerificationStatus,
)
from app.services.product_spec_value_service import ProductSpecValueService, SpecValueInput

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _reset(db):
    for model in (ProductSpecValueHistory, ProductSpecValue, Product, CategorySpecificationDefinition, Category):
        db.query(model).delete()
    db.commit()


def _fixtures(db):
    category = Category(name="Notebooks", slug="notebooks")
    product = Product(name="Notebook prueba", category_entity=category, specs={"sections": []})
    ram_capacity = CategorySpecificationDefinition(
        category=category,
        key="ram_capacity",
        label="Capacidad RAM",
        group="Memoria",
        data_type="integer",
        unit="GB",
        filter_type="range",
    )
    rgb = CategorySpecificationDefinition(
        category=category,
        key="rgb",
        label="RGB",
        group="Iluminación",
        data_type="boolean",
        filter_type="boolean",
    )
    db.add_all([category, product, ram_capacity, rgb])
    db.commit()
    return product, ram_capacity, rgb


def test_creates_structured_numeric_value_with_history():
    with Session() as db:
        _reset(db)
        product, ram_capacity, _rgb = _fixtures(db)

        value = ProductSpecValueService(db).upsert(
            SpecValueInput(
                product_id=product.id,
                definition_id=ram_capacity.id,
                value_kind=SpecValueKind.NUMBER.value,
                raw_value="16 GB DDR5 5600 MHz",
                value_number=16,
                unit="GB",
                source_type=SpecValueSourceType.AI.value,
                source_name="Gemini",
                extraction_method="product_specs_json",
            )
        )

        assert value.value_number == 16
        assert value.unit == "GB"
        assert value.source_type == SpecValueSourceType.AI.value
        assert value.verification_status == SpecVerificationStatus.AUTO.value
        assert value.conflict_status == SpecConflictStatus.NONE.value
        assert db.query(ProductSpecValueHistory).one().action == SpecValueHistoryAction.CREATED.value


def test_verified_value_is_not_overwritten_by_scraper_conflict():
    with Session() as db:
        _reset(db)
        product, ram_capacity, _rgb = _fixtures(db)
        service = ProductSpecValueService(db)
        value = service.upsert(
            SpecValueInput(
                product_id=product.id,
                definition_id=ram_capacity.id,
                value_kind=SpecValueKind.NUMBER.value,
                value_number=16,
                unit="GB",
                source_type=SpecValueSourceType.MANUFACTURER.value,
                verification_status=SpecVerificationStatus.VERIFIED.value,
                changed_by="admin@example.com",
            )
        )

        value = service.upsert(
            SpecValueInput(
                product_id=product.id,
                definition_id=ram_capacity.id,
                value_kind=SpecValueKind.NUMBER.value,
                value_number=8,
                unit="GB",
                source_type=SpecValueSourceType.SCRAPER.value,
                source_url="https://store.example/notebook",
            )
        )

        assert value.value_number == 16
        assert value.verification_status == SpecVerificationStatus.VERIFIED.value
        assert value.conflict_status == SpecConflictStatus.PENDING.value
        conflict = db.query(ProductSpecValueHistory).filter_by(action=SpecValueHistoryAction.CONFLICT_DETECTED.value).one()
        assert conflict.incoming_value["value"]["number"] == 8


def test_higher_priority_source_replaces_auto_value_and_requires_review():
    with Session() as db:
        _reset(db)
        product, ram_capacity, _rgb = _fixtures(db)
        service = ProductSpecValueService(db)
        service.upsert(
            SpecValueInput(
                product_id=product.id,
                definition_id=ram_capacity.id,
                value_kind=SpecValueKind.NUMBER.value,
                value_number=8,
                unit="GB",
                source_type=SpecValueSourceType.AI.value,
            )
        )

        value = service.upsert(
            SpecValueInput(
                product_id=product.id,
                definition_id=ram_capacity.id,
                value_kind=SpecValueKind.NUMBER.value,
                value_number=16,
                unit="GB",
                source_type=SpecValueSourceType.MANUFACTURER.value,
                source_name="Lenovo PSREF",
            )
        )

        assert value.value_number == 16
        assert value.source_type == SpecValueSourceType.MANUFACTURER.value
        assert value.verification_status == SpecVerificationStatus.REVIEW.value
        assert value.conflict_status == SpecConflictStatus.PENDING.value
        assert db.query(ProductSpecValueHistory).filter_by(action=SpecValueHistoryAction.VALUE_CHANGED.value).count() == 1


def test_boolean_value_and_manual_verification():
    with Session() as db:
        _reset(db)
        product, _ram_capacity, rgb = _fixtures(db)
        service = ProductSpecValueService(db)
        value = service.upsert(
            SpecValueInput(
                product_id=product.id,
                definition_id=rgb.id,
                value_kind=SpecValueKind.BOOLEAN.value,
                value_boolean=True,
                source_type=SpecValueSourceType.STORE.value,
            )
        )

        service.verify(value, verified_by="admin@example.com")

        assert value.value_boolean is True
        assert value.verification_status == SpecVerificationStatus.VERIFIED.value
        assert value.conflict_status == SpecConflictStatus.RESOLVED.value
        assert value.verified_by == "admin@example.com"
        assert db.query(ProductSpecValueHistory).filter_by(action=SpecValueHistoryAction.VERIFIED.value).count() == 1
