# Matriz de cumplimiento

Cada indicador de las tres pautas con su evidencia en el repositorio. **«Equipo»** marca lo que la pauta exige que
escriban o hagan ustedes (conclusiones, justificaciones, reflexiones y la defensa oral): no se puede delegar en la IA.

Rutas de la API con prefijo `/api/v1`. Páginas del frontend en `frontend/app/`.

## ISY0101 · Evaluación Parcial 3: Implementación de observabilidad

| Indicador | Peso | Evidencia | Estado |
|---|---|---|---|
| IE1 Métricas de precisión, consistencia y frecuencia de errores con datos variables | 15 % | `scripts/evaluar_ia.py` + `evals/escenarios.json` (40 casos en 13 categorías y 3 conjuntos; Gemini contra solo reglas; 3 repeticiones para medir consistencia). Resultados: `evals/resultados/eval-2026-11-22.md` y `eval-2026-11-23-correcciones.md`. Errores y respaldos por ejecución en `agent_runs.status`. | Listo |
| IE2 Latencia y uso de recursos | 10 % | `app/observability/tracer.py` mide la latencia de punta a punta, la de cada llamada a Gemini, herramienta y etapa, el CPU del proceso y los tokens de entrada y salida. Percentiles p50/p95/p99 en `app/observability/metrics.py`; tabla en los informes de evaluación. | Listo |
| IE3 Examina logs y eventos para encontrar fallas | 15 % | Log JSONL (`TRACE_LOG_FILE`) y tablas `agent_runs`/`agent_spans`. `scripts/analizar_trazas.py`: errores agrupados, anomalías (> 2 × p95), herramientas, precios sin respaldo, inyecciones, auditoría de privacidad → `evals/resultados/analisis-trazas-2026-11-22.md`. Hallazgos y correcciones en `docs/entrega/ISY0101-EP3.md` §2. | Listo |
| IE4 Dashboard visual | 10 % | `/observabilidad` (`frontend/app/observabilidad/page.tsx`): latencia p95 destacada, objetivos de servicio con alerta, ejecuciones y latencia en el tiempo, tablas por flujo, herramienta y etapa, y la cascada de cada ejecución. Exportable a Grafana: `GET /observability/prometheus`. Capturas en `docs/entrega/capturas/` (01–03: panel, cascada de 21,9 s y celular). | Listo |
| IE5 Informe técnico con recomendaciones justificadas | 10 % | Borrador: `docs/entrega/ISY0101-EP3.md` (máx. 5 páginas, con referencias APA). | Borrador; **equipo**: conclusiones y reflexiones |
| IE6 Patrones o anomalías y su vínculo con áreas críticas (presentación) | 10 % | Las 4 fallas encontradas (P05, P10, cola de latencia de Gemini, cuota 429) con sus trazas y la corrección de cada una: informe §2. | **Equipo** (exposición) |
| IE7 Mejoras de desempeño y escalabilidad (presentación) | 10 % | Informe §4: implementadas (límite de tiempo, reglas, aviso de presupuesto, métrica de desacuerdo) y propuestas (caché, una sola llamada, cola con reintentos, plan pagado). | **Equipo** (exposición) |
| IE8 Seguridad, ética y privacidad (presentación) | 10 % | `app/observability/guardrails.py` (inyección, precios con respaldo), `redaction.py` (enmascarado y seudónimo), `app/routers/privacy.py` (descargar y borrar datos), aviso de IA en `/perfil` y `/armar/asistente`, límites por minuto. | **Equipo** (exposición) |
| IE9 Lenguaje técnico y defensa con datos del dashboard | 10 % | Panel `/observabilidad` con datos reales de la evaluación. | **Equipo** |

## ISY0101 · Evaluación Final Transversal

Encargo 20 % (en pareja) · Defensa 80 % (individual). Pesos: encargo / defensa.

| Indicador | Peso | Evidencia | Estado |
|---|---|---|---|
| IE1 Prompts según el requerimiento | 2 % / 10 % | `app/pcbuilder/assistant.py` (`EXTRACT_SYSTEM` con salida JSON, `EXPLAIN_SYSTEM`, `REVIEW_SYSTEM`), `app/agent/graph.py` (`ACT_SYSTEM` con reglas de armado), `app/agent/planning.py` (planificación). Datos del usuario envueltos como datos, no como órdenes (`wrap_user_text`). | Listo |
| IE2 RAG con fuentes internas y externas | 2 % | Internas: 9 guías de compatibilidad (`app/pcbuilder/guides.py`) en la base de conocimiento con búsqueda híbrida (`app/ai/rag/knowledge_store.py`) y el catálogo con precios. Externa: `research_part_web` (`app/agent/pc_tools.py`) sobre `app/ai/research/web_research_service.py` (búsqueda, descarga con validación de URL, reordenamiento y validación de afirmaciones). | Listo |
| IE3 Arquitectura LLM + recuperación + control de contexto | 2 % | README §Arquitectura, `docs/agente/ARQUITECTURA.md`, `docs/entrega/ISY0101-EFT.md` §2.3. Control de contexto: ventana de 10 turnos, guías recortadas a 900 caracteres, datos en JSON. | Listo |
| IE4 Justificación de decisiones de diseño | 1 % / 10 % | `docs/entrega/ISY0101-EFT.md` §2.4 (motor de reglas frente al LLM, modelo flash-lite, SQLite/RDS, Gemini frente a otros). | Borrador; **equipo** |
| IE5 Agente con herramientas de consulta, escritura y razonamiento | 2 % / 10 % | `app/agent/tools.py` y `pc_tools.py`: 19 herramientas (consulta: catálogo, precios, piezas, guías, web; razonamiento: compatibilidad, recomendación, tendencia; escritura: alertas, listas, memoria, «Mis computadores»). Pruebas: `tests/agent/`. | Listo |
| IE6 Memoria y recuperación de contexto | 2 % / 5 % | Corto plazo: checkpointer de LangGraph (`agent_checkpoints.db`). Largo plazo: `app/agent/memory.py` (preferencias con embeddings). Necesidades conocidas del asistente (`KnownNeeds`). | Listo |
| IE7 Planificación y toma de decisiones | 2 % / 10 % | `app/agent/planning.py` (`heuristic_plan`, `pc_plan`, `diagnose` con replanificación por incompatibilidad o presupuesto) y nodos `plan`/`reflect` de `app/agent/graph.py`. El asistente decide entre preguntar, armar o bloquear, y desempata reglas contra Gemini (`resolve_disagreements`). | Listo |
| IE8 Documentación de la orquestación | 1 % / 5 % | `docs/agente/ARQUITECTURA.md`, `docs/entrega/ISY0101-EFT.md` §3.4 (diagrama de flujo). | Listo |
| IE9 Métricas de observabilidad | 1 % / 5 % | Igual que IE1 e IE2 de la EP3. | Listo |
| IE10 Análisis de registros | 2 % | Igual que IE3 de la EP3. | Listo |
| IE11 Seguridad y uso responsable | 2 % / 5 % | Igual que IE8 de la EP3. | Listo |
| IE12 Propuesta de mejoras | 1 % / 5 % | Informe EFT §4.2: el desempate reglas/Gemini ya está implementado y medido (`evals/resultados/eval-2026-11-23-desempate.md`); quedan 4 propuestas con su dato. | Borrador; **equipo**: priorizar |
| IE13–IE15 Fundamentación, exposición y respuestas | 15 % | Prototipo funcionando + panel. | **Equipo** (defensa individual) |
| Formato: PDF + código en Jupyter/Colab | — | `notebooks/EFT_ISY0101.ipynb` (clona, instala, prueba, evalúa y grafica). | Listo; **equipo**: exportar el informe a PDF |

## ITY1102 · Evaluación Parcial 3: despliegue

Detalle en [`EP3_ITY1102/README.md`](../../EP3_ITY1102/README.md) y en el informe `EP3_ITY1102/documento/EP3_Equipo1_Informe.pdf`.

| Indicador | Peso | Evidencia | Estado |
|---|---|---|---|
| IE1 Modelo de IA funcional | 10 % | `ml/`, `EP3_ITY1102/modelo/` (modelo, `metrics.json` con accuracy, precision, recall y F1). | Listo |
| IE2 Consumo de resultados en la aplicación | 10 % | API `/ml`, dashboard `/api/v1/ml/dashboard`; ahora también el armador y el asistente consumen Gemini y el motor de reglas. | Listo |
| IE3 Contexto y arquitectura (presentación) | 10 % | `EP3_ITY1102/diagramas/`. | **Equipo** |
| IE4 Plataforma AIaaS (SageMaker) | 5 % | Contenedor con contrato SageMaker (`/ping`, `/invocations`); `CreateModel` denegado por IAM del laboratorio (`EP3_ITY1102/evidencia/sagemaker-intento.txt`). | **Brecha**: pedir al docente un rol con permisos de SageMaker o aceptar la justificación |
| IE5 Infraestructura mínima y escalabilidad | 5 % | ALB + Auto Scaling 2→4 + RDS + CloudFront; Locust sin fallos (`EP3_ITY1102/pruebas/resultados/`, `evidencia/asg-escalado.txt`, `cloudwatch.txt`). | Listo; **volver a desplegar antes de la defensa** (se destruyó para no gastar créditos): [`DEPLOY_DEFENSA.md`](DEPLOY_DEFENSA.md) |
| IE7 APIs REST y comunicación entre servicios | 10 % | Swagger `/docs`, RabbitMQ + worker (`app/messaging/`), límite de tasa y TLS por CloudFront. | Listo |
| IE10 Testing y calidad | 10 % | Pruebas unitarias e integración (`tests/`), Locust, métricas p50/p95/p99 y tasa de error; ahora también la evaluación de la IA. | Listo |
| IE6, IE8, IE11 Justificaciones (presentación) | 15 % | Informe §Costos y decisiones. | **Equipo** |
| IE9 Demostración en vivo | 10 % | Requiere el sistema desplegado en AWS: `desplegar.sh` (API, modelo y frontend) + `verificar_defensa.sh`; guía en [`DEPLOY_DEFENSA.md`](DEPLOY_DEFENSA.md), con plan B local. | **Equipo**; redesplegar |
| IE12, IE13 Lenguaje técnico y respuestas | 15 % | — | **Equipo** |
