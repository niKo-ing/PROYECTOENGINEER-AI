# TodoBarato AI para 10.000 usuarios en servidor propio

Esta es la parte 2 del trabajo. La parte 1 (`INFORME_SERVIDOR_IA.md`) calcula cuánto cuesta el tarro con GPU. Esta parte explica **qué hay que mejorar en la página para que aguante 10.000 usuarios** corriendo en ese servidor propio, **cómo demostrarlo** y **cómo mantenerla funcionando**.

Números calculados con `costos_servidor_propio.py` · precios del 08-11-2026.

> **Estado:** los pasos 1 a 7 y el 9 de la sección 4.2 ya están hechos en la rama `mejoras-10000-usuarios`; falta el 8 (streaming). Detalle y mediciones en `OPTIMIZACIONES.md`.

---

## 0. Qué hay que entregar (lo que entendimos)

El profe lo explicó en clases y no dejó nada escrito, así que esta es nuestra interpretación:

1. **Infraestructura propia:** un servidor físico con GPU donde corran la IA y todas las páginas, con su costo de compra y de mantención (parte 1).
2. **Limitaciones:** qué no puede hacer ese servidor y cómo lo manejamos (sección 2).
3. **Mejorar la página** para que aguante unos **10.000 usuarios** (secciones 3 y 4).
4. **Demostrar que aguanta** con pruebas de carga y de falla (sección 5).
5. **Mantenerla funcionando:** respaldos, monitoreo y actualizaciones (sección 6).

**Mensaje para confirmar con el profe** (para copiar y pegar):

> Profe, para la próxima entrega entendimos que tenemos que: (1) dimensionar y costear un servidor propio con GPU para la IA y la página, (2) explicar sus limitaciones, (3) mejorar la app para que soporte ~10.000 usuarios y (4) demostrarlo con pruebas de carga. ¿Los 10.000 usuarios son al día o conectados al mismo tiempo? ¿Falta algo más?

## 1. Qué significa "aguantar 10.000 usuarios"

Hay dos formas de leerlo, y el resultado cambia muchísimo:

| Escenario | Catálogo en hora pico | Respuestas de IA a la vez | GPU necesarias | ¿Alcanza un tarro? |
|---|---|---|---|---|
| EP2 actual (1.200 sesiones/día) | 2 req/s | 3 | 1 | Sí, y sobra |
| **10.000 usuarios activos al día** | **17 req/s** | **18** | **1** (usamos 2 para tener respaldo) | **Sí** |
| 10.000 usuarios **simultáneos** | 1.500 req/s | 1.000 | ~34 | No: costaría ~$360 millones |

**Usamos la meta de 10.000 usuarios activos al día**, que es lo normal en una página de este tipo. Con 10.000 activos al día, en la hora pico hay unas 1.000 personas navegando y unas 18 esperando una respuesta de la IA.

Si el profe quiere 10.000 **simultáneos**, la conclusión cambia: con un servidor propio no es viable y conviene la API (Gemini), que escala sola.

Supuestos del cálculo: 8 páginas por visita, 3 llamadas a la API por página, 1 consulta de IA por usuario al día, 3 llamadas al LLM por consulta y una hora pico 6 veces mayor que el promedio.

## 2. Limitaciones del servidor propio y cómo las manejamos

| Limitación | Qué pasa | Cómo la manejamos |
|---|---|---|
| **Es una sola máquina** | Si falla, la página se cae | Dos tarros iguales; si uno muere, el otro atiende todo (opción C) |
| **La GPU es finita** | Con muchos chats a la vez, las respuestas se ponen lentas | Cola de espera, límite de consultas por usuario y Gemini como respaldo |
| **No escala sola** | AWS agregaba réplicas automáticamente; acá hay que comprar otra máquina | Caché fuerte para que la mayoría de las visitas no lleguen al servidor |
| **Cortes de luz** | Se apaga todo | UPS de 15-20 minutos y apagado ordenado; la base se respalda fuera del local |
| **Internet de la casa u oficina** | Cortes del enlace, sin IP fija y expuesto a ataques | Cloudflare delante (HTTPS, caché, protección DDoS) + fibra con IP fija + 4G de respaldo |
| **Modelo abierto vs. Gemini** | Un modelo de 8B a 30B responde algo peor | El RAG le entrega los datos del catálogo; las preguntas difíciles pueden ir a Gemini |
| **Mantención manual** | Nadie aplica parches ni revisa respaldos por nosotros | Técnico de 16 h/mes, actualizaciones automáticas y alertas |

## 3. Problemas que encontramos en el código

Revisamos el repo buscando lo que fallaría con 10.000 usuarios:

| # | Problema | Dónde | Qué pasa con 10.000 usuarios | Prioridad |
|---|---|---|---|---|
| 1 | **Cualquiera puede crear productos**: `POST /api/v1/products` no pide login | `app/routers/products.py:15` | Cualquier persona puede llenar el catálogo de basura | **Urgente** |
| 2 | **No hay límite de consultas** en el chat ni en el agente | `app/routers/ai.py:25`, `app/routers/agent.py:44` | Un solo usuario (o un bot) puede ocupar toda la GPU | **Urgente** |
| 3 | **La búsqueda usa `ILIKE '%texto%'`**, que lee toda la tabla | `app/repositories/product_repository.py:65` | Cada búsqueda se pone más lenta a medida que crece el catálogo | Alta |
| 4 | **No hay caché**: cada visita consulta la base | Todo el catálogo | Los precios solo cambian cuando corre la ingesta, pero se recalculan en cada visita | Alta |
| 5 | **No se puede usar un modelo propio**: el cliente OpenAI y el agente no aceptan una dirección propia | `app/ai/providers/openai_provider.py:16`, `app/agent/llm.py:41` | No se puede conectar vLLM | Alta (es lo que pide el profe) |
| 6 | **El chat espera la respuesta completa** (hasta 180 s) en vez de mostrarla de a poco | `app/routers/ai.py`, `frontend/next.config.ts` | Cada consulta ocupa un hilo del servidor; con muchas consultas a la vez se acaban | Media |
| 7 | **Conexiones a la base sin ajustar**: 5 + 10 por proceso, por defecto | `app/db.py:20` | Con 8 procesos por tarro se superan las 100 conexiones que permite PostgreSQL | Media |
| 8 | **Cada proceso crea las tablas al arrancar** con `create_all` | `app/main.py:211` | Choques al arrancar varios procesos a la vez; además ya existe Alembic | Baja |

## 4. Mejoras propuestas

### 4.1 Arquitectura en los dos tarros

```text
Usuarios
   │
Cloudflare (HTTPS, caché de páginas e imágenes, protección DDoS, reparto entre los 2 tarros)
   │
   ├── Tarro 1 ─────────────────────────────┐   ├── Tarro 2 (igual, en espera activa)
   │  Caddy (proxy)                         │   │  Caddy
   │  Next.js (frontend)                    │   │  Next.js
   │  FastAPI × 8 procesos                  │   │  FastAPI × 8 procesos
   │  Redis (caché + límites + cola de IA)  │   │  Redis réplica
   │  PgBouncer → PostgreSQL principal ─────┼───┼→ PostgreSQL réplica (se copia en vivo)
   │  vLLM + modelo abierto en la RTX 5090  │   │  vLLM + modelo en la RTX 5090
   │  Worker de ingesta (scraping)          │   │  Prometheus + Grafana (monitoreo)
   └────────────────────────────────────────┘   └───────────────────────────────
Respaldo diario de la base → nube (S3 o Backblaze)   ·   Si las 2 GPU están llenas → Gemini
```

Todo corre en contenedores Docker. El proyecto ya tiene `docker-compose.yml`; se agregan los servicios `redis`, `pgbouncer`, `postgres`, `vllm` y `caddy`.

### 4.2 Cambios en el código, en orden

| Paso | Cambio | Resuelve | Esfuerzo |
|---|---|---|---|
| 1 | Pedir login de admin en `POST /products` (`CurrentAdmin`, como en `admin.py`) | Problema 1 | 10 min |
| 2 | Límite por usuario con Redis: por ejemplo 20 consultas de IA por hora y 60 visitas al catálogo por minuto por IP; si se pasa, responder **429** | Problema 2 | 2-3 h |
| 3 | Agregar `OPENAI_BASE_URL` en `config.py`, el adaptador OpenAI y el agente (`ChatOpenAI`) para apuntar a vLLM | Problema 5 | 1-2 h |
| 4 | Cola de IA: máximo de consultas a la vez por GPU (por ejemplo 24). Si la cola está llena, mandar la consulta a Gemini o pedir "intenta en unos segundos" | Problema 2 + la GPU es finita | 3-4 h |
| 5 | Caché en Redis de búsquedas, facetas, producto e historial (5-10 min; se borra al terminar cada ingesta) + `Cache-Control` para Cloudflare | Problema 4 | 3-4 h |
| 6 | Índice `pg_trgm` (GIN) sobre nombre, marca y modelo en una migración de Alembic | Problema 3 | 1 h |
| 7 | Ajustar el pool (`pool_size=5, max_overflow=5`) + PgBouncer delante de PostgreSQL | Problema 7 | 1 h |
| 8 | Respuesta del chat en streaming: el texto aparece de a poco | Problema 6 | 4-6 h |
| 9 | Quitar `create_all` del arranque y usar solo `alembic upgrade head` | Problema 8 | 15 min |

Los pasos 1 a 7 son los que más importan para aguantar la carga. El paso 8 mejora la sensación de rapidez.

## 5. Cómo demostrar que aguanta

El repo ya tiene `EP2_ITY1102/infra/prueba_carga.sh`. Para esta entrega conviene usar **k6** o **Locust**, que simulan usuarios con un recorrido realista: inicio → búsqueda → producto → chat.

| Prueba | Cómo | Meta para aprobar |
|---|---|---|
| Carga normal (hora pico de 10.000/día) | 1.000 usuarios virtuales navegando + 18 chats a la vez, durante 15 min | Catálogo p95 < 1 s · primera palabra del chat < 3 s · errores < 1 % |
| Estrés | Subir de a poco hasta que algo falle | Encontrar el límite real (por ejemplo "aguanta 2.500 a la vez") y anotar qué falló primero |
| Pico repentino | De 100 a 2.000 usuarios en 30 s | No se cae; si hace falta, responde 429 o "intenta de nuevo" |
| Falla de un tarro | Desconectar el tarro 1 en plena carga | La página sigue arriba en < 1 min con el tarro 2 |
| Abuso | Un bot mandando 100 chats seguidos | Recibe 429 sin afectar a los demás usuarios |
| Rendimiento de la GPU | `vllm bench` con el modelo elegido | Confirmar los ~1.500 tok/s que supusimos (si da menos, usar un modelo más chico) |

Hay que guardar como evidencia los gráficos de Grafana y los reportes de k6, igual que en la carpeta `evidencia/` de la EP2.

## 6. Cómo mantenerla funcionando

| Tarea | Frecuencia | Herramienta |
|---|---|---|
| Respaldo de la base a la nube y prueba de restauración | Diario / mensual | `pg_dump` + S3 o Backblaze |
| Monitoreo de CPU, RAM, GPU, latencia, errores y cola de IA | Siempre | Prometheus + Grafana + exportador de NVIDIA |
| Alertas: página caída, disco lleno, GPU caliente, cola llena | Siempre | Uptime Kuma o Grafana → correo o Telegram |
| Parches de seguridad del sistema y Docker | Semanal | `unattended-upgrades` |
| Actualizar el modelo o vLLM | Trimestral | Primero en el tarro 2 y luego en el 1 (sin caída) |
| Revisar la batería de la UPS y limpiar el polvo | Semestral | Técnico |
| Ingesta de precios | Programada | Worker de ingesta (ya existe) |

## 7. Costos para 10.000 usuarios al día

| Alternativa | Compra | Costo mensual | A 3 años |
|---|---|---|---|
| A. 1 tarro RTX 5090 (sin respaldo) | $10,6 M | $621.769 | $22,4 M |
| **C. 2 tarros RTX 5090 (recomendada)** | **$21,4 M** | **$1.211.352** | **$43,6 M** |
| Nube: AWS + Gemini para 10.000 al día | $0 | $525.954 | $18,9 M |

El costo mensual de la opción C incluye la depreciación ($594.029), la luz ($155.344), internet con enlace de respaldo ($122.000), el técnico ($240.000), repuestos ($89.104) y dominio, respaldos y Cloudflare ($10.875).

**Conclusión:** con 10.000 usuarios al día, **dos tarros con RTX 5090 aguantan la carga con margen**: cada GPU podría atender la carga completa sola. Pero cuestan unas 2,3 veces más que la nube. Se justifican por privacidad, por no depender de Google y por tener un costo fijo que no sube con cada consulta. Si la meta fueran 10.000 usuarios **simultáneos**, el servidor propio deja de ser viable y conviene la API.

## 8. Reparto sugerido entre los compañeros

| Persona | Tarea |
|---|---|
| 1 | Pasos 1, 2 y 9 (seguridad y límites) + prueba de abuso |
| 2 | Pasos 3 y 4 (vLLM, cola y Gemini de respaldo) + benchmark de la GPU |
| 3 | Pasos 5, 6 y 7 (caché, índice y PgBouncer) + pruebas de carga con k6 |
| 4 | Docker Compose de los 2 tarros, monitoreo, respaldos, prueba de falla y documento final |
