# Servidor propio: TodoBarato AI en dos tarros con GPU

| Archivo | Para qué |
|---|---|
| `OPTIMIZACIONES.md` | Qué se optimizó, dónde, cómo, por qué y para qué, con los números de la EP2 y los nuevos |
| `INFORME_SERVIDOR_IA.md` | Hardware y costos del tarro con GPU |
| `PLAN_10000_USUARIOS.md` | Plan para aguantar 10.000 usuarios: limitaciones, problemas encontrados y pruebas |
| `costos_servidor_propio.py` | Calcula capacidad y costos (`python servidor_propio/costos_servidor_propio.py`) |
| `docker-compose.yml` | Todos los servicios de un tarro: vLLM, PostgreSQL, PgBouncer, Redis, API, worker, web, Caddy, túnel y monitoreo |
| `Caddyfile` | Balanceador con chequeos cada 2 s y reintento en el otro tarro |
| `.env.servidor.example` | Variables de entorno (copiar como `.env.servidor`) |
| `prueba_caida.sh` | Prueba de caída abrupta (la misma medición que la EP2) |
| `carga_10000.js` | Prueba de carga con k6: hora pico de 10.000 usuarios al día |
| `medir_latencia.py` | Mide req/s y p50/p95/p99 de una ruta, para comparar antes y después |

## Levantar

Cada tarro necesita Ubuntu 24.04, Docker, NVIDIA Container Toolkit y su `.env.servidor`.

```bash
cd servidor_propio
cp .env.servidor.example .env.servidor   # completar claves y la IP del otro tarro
docker compose --env-file .env.servidor --profile principal up -d   # tarro 1 (con worker de ingesta)
docker compose --env-file .env.servidor up -d                       # tarro 2
```

La primera vez, vLLM descarga el modelo (~15 GB).

## Pendiente

- La réplica de PostgreSQL del tarro 2: configurar `pg_basebackup` y la replicación en streaming.
- Medir en los tarros reales: `prueba_caida.sh`, `carga_10000.js` y `vllm bench serve`.
- Streaming de la respuesta del chat.
