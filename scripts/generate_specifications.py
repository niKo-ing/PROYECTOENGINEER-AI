"""Generate structured technical specs (ficha técnica) for catalog products.

Extracts a JSON technical sheet from the real catalog data available for a
product (name, brand, category and, when present, the store description):

    {
      "highlights": ["16 GB DDR5", "512 GB SSD"],      # key specs consumers look for
      "sections": [                                    # ordered, category-appropriate
        {"title": "Procesador", "items": [{"label": "CPU", "value": "..."}]}
      ]
    }

The extractor NEVER invents values: every label/value must be grounded in the
provided source text. Sections follow the product category (Notebooks vs
Celulares). Results are stored in products.specs so the UI can show key
specs at the top and a divided, detailed ficha below.

Usage:
    python -m scripts.generate_specifications [--product-id 28] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings
from app.db import SessionLocal
from app.models.catalog import Product

SYSTEM_INSTRUCTIONS = (
    "Eres un técnico que extrae la ficha de especificaciones de un producto para una "
    "página de comparación estilo SoloTodo. Recibes el nombre oficial, la marca, la "
    "categoría y, si existe, la descripción técnica que publicó la tienda.\n"
    "Reglas estrictas:\n"
    "1. Usa ÚNICAMENTE datos presentes en el texto de origen. NO inventes valores, "
    "   medidas, pantallas, cámaras, baterías, puertos ni versiones.\n"
    "2. Si una característica no aparece en el origen, omitela: jamás la anotes como "
    "   'No' o 'Sí'.\n"
    "3. Etiquetas cortas y valor técnico concreto (ej. label 'RAM', value '16 GB DDR5 (4800 MHz)').\n"
    "4. Desglosa todo lo explícito: si el origen dice '16GB RAM 512GB SSD 15.6 FHD', crea ítems separados para RAM, almacenamiento, pantalla y resolución.\n"
    "5. Incluye siempre una sección 'Información general' con marca, modelo/serie, categoría, color o MPN si esos datos están explícitos.\n"
    "6. Agrupa los datos en secciones con títulos típicos según la categoría.\n"
    "   Notebooks: Procesador, RAM, Almacenamiento, Pantalla, Tarjeta de video, Puertos, "
    "   Batería, Peso y dimensiones, Sistema operativo, Otros.\n"
    "   Celulares: Pantalla, Procesador, RAM, Almacenamiento, Cámara trasera, Cámara "
    "   frontal, Batería y carga, Conectividad, Dimensiones y peso, Sistema operativo, Otros.\n"
    "7. Para notebooks intenta separar: procesador/modelo, núcleos si aparecen, RAM/capacidad/tipo, almacenamiento/capacidad/tipo, pantalla/tamaño/resolución/tasa/touch, GPU, sistema operativo, color y MPN.\n"
    "8. Para celulares intenta separar: pantalla/tamaño/tipo/Hz, procesador, RAM, almacenamiento, cámaras, batería/carga, conectividad, SIM, resistencia, color y dimensiones.\n"
    "9. Incluye solo secciones con al menos un dato real extraído.\n"
    "10. 'highlights' debe listar las 5 a 7 características que un consumidor busca "
    "   primero para decidir (al final de arriba).\n"
    "11. Responde ÚNICAMENTE con un JSON válido con este esquema:\n"
    '   {"highlights": [string], "sections": [{"title": string, "items": [{"label": string, "value": string}]}]}\n'
    "   Sin texto adicional, sin comentarios, sin marcas de código."
)

KNOWN_SECTIONS = (
    "Procesador, RAM, Almacenamiento, Pantalla, Tarjeta de video, Puertos, Batería, "
    "Peso y dimensiones, Sistema operativo, Cámara, Conectividad, Otros"
)

PROMPT_TEMPLATE = (
    "Extrae la ficha técnica real de este producto.\n"
    "Ficha del catálogo (datos reales, única fuente de verdad):\n"
    "- Nombre: {name}\n"
    "- Marca: {brand}\n"
    "- Categoría: {category}\n"
    "- Modelo/MPN: {model_mpn}\n"
    "- Tienda: {store}\n"
    "- Descripción técnica disponible de la tienda:\n{description}\n"
    "- Títulos de sección típicos que puedes usar: {known_sections}\n"
)


def _source_description(product: Product, limit: int = 6000) -> str:
    parts = []
    if product.description:
        parts.append(product.description)
    return "\n".join(parts)[:limit]


def build_fact_sheet(product: Product) -> str:
    stores = sorted({offer.store.name for offer in product.offers if offer.store})
    return PROMPT_TEMPLATE.format(
        name=product.name,
        brand=product.brand or "sin marca registrada",
        category=product.category,
        model_mpn=" / ".join(filter(None, [product.model, product.mpn])) or "sin registro",
        store=", ".join(stores) or "desconocida",
        description=_source_description(product) or "(sin texto técnico: extrae solo del nombre)",
        known_sections=KNOWN_SECTIONS,
    )


def _clean_text(value: str) -> str:
    value = value.strip()
    value = value.strip("`")
    if value.startswith("json"):
        value = value[4:].lstrip()
    return value.strip()


def _extract_json(text: str) -> dict:
    candidate = _clean_text(text)
    last_error: Exception | None = None
    strategies = [
        lambda: json.loads(candidate),
        lambda: json.JSONDecoder().raw_decode(candidate)[0],
    ]

    def balanced() -> object:
        start = candidate.find("{")
        if start < 0:
            raise ValueError("sin objeto JSON en la respuesta")
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(candidate)):
            ch = candidate[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(candidate[start : i + 1])
        raise ValueError("objeto JSON sin cerrar")

    strategies.append(balanced)
    for strategy in strategies:
        try:
            data = strategy()
            if not isinstance(data, dict):
                raise ValueError("respuesta no es un objeto JSON")
            return data
        except ValueError as error:
            last_error = error
    raise ValueError(f"JSON inválido: {last_error}")


def _digest(specs: dict) -> dict:
    """Normalize and cap an extraction into the stored shape."""
    if not isinstance(specs, dict):
        raise ValueError("no es un dict")
    highlights = specs.get("highlights") or []
    if not isinstance(highlights, list):
        highlights = []
    highlights = [str(h).strip() for h in highlights if str(h).strip()][:7]

    sections = []
    raw_sections = specs.get("sections")
    if isinstance(raw_sections, list):
        for sec in raw_sections[:12]:
            if not isinstance(sec, dict):
                continue
            title = str(sec.get("title", "")).strip()
            items = []
            raw_items = sec.get("items") or []
            if not isinstance(raw_items, list):
                continue
            for item in raw_items[:12]:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label", "")).strip()
                value = str(item.get("value", "")).strip()
                if label and value and len(value) <= 500:
                    items.append({"label": label, "value": value})
            if title and items:
                sections.append({"title": title, "items": items})

    if not highlights and not sections:
        raise ValueError("sin datos extraíbles")
    return {"highlights": highlights, "sections": sections}


def call_gemini(client: genai.Client, model: str, timeout_seconds: float, prompt: str) -> str:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    systemInstruction=SYSTEM_INSTRUCTIONS,
                    temperature=0.2,
                    maxOutputTokens=2000,
                ),
            )
            return (getattr(response, "text", "") or "").strip()
        except Exception as error:  # provider flakiness is retried
            last_error = error
            print(f"  LLM error (intento {attempt + 1}): {type(error).__name__}")
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"LLM falló tras 3 intentos: {last_error!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-id", type=int, help="Generar solo para este producto")
    parser.add_argument("--force", action="store_true", help="Regenerar aunque ya exista ficha técnica")
    parser.add_argument("--dry-run", action="store_true", help="Imprimir la ficha sin llamar al LLM")
    args = parser.parse_args()

    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY no está configurada en el entorno")

    client = genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(timeout=int(settings.llm_timeout_seconds * 1000)))

    db = SessionLocal()
    generated = 0
    try:
        query = db.query(Product)
        if not args.force:
            query = query.filter(Product.specs.is_(None))
        if args.product_id:
            query = query.filter(Product.id == args.product_id)
        products = query.order_by(Product.id).all()

        print(f"Procesando {len(products)} productos sin ficha técnica")
        for product in products:
            prompt = build_fact_sheet(product)
            if args.dry_run:
                print(f"\n#{product.id} {product.name}\n{prompt}")
                continue
            try:
                raw = call_gemini(client, settings.gemini_model, settings.llm_timeout_seconds, prompt)
                specs = _digest(_extract_json(raw))
            except ValueError:
                # Invalid JSON: retry the extraction once (not a provider error).
                try:
                    raw = call_gemini(client, settings.gemini_model, settings.llm_timeout_seconds, prompt)
                    specs = _digest(_extract_json(raw))
                except (RuntimeError, ValueError) as error:
                    print(f"  #{product.id} {product.name[:40]}: saltado ({error})")
                    continue
            except RuntimeError as error:
                print(f"  #{product.id} {product.name[:40]}: saltado ({error})")
                continue
            product.specs = specs
            generated += 1
            n_items = sum(len(s["items"]) for s in specs["sections"])
            print(f"  #{product.id} {product.name[:40]}: {len(specs['highlights'])} destacadas / {len(specs['sections'])} secciones / {n_items} ítems")
            db.commit()

        if not args.dry_run:
            print(f"Generadas {generated} fichas técnicas")
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
