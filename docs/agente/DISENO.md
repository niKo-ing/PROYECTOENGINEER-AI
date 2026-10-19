# Bocetos de diseño del agente

Contratos y esquemas que se definieron antes de programar cada pieza. Sirven de referencia para leer el código (`app/agent/`).

## 1. Estado del grafo (`AgentState`)

```text
messages      historial del hilo (lo persiste el checkpointer)
turn          n.º de turno dentro del hilo (filtra la traza del turno actual)
goal          último mensaje del usuario
budget_clp    presupuesto extraído del texto, o null
memories      recuerdos recuperados ("[kind] contenido")
plan          [{id, action, priority 1-3, status pendiente|hecho}]
plan_source   "llm" | "heuristic"
adaptation    texto de la adaptación vigente tras un replan
replan_reason motivo pendiente de atender (lo consume el nodo plan)
handled       motivos ya atendidos en este pedido (anti-bucle)
replans       replanificaciones usadas (tope 2)
steps         pasos del nodo act (tope 10)
wrote         escrituras que sí se hicieron
trace         eventos {turn, node, ...}; es aditivo
```

Se reinicia en `recall` al comenzar cada turno, salvo `messages` y `trace`.

## 2. Contrato del plan (lo que se le pide al LLM)

```json
{"steps": [
  {"action": "Buscar candidatos con tope de $400.000 (search_products)", "priority": 1},
  {"action": "Juzgar si es buen momento con analyze_price_trend", "priority": 2},
  {"action": "Guardar la lista (save_shopping_list)", "priority": 3}
]}
```

Reglas de `parse_plan`: acepta JSON dentro de un bloque de código, máximo 8 pasos, prioridad fuera de 1–3 pasa a 2, orden estable por prioridad. Cualquier otra cosa → plan por reglas.

## 3. Eventos de la traza

| `node` | Campos |
|---|---|
| `recall` | `memories[{content, relevance}]`, `budget_clp` |
| `plan` | `source`, `replan` (motivo o null), `plan[]` |
| `act` | `step`, `tool_calls[{tool, args}]` |
| `reflect` | `observed[]`, `diagnosis{reason, detail}`, `decision` (`replanificar` / `continuar_sin_replan`) |
| `give_up` | `max_steps` |
| `remember` | `stored[]` |

## 4. Contrato de la API

`POST /api/v1/agent/run` (autenticado)

```json
// pedido
{"message": "Quiero un notebook Lenovo, presupuesto $400.000. Arma una lista.", "thread_id": "demo-1"}
// respuesta
{"thread_id": "demo-1", "answer": "...", "plan": [...], "plan_source": "llm",
 "tools_used": ["search_products", "..."], "wrote": ["save_shopping_list"],
 "replans": 0, "memories_used": [], "steps": 5, "trace": [...]}
```

Errores: `422` entrada inválida (mensaje de 2 a 1200 caracteres; `thread_id` solo `[A-Za-z0-9_-]`, máx. 64), `401/403` sin sesión, `429` cuota del modelo agotada, `503` modelo sin configurar o caído.

`GET /api/v1/agent/memories` lista lo que el agente recuerda del usuario autenticado.

## 5. Esqueleto del prompt de acción

```text
Eres el AGENTE DE AHORRO de TodoBarato ... Reglas: precios en CLP; solo datos de las herramientas;
sigue el plan; antes de recomendar comprar revisa oferta y tendencia; escribe solo si se pidió;
respeta el presupuesto; cierra con respuesta breve.

Objetivo actual: ...
Presupuesto: ...
Memoria de largo plazo relevante: ...
Resumen de la conversación anterior: ...        (solo si se recortó la ventana)
Plan vigente: 1. [hecho] (prioridad 1) ...
CAMBIO DE CONDICIONES (ya replanificado): ...   (solo tras un replan)
```

## 6. Esquema de datos nuevo

```text
agent_memories(id, user_id, kind, content, content_hash, embedding JSON, embedding_provider,
               importance 1-5, created_at, last_used_at)
price_alerts(id, user_id, product_id→products, target_price_clp, price_at_creation_clp,
             active, triggered_at, triggered_price_clp, created_at)
shopping_lists(id, user_id, name, items JSON, total_clp, budget_clp, notes, created_at)
```

Migración: `alembic/versions/20260920_01_agent_tables.py` (aditiva e idempotente).

## 7. Veredicto de tendencia de precios (`analyze_price_trend`)

```text
si precio_actual <= mínimo_histórico * 1,03  → buen_momento
si precio_actual >= promedio_histórico * 1,05 → esperar
si no                                          → precio_normal
con menos de 3 observaciones                   → sin_historial_suficiente
```
