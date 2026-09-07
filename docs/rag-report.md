# RAG + Web Research + Mejoras IA — Reporte de implementación

Fecha: 2026-09-07 · Sin commit (brief). Base vigente: AI V2/V3 (validados, intactos).

## IMPLEMENTADO

Fases 0–26 del brief sobre la arquitectura V2/V3 existente (incremental y compatible hacia atrás):

- **Fase 0 (auditoría)**: V3 ya traía web research real (DuckDuckGo + `HTTPDocumentRetriever` + `WebResearchService`); `app/ai/evidence.py` sin `TECHNICAL_DOCUMENT`; SSRF preexistente en `app/ingestion/discovery/security.py`; `google.genai.embed_content` compatible; head alembic previo `20260903_02`.
- **Persistencia de conocimiento (Fases 1–3)**: `app/models/knowledge.py` (`KnowledgeSource`, `KnowledgeDocument`, `KnowledgeChunk`) + migración `20260907_01_knowledge_base.py` (head actual).
- **Embeddings intercambiables (Fase 7)**: `app/ai/rag/embedding.py` (Protocol `EmbeddingProvider`: `LocalHash`, `Gemini`, `OpenAI`, `Cached` + `cosine_similarity`) y `app/ai/rag/factory.py`. **No acoplado a Gemini**: `EMBEDDING_PROVIDER=auto|gemini|openai|local`, default **`local`** (offline, determinístico). Gemini usa `gemini-embedding-001`.
- **Retrieval (Fases 8–10)**: `app/ai/rag/retrievers.py` (`KeywordRetriever`, `VectorRetriever`, `HybridRetriever` — embeddings JSON, sin pgvector) y `app/ai/rag/reranker.py` (pesos 0.35/0.20/0.20/0.15/0.10 vía `RAG_RERANK_WEIGHTS`).
- **KnowledgeStore (Fases 4–6/23)**: `app/ai/rag/knowledge_store.py` — `upsert_document` (dedupe url/hash), `ingest_research_report` (idempotente), `search`, `search_research`, `evidence_for`, `from_settings`; `TTLCache` en `app/ai/rag/cache.py`.
- **Orquestador KB-first (Fases 23)**: `_kb_query` (mensaje + identidad brand/model), `search_research` con filtros por `product_id`/brand/model → si hay evidencia, no dispara web; si no, usa `WebResearchService`.
- **WebResearchService (Fases 23/26)**: caché TTL por query, SSRF (`_url_allowed`), `_persist` (persiste evidencia en KB para reuso), `from_settings(db=...)`.
- **Planner (Fases 13/14)**: `ResearchBudget` + `Planner.research_plan` con perfiles `RESEARCH_CATALOG_ONLY` / `RESEARCH_STANDARD` / `RESEARCH_DEEP`.
- **Recommendation (Fases 11/15/17)**: `confidence`, `evidence`, `unknowns` (+ en `as_dict`); cobertura ponderada de specs con clamp.
- **Contexto (Fase 18/22)**: `app/ai/context_builder.py` (`AIContextBuilder` con `token_limit`/`reserved_for_answer`, truncación por caracteres ~3.5 char/token, incl. sección única sobredimensionada); el orquestador lo usa con `rag_token_budget`.
- **Observabilidad (Fase 20)**: `app/ai/observability.py` (`AITrace`, `trace_step`, stages plan/rag/web_research/research_profile).
- **Contrato (Fase 21)**: `ChatResponse` suma `recommendation`, `evidence`, `trace` (aditivos, no rompe V2/V3).

## RAG

- Recuperación híbrida (keyword SQL ILIKE + vector cosine + reranker por peso) sobre las tablas `knowledge_*`, **100% offline** con provider `local`.
- **Fix de recall por identidad**: el retriever clave ahora matchea también `title/brand/model` del documento (no solo content), para que queries tipo `xiaomi` o `x6` encuentren documentos que solo mencionan el modelo en metadatos. Sin esto la búsqueda KB-first fallaba y caía a web con KB poblada.
- Deduplicación por URL y `content_hash`; evidencia persistida por web research se reutiliza KB-first.
- Compatibilidad embeddings: mismo pipeline con Gemini/OpenAI/local según env; pgvector queda como optimización futura opcional (`EMBEDDING_USE_PGVECTOR`) sin cambiar interfaces.

## WEB RESEARCH

- Cadena: `Planner` → queries DDG → selección resultados → `HTTPDocumentRetriever` por URL → veredictos → contexto → persistencia en KB.
- Caché en memoria (`TTLCache`, TTL `research_cache_ttl_seconds`).
- SSRF: `_url_allowed` (vía `validate_url` best-effort de `app.ingestion.discovery.security`) bloquea loopback/privadas antes del fetch; el LLM no controla requests.
- Límites de presupuesto: `max_queries`/`max_sources`/`max_documents` desde config.

## EVIDENCE

- `app/ai/evidence.py` (`Evidence`, `EvidenceKind`, `KnowledgeSourceType`) sin cambios rompedores.
- `KnowledgeStore.search_research` adapta chunks → `ResearchReport` con contexto `[Evidencia recuperada de la knowledge base (RAG)]`.
- Evidencia ligada a `product_id`/brand/model/variant; `unknowns` mapea veredictos `insufficient_evidence`; `confidence` por prioridad de fuente (catalog 60 > manufacturer 50 > benchmark 40 > review 30 > technical 25 > web 20 > ai_research 15).
- No-hallucination: sin evidencia en KB ni de web research, el engine no inventa datos (fluye a `unknowns`/`need_clarification`).

## AI

- Mejoras no rompedoras sobre V2/V3: planner con presupuesto de investigación, recomendación con confianza/evidencia/desconocidos, builder de contexto con presupuesto de tokens, traces en la respuesta.
- Integración con `LLMProvider` existente (Spark de herramientas sin cambios: `request_tools`/`generate_final`).

## FRONTEND

- `pnpm tsc --noEmit`: OK (sin errores).
- `pnpm lint`: 0 errores (8 warnings preexistentes, no introducidos).
- `pnpm build`: OK (9 rutas, build completo).
- Contrato `ChatResponse` aditivo: los campos nuevos son opcionales, la UI actual no requiere cambios.

## MIGRATIONS

- `20260907_01_knowledge_base` (head): crea `knowledge_sources`, `knowledge_documents`, `knowledge_chunks` (metadata JSON, embeddings JSON; sin pgvector).
- Validado sobre la base real (Supabase Postgres de desarrollo) con datos legacy:
  - `alembic upgrade head`: `20260903_01 → 20260903_02` (spec applicability, aditivo) → `20260907_01_knowledge_base`.
  - `alembic current`: `20260907_01_knowledge_base (head)`.
  - Tablas `knowledge_*` confirmadas en el inspector.

## TESTS

- Baseline revalidado: **703 passed** antes de añadir tests nuevos.
- Suite completa actual: **744 passed** (V2/V3 + RAG, sin red ni API keys).
- Nuevos:
  - `tests/test_rag_embedding.py` (6)
  - `tests/test_rag_knowledge_store.py` (11; fixture aísla tablas `knowledge_*`)
  - `tests/test_rag_retrievers_reranker.py` (9)
  - `tests/test_rag_context_builder.py` (5)
  - `tests/test_rag_planner_and_recommendation.py` (6)
  - `tests/test_rag_orchestrator_integration.py` (4; KB-first > web, caché web, SSRF, persistencia)
- `reset_database` ampliado a `knowledge_*` en `test_ai_orchestrator.py`, `test_ai_chat.py`, `test_research_integration.py`.

## PENDIENTE

- ~~`_wants_external_information` detectado pero no escalado al perfil `RESEARCH_DEEP`~~ → **RESUELTO en V4**: `decide_research` escala por profundidad (`NONE/LIGHT/DEEP`) con presupuestos por nivel; deep se alcanza por términos léxicos o ≥2 tópicos detectados.
- Embeddings con red (Gemini/OpenAI reales) sin prueba de integración; la suite corre offline con `LocalHash`.
- pgvector / `tsvector` como optimización post-particionada, opcional.
- ~~Frontend podría mostrar `evidence`/`trace` por mensaje~~ → **RESUELTO en V4**: `EvidencePanel` (badges de `claim_type` + confianza + fuente) y bloque "¿Por qué esta recomendación?" (V4 fields).

## AI V4 (delta sobre lo anterior)

- **Escalación de research**: `app/ai/planner.py` — `ResearchDepth` (NONE/LIGHT/DEEP), `ResearchDecision`, `decide_research`; presupuestos por nivel en env (`RESEARCH_LIGHT_MAX_*` / `RESEARCH_DEEP_MAX_*`), topes hard subidos.
- **Query planning por tópicos**: `app/ai/research/query_planning.py` — `detect_topics`, `plan_queries(depth)` (deep = 1 query por tópico; light = escalera legacy), `source_strategy`/`expected_source_for_topic`; `source_discovery.build_queries` quedó como shim.
- **Cache freshness-tipada**: `_cache_ttl_for` en `web_research_service.py` (precio 300s, specs 86400s, benchmark 3600s, review 7200s).
- **Multi-producto + variante-safe**: filtro `product_ids` (IN) en `retrievers.py`/`knowledge_store.py` (fix compare que perdía el 2º producto) + `_variant_model_score` (exacto > subset > superset > solapamiento).
- **Eval RAG hermético**: `app/ai/rag/evaluation.py` (P@K/R@K/MRR/MAP) + `eval_dataset.py` (34 queries / 33 docs con keywords disjuntas por variante). Resultados K=3: MRR 0.892, Recall@3 0.941, P@3 0.328, MAP 0.892 (embedding local-hash, sin red).
- **Grounded answering**: `ClaimType`/`Claim` en `evidence.py`; `resolve_claim` (resolución de conflictos por `0.5*priority + 0.3*confidence + 0.2*freshness`, margen 0.05; irresoluble ⇒ CONFLICT honesto); `evidence_to_sections`/`build_grounded_prompt` en `context_builder.py`.
- **Recomendación V4**: `user_need`, `hard_constraints`, `soft_preferences`, `criteria_scores`, `final_reason`, `basis` (+ `_v4_explanation`).
- **Follow-up + observabilidad**: `_expand_follow_up` (rewrite de turnos), `_kb_query` con tópicos, `new_trace_id`, `AITrace.trace_id`, `ChatResponse.trace_id`.
- **Frontend**: `components/chat/evidence-panel.tsx`, integrado en `chat-interface.tsx` (types `EvidenceEntry`/`RecommendationDetail` en `lib/api/chat.ts`); `eslint` 0 errores, `tsc --noEmit` OK.

## TESTS (V4)

- Suite completa actual: **777 passed** (703 baseline + 74 nuevos), sin red ni API keys, 0 regresiones.
- Nuevos: `test_v4_research_depth.py` (9), `test_v4_rag_evaluation.py` (5), `test_v4_variant_safety.py` (5), `test_v4_evidence_grounding.py` (7), `test_v4_followup.py` (7).
- Detalle en `docs/ai-v4.md`.