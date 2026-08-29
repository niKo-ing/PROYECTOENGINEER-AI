"""Generate AI descriptions for catalog products missing one.

Creates a concise factual description (max 2 short sentences) that ONLY
uses real catalog data (name, brand, category, price, stores). It never
invents specs, colors, guarantees or prices. Results are stored in
products.description_ai so the UI can label them "Generada con IA".

Usage:
    python -m scripts.generate_descriptions_ai [--product-id 28] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import time
from decimal import Decimal

from google import genai
from google.genai import types

from app.core.config import settings
from app.db import SessionLocal
from app.models.catalog import Product

SYSTEM_INSTRUCTIONS = (
    "Eres un redactor de fichas técnicas para un comparador de tecnología. Genera descripciones objetivas, ordenadas y fáciles de leer "
    "en español. Usa ÚNICAMENTE los datos que se te entregan en la ficha. "
    "No inventes características, especificaciones, colores, garantías, existencias ni precios. "
    "No agregues opiniones, superlativos ni llamados a la acción. "
    "Formatea los precios en pesos chilenos (ej. $1.234.567). "
    "Responde con este formato exacto, sin markdown extra: \n"
    "Resumen\n"
    "1 párrafo de 2 a 3 frases con el tipo de producto y sus datos principales.\n\n"
    "Características destacadas\n"
    "- 3 a 6 bullets con specs reales.\n\n"
    "Datos comerciales\n"
    "- 1 a 3 bullets con precio, tienda y cantidad de ofertas si están disponibles."
)

PROMPT_TEMPLATE = (
    "Escribe una descripción corta y objetiva de este producto.\n"
    "Ficha del producto (datos reales del catálogo):\n"
    "- Nombre: {name}\n"
    "- Marca: {brand}\n"
    "- Categoría: {category}\n"
    "- Precio más bajo: {lowest_price}\n"
    "- Tienda con mejor precio: {lowest_price_store}\n"
    "- Cantidad de ofertas en el catálogo: {offer_count}\n"
    "- Tiendas y precios actuales del catálogo:\n{offers}\n"
    "- Ficha técnica estructurada disponible:\n{specs}\n"
)


def format_clp(value: int | None) -> str:
    if value is None:
        return "sin precio"
    return f"${value:,}".replace(",", ".")


def build_fact_sheet(product: Product) -> str:
    offers = sorted((o for o in product.offers if o.availability and o.currency == "CLP"), key=lambda o: o.price)
    lines = []
    for offer in offers[:3]:
        lines.append(f"  - {offer.store.name}: {format_clp(int(offer.price))}")
    specs = product.specs or {}
    spec_lines = []
    for highlight in specs.get("highlights", [])[:7]:
        spec_lines.append(f"  - Destacado: {highlight}")
    for section in specs.get("sections", [])[:10]:
        title = section.get("title")
        items = section.get("items") or []
        values = "; ".join(f"{item.get('label')}: {item.get('value')}" for item in items[:8])
        if title and values:
            spec_lines.append(f"  - {title}: {values}")
    return PROMPT_TEMPLATE.format(
        name=product.name,
        brand=product.brand or "sin marca registrada",
        category=product.category,
        lowest_price=format_clp(product.lowest_price),
        lowest_price_store=product.lowest_price_store or "desconocida",
        offer_count=product.offer_count,
        offers="\n".join(lines) if lines else "  - (sin ofertas)",
        specs="\n".join(spec_lines) if spec_lines else "  - (sin ficha técnica estructurada)",
    )


def call_gemini(client: genai.Client, model: str, timeout_seconds: float, prompt: str) -> str:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    systemInstruction=SYSTEM_INSTRUCTIONS,
                    temperature=0.3,
                    maxOutputTokens=700,
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
    parser.add_argument("--force", action="store_true", help="Regenerar aunque ya exista descripción IA")
    parser.add_argument("--dry-run", action="store_true", help="Imprimir la ficha sin llamar al LLM")
    args = parser.parse_args()

    if settings.llm_provider != "gemini":
        print("Este script usa el provider Gemini configurado en LLM_PROVIDER.")
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY no está configurada en el entorno")

    client = genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(timeout=int(settings.llm_timeout_seconds * 1000)))

    db = SessionLocal()
    generated = 0
    try:
        query = db.query(Product)
        if not args.force:
            query = query.filter(Product.description_ai.is_(None))
        if args.product_id:
            query = query.filter(Product.id == args.product_id)
        products = query.order_by(Product.id).all()

        print(f"Procesando {len(products)} productos sin descripción IA")
        for product in products:
            prompt = build_fact_sheet(product)
            if args.dry_run:
                print(f"\n#{product.id} {product.name}\n{prompt}")
                continue
            try:
                description = call_gemini(client, settings.gemini_model, settings.llm_timeout_seconds, prompt)
            except RuntimeError as error:
                print(f"  #{product.id} {product.name[:40]}: saltado ({error})")
                continue
            if not description:
                print(f"  #{product.id} {product.name[:40]}: respuesta vacía, saltado")
                continue
            product.description_ai = description
            generated += 1
            print(f"  #{product.id} {product.name[:40]}: -> {description[:100]}")
            db.commit()

        if not args.dry_run:
            print(f"Generadas {generated} descripciones")
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
