# SOLOTODO AI V3 — Versión final: Web Research + Evidence Validation (Backend)

**Fecha:** 2026-09-04
**Estado:** Implementado y validado. Sin commits.
**Validación:** `pytest` **703 passed** (679 baseline + 24 nuevos) · `frontend` lint **0 errores** · `pnpm build` **OK** · TypeScript **OK**.

---

## 1. Resumen ejecutivo

SOLOTODO AI V3 agrega al asistente una **capa de investigación web externa con validación de evidencia**, sin romper la V2. Cuando el catálogo no alcanza (preguntas sobre reviews, specs ausentes, comparaciones), el orquestador consulta proveedores web reales, jerarquiza las fuentes siguiendo criterio *manufacturer-first* y solo entrega afirmaciones respaldadas por evidencia. Si la evidencia es insuficiente o contradictoria, la IA dice "no sé". El módulo es 100% offline-testable (proveedores inyectables, mocks deterministas) y el UI solo gana una sección de "Fuentes consultadas".

**Baseline 679 → 703 tests verdes. Cero regresiones. Sin commits.**

## 2. Objetivo y alcance (V3)

| Tema | Estado |
|---|---|
| Capa de Web Research externo | Implementado (pasos 1–8 del plan + tests + validación) |
| Enriquecer respuestas con datos verificados | Implementado |
| No romper la V2 (`AIOrchestrator`, `ConversationState`, `Intent`, `EntityResolver`, `Planner`, `RecommendationEngine`) | Verificado: intactos; V3 se conecta por composición |
| Endpoint / modelo de datos | `ChatResponse` extendido de forma aditiva (`sources`, `research`) |

## 3. Alcance fuera (explícitamente NO se hizo)

- **NO** se vectorizó el catálogo, ni se reemplazó SQL por RAG/pgvector.
- **NO** se hizo scraping masivo.
- **NO** se confía en snippets; los claims se respaldan con extracción de documento o con fallback anotado.
- **NO** se mezclan variantes (POCO X6 ≠ POCO X6 Pro): mismatch de variante ⇒ `VARIANT_MISMATCH`.
- **NO** se inventan benchmarks ni precios: sin evidencia ⇒ `insufficient_evidence` ⇒ la IA responde "no sé".
- **NO** se añadieron tools nuevas al `AIEngine` (`test_ai_chat.py:98` aserta el set cerrado de 6 tools).
- **NO** se rediseñó el frontend; solo se preparó y se renderiza la evidencia ya devuelta por el backend.

## 4. Decisiones de diseño clave

1. **Proveedor default = DuckDuckGo HTML** (validado por el usuario): sin API key, `httpx` + timeout, inyectable y mockeable. Interfaz `WebSearchProvider` permite migrar a Tavily/Serper vía `.env` sin tocar el orquestador.
2. **Catalog first, research solo como provisión**: el research corre después del plan de catálogo; salta si el catálogo ya cubre la pregunta (specs presentes, sin intención de info externa).
3. **Manufacturer-first genérico**: `source_priority` es genérico (fabrica > documentación oficial > benchmark > review > web genérica), **no** hardcodeado por marca.
4. **Reranker determinista sin embeddings**: combina cobertura de tokens de modelo, brand-hit, `is_official_source`, prioridad de fuente y match de variante.
5. **Límites configurables por env**, no hardcodeados en el orquestador.
6. **Tests offline**: `FakeProvider`/`FakeResearchService` deterministas; el research solo testea contra evidencia, nunca reinventa.

## 5. Arquitectura del módulo (`app/ai/research/`)

```text
app/ai/research/
├── schemas.py               # ResearchReport, EvidenceItem, Verdict, intent_kind…
├── source_discovery.py      # DiscoveryProvider y fallback de modelo (excluye brand)
├── validation.py            # agreement / conflict / missing / variant mismatch
├── reranker.py              # ranking determinista de fuentes
├── chunking.py              # chunks con boundary y capa dura de chars
├── benchmark.py             # parser posicional de Geekbench (single/multi-core)
├── sources.py               # source_type_for_url, SOURCE_PRIORITY, _host sin www
└── web_research_service.py  # WebSearchProvider|DocumentRetriever, DuckDuckGoSearchProvider,
                             # HTTPDocumentRetriever, WebResearchService
```

Flujo: `WebResearchService.run(targets)` → queries con budget → ranking de resultados → selección por target (`per_target_slots`) → extracción de evidencia desde documento (1er chunk, `max_chars`) o snippet fallback → verdicts de benchmark → `context` anotado + `note` → `ResearchReport`.

## 6. Catálogo primero y provisión de research

`_should_research` en `app/ai/orchestrator.py`:

1. gate `settings.research_enabled`
2. intent ∈ `_RESEARCH_KINDS = {COMPARE, RECOMMEND, PRODUCT_DETAIL, SPECIFICATION}` (`PRICE_CHECK` quedó excluido: los precios solo vienen del catálogo)
3. hay `products`; hay identidad de target (`_has_target_identity`)
4. el usuario pide info externa (`_wants_external_information`) **o** hay gaps de specs (`_has_spec_gaps`)

Si el catálogo está completo, `research_calls = 0` sin invocar el servicio. El `ResearchReport` se funde en la respuesta: `.sources` = `[item.as_dict() for item in evidence]`, y el `research_context` anotado se inyecta al prompt vía `_augment_prompt`.

## 7. Discovery, ranking y selección de fuentes

- Parámetros de descubrimiento por kwargs (queries/urls), con `_fallback_model` sin brand tokens ("Samsung Galaxy S24 Ultra" → model "Galaxy S24 Ultra").
- Ranking con prioridad genérica de tipo de fuente; `_host` normaliza quitando `www.`.
- Presupuesto de ejecución (`max_research_queries`, `max_research_sources`, `max_research_documents`) y cuota de slots por target para no saturar la respuesta.
- `source_for_result` usa `result.source_type` (estrategia) o `source_type_for_url` como fallback.

## 8. Evidence validation y protocolo "no inventar"

- `values_equivalent` con alias de unidades (`gigas` → `gb`).
- `_conflicting_numeric`: mismo unit presente en ambas fuentes sin valor en común ⇒ `CONFLICT`.
- La evidencia **debe mencionar el modelo**: si lo menciona pero no supera `variant_matches` ⇒ `VARIANT_MISMATCH`; si no lo menciona ⇒ `insufficient_evidence`.
- Con `insufficient_evidence` la respuesta del asistente declara no tener suficiente información en lugar de inventar.

## 9. Integración con el orquestador (V2 intacta)

- `AIOrchestrator.__init__` acepta `research_service: WebResearchService | None` (composición; `None` ⇒ V3 apagado sin tocar V2).
- `chat()` corre research tras el plan de catálogo; pasa `sources`/`research` a `_response`.
- `ChatResponse` aditivo: `sources: list[dict[str, Any]]` + `research: bool`. `frontend/lib/api/chat.ts` y el resto del contrato existente no se rompen.

## 10. Configuración (env)

```text
RESEARCH_ENABLED            (default true)
MAX_RESEARCH_QUERIES        (3)
MAX_RESEARCH_SOURCES        (4)
MAX_RESEARCH_DOCUMENTS      (3)
MAX_RESEARCH_CHUNKS         (24)
MAX_RESEARCH_CHARS          (6000)
RESEARCH_TIMEOUT_SECONDS    (10)
```

Todos definidos en `app/core/config.py`. Cuando `RESEARCH_ENABLED=false` el gate corta sin llamar a la red.

## 11. Tests

- `tests/test_web_research.py` — **21 tests** puros: parsing DDG, chunking, benchmark, validation y reranker (offline, mocks deterministas).
- `tests/test_research_integration.py` — **3 tests** e2e contra el orquestador con `FakeResearchService`: research adjunto cuando se pide info externa; `research_calls=0` con catálogo completo; salto sin identidad. Cada test resetea la base compartida (`reset_database`).
- Los tests del módulo respetan el set cerrado de tools y el contrato de `ChatResponse`.

## 12. Evaluación y resultados

| Check | Resultado |
|---|---|
| Backend `pytest` | **703 passed** (679 baseline + 24 nuevos), 0 fallos |
| `tests/test_ai_chat.py` + `test_ai_orchestrator.py` (V2) | Verdes tras el cambio aditivo de `ChatResponse` |
| Import `app.ai.orchestrator` | OK |
| Frontend `pnpm lint` | 0 errores (8 warnings pre-existentes, ajenos a V3) |
| Frontend `pnpm build` | OK, TypeScript OK, 9 rutas generadas |
| Regresiones de V2 | Ninguna |

## 13. Riesgos, limitaciones y trabajo futuro

- **Fallback de snippets:** cuando el documento no responde, la evidencia de snippet queda anotada como fallback; futuro: priorizar extracción de más chunkes/dominios oficiales.
- **Proveedor default sin key** (DuckDuckGo HTML) puede saturar o variar HTML; la interfaz `WebSearchProvider` ya permite migrar a Tavily/Serper.
- **Benchmarks:** parser posicional de Geekbench single/multi-core; no cubre benchmarks propietarios.
- **Futuro:** guardar evidencia versionada (tabla `research_evidence`), caché de proveedor y revalidación periódica de datos verificados.
```