# Cómo optimizamos TodoBarato AI: qué, dónde, cómo, por qué y para qué

Esta guía responde la pregunta del profe: **¿qué hay que hacer para optimizar, por ejemplo, los tiempos de respuesta?** Junta lo que medimos en la EP2 (AWS) con lo que cambiamos para el servidor propio y los 10.000 usuarios.

---

## 1. Cómo se optimiza: el método

Optimizar no es "cambiar cosas para que ande más rápido". Es un ciclo que se repite:

1. **Medir** cómo está hoy, con números: tiempo de respuesta, errores y solicitudes por segundo.
2. **Encontrar el cuello de botella**: la parte que más tiempo o errores aporta.
3. **Cambiar una sola cosa**, la que ataca ese cuello de botella.
4. **Volver a medir con la misma prueba** y comparar antes y después.
5. Si mejoró, se deja; si no, se revierte. Luego se busca el siguiente cuello de botella.

Si se cambian varias cosas a la vez, no se sabe cuál sirvió. Si no se mide antes, no se puede demostrar la mejora.

### Qué números se miden

| Métrica | Qué es | Por qué importa |
|---|---|---|
| **p50 / p95 / p99** | El tiempo dentro del cual responde el 50 %, 95 % o 99 % de las solicitudes | El promedio esconde a los usuarios que esperan mucho. El p95 dice qué tan mal le va al 5 % más lento |
| **req/s** | Solicitudes por segundo que aguanta el sistema | Dice cuántos usuarios caben |
| **Tasa de errores** | Porcentaje de respuestas 5xx o fallidas | Un sistema rápido que falla no sirve |
| **Disponibilidad** | Porcentaje del tiempo en que el sistema responde bien | La meta de la EP2 era ≥ 99,5 % al mes |
| **Ventana de errores** | Cuántos segundos dura el problema cuando algo se cae | Mide qué tan rápido se recupera |
| **Primera palabra / tokens por segundo** | Cuánto tarda la IA en empezar a responder y qué tan rápido escribe | Es lo que el usuario siente en el chat |

### Dónde se pierde el tiempo de una solicitud

```text
Navegador → Internet → Cloudflare → Balanceador (Caddy) → API (FastAPI) → Redis / PostgreSQL → GPU (vLLM)
  caché       ~20-120 ms   caché         reintentos            procesos        caché / índices      cola y lotes
```

Se optimiza en cada capa, partiendo por la que más pesa. En el catálogo pesaba la consulta a la base. En el chat pesa la GPU: el LLM tarda segundos, mientras el resto tarda milisegundos.

---

## 2. Optimización de disponibilidad: lo que medimos en la EP2

Prueba: consultar `/health` cada 0,5 s durante 2 minutos mientras se apaga una réplica. Tabla 10.2 del documento de la EP2:

| Escenario | Solicitudes | Fallidas | Disponibilidad | Ventana de errores |
|---|---|---|---|---|
| Retiro planificado (drenaje de 30 s) | 155 | **0** | 100 % | 0 s |
| Caída abrupta, health check 15 s × 3 | 140 | 9 | 93,57 % | **27 s** |
| Caída abrupta, health check 5 s × 2 | 147 | 5 | 96,60 % | **12 s** |

### 2.1 Health check más frecuente (EP2, medido)

- **Qué:** cambiar el chequeo del balanceador de "cada 15 s, 3 fallas" a "cada 5 s, 2 fallas".
- **Dónde:** el Target Group del ALB (`EP2_ITY1102/infra/desplegar.sh`, `--health-check-interval-seconds 5`).
- **Por qué:** el balanceador no sabe que una réplica murió hasta que falla varios chequeos seguidos. Con 15 s × 3 puede tardar hasta 45 s en darse cuenta, y mientras tanto sigue mandando usuarios a la réplica muerta, que reciben 502.
- **Para qué:** detectar la caída antes, para que menos usuarios caigan en la réplica muerta.
- **Resultado:** la ventana bajó de 27 a 12 s y los errores de 9 a 5. Más chequeos casi no cuestan nada.
- **Límite:** no llega a cero. Siempre queda una ventana entre que la réplica muere y que el balanceador lo detecta.

### 2.2 Drenaje en el retiro planificado (EP2, medido)

- **Qué:** antes de apagar una réplica, el balanceador deja de mandarle usuarios nuevos y espera 30 s a que termine lo que tiene.
- **Por qué y para qué:** en una actualización planificada se avisa antes de apagar. **Resultado: 0 errores.** Por eso los despliegues usan retiro gradual (`actualizacion_gradual.sh`).

### 2.3 Reintentos ante caídas abruptas (nuevo; el siguiente paso de la EP2)

El documento de la EP2 cerraba con: *"Siguiente paso: reintentar en el cliente los 502 de GET"*. Ahora está hecho en dos lugares:

| Dónde | Cómo |
|---|---|
| **Balanceador** (`servidor_propio/Caddyfile`) | Si la conexión a un tarro falla, Caddy **reintenta la misma solicitud en el otro tarro** de inmediato (`lb_try_duration 5s`, `lb_retries 2`). Además chequea cada 2 s y saca al tarro con 2 fallas (4 s, contra 10 s del ALB) |
| **Página** (`frontend/lib/api/http.ts`) | Las lecturas del catálogo se reintentan hasta 2 veces (a los 300 ms y a los 1.000 ms) si llega un 502, 503 o 504 o falla la red. Un 429 respeta el `Retry-After` |

- **Por qué:** el health check solo acorta la ventana. El reintento hace que la solicitud que iba a fallar se responda en el otro servidor, y el usuario no ve el error.
- **Por qué solo las lecturas (GET):** leer el catálogo dos veces no daña nada. Repetir un chat o una alerta podría duplicarla. Por eso el chat no se reintenta solo.
- **Para qué:** acercar la ventana de errores a 0 s en una caída abrupta.
- **Cómo se mide:** `servidor_propio/prueba_caida.sh` hace la misma prueba de la EP2. A los 10 s se apaga un tarro y el script compara contra los 5 errores en 147 de la EP2. **Esto falta medirlo en los tarros reales**; lo esperado es 0-1 errores.

### 2.4 Dos servidores en vez de uno

- **Qué:** dos tarros iguales; Cloudflare manda el tráfico a cualquiera de los dos por el mismo túnel.
- **Por qué:** con un solo tarro, cualquier falla deja la página caída hasta que alguien la arregle (RTO de horas). Con dos, el otro sigue atendiendo.
- **Para qué:** cumplir la meta de disponibilidad (≥ 99,5 %) sin la nube.

---

## 3. Optimización de tiempos de respuesta

### 3.1 Caché del catálogo (medido en local)

- **Qué:** guardar la respuesta de búsquedas, facetas, productos, ofertas, historial y categorías durante 5 minutos.
- **Dónde:** `app/core/cache.py`, usado en `app/routers/products.py` y `app/routers/categories.py`. Se borra sola al terminar cada ingesta (`app/ingestion/runner.py`) y al cambiar el catálogo.
- **Cómo:** con Redis (compartido por los 2 tarros y todos los procesos) o en memoria si no hay Redis. Además manda `Cache-Control`: el navegador guarda la respuesta 30 s y Cloudflare 5 min.
- **Por qué:** los precios solo cambian cuando corre la ingesta. Antes, mil personas buscando "notebook" hacían mil consultas iguales a la base.
- **Para qué:** responder en milisegundos y que la base trabaje solo cuando algo cambió.
- **Resultado medido** (`servidor_propio/medir_latencia.py`, 20 clientes a la vez, 15 s, en el mismo computador):

| Ruta | Sin caché | Con caché | Mejora |
|---|---|---|---|
| Búsqueda `/products?query=notebook` | 357 req/s · p95 85,5 ms | **2.727 req/s · p95 11,3 ms** | 7,6× más solicitudes, 7,6× menos tiempo |
| Categorías | 1.018 req/s · p95 26,6 ms | **2.828 req/s · p95 12,3 ms** | 2,8× más solicitudes |

Esta prueba usó SQLite con el catálogo de ejemplo (5 productos). Con el catálogo real, la diferencia es mayor, porque sin caché cada búsqueda trabaja más. En la EP2, el catálogo en AWS daba 43,9 req/s con p95 de 0,95 s.

### 3.2 Índice de búsqueda (trigramas)

- **Qué:** índice GIN `pg_trgm` sobre nombre, marca y modelo.
- **Dónde:** `alembic/versions/20261108_01_search_trigram_indexes.py`.
- **Por qué:** la búsqueda usa `ILIKE '%texto%'`. Un índice normal no sirve para eso, así que PostgreSQL leía **toda la tabla** en cada búsqueda. Con más productos, cada búsqueda se ponía más lenta.
- **Para qué:** que la búsqueda siga rápida aunque el catálogo crezca de cientos a decenas de miles de productos.
- **Cómo se mide:** con `EXPLAIN ANALYZE SELECT ... WHERE name ILIKE '%rtx%'` antes y después. Antes aparece `Seq Scan` (lee todo) y después `Bitmap Index Scan` (usa el índice).

### 3.3 Conexiones a la base: pool + PgBouncer

- **Qué:** cada proceso abre como máximo 10 conexiones (`DB_POOL_SIZE` + `DB_MAX_OVERFLOW`) y espera hasta 10 s por una libre. PgBouncer reparte todas esas conexiones en pocas conexiones reales a PostgreSQL.
- **Dónde:** `app/db.py` y el servicio `pgbouncer` en `servidor_propio/docker-compose.yml`.
- **Por qué:** por defecto eran 15 conexiones por proceso. 2 tarros × 8 procesos × 15 = 240, más que las 100 que acepta PostgreSQL. En el pico aparecía "too many connections" y la página fallaba.
- **Para qué:** que el pico de usuarios no tumbe la base.

### 3.4 Cola de la GPU y respaldo con Gemini

- **Qué:** cada proceso deja entrar como máximo `AI_MAX_CONCURRENT` consultas al modelo propio (8 procesos × 4 = 32 por tarro, igual a `--max-num-seqs` de vLLM). Las demás esperan hasta 8 s; si no hay cupo, van a Gemini o reciben 503 con "intenta en unos segundos".
- **Dónde:** `app/ai/llm_router.py`, usado en `app/routers/ai.py` y `app/routers/agent.py`.
- **Por qué:** la GPU procesa las respuestas en lotes. Hasta cierto punto, sumar usuarios casi no la frena. Pasado ese punto, **todas** las respuestas se vuelven lentas a la vez. Es mejor atender bien a 32 y mandar el resto a Gemini que atender mal a 100.
- **Para qué:** que el tiempo de respuesta del chat no se dispare en el pico, y que nadie quede esperando sin respuesta.
- **Cálculo (ley de Little):** respuestas a la vez = llamadas por segundo × duración de cada respuesta. Con 10.000 usuarios al día: 2,08 × 8,5 s ≈ 18 a la vez. Caben en una GPU (32 cupos), y si un tarro cae, el otro aguanta solo.

### 3.5 Cortacircuitos: no esperar a un modelo caído

- **Qué:** si el modelo propio falla (GPU, vLLM o timeout), esa consulta se repite en Gemini y **durante 30 s todas las consultas van directo a Gemini**, sin intentar la GPU.
- **Dónde:** `mark_primary_down()` en `app/ai/llm_router.py` y `app/routers/ai.py`.
- **Por qué:** sin esto, cada usuario esperaría su propio timeout (30 s) antes de recibir un error.
- **Para qué:** con el modelo caído, el usuario recibe una respuesta en 1-3 s (Gemini) en vez de un error a los 30 s.

### 3.6 Configuración de vLLM

| Opción | Por qué | Para qué |
|---|---|---|
| `--enable-prefix-caching` | Las instrucciones del sistema son iguales en todas las consultas | No volver a procesarlas: la primera palabra sale antes |
| `--max-num-seqs 32` | Es el lote máximo que la GPU atiende bien | Mantener una velocidad estable por usuario |
| Modelo de 7-8B (y no de 70B) | Un modelo más chico responde más rápido y caben más usuarios por GPU | Equilibrio entre calidad y velocidad; el RAG le da los datos del catálogo |
| `--max-model-len 8192` | Nuestras consultas usan ~2.500 tokens | No reservar memoria que no se usa |

### 3.7 Límites de uso por usuario y por IP

- **Qué:** 30 consultas de IA por hora por usuario y 120 solicitudes al catálogo por minuto por IP. Al pasarse, responde **429** con `Retry-After`.
- **Dónde:** `app/core/limits.py`. El límite por IP viene apagado por defecto (`CATALOG_RATE_LIMIT_PER_MINUTE=0`) y se activa en `.env.servidor`. Solo funciona donde la API recibe la IP real del visitante: en los tarros, Caddy toma la IP de `Cf-Connecting-Ip`. Detrás del proxy de Next.js, todos llegarían con la misma IP y compartirían el límite.
- **Por qué:** un solo bot podía ocupar toda la GPU o la API, y la página se ponía lenta para todos.
- **Para qué:** proteger el tiempo de respuesta de los usuarios normales.

### 3.8 Seguridad que también es rendimiento

`POST /api/v1/products` no pedía login: cualquiera podía llenar el catálogo de basura. Ahora exige ser administrador (`app/routers/products.py`).

### 3.9 Pendiente: mostrar la respuesta del chat de a poco (streaming)

Hoy el chat espera la respuesta completa (5-10 s) antes de mostrar algo. Con streaming, la primera palabra aparece en menos de 1 s. La respuesta total no se acorta, pero **se siente mucho más rápida**. Es el siguiente paso.

---

## 4. Cómo demostrar todo

| Prueba | Script | Qué comparar |
|---|---|---|
| Caché antes y después | `medir_latencia.py` con `CATALOG_CACHE_TTL_SECONDS=0` y `=300` | req/s y p95 (tabla 3.1) |
| Hora pico de 10.000 usuarios al día | `k6 run carga_10000.js` | p95 del catálogo < 1 s, errores < 1 % |
| Caída abrupta de un tarro | `prueba_caida.sh` | Fallidas y ventana contra la EP2 (5 errores, 12 s) |
| Abuso | 100 chats seguidos con un usuario | Desde la 31ª consulta, 429 sin afectar a los demás |
| GPU | `vllm bench serve` | Tokens por segundo reales contra los ~1.500 supuestos |

---

## 5. Preguntas probables del profe

**¿Por qué miden el p95 y no el promedio?**
Porque el promedio esconde a los que esperan mucho. Si 95 responden en 0,1 s y 5 en 10 s, el promedio es 0,6 s y parece bueno, pero 5 de cada 100 usuarios esperan 10 s.

**¿Por qué bajaron los errores al cambiar el health check, pero no llegaron a cero?**
Porque el balanceador necesita ver fallas seguidas antes de sacar la réplica. Mientras tanto, algunas solicitudes siguen llegando a la réplica muerta. Para llegar a cero agregamos reintentos: la solicitud fallida se repite en el otro servidor.

**¿Por qué no reintentan también el chat?**
Porque no es seguro repetirlo: el agente crea alertas y listas, y repetirlo podría duplicarlas. Solo se reintentan las lecturas. El chat tiene su propio respaldo (Gemini) cuando el modelo propio falla antes de responder.

**¿Cuál fue el cuello de botella?**
En la EP2, la CPU de la API (54 %, contra 15 % de la base). En el catálogo, las consultas repetidas a la base, que resolvimos con caché. En el chat, la GPU, que manejamos con la cola, el límite de cupos y el respaldo.

**¿La caché no muestra precios viejos?**
Como máximo por 5 minutos, y se borra sola al terminar cada ingesta, que es cuando cambian los precios. Antes de la caché el precio tampoco era más nuevo: venía de la última ingesta igual.

**¿Qué pasa si se corta la luz?**
La UPS da 15-20 minutos para apagar ordenadamente. La base se respalda todos los días fuera del local, y Cloudflare muestra una página de error mientras tanto. Es una limitación real del servidor propio frente a la nube.
