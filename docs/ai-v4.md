# SOLOTODO AI V4 — Versión final: Research Depth, Topic Planning, RAG Eval & Grounded Answering

**Fecha:** 2026-09-07
**Estado:** Implementado y validado. Sin commits.
**Validación:** `pytest` **777 passed** (703 baseline V3 + 74 nuevos) · frontend `eslint` **0 errores** · `tsc --noEmit` **OK**.

---

## 1. Resumen ejecutivo

SOLOTODO AI V4 agrega cuatro capacidades sobre la V3 sin romper contrato:

1. **Profundidad de research** — `decide_research` decide entre `NONE` / `LIGHT` / `DEEP` con presupuestos diferenciados.
2. **Query planning por tópicos** — `plan_queries(depth)` genera una query por tópico detectado (deep) o la escalera legacy (light), con estrategia de fuente por tópico.
3. **Evaluación de RAG** — harness hermético (`evaluate` + dataset de 34 queries / 33 docs) y filtros multi-producto variante-seguros.
4. **Grounded answering** — `ClaimType`/`Claim` en evidencia, `resolve_claim` con resolución determinista de conflictos por peso de fuente, y prompt grounded (`evidence_to_sections`) donde el modelo solo puede afirmar datos etiquetados como "apoya".

El UI gana dos bloques por mensaje asistente: **"¿Por qué esta recomendación?"** (V4 fields) y **"Evidencia recopilada"** (badges por `claim_type` + confianza + fuente).

**Baseline 703 → 777 tests verdes. Cero regresiones. Sin commits.**

## 2. Objetivo y alcance (V4)

| Tema | Estado |
|---|---|
| Escalación de research por profundidad (NONE/LIGHT/DEEP) | Implementado en `app/ai/planner.py` (`decide_research`) |
| Presupuestos configurable por profundidad | `research_{light,deep}_max_{queries,sources,documents}` |
| Query planning por tópicos (`detect_topics`, `plan_queries`) | `app/ai/research/query_planning.py` |
| Cache freshness-tipada por tipo de fuente | `_cache_ttl_for` en `web_research_service.py` |
| Filtros multi-producto (`product_ids` IN) + scoring por variante | `knowledge_store.py`, `reranker.py` |
| Harness de evaluación IR (P@K, R@K, MRR, MAP) + dataset curado | `app/ai/rag/evaluation.py`, `eval_dataset.py` |
| Grounded answering con claims y resolución de conflictos | `evidence.py`, `validation.py`, `context_builder.py` |
| Campos V4 en recomendación (`user_need`, `criteria_scores`, `final_reason`, `basis`) | `recommendation.py` |
| Follow-up/rewrite de queries y `trace_id` end-to-end | `orchestrator.py`, `observability.py`, `ChatResponse.trace_id` |
| Frontend: paneles de evidencia y "por qué" | `components/chat/evidence-panel.tsx` |

## 3. Alcance fuera (explícitamente NO se hizo)

- **NO** se reemplazó el catálogo SQL por pgvector; el RAG sigue sobre documentos de conocimiento con embeddings local-hash offline.
- **NO** se inventan benchmarks ni precios: conflicto irresoluble ⇒ el asistente declara "no sé".
- **NO** se mezclan variantes: `RTX 5070` ≠ `5070 Ti` ≠ `5070 Laptop` (keywords del dataset garantizan disjointness y el scoring de variante es `exacto > subset > superset > solapamiento`).
- **NO** se muestran las trazas internas completas al usuario; solo `trace_id` para correlación.
- **NO** se sube `.env` ni a repo privado (compartido por Slack/Drive).

## 4. Decisiones de diseño clave

1. **Política separada del booleano legacy**: `decide_research` (ResearchDecision con `depth`) coexiste con `research_plan`/`ResearchBudget` intactos; `build_queries` sigue siendo shim hacia `plan_queries(depth="light")`. Backward-compat verificado por test.
2. **Deep se dispara por términos léxicos O ≥2 tópicos** (`detect_topics` cuenta los 8 tópicos del `TOPIC_PRIORITY`). Una pregunta de performance simple (ej: "cómo rinde") NO es deep; una comparativa multi-aspecto SÍ.
3. **Clamp siempre en settings**: `_decision()` recorta presupuestos a los topes hard (`max_research_*`), tanto al crear el servicio como por corrida en el orquestador.
4. **Freshness por tipo de fuente**: precio/web expiran en minutos, specs de fabricante viven 24h, benchmark ~1h, review ~2h (`_cache_ttl_for`).
5. **Grounded prompt**: cada claim se renderiza etiquetado ("apoya" / "CONFLICTO" / "no aplica a la variante" / "sin confirmar"); el header ordena responder "solamente con datos respaldados" y admitir ignorancia.
6. **Resolución de conflictos determinista**: `0.5*(source_priority/60) + 0.3*confidence + 0.2*freshness(90 días)`; margen ≥0.05 ⇒ AGREEMENT con nota; si no, CONFLICT con nota honesta.

## 5. Arquitectura del módulo

```text
app/ai/
├── planner.py                     # ResearchDepth, ResearchDecision, decide_research, _DEEP_TERMS
├── ai/research/
│   ├── query_planning.py          # detect_topics, plan_queries, source_strategy, expected_source_for_topic
│   ├── source_discovery.py        # shim backward-compat de build_queries
│   ├── schemas.py                 # ResearchQuery +topic/priority; ResearchReport +depth/topics
│   ├── web_research_service.py    # research_depth + _cache_ttl_for
│   └── validation.py              # resolve_claim, _source_weighted, ClaimVerdict.as_dict
├── rag/
│   ├── evaluation.py              # precision_at_k, recall_at_k, mr r, map, retrieve_metrics, evaluate
│   ├── eval_dataset.py            # RAG_EVAL_CORPUS (33 docs) + RAG_EVAL_CASES (34 queries)
│   ├── retrievers.py              # filtro product_ids (IN)
│   ├── reranker.py                # _variant_model_score + _score_product_match
│   └── knowledge_store.py         # _target_filters multi-producto
├── evidence.py                    # ClaimType, Claim, Evidence.published_at/claim_type
├── context_builder.py             # evidence_to_sections, build_grounded_prompt
├── recommendation.py              # user_need, hard_constraints, criteria_scores, final_reason, basis
├── observability.py               # new_trace_id, AITrace.trace_id, _KNOWN_STAGES ampliado
└── orchestrator.py                # decide_research, _expand_follow_up, _kb_query(topics), trace stages
```

## 6. Escalación de research

`decide_research(intent, *, products_available, has_spec_gaps, wants_external, message)`:

1. `_RESEARCHABLE_KINDS = {COMPARE, RECOMMEND, PRODUCT_DETAIL, SPECIFICATION}` — `PRICE_CHECK` y `SEARCH` nunca van a research (catálogo-first).
2. `depth = _is_deep(...)`: `_DEEP_TERMS` (points: "investiga", "en profundidad", "a fondo", "para mi caso de uso", "relación precio/rendimiento", "vale la pena", "cuántos fps", …) **o** `len(detect_topics(...)) >= 2`.
3. Light ⇒ presupuestos `research_light_*`; Deep ⇒ `research_deep_*`; ambos clamped a los topes hard.

Tests: `tests/test_v4_research_depth.py` (9 tests: price→NONE, spec completa→NONE, performance→LIGHT, deep comparativa→DEEP aunque `wants_external=False`, clamps, backward compat).

## 7. Query planning por tópicos

`plan_queries(targets, message, max_queries, depth)`:

- Deep = **una query por tópico detectado**, respetando `max_queries` (orden de prioridad: especificaciones → benchmarks → reviews → precio → …).
- Light = escalera legacy (manufacturer > benchmark > review > general) acotada por `max_queries`.
- `expected_source_for_topic(topic)` ⇒ estrategia de fuente (specs→manufacturer, benchmarks→benchmark, reviews→review, precio→web).

## 8. Evaluación de RAG (harness hermético)

34 queries curadas (motherboards/GPU/CPU/SSD) contra 33 documentos con keywords **disjuntas por variante** — el dataset mete el test de *variant safety* en el propio ground-truth.

Métricas a K=3 sobre store hermético (embeddings local-hash, sin red):

| Métrica | GPU | CPU | SSD | Motherboard | **Global** |
|---|---|---|---|---|---|
| Precision@3 | 0.364 | 0.333 | 0.333 | 0.271 | **0.328** |
| Recall@3 | 1.0 | 1.0 | 1.0 | 0.75 | **0.941** |
| MRR | 1.0 | 0.917 | 0.929 | 0.688 | **0.892** |
| MAP | 1.0 | 0.917 | 0.929 | 0.688 | **0.892** |

Nota: P@K baja porque la relevancia por substring es estricta y el corpus es pequeño; la columna de calidad real (no mezclar SKUs) la cubre MRR/Recall y los tests de filtros (`tests/test_v4_variant_safety.py`, `tests/test_v4_rag_evaluation.py`).

## 9. Grounded answering (`resolve_claim` + prompt)

- `classify_evidence` (V3) etiqueta AGREEMENT / CONFLICT / VARIANT_MISMATCH / INSUFFICIENT_EVIDENCE.
- **Nuevo:** ante CONFLICT, `_source_weighted` puntúa cada item y si la fuente dominante supera por ≥0.05 el runner-up ⇒ AGREEMENT con nota "Conflicto resuelto…"; si el peso es parejo ⇒ CONFLICT con nota "no resuelto" y el asistente dice "no sé".
- `evidence_to_sections` renderiza por claim: `- consumo: apoya` + `· apoya Fuente(url)`/`· en contra Fuente(url)`; conflicto ⇒ `CONFLICTO`.
- Test suite: `tests/test_v4_evidence_grounding.py` (7 tests).

## 10. Multi-producto y variante-safe

- `_target_filters`: 1 id ⇒ `product_id` strict; N ids ⇒ `product_ids` (IN) → el compare con 2 productos ya no pierde el segundo (regresión V3 arreglada).
- `_variant_model_score(model, candidate)`: exacto 1.0, subset 0.5, superset 0.35, solapamiento proporcional ≤0.3, 0 si no comparten familia.
- Tests `tests/test_v4_variant_safety.py` (5 tests): no leak de Laptop en queries de escritorio, filtro por modelo scopes a 1 variante, compare conserva ambos product_id.

## 11. Follow-up y observabilidad

- `_expand_follow_up(message, state)` antepone el último turno de usuario ("¿y cuál consume más?" → "compara la RTX 5070 con la 5070 Ti ¿y cuál consume más?").
- `new_trace_id()` (16 hex, sha256 de `time_ns`); `AITrace.trace_id`; `ChatResponse.trace_id`; stages trazeados: intent, planner, research_plan, query_rewrite, rag, web_research, evidence.
- `tests/test_v4_followup.py` (7 tests).

## 12. Configuración (env)

```text
RESEARCH_ENABLED                (true)              # unchanged
MAX_RESEARCH_QUERIES            (5)                 # hard ceiling subida 3→5
MAX_RESEARCH_SOURCES            (6)                 # 4→6
MAX_RESEARCH_DOCUMENTS          (4)                 # 3→4
RESEARCH_LIGHT_MAX_QUERIES      (2)                 # presupuesto light
RESEARCH_LIGHT_MAX_SOURCES      (3)
RESEARCH_LIGHT_MAX_DOCUMENTS    (2)
RESEARCH_DEEP_MAX_QUERIES       (4)
RESEARCH_DEEP_MAX_SOURCES       (6)
RESEARCH_DEEP_MAX_DOCUMENTS     (3)
RESEARCH_CACHE_PRICE_TTL_SECONDS    (300)
RESEARCH_CACHE_SPEC_TTL_SECONDS     (86400)
RESEARCH_CACHE_BENCHMARK_TTL_SECONDS (3600)
RESEARCH_CACHE_REVIEW_TTL_SECONDS   (7200)
```

## 13. Tests

- `tests/test_v4_research_depth.py` — 9 (escalación NONE/LIGHT/DEEP + clamps + backward compat).
- `tests/test_v4_rag_evaluation.py` — 5 (métricas + dataset + eval por categoría + filtro variante).
- `tests/test_v4_variant_safety.py` — 5 (leak de variantes, multi-producto, filtros).
- `tests/test_v4_evidence_grounding.py` — 7 (conflictos resueltos/no resueltos, secciones, prompt).
- `tests/test_v4_followup.py` — 7 (rewrite, `_kb_query`, `trace_id`, AITrace).
- **Total**: 777 passed (703 baseline + 74 nuevos), 0 regresiones.

## 14. Evaluación y resultados

| Check | Resultado |
|---|---|
| Backend `pytest` | **777 passed** (703 baseline V3 + 74 nuevos) |
| V2/V3 suites | Verdes (planner, recommendation, orchestrator, web_research, integration, rag_*) |
| Frontend `eslint` | 0 errores |
| Frontend `tsc --noEmit` | OK |
| RAG Metrics (hermético, K=3) | MRR **0.892**, Recall@3 **0.941**, P@3 **0.328**, MAP **0.892** |
| Regresiones | Ninguna |

## 15. Riesgos, limitaciones y trabajo futuro

- **P@K bajo por substring-strict**: con corpus pequeño y keyword ground-truth, precision penaliza solapamientos; migrar a `relevant_ids` + juicio humano con pgvector real.
- **Embeddings local-hash**: suficiente para RAG hermético/testable, no para masas de docs; el `Provider` ya permite swap.
- **`detect_topics` es léxico**: tópicos fuera del `_TOPIC_MARKERS` caen en defaults; futura mejora: clasificador de tópicos.
- **Resolución de conflictos por peso determinista**: no consulta al usuario; futuro: pausa activa para que el usuario elija fuente.
- **Futuro**: persistir evidencia versionada (`research_evidence`), caché cross-request, revalidación periódica, evaluación continua del dataset en CI.