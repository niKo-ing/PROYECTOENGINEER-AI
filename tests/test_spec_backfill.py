from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.catalog.spec_backfill import backfill_product_specs
from app.db import Base
from app.models.catalog import Category, CategorySpecificationDefinition, Product, ProductSpecValue, ProductSpecValueHistory, SpecConflictStatus, SpecValueSourceType, SpecVerificationStatus
from app.services.product_spec_value_service import ProductSpecValueService

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _reset(db):
    for model in (ProductSpecValueHistory, ProductSpecValue, Product, CategorySpecificationDefinition, Category):
        db.query(model).delete()
    db.commit()


def _add_notebook(db):
    category = Category(name="Notebooks", slug="notebooks")
    defs = [
        CategorySpecificationDefinition(category=category, key="processor", label="Procesador", group="Procesador", data_type="text"),
        CategorySpecificationDefinition(category=category, key="processor_cores", label="Núcleos CPU", group="Procesador", data_type="integer"),
        CategorySpecificationDefinition(category=category, key="ram_capacity", label="Capacidad RAM", group="Memoria", data_type="integer", unit="GB"),
        CategorySpecificationDefinition(category=category, key="ram_type", label="Tipo de RAM", group="Memoria", data_type="text"),
        CategorySpecificationDefinition(category=category, key="ram_speed", label="Velocidad RAM", group="Memoria", data_type="integer", unit="MHz"),
        CategorySpecificationDefinition(category=category, key="storage_capacity", label="Capacidad almacenamiento", group="Almacenamiento", data_type="integer", unit="GB"),
        CategorySpecificationDefinition(category=category, key="screen_size", label="Tamaño pantalla", group="Pantalla", data_type="decimal", unit='"'),
        CategorySpecificationDefinition(category=category, key="screen_resolution", label="Resolución pantalla", group="Pantalla", data_type="text"),
    ]
    product = Product(
        name="Notebook Acer 8GB RAM 128GB SSD 14 WUXGA",
        brand="Acer",
        model="AL14",
        category_entity=category,
        specs={
            "highlights": ["8 GB RAM"],
            "sections": [
                {"title": "Procesador", "items": [{"label": "Procesador", "value": "Intel Core i3"}, {"label": "Núcleos", "value": "8 Núcleos"}]},
                {"title": "RAM", "items": [{"label": "Capacidad", "value": "8 GB"}, {"label": "Tipo", "value": "DDR5"}, {"label": "Velocidad", "value": "5500 MB/s"}]},
                {"title": "Almacenamiento", "items": [{"label": "Capacidad", "value": "128 GB SSD"}]},
                {"title": "Pantalla", "items": [{"label": "Tamaño", "value": "14\""}, {"label": "Resolución", "value": "WUXGA"}]},
                {"title": "Otros", "items": [{"label": "Garantía", "value": "1 año"}]},
            ],
        },
    )
    db.add_all([category, product, *defs])
    db.commit()
    return product


def test_backfills_product_specs_to_canonical_values_conservatively():
    with Session() as db:
        _reset(db)
        product = _add_notebook(db)
        original_specs = product.specs.copy()

        result = backfill_product_specs(product, ProductSpecValueService(db, auto_commit=False))
        db.commit()

        values = {value.definition.key: value for value in db.query(ProductSpecValue).all()}
        assert result.created_or_updated == 8
        assert result.skipped == 1
        assert values["ram_capacity"].value_number == 8
        assert values["ram_capacity"].unit == "GB"
        assert values["ram_capacity"].source_type == SpecValueSourceType.STORE.value
        assert values["ram_type"].value_text == "DDR5"
        assert values["ram_speed"].value_number is None
        assert values["ram_speed"].value_text == "5500 MB/s"
        assert values["ram_speed"].source_type == SpecValueSourceType.UNKNOWN.value
        assert values["screen_resolution"].value_text == "1920 × 1200"
        assert values["processor_cores"].raw_value == "8 Núcleos"
        assert values["processor_cores"].verification_status == SpecVerificationStatus.REVIEW.value
        assert values["processor_cores"].conflict_status == SpecConflictStatus.NONE.value
        assert product.specs == original_specs


def test_backfill_is_idempotent():
    with Session() as db:
        _reset(db)
        product = _add_notebook(db)
        service = ProductSpecValueService(db, auto_commit=False)

        backfill_product_specs(product, service)
        db.commit()
        first_count = db.query(ProductSpecValue).count()
        first_history_count = db.query(ProductSpecValueHistory).count()
        backfill_product_specs(product, service)
        db.commit()

        assert db.query(ProductSpecValue).count() == first_count
        assert db.query(ProductSpecValueHistory).count() == first_history_count
