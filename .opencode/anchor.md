# SoloTodo AI
## Última sesión activa: Procedencia y conflicto ram_speed resueltos (31/08/2026)

## Goal
- Auditar y corregir procedencia real de `ProductSpecValue`: no etiquetar todo como `ai`; corregir semántica del conflicto `ram_speed` sin inventar datos; conectar la ingesta a valores canónicos cuando el conector entregue specs.

## Constraints & Preferences
- No convertir `5500 MB/s` → `MHz` automáticamente; corregir solo con evidencia (LPDDR5-5500 documentada) conservando raw.
- Procedencia refleja evidencia original: evidencia literal en name/description → `store`; sin evidencia → `unknown`; nunca asumir `ai`.
- NO inventar datos; diagnósticos basados en BD real (PostgreSQL vía DATABASE_URL).
- No tocar taxonomía reorganizada (44 categorías). No errores de lint/build.
- IA = capa de enriquecimiento posterior, no fuente principal.

## Progress
### Done (última sesión)
- `--refresh-provenance` en `scripts/backfill_product_spec_values.py` → `force_source_update` para re-etiquetar procedencia real en BD: ahora **62 store / 17 unknown (0 ai)**.
- `app/catalog/spec_backfill.py`: inferencia 'store' solo si raw aparece literal en name/description (source_name = stores de offers, extraction_method 'product_specs_json:store_evidence'); si no → 'unknown' ('product_specs_json:unverified_origin').
- `app/ingestion/dto.py`: campos `specs_source_type/specs_source_name/specs_extraction_method` en `NormalizedOffer`.
- `app/ingestion/service.py`: `_backfill_canonical_specs()` (no-op si conector no entrega specs; por defecto `store` + nombre tienda + método `{source}:structured_specs`).
- `verify()` en `ProductSpecValueService` acepta `correction: SpecValueInput` opcional (corrección admin con cambio de semántica, registro en historial como VERIFIED).
- `POST /admin/spec-values/{id}/verify` acepta fields opcionales de corrección (`value_kind`, `raw_value`, `value_text`, `value_number`, `value_boolean`, `value_json`, `unit`, `source_type`, `source_name`, `source_url`, `extraction_method`).
- `catalog_quality.py`: reporte ampliado con `source_names`, `extraction_methods`, `provenance_summary`, `conflicts_by_source`; schema actualizado en `app/routers/admin.py`.
- **Conflicto ram_speed (producto 32, valor id 69) RESUELTO**: corrección `5500 MT/s` (src=admin, 'Revisión manual'), nota documentando que "5500 MB/s" es rotulado de tienda (descripción HP + silicio Ryzen 5 7520U documentan LPDDR5-5500); raw conservado.
- Reporte real actual: 21 productos, 24 ofertas, 3 tiendas, 79 valores, 6 sin specs, 78 review / 1 verified, **0 conflictos**, completitud 32%, procedencia `store 61 / unknown 17 / admin 1`.
- Tests: `589 passed, 2 warnings` (StarletteDeprecationWarning httpx + DeprecationWarning google genai `_UnionGenericAlias`); nuevos: `test_admin_verifies_spec_value_with_correction`, `test_ingestion_structured_specs_create_store_sourced_canonical_values`.
- Frontend: `pnpm lint` 0 errors / 7 warnings conocidos; `pnpm build` OK.

### Done (sesiones previas, vigentes)
- Taxonomía: grupos `PC y Componentes`/`Computadores`/`Monitores y Pantallas`/`Periféricos`/`Gaming`/`Redes`/`Móviles`; 44 categorías / 153 spec definitions; seed idempotente con limpieza de categorías obsoletas vacías.
- Sistema canónico `ProductSpecValue`: modelos `ProductSpecValue`/`ProductSpecValueHistory`, enums `SpecValueKind`/`SpecValueSourceType`/`SpecVerificationStatus`/`SpecConflictStatus`/`SpecValueHistoryAction`; migración `alembic/versions/20260829_02_product_spec_values.py` (head `20260829_02`); repo `app/repositories/product_spec_value_repository.py`; servicio en `app/services/product_spec_value_service.py` (prioridad ADMIN>MANUFACTURER>EXTERNAL>STORE>SCRAPER/INGESTION>AI>UNKNOWN, protege `verified`, conflictos pending, historial, `auto_commit`, `force_source_update`).
- Backfill idempotente `app/catalog/spec_backfill.py` + `scripts/backfill_product_spec_values.py` (normaliza `8 GB`→número+GB, `14`→pulgadas, `WUXGA`→`1920 × 1200`; conserva raw; NO convierte `MB/s`→`MHz`; agrupa `Puertos`, `Wi-Fi/Bluetooth`).
- Ficha canónica: `app/catalog/spec_sheet.py` `build_canonical_spec_sheet` + `format_spec_value` (`14"` sin espacio); `ProductRead.canonical_specs`; `ProductService.get/search`; `SpecSheet` frontend con fallback JSON y badges.
- Admin real: `frontend/app/admin/page.tsx` (Dashboard/Productos/Categorías/Revisión/Conflictos/Tiendas/Ofertas/Ingesta/Estadísticas); endpoints `/admin/dashboard`, `/admin/spec-values/review`, `/admin/spec-values/{id}/verify`, `/admin/catalog/quality`; link en `site-header.tsx`; tipos en `frontend/types/admin.ts` + `frontend/lib/api/admin.ts`.
- Calidad: `app/catalog/catalog_quality.py` score por perfil de categoría (notebooks, tarjetas-graficas, memoria-ram, celulares, monitores) diferenciando faltante vs no aplicable.

## Key Decisions
- Mantener `Product.specs` JSON como fallback público; `ProductSpecValue` es capa canónica paralela.
- No convertir automáticamente unidades ambiguas; solo corrección admin con evidencia documentada.
- Conectores actuales no llenan `NormalizedOffer.specs`; si futuro connector entrega specs, el pipeline crea valores `store` (fila confirmada por test).
- Tests de carrera SQLite `StaticPool` validan `<=1` (ambos threads pueden abortar).

## Critical Facts
- BD real = PostgreSQL (Alembic `PostgresqlImpl`), no `solotodo.db`.
- `Product.specs` lo genera Gemini (`scripts/generate_specifications.py`) desde name/brand/category/description; por eso antes todo era `ai`.
- 6 productos sin specs canónicas; completitud 32% (REAL).

## Next Steps (futuras)
- Si un conector empieza a entregar specs: conectar metadata `specs_source_*` (flujo ya listo).
- Considerar enriquecimiento de los 17 valores `unknown` vía fabricante/scraping antes que IA.
- Procesar los 78 revisión restantes (señal `source_name="Product.specs JSON"` = foco).
- Revisar los 6 productos sin specs (los de "0 values, N skipped": #37, #49, #51, #59, #60, #61).

## Relevant Files
- `app/catalog/spec_backfill.py`, `app/catalog/spec_sheet.py`, `app/catalog/catalog_quality.py`
- `app/services/product_spec_value_service.py` (verify con correction), `app/repositories/product_spec_value_repository.py`
- `app/ingestion/dto.py` (+specs_source_*), `app/ingestion/service.py` (`_backfill_canonical_specs`)
- `app/routers/admin.py` (verify con corrección, quality ampliado)
- `scripts/backfill_product_spec_values.py` (`--refresh-provenance`)
- `alembic/versions/20260829_02_product_spec_values.py`
- Tests: `test_admin_spec_review.py`, `test_spec_backfill.py`, `test_ingestion_pipeline.py`, `test_catalog_api.py`, `test_concurrency.py`
- Otros: `app/catalog/matching.py` (ProductMatcher), `app/ingestion/connectors.py` (StoreConnector, MockStoreConnector), `scripts/generate_specifications.py`, `frontend/components/product/product-specs.tsx`, `frontend/app/admin/page.tsx`