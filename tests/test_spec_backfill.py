from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from decimal import Decimal

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


def _add_rich_notebook(db):
    category = Category(name="Notebooks", slug="notebooks")
    defs = [
        CategorySpecificationDefinition(category=category, key="processor", label="Procesador", group="Procesador", data_type="text"),
        CategorySpecificationDefinition(category=category, key="processor_base_frequency", label="Frecuencia base CPU", group="Procesador", data_type="decimal", unit="GHz"),
        CategorySpecificationDefinition(category=category, key="processor_boost_frequency", label="Frecuencia turbo CPU", group="Procesador", data_type="decimal", unit="GHz"),
        CategorySpecificationDefinition(category=category, key="processor_cache", label="Cache CPU", group="Procesador", data_type="integer", unit="MB"),
        CategorySpecificationDefinition(category=category, key="processor_tdp", label="TDP CPU", group="Procesador", data_type="integer", unit="W"),
        CategorySpecificationDefinition(category=category, key="storage_capacity", label="Capacidad almacenamiento", group="Almacenamiento", data_type="integer", unit="GB"),
        CategorySpecificationDefinition(category=category, key="screen_refresh_rate", label="Frecuencia pantalla", group="Pantalla", data_type="integer", unit="Hz"),
        CategorySpecificationDefinition(category=category, key="touchscreen", label="Pantalla táctil", group="Pantalla", data_type="boolean"),
        CategorySpecificationDefinition(category=category, key="gpu_type", label="Tipo de GPU", group="Gráficos", data_type="text"),
        CategorySpecificationDefinition(category=category, key="os", label="Sistema operativo", group="Software", data_type="text"),
        CategorySpecificationDefinition(category=category, key="webcam", label="Cámara web", group="Cámara", data_type="text"),
    ]
    product = Product(
        name="Notebook Gamer 16 144Hz RTX 4060",
        brand="Asus",
        category_entity=category,
        specs={
            "highlights": [],
            "sections": [
                {"title": "Procesador", "items": [
                    {"label": "Velocidad máxima", "value": "hasta 4,3 GHz"},
                    {"label": "Frecuencia base", "value": "2.80 GHz"},
                    {"label": "Caché", "value": "4 MB de caché L3"},
                    {"label": "TDP", "value": "15 W"},
                ]},
                {"title": "Almacenamiento", "items": [{"label": "Capacidad", "value": "2 TB SSD"}]},
                {"title": "Pantalla", "items": [
                    {"label": "Tasa de refresco", "value": "144 Hz"},
                    {"label": "Touch", "value": "Sí"},
                ]},
                {"title": "Tarjeta de video", "items": [{"label": "Tipo", "value": "Dedicada"}]},
                {"title": "Sistema operativo", "items": [{"label": "Sistema operativo", "value": "Windows 11"}]},
                {"title": "Cámara", "items": [{"label": "Cámara web", "value": "720p HD"}]},
            ],
        },
    )
    db.add_all([category, product, *defs])
    db.commit()
    return product


def test_backfill_captures_expanded_notebook_specs():
    with Session() as db:
        _reset(db)
        product = _add_rich_notebook(db)

        result = backfill_product_specs(product, ProductSpecValueService(db, auto_commit=False))
        db.commit()

        values = {value.definition.key: value for value in db.query(ProductSpecValue).all()}
        assert result.created_or_updated == 10
        assert values["processor_boost_frequency"].value_number == Decimal("4.3")
        assert values["processor_boost_frequency"].unit == "GHz"
        assert values["processor_base_frequency"].value_number == Decimal("2.8")
        assert values["processor_cache"].value_number == 4
        assert values["processor_cache"].unit == "MB"
        assert values["processor_tdp"].value_number == 15
        assert values["processor_tdp"].unit == "W"
        assert values["screen_refresh_rate"].value_number == 144
        assert values["screen_refresh_rate"].unit == "Hz"
        assert values["touchscreen"].value_boolean is True
        assert values["gpu_type"].value_text == "Dedicada"
        assert values["os"].value_text == "Windows 11"
        assert values["webcam"].value_text == "720p HD"


def test_backfill_parses_terabytes_as_gigabytes():
    with Session() as db:
        _reset(db)
        product = _add_rich_notebook(db)

        backfill_product_specs(product, ProductSpecValueService(db, auto_commit=False))
        db.commit()

        value = db.query(ProductSpecValue).filter(ProductSpecValue.definition.has(key="storage_capacity")).one()
        assert value.value_number == 2048
        assert value.unit == "GB"


def _add_mobile(db):
    category = Category(name="Celulares", slug="celulares")
    defs = [
        CategorySpecificationDefinition(category=category, key="battery_capacity", label="Capacidad batería", group="Energía", data_type="integer", unit="mAh"),
        CategorySpecificationDefinition(category=category, key="rear_camera_megapixels", label="Megapíxeles cámara trasera", group="Cámara", data_type="decimal", unit="MP"),
        CategorySpecificationDefinition(category=category, key="weight", label="Peso", group="Dimensiones", data_type="integer", unit="g"),
    ]
    product = Product(
        name="Smartphone Galaxy A57 5G 128GB 6.7''",
        brand="Samsung",
        category_entity=category,
        specs={
            "highlights": ["5000 mAh"],
            "sections": [
                {"title": "Batería", "items": [{"label": "Capacidad", "value": "5000 mAh"}]},
                {"title": "Cámara", "items": [{"label": "Resolución trasera", "value": "200 MP"}]},
                {"title": "Otros", "items": [{"label": "Peso", "value": "187 g"}]},
            ],
        },
    )
    db.add_all([category, product, *defs])
    db.commit()
    return product


def test_backfill_captures_mobile_numeric_specs():
    with Session() as db:
        _reset(db)
        product = _add_mobile(db)

        result = backfill_product_specs(product, ProductSpecValueService(db, auto_commit=False))
        db.commit()

        values = {value.definition.key: value for value in db.query(ProductSpecValue).all()}
        assert result.created_or_updated == 3
        assert values["battery_capacity"].value_number == 5000
        assert values["battery_capacity"].unit == "mAh"
        assert values["rear_camera_megapixels"].value_number == 200
        assert values["rear_camera_megapixels"].unit == "MP"
        assert values["weight"].value_number == 187
        assert values["weight"].unit == "g"
