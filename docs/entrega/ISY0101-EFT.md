# TodoBarato AI: agente con Gemini para armar computadores compatibles

**ISY0101 · Ingeniería de Soluciones con IA · Evaluación Final Transversal**
Equipo: [NOMBRE 1] y [NOMBRE 2] · Docente: [NOMBRE] · Fecha: [FECHA]
Repositorio: <https://github.com/niKo-ing/PROYECTOENGINEER-AI> · Código en Colab: `notebooks/EFT_ISY0101.ipynb`

> **Borrador.** Lo técnico y los datos salen del repositorio y de `evals/resultados/`. Las secciones **[EQUIPO]** las
> exige la pauta sin apoyo de IA: justificaciones propias, conclusiones y reflexiones individuales. La pauta pide el
> informe en PDF y el código en Jupyter/Colab.

## 1. Análisis del caso organizacional (IE4, IE8)

**Contexto.** En Chile, armar o mejorar un computador obliga a cruzar precios de varias tiendas y reglas técnicas que el
comprador no domina: socket y chipset, DDR4 o DDR5, largo de la tarjeta frente al gabinete, altura del disipador y
watts de la fuente. Un error se descubre al armar, cuando ya se compró. TodoBarato reúne el catálogo con precios de
tiendas chilenas; el caso es agregar un asesor que arme y revise equipos sin equivocarse.

**Requerimientos.**

* RF1: entender pedidos en lenguaje natural («700 lucas pa jugar valorant»).
* RF2: preguntar lo que falta.
* RF3: armar un PC compatible dentro del presupuesto.
* RF4: explicar con fuentes.
* RF5: guardar y revisar los equipos del usuario.
* RNF: no inventar compatibilidades ni precios, responder en segundos, proteger los datos personales y medir todo.

**Desafíos.** Los LLM alucinan medidas y precios, la jerga y los montos en palabras confunden a un extractor por reglas,
la cuota del plan gratuito de Gemini es limitada y la Ley 21.719 eleva las exigencias sobre datos personales.

[EQUIPO: amplíen con su lectura del caso y de los usuarios objetivo.]

## 2. Diseño de la solución basada en LLM y RAG

### 2.1 Formulación de prompts (IE1)

| Prompt | Archivo | Técnica |
|---|---|---|
| `EXTRACT_SYSTEM` | `app/pcbuilder/assistant.py` | Salida JSON con esquema fijo (uso, presupuesto, marcas, wifi, tamaño, pregunta), lista cerrada de usos y regla «no inventes un presupuesto» |
| `EXPLAIN_SYSTEM` | ídem | Solo datos del JSON y de las guías; precios copiados tal cual; citar la guía entre corchetes; avisar si se pasa del presupuesto; 90–160 palabras |
| `REVIEW_SYSTEM` | ídem | Revisión de un PC guardado en tres partes: compatibilidad, para qué alcanza, mejor mejora |
| `ACT_SYSTEM` | `app/agent/graph.py` | Reglas de uso de herramientas: no afirmar compatibilidad sin `check_pc_compatibility`, preguntar si falta uso o presupuesto, guardar solo si se pide |

El texto del usuario va envuelto como **datos** (`wrap_user_text`) para que no se lea como instrucción. Los prompts se
ajustaron con la evaluación: por ejemplo, la regla de avisar el exceso de presupuesto se agregó tras el caso P05, y desde
entonces Gemini lo dijo en el 100 % de los casos (sección 4.2).

### 2.2 Pipeline RAG con fuentes internas y externas (IE2)

```mermaid
flowchart LR
  P[Pedido] --> Q[Consulta: uso + problemas del reporte]
  Q --> I[(Base de conocimiento<br/>9 guías internas)]
  Q --> C[(Catálogo con precios<br/>de tiendas chilenas)]
  Q -. dato que falta .-> W[Búsqueda web<br/>research_part_web]
  I --> H[Búsqueda híbrida<br/>palabras clave + embeddings]
  W --> V[Validar URL, descargar,<br/>reordenar y validar afirmaciones]
  H --> X[Contexto JSON]
  C --> X
  V --> X
  X --> G[Gemini explica<br/>citando la fuente]
  G --> K{¿Precios con respaldo?}
  K -- no --> R[Explicación por reglas]
  K -- sí --> U[Respuesta]
```

* **Fuente interna:** 9 guías escritas por el equipo (socket y chipset, memoria, fuente, gabinete, refrigeración, tarjeta
  gráfica, almacenamiento, presupuesto por uso y cómo mejorar un PC). Se indexan en `knowledge_documents` con búsqueda
  híbrida (`app/ai/rag/knowledge_store.py`). Las guías ligadas a cada problema del reporte (p. ej. `socket` → «Socket y
  chipset») se anteponen a las encontradas por similitud.
* **Catálogo:** piezas con especificaciones y ofertas vigentes (`StoreOffer`), con su historial de precios.
* **Fuente externa:** `research_part_web` usa `WebResearchService`. Planifica consultas, busca, descarga con validación
  contra SSRF, reordena, trocea y valida afirmaciones. Tiene presupuesto de consultas, documentos y caracteres, y
  devuelve las URL para citarlas.

### 2.3 Arquitectura y control de contexto (IE3)

```mermaid
flowchart TB
  UI[Next.js: /armar, /armar/asistente, /mis-pc, /guias, /chat, /observabilidad] --> API[FastAPI /api/v1]
  API --> AS[Asistente de armado]
  API --> AG[Agente LangGraph]
  AS --> LLM[Gemini 3.5 flash-lite]
  AG --> LLM
  AS --> MOT[Motor de compatibilidad<br/>y recomendador]
  AG --> TOOLS[19 herramientas]
  TOOLS --> MOT
  TOOLS --> RAG[RAG: guías + web]
  TOOLS --> DB[(Catálogo, Mis computadores,<br/>alertas, listas, memoria)]
  AS --> OBS[RunTracer → agent_runs / agent_spans / JSONL]
  AG --> OBS
  OBS --> PANEL[Panel /observabilidad + Prometheus]
```

**Control de contexto:**

* ventana de 24 mensajes en el agente y de 10 turnos en el asistente;
* fragmentos de guías recortados a 900 caracteres;
* datos entregados al modelo como JSON con solo los campos necesarios (piezas, precios, motivos, advertencias, consumo);
* las 4 memorias más relevantes por consulta;
* tope de 10 pasos por tarea.

### 2.4 Justificación de decisiones (IE4)

| Decisión | Alternativa | Motivo (con dato) |
|---|---|---|
| Compatibilidad por reglas, no por el LLM | Que Gemini decida | Es verificable y determinista: 100 % de armados compatibles en todas las corridas |
| Gemini para entender y explicar | Solo reglas | Las reglas aciertan 40 % con casos nuevos; Gemini, 80–90 % |
| `gemini-3.5-flash-lite` | Modelos más grandes | p50 de 2,7 s y ~1.800 tokens por consulta; la tarea es extraer y redactar, no razonar en profundidad |
| Descartar explicaciones con precios sin respaldo | Confiar en el prompt | El prompt no garantiza; la regla en código sí (0 precios sin respaldo) |
| Respaldo por reglas si Gemini falla | Mostrar un error | Con cuota agotada (429), el usuario igual recibe su armado |
| SQLite local / PostgreSQL (RDS) en AWS | Supabase | El proyecto de Supabase se perdió; las cuentas propias quitan esa dependencia |

[EQUIPO: justifiquen con sus palabras por qué estas decisiones responden al caso y qué limitaciones aceptan.]

## 3. Desarrollo del agente funcional

### 3.1 Herramientas de consulta, escritura y razonamiento (IE5)

| Tipo | Herramientas |
|---|---|
| Consulta | `search_products`, `get_product_offers`, `get_price_history`, `compare_products`, `get_user_profile`, `recall_memory`, `check_price_alerts`, `search_pc_parts`, `list_my_pcs`, `search_compatibility_guide`, `research_part_web` |
| Razonamiento | `check_pc_compatibility` (motor de reglas), `recommend_pc_build` (búsqueda con presupuesto), `suggest_pc_upgrade` (mejor mejora por peso invertido), `analyze_price_trend` |
| Escritura | `create_price_alert`, `save_shopping_list`, `remember_preference`, `save_pc_build` |

Cada herramienta valida su entrada con Pydantic y devuelve JSON. Ante un error, lanza `ToolException` para que el modelo
corrija sin que se caiga el flujo. Las escrituras se permiten solo si el pedido lo dice; es una regla en código, no solo
en el prompt. En la evaluación hubo 100 % de escrituras correctas.

![Figura. Asistente de armado: pedido en lenguaje coloquial, armado compatible y explicación con las guías citadas](capturas/09-asistente.png)

*Figura.* «Tengo 700 lucas pa jugar Valorant, ojalá AMD»: el asistente entiende uso y presupuesto, arma un PC de
$685.000 que el motor de reglas declara compatible, lo explica citando tres guías (RAG) y permite guardarlo en «Mis
computadores» (herramienta de escritura) o ajustarlo en el armador. Más capturas (armador, Mis computadores, guías,
perfil y panel) en `docs/entrega/capturas/`.

### 3.2 Memoria y recuperación de contexto (IE6)

* **Corto plazo:** el checkpointer de LangGraph (SQLite local, Postgres en AWS) guarda el hilo; el usuario retoma la
  conversación con su `thread_id`.
* **Largo plazo:** `LongTermMemory` guarda preferencias declaradas («prefiero AMD») con embeddings. Al inicio de cada
  turno, el nodo `recall` recupera las 4 más parecidas, y una red de seguridad las guarda aunque el modelo no llame a
  `remember_preference`.
* **Asistente:** las necesidades ya conocidas (`KnownNeeds`) viajan con cada turno; lo último que dijo el usuario manda
  (caso «cambio de opinión»: 100 %).
* **Perfil:** «Mis computadores» persiste los equipos para revisarlos y mejorarlos después.

### 3.3 Planificación y toma de decisiones (IE7)

* **El asistente decide entre tres salidas:** preguntar (falta uso o presupuesto, o el presupuesto es menor a $250.000),
  armar o bloquear (inyección grave).
* **El agente planifica:** Gemini propone un plan; si falla, `heuristic_plan` arma uno por reglas, con `pc_plan` para
  pedidos de armado.
* **El agente reflexiona después de cada herramienta:** `diagnose` detecta un armado incompatible o sobre el
  presupuesto y replanifica, como máximo 2 veces, con una pista concreta (p. ej. «busque un reemplazo para la pieza que
  falla»). Si se acaban los 10 pasos, cierra con lo logrado.

### 3.4 Orquestación y flujo automatizado (IE8)

```mermaid
flowchart LR
  S((Inicio)) --> R[recall<br/>memorias]
  R --> P[plan]
  P --> A[act<br/>Gemini + herramientas]
  A -- llamadas --> T[tools]
  T --> F[reflect<br/>diagnose]
  F -- replanificar --> P
  F -- seguir --> A
  A -- respuesta --> M[remember]
  A -- tope de pasos --> G[give_up]
  G --> M
  M --> E((Fin))
```

Ejemplo real de la evaluación (caso G01, 2 de 2 correctos): con «¿Es compatible el Ryzen 5 7600 con la MSI B550M
PRO-VDH WIFI?», el agente:

1. busca las dos piezas (`search_pc_parts` dos veces);
2. llama a `check_pc_compatibility`, que reporta el socket distinto;
3. el nodo `reflect` diagnostica «incompatible» y replanifica una vez;
4. responde que no son compatibles (AM5 y DDR5 frente a AM4 y DDR4) y ofrece buscar una placa AM5 (B650).

Fueron 5 llamadas a Gemini y unos 5,7 s.

Detalle: `docs/agente/ARQUITECTURA.md`.

## 4. Observabilidad, trazabilidad y seguridad

### 4.1 Métricas: precisión, latencia y consistencia (IE9)

Son 40 escenarios variables en 13 categorías, con 3 repeticiones, comparando Gemini contra el modo solo reglas. Detalle
y metodología: `docs/entrega/ISY0101-EP3.md` §2.

| Métrica (23-11, tras las correcciones) | Gemini | Solo reglas |
|---|---|---|
| Acierto, conjunto de prueba / prueba 2 (ciego) | 90 % / 90 % | 40 % / 70 % |
| Exactitud del estado | 100 % | 65 % |
| Consistencia entre repeticiones | 100 % | — |
| Armados compatibles / precios con respaldo | 100 % / 100 % | 100 % / 100 % |
| Latencia p50 / p95 | 2,7 s / 4,9 s | < 1 ms / 50 ms |
| Tokens por consulta | 1.881 | 0 |

Agente (22-11): 87,5 % de éxito, 100 % de herramientas correctas, p95 de 8,4 s, 3,5 llamadas y 8.707 tokens por
ejecución.

### 4.2 Análisis de registros y propuesta de mejoras (IE10, IE12)

Las trazas (235 ejecuciones) mostraron siete hallazgos; cada uno tiene su evidencia y su corrección en
`docs/entrega/ISY0101-EP3.md` §3. Los principales:

* «videollamadas» se leía como edición y «4K» como $4.000: se corrigió y P05 y P10 pasaron a acertar el presupuesto 3
  de 3;
* más del 98 % de la latencia es espera a Gemini, con colas de hasta 21,9 s: se fijó un límite de 10 s con respaldo;
* la cuota gratuita produjo 3 respuestas 429;
* en 6 de 7 desacuerdos entre reglas y Gemini, Gemini tenía razón.

**Mejoras propuestas con su dato:**

1. medir la tasa de respaldo con el límite de 10 s;
2. cola con reintentos y plan pagado para la cuota;
3. dar prioridad a Gemini en un desacuerdo, validado con un conjunto ciego nuevo;
4. ahorrar la llamada de extracción cuando el pedido trae uso y monto en cifras;
5. caché de explicaciones por armado.

[EQUIPO: prioricen estas mejoras y justifiquen el orden.]

### 4.3 Seguridad y uso responsable (IE11)

* **Inyección de instrucciones:** las graves se bloquean sin llamar al modelo; las leves se tratan como datos (OWASP
  LLM01).
* **Alucinaciones:** compatibilidad por reglas, explicación descartada si cita precios sin respaldo, fuentes citadas.
* **Privacidad (Ley 19.628 y Ley 21.719):**
  * seudónimo con sal en las trazas;
  * correos, RUT, teléfonos y tarjetas enmascarados (auditoría: 0 en los registros);
  * descarga y borrado total en `/perfil`.
* **Cuentas y abuso:**
  * contraseñas con scrypt;
  * tokens firmados;
  * límite de consultas por minuto;
  * panel de observabilidad solo para administradores.
* **Transparencia:** aviso de que Gemini procesa el texto, de que los precios son referenciales y de qué se registra.

[EQUIPO: reflexión ética sobre riesgos y dilemas: sesgo hacia ciertas tiendas, dependencia de un proveedor, qué pasa si
el usuario confía ciegamente.]

## 5. Conclusiones **[EQUIPO]**

[Sin IA.]

### Reflexión individual: [NOMBRE 1] **[sin IA]**

### Reflexión individual: [NOMBRE 2] **[sin IA]**

## Declaración de uso de IA

[Completen con lo que realmente usaron: herramienta, para qué y cómo lo validaron. Gemini es parte de la solución.]

## Referencias

> Verifiquen cada referencia antes de entregar.

Google. (s. f.). *Gemini API documentation*. Recuperado el [fecha] de <https://ai.google.dev/gemini-api/docs>

LangChain. (s. f.). *LangGraph documentation*. Recuperado el [fecha] de <https://langchain-ai.github.io/langgraph/>

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel,
T., Riedel, S., & Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *Advances in
Neural Information Processing Systems, 33*, 9459–9474.

Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2023). ReAct: Synergizing reasoning and acting
in language models. *International Conference on Learning Representations*.

Ley N.° 19.628. Sobre protección de la vida privada. (1999). Biblioteca del Congreso Nacional de Chile.

Ley N.° 21.719. Regula la protección y el tratamiento de los datos personales y crea la Agencia de Protección de Datos
Personales. (2024). Biblioteca del Congreso Nacional de Chile.

OWASP Foundation. (2025). *OWASP Top 10 for large language model applications*. <https://genai.owasp.org/llm-top-10/>
