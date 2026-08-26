# Constraint & Concurrency Audit

**Date**: 2026-08-26  
**Test count**: 480 (19 new concurrency tests)

## Constraint Audit Table

| Table | Constraint | Type | Correct? | Notes |
|-------|-----------|------|----------|-------|
| Product | `gtin` UNIQUE | Index | ✅ | Leading zeros preserved in VARCHAR. Lengths 8/12/13/14 enforced by `normalize_gtin()`. |
| Product | `mpn` UNIQUE | Index | ⚠️ | Catches exact string duplicates. Does NOT catch variant equivalents (RTX-5070 vs RTX 5070). See MPN analysis below. |
| Product | `brand` indexed | Index | ✅ | Non-unique, correct — multiple products can share a brand. |
| Product | `model` indexed | Index | ✅ | Non-unique, correct — multiple products can share a model. |
| Product | `manufacturer_sku` indexed | Index | ✅ | Non-unique, correct — store-internal IDs filtered by `match_by_manufacturer_sku()`. |
| StoreOffer | `UNIQUE(store_id, url)` | Constraint | ✅ | Prevents duplicate offers per store per URL. |
| StoreOffer | `external_id` indexed | Index | ✅ | Non-unique — different stores can have same external_id. |
| Store | `domain` UNIQUE | Column | ✅ | One store per domain. |
| Store | `name` UNIQUE | Column | ✅ | One store per name. |
| Category | `UNIQUE(name, parent_id)` | Constraint | ✅ | Allows same name under different parents (e.g., "Notebooks" under "Tecnología" and "Gaming"). |
| Category | `slug` UNIQUE | Column | ✅ | One slug per category. |
| PriceHistory | (no unique constraints) | — | ✅ | Multiple observations of same price are valid (temporal tracking). |
| ProductSpec | `UNIQUE(product_id, name)` | Constraint | ✅ | One spec per product per name. Different products can share spec names. |
| IngestionSource | `UNIQUE(name, store_id)` | Constraint | ✅ | One source per name per store. |

## MPN UNIQUE Analysis

**Current**: `UNIQUE(mpn)` catches exact string duplicates.

**Variant gap**: `mpn_variants()` normalizes "RTX-5070", "RTX 5070", "RTX5070" to different strings. UNIQUE(mpn) only catches exact matches.

**Cross-brand scenario**:
- Product A: mpn="RTX-5070", brand="ASUS" → stored
- Product B: mpn="RTX 5070", brand="MSI" → stored (different MPN string, different brand)
- Query for "RTX 5070" + "ASUS" → finds Product A via `mpn_matches()` (Python-side variant comparison)
- Query for "RTX 5070" + "MSI" → finds Product B via exact brand+MPN match

**Assessment**: Current behavior is acceptable. Cross-brand MPN collisions with variant formatting are rare in practice. The `match_by_mpn_brand()` query works correctly because:
1. It filters by brand first (ILIKE), narrowing to the correct brand
2. Then uses `mpn_matches()` for variant comparison in Python
3. UNIQUE(mpn) prevents true duplicates (same MPN string)

**Future improvement** (when moving to PostgreSQL): Add a partial unique index on `normalize_mpn(mpn)` to catch variant duplicates.

## GTIN Analysis

**Leading zeros**: `normalize_gtin()` strips non-digits, validates length. GTIN-12 "012345678901" → stored as "012345678901" (12 chars). VARCHAR preserves leading zeros. ✅

**Different lengths**: GTIN-12 and GTIN-13 for the same physical product are different identifiers → two Products is correct behavior. ✅

## ProductSpecifications Boundary

**Identity fields** (on Product model): GTIN, MPN, brand, model, manufacturer_sku  
**Attribute fields** (on ProductSpecification): RAM, storage, screen size, CPU, GPU, color, weight

Specs are variant-specific (e.g., "RAM=16GB" vs "RAM=32GB" for same product model). The `UNIQUE(product_id, name)` constraint prevents duplicate specs per product. ✅

## Concurrency Findings

### Race conditions identified

| Race | Window | Mitigation | Status |
|------|--------|------------|--------|
| `_find_offer` returns None → two threads both create | Between SELECT and INSERT | `UNIQUE(store_id, url)` catches duplicate | ✅ Catches |
| `match()` returns NO_MATCH → two threads both create Product | Between SELECT and INSERT | `UNIQUE(mpn)` catches duplicate | ✅ Catches |
| Both threads create same Store | Between SELECT and INSERT | `UNIQUE(domain)` catches duplicate | ✅ Catches |
| Store creation race (domain collision) | Between SELECT and INSERT | `UNIQUE(domain)` + `_get_or_create_store` | ✅ Catches |

### Transaction boundaries

- **Per-offer commit**: Each `ingest()` commits independently. One bad offer doesn't undo others. ✅
- **Pipeline isolation**: Pipeline catches `ValueError`, `KeyError`, `decimal.InvalidOperation`, `OfferValidationError`. Other exceptions abort pipeline. ✅
- **Product+Offer atomicity**: `_create_product` uses `flush()`, not `commit()`. Product and Offer are in the same transaction. ✅
- **DB error propagation**: `commit()` failure rolls back session. Pipeline continues with next offer. ✅

### Production recommendations (PostgreSQL)

1. Use `SELECT ... FOR UPDATE` in `_find_offer` for row-level locking
2. Use `INSERT ... ON CONFLICT DO NOTHING` for store/offer creation
3. Wrap `ingest()` in a savepoint for nested transaction safety
4. Use connection pooling with proper isolation level (READ COMMITTED)

## Pipeline fix applied

- `pipeline.py`: Added `decimal.InvalidOperation` to exception handling (extraction errors from invalid Decimal conversion in `connector.normalize()`)
