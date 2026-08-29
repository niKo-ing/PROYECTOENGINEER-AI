from app.models.catalog import Category, Product
from scripts.enrich_specifications import enrich_specs


def test_enriches_exact_cpu_model_without_overwriting_existing_specs():
    product = Product(
        name="Notebook Lenovo IdeaPad Intel Core i5-13420H 8GB RAM 512GB SSD",
        brand="Lenovo",
        category_entity=Category(name="Notebooks", slug="notebooks"),
        specs={
            "highlights": ["8GB RAM"],
            "sections": [
                {"title": "Procesador", "items": [{"label": "Procesador", "value": "Intel Core i5-13420H"}]},
                {"title": "RAM", "items": [{"label": "Capacidad", "value": "8 GB"}]},
            ],
        },
    )

    specs, changes = enrich_specs(product)
    processor = next(section for section in specs["sections"] if section["title"] == "Procesador")
    labels = {item["label"] for item in processor["items"]}

    assert "Procesador" in labels
    assert "Núcleos" in labels
    assert "Hilos" in labels
    assert "Frecuencia turbo" in labels
    assert "Gráficos integrados" in labels
    assert any("8 núcleos / 12 hilos" in highlight for highlight in specs["highlights"])
    assert changes


def test_enriches_dedicated_gpu_specs():
    product = Product(
        name='Notebook HP Victus i5-12450H RTX 2050 15.6" 8GB RAM',
        brand="HP",
        category_entity=Category(name="Notebooks", slug="notebooks"),
        specs={"highlights": [], "sections": [{"title": "Tarjeta de video", "items": [{"label": "Modelo", "value": "RTX 2050"}]}]},
    )

    specs, _changes = enrich_specs(product)
    gpu = next(section for section in specs["sections"] if section["title"] == "Tarjeta de video")
    values = {item["label"]: item["value"] for item in gpu["items"]}

    assert values["Tipo"] == "Dedicada"
    assert values["VRAM"] == "4 GB GDDR6"
    assert values["Arquitectura"] == "Ampere"


def test_does_not_enrich_ambiguous_cpu_family():
    product = Product(
        name="Notebook HP OMEN Intel Ultra 7 16GB 1TB",
        brand="HP",
        category_entity=Category(name="Notebooks", slug="notebooks"),
        specs={"highlights": [], "sections": [{"title": "Procesador", "items": [{"label": "Procesador", "value": "Intel Ultra 7"}]}]},
    )

    _specs, changes = enrich_specs(product)

    assert not changes
