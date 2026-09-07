"""Research canonical spec values per component model from registered source URLs.

For every catalog product that matches a known component (CPU / GPU / phone),
the script fetches the canonical source URL, extracts a grounded plain-text
context and asks the LLM to produce spec values with an evidence quote from the
page. Values are validated against the page context before being persisted with
full provenance (source_type, source_url, confidence, verification_status=review).

It never searches the free web and never invents values: anything without
evidence in the fetched page is discarded.

Usage:
    python -m scripts.research_spec_values [--product-id 55] [--plan] [--dry-run] [--limit 5]
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy.orm import selectinload

from app.catalog.spec_fetch import fetch_page, normalize_context
from app.catalog.ai_config import DEFAULT_RESEARCH_CONFIG
from app.catalog.spec_research import (
    _extract_json,
    allowed_keys_for,
    build_prompt,
    call_gemini,
    cross_validate_outcome,
    extract_specs,
    extracted_input_multi,
    interpret_variant_hints,
    research_input,
)
from app.catalog.spec_backfill import _parse_number_with_unit
from app.catalog.spec_sources import SpecSource, sources_for_product
from app.core.config import settings
from app.db import SessionLocal
from app.models.catalog import Category, Product, ProductSpecValue
from app.services.product_spec_value_service import ProductSpecValueService


def _spec_number(spec, definition):
    parsed = _parse_number_with_unit(spec.value, definition.unit)
    return int(parsed[0]) if parsed else None


def _matches_variant_hint(value_number, definition, product_name: str) -> bool:
    """True when a numeric value equals a variant hint for the definition's unit."""
    if value_number is None or not product_name:
        return False
    canonical = (definition.unit or "").casefold()
    return any(
        hint_number == value_number and hint_unit == canonical
        for hint_number, hint_unit in interpret_variant_hints(product_name)
    )


def _protect_variant_value(db, product: Product, definition, spec, *, product_name: str) -> bool:
    """Skip persisting when an existing value better matches the concrete variant.

    Returns True when the current DB value matches a variant hint but the proposed
    LLM value does not, meaning the proposal belongs to a different SKU variant and
    must not overwrite the better existing value.
    """
    existing = (
        db.query(ProductSpecValue)
        .filter(
            ProductSpecValue.product_id == product.id,
            ProductSpecValue.definition_id == definition.id,
        )
        .first()
    )
    proposed_number = _spec_number(spec, definition)
    if existing is None or existing.value_number is None:
        return False
    existing_matches = _matches_variant_hint(existing.value_number, definition, product_name)
    proposed_matches = _matches_variant_hint(proposed_number, definition, product_name)
    return existing_matches and not proposed_matches


def _current_value_keys(db, product_id: int, defs: dict) -> set[str]:
    """Return definition keys that already have a non-empty current value."""
    present: set[str] = set()
    rows = (
        db.query(ProductSpecValue)
        .filter(ProductSpecValue.product_id == product_id)
        .all()
    )
    for row in rows:
        key = defs.get(row.definition_id, None)
        # fallback: map by definition_id
        if key is None:
            for k, d in defs.items():
                if d.id == row.definition_id:
                    key = k
                    break
        if key is None:
            continue
        has_value = (
            row.value_text is not None
            or row.value_number is not None
            or row.value_boolean is not None
            or row.value_json is not None
        )
        if has_value:
            present.add(key)
    return present


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product-id", type=int, help="Investigar solo este producto")
    parser.add_argument("--limit", type=int, help="Máximo de productos a procesar")
    parser.add_argument("--plan", action="store_true", help="Listar coincidencias de fuentes sin red ni LLM")
    parser.add_argument("--dry-run", action="store_true", help="Ejecutar extracción pero no persistir")
    parser.add_argument("--force-source-update", action="store_true", help="Forzar actualización de la fuente de origen")
    args = parser.parse_args()

    if settings.gemini_api_key is None and not args.plan:
        raise SystemExit("GEMINI_API_KEY no está configurada en el entorno")

    db = SessionLocal()
    try:
        query = db.query(Product).options(selectinload(Product.category_entity).selectinload(Category.spec_definitions)).order_by(Product.id)
        if args.product_id:
            query = query.filter(Product.id == args.product_id)
        if args.limit:
            query = query.limit(args.limit)

        client = None
        if not args.plan:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(timeout=int(settings.llm_timeout_seconds * 1000)))

        html_cache: dict[str, str] = {}
        extraction_cache: dict[tuple[str, frozenset[str]], list] = {}
        products_planned = 0
        products_researched = 0
        total_values = 0

        research_cfg = DEFAULT_RESEARCH_CONFIG

        for product in query.all():
            defs = {definition.key: definition for definition in (product.category_entity.spec_definitions if product.category_entity else ())}
            entries = sources_for_product(product)
            if not entries:
                continue
            products_planned += 1
            print(f"\n#{product.id} {product.name[:70]}")
            for entry in entries:
                n_allowed = len(allowed_keys_for(defs, entry))
                print(f"  [{entry.kind}] {entry.target}  ->  {entry.url}  ({entry.source_name}, {n_allowed} claves permitidas)")
            if args.plan:
                if not defs:
                    print("  ! producto sin definiciones de categoría")
                continue

            if not defs:
                continue
            existing = _current_value_keys(db, product.id, defs)
            missing = {key for key in defs if key not in existing}
            print(f"  specs vigentes: {len(existing)} | faltantes: {len(missing)}")

            service = ProductSpecValueService(db, auto_commit=False)
            research: dict[str, list] = {}
            for entry in sorted(entries, key=lambda e: e.priority):
                try:
                    if entry.url in html_cache:
                        html = html_cache[entry.url]
                    else:
                        html = fetch_page(entry.url).html
                        html_cache[entry.url] = html
                    context = normalize_context(html, entry.needles, prefer_text=entry.prefer_text)
                    if not context.strip():
                        print(f"  ! {entry.target}: página sin texto extraíble")
                        continue
                    batch = allowed_keys_for(defs, entry) & missing
                    attempt = 0
                    while batch and attempt < 2:
                        attempt += 1
                        allowed_keys = frozenset(batch)
                        cache_key = (entry.url, allowed_keys)
                        specs = extraction_cache.get(cache_key)
                        if specs is None:
                            def_list = [defs[k] for k in sorted(batch)]
                            prompt = build_prompt(context[:40000], entry, def_list, product_name=product.name)
                            if not args.plan:
                                print(f"    [{entry.target}] LLM intento {attempt} ({len(prompt):,} caracteres de prompt, {len(batch)} faltantes)...")
                            raw = call_gemini(client, settings.gemini_model, settings.llm_timeout_seconds, prompt)
                            specs = extract_specs(_extract_json(raw), set(allowed_keys), context)
                            extraction_cache[cache_key] = specs
                        for spec in specs:
                            research.setdefault(spec.key, []).append((entry, spec))
                        extracted_now = {spec.key for spec in specs}
                        leftovers = batch - extracted_now
                        if attempt == 1 and leftovers:
                            batch = leftovers
                        else:
                            batch = set()
                except RuntimeError as error:
                    print(f"  ! {entry.target}: {error}")
                except ValueError as error:
                    print(f"  ! {entry.target}: {error}")

            outcome_list: list = []
            for key, pairs in sorted(research.items()):
                if key not in defs:
                    continue
                outcome = cross_validate_outcome(pairs, defs[key], research_cfg, product_name=product.name)
                outcome_list.append(outcome)

            proposed: list[tuple] = []
            for outcome in outcome_list:
                definition = outcome.definition
                if outcome.ambiguous:
                    print(f"  ! {definition.key}: opciones ambiguas, sin valor de variante definido; sin persistir (revisar)")
                    continue
                if outcome.spec is None or outcome.source is None:
                    continue
                if definition.filter_type == "multi":
                    multi_pairs = research.get(definition.key, [])
                    internal: list = []
                    seen_multi: set[str] = set()
                    for _src, _sp in multi_pairs:
                        if _sp.value in seen_multi:
                            continue
                        seen_multi.add(_sp.value)
                        internal.append(_sp)
                    if internal:
                        incoming = extracted_input_multi(product, definition, internal, outcome.source, force_source_update=args.force_source_update)
                        proposed.append((outcome.source, definition, internal[0], incoming))
                    continue
                if _protect_variant_value(db, product, definition, outcome.spec, product_name=product.name):
                    continue
                confidence = research_cfg.agreement_confidence if (outcome.conflict is False and outcome.source_count >= 2) else research_cfg.single_source_confidence
                incoming = research_input(
                    product,
                    outcome,
                    outcome.source,
                    force_source_update=args.force_source_update,
                    confidence=confidence,
                    note_extra=outcome.note,
                )
                proposed.append((outcome.source, definition, outcome.spec, incoming))

            if args.dry_run:
                if proposed:
                    print(f"    {len(proposed)} valores propuestos (dry-run, no persistidos):")
                    for entry, definition, spec, incoming in proposed:
                        rendered = incoming.value_number if incoming.value_number is not None else incoming.value_text
                        print(f"      {definition.key:32} {rendered!r}  [{entry.source_name}]")
            else:
                for entry, definition, spec, incoming in proposed:
                    service.upsert(incoming)
                db.commit()
                products_researched += 1
                total_values += len(proposed)
                print(f"  persistidos {len(proposed)} valores")

        print(f"\nPlanned products: {products_planned}")
        if not args.plan and not args.dry_run:
            print(f"Products researched: {products_researched}; spec values written: {total_values}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())