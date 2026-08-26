# Diseño: Ejecución Periódica e Idempotente — SP Digital + Paris

## Estado actual (resumen)

| Componente | Estado | Gaps clave |
|------------|--------|------------|
| Connectores | Funcionales (SP Digital + Paris) | Aceptan `urls: list[str]`, sin descubrimiento |
| Pipeline | Funcional, secuencial, síncrono | Sin concurrencia, sin observabilidad |
| Service (ingest) | Funcional, upsert por external_id o URL | `error_count` write-only, sin reset automático |
| ProductMatcher | Funcional | Sin cambios necesarios |
| DB schema | 8 tablas activas | Sin tabla de runs, sin config de sync por tienda |
| Scheduler | **No existe** | Nada de cron, background tasks, ni APScheduler |
| Admin API | Solo discovery endpoint | Sin endpoint para disparar ingestión |
| httpx | En uso por conectores | listed as dev dependency (bug de empaquetado) |

---

## Diseño propuesto

### Arquitectura

```
FastAPI (uvicorn)
  └─ lifespan startup
       └─ APScheduler (BackgroundScheduler)
            ├─ Job: sync_spdigital  (cada N minutos)
            └─ Job: sync_paris      (cada N minutos)

Cada job:
  1. Leer URLs del repositorio/config
  2. Crear StoreConnector(urls=...)
  3. Ejecutar IngestionPipeline.run(connector)
  4. Registrar resultado en ingestion_runs
```

**Por qué APScheduler embebido:**
- Sin infraestructura adicional (no Redis, no Celery, no segundo container)
- 2 tiendas, ~100 URLs cada una, ~2-5 min por run → cabe en el mismo proceso
- `BackgroundScheduler` usa thread pool → no bloquea el event loop de FastAPI
- Si en el futuro se necesita escalar, se migra a Celery/Redis sin cambiar la interfaz de conectores

### Flujo de un run periódico

```
APScheduler triggers job (cada N minutos)
  │
  ├─ IngestionRunner.run(connector_class, urls)
  │    │
  │    ├─ connector = connector_class(urls=urls)
  │    ├─ report = IngestionPipeline(service).run(connector)
  │    │    │
  │    │    ├─ connector.extract()  →  yields records (HTTP + parse)
  │    │    ├─ connector.normalize(record)  →  NormalizedOffer
  │    │    └─ service.ingest(connector, offer)  →  Product + StoreOffer + PriceHistory
  │    │
  │    └─ Registrar IngestionRun en DB
  │
  └─ Log resultado
```

---

## Cambios de DB requeridos

### 1. Tabla nueva: `ingestion_runs`

**Por qué:** Actualmente no hay forma de saber cuándo corrió un conector, cuántos productos procesó, o si falló. El campo `last_synced_at` de `ingestion_sources` no es suficiente (no tiene métricas, no tiene histórico).

```python
class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id              = mapped_column(Integer, primary_key=True)
    store_id        = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    source_name     = mapped_column(String(160), nullable=False)  # "spdigital:www.spdigital.cl"
    started_at      = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at     = mapped_column(DateTime(timezone=True), nullable=True)
    status          = mapped_column(String(32), nullable=False, default="running")
                                        # "running" | "success" | "partial" | "error"
    urls_total      = mapped_column(Integer, nullable=False, default=0)
    urls_processed  = mapped_column(Integer, nullable=False, default=0)
    products_created = mapped_column(Integer, nullable=False, default=0)
    products_updated = mapped_column(Integer, nullable=False, default=0)
    price_changes   = mapped_column(Integer, nullable=False, default=0)
    errors_count    = mapped_column(Integer, nullable=False, default=0)
    error_messages  = mapped_column(Text, nullable=True)  # JSON array of first N errors
    duration_ms     = mapped_column(Integer, nullable=True)
```

**Índices:**
- `ix_ingestion_runs_store_id` (en `store_id`)
- `ix_ingestion_runs_started_at` (en `started_at`)

**Relación:** `store` → `Store` (back_populates `ingestion_runs`)

### 2. Columnas nuevas en `stores`: configuración de sync

```python
# Agregar a tabla stores:
sync_enabled       = mapped_column(Boolean, nullable=False, default=False)
sync_interval_min  = mapped_column(Integer, nullable=True)  # None = no auto-sync
sync_last_run_at   = mapped_column(DateTime(timezone=True), nullable=True)
sync_config        = mapped_column(JSON, nullable=True)  # flexible: {"max_concurrent": 5, ...}
```

**Por qué:** Cada tienda necesita configurar:
- Si el sync automático está habilitado
- Cada cuántos minutos corre
- Parámetros específicos (concurrency, delay entre requests)

**Las tiendas existentes (SP Digital, Paris) se configuran manualmente en la primera migración.**

### 3. NO se modifica `store_offers`

La constraint `uq_store_offer_url` en (`store_id`, `url`) es suficiente. El `_find_offer()` del service ya busca por `external_id` primero y cae back a `url`. Si el `external_id` existe, se actualiza; si no, se busca por URL.

**Riesgo conocido:** Si la URL cambia de forma (trailing slash, query params), se crearía un offer duplicado. Mitigación: normalizar URLs en el conector antes de pasar al pipeline (esto es código, no DB).

---

## Cambios de código requeridos

### A. Nuevo: `app/ingestion/scheduler.py`

```python
class IngestionScheduler:
    """APScheduler wrapper para ejecución periódica de conectores."""

    def __init__(self, db_factory, app_config):
        self.scheduler = BackgroundScheduler()
        self.db_factory = db_factory
        self.config = app_config

    def start(self):
        """Llamar en FastAPI lifespan startup."""
        # Lee stores con sync_enabled=True de la DB
        # Registra un job por cada tienda habilitada
        # Job function: self._run_store_sync(store_id, connector_class, urls)

    def shutdown(self):
        """Llamar en FastAPI lifespan shutdown."""

    def _run_store_sync(self, store_id, connector_class, urls):
        """Ejecuta un sync completo para una tienda."""
        # 1. Crear DB session
        # 2. Registrar IngestionRun(status="running")
        # 3. Crear connector(urls=urls)
        # 4. Ejecutar pipeline
        # 5. Actualizar IngestionRun con resultados
        # 6. Actualizar stores.sync_last_run_at
```

### B. Nuevo: `app/ingestion/runner.py`

```python
class IngestionRunner:
    """Ejecuta un sync puntual y registra resultados."""

    def run(self, db, connector_class, urls, source_name) -> IngestionRun:
        run = self._start_run(db, source_name)
        try:
            connector = connector_class(urls=urls)
            service = CatalogIngestionService(db)
            report = IngestionPipeline(service).run(connector)
            return self._finish_run(db, run, report)
        except Exception as e:
            return self._error_run(db, run, e)
```

### C. Modificar: `app/ingestion/pipeline.py`

**Cambios mínimos:**
- `PipelineReport` agregar `duration_ms`, `urls_total`
- Sin cambios en la lógica core

### D. Modificar: `app/ingestion/connectors/` (ambos)

**Agregar al ABC `StoreConnector`:**
```python
class StoreConnector(ABC):
    # ... existente ...
    max_concurrent: int = 1   # nuevas requests paralelas
    request_delay: float = 0  # segundos entre requests (politeness)
```

**SPDigitalConnector y ParisConnector:**
- Mover `httpx` a `dependencies` principales (fix del bug de empaquetado)
- Agregar retry con backoff en `_fetch_html()`
- Agregar delay entre requests si `request_delay > 0`
- Agregar normalización de URLs (strip trailing slashes, remove tracking params)

### E. Nuevo endpoint: `POST /api/v1/admin/ingestion/run`

```python
@router.post("/ingestion/run")
def trigger_ingestion_run(store_domain: str):
    """Dispara un sync manual para una tienda."""
    # 1. Buscar store por domain
    # 2. Leer URLs del sync_config
    # 3. Ejecutar IngestionRunner.run()
    # 4. Retornar IngestionRun结果
```

### F. Migración de DB (Alembic)

```python
# migration: add ingestion_runs + store sync config

def upgrade():
    # 1. Tabla ingestion_runs
    op.create_table('ingestion_runs', ...)

    # 2. Columnas en stores
    op.add_column('stores', sa.Column('sync_enabled', sa.Boolean, default=False))
    op.add_column('stores', sa.Column('sync_interval_min', sa.Integer, nullable=True))
    op.add_column('stores', sa.Column('sync_last_run_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('stores', sa.Column('sync_config', sa.JSON, nullable=True))

    # 3. Configurar tiendas existentes
    op.execute("""
        UPDATE stores SET
            sync_enabled = true,
            sync_interval_min = 30,
            sync_config = '{"max_concurrent": 3, "request_delay": 0.5}'
        WHERE domain IN ('www.spdigital.cl', 'www.paris.cl')
    """)
```

---

## Tabla resumen de cambios

| Archivo | Tipo | Cambio |
|---------|------|--------|
| `app/models/catalog.py` | Modificar | Agregar `IngestionRun` model + campos en `Store` |
| `app/ingestion/scheduler.py` | **Nuevo** | APScheduler wrapper |
| `app/ingestion/runner.py` | **Nuevo** | Ejecución puntual con tracking |
| `app/ingestion/pipeline.py` | Modificar | Agregar `duration_ms`, `urls_total` a report |
| `app/ingestion/connectors/__init__.py` | Modificar | Agregar `max_concurrent`, `request_delay` al ABC |
| `app/ingestion/connectors/spdigital/connector.py` | Modificar | Retry, delay, URL normalization |
| `app/ingestion/connectors/paris/connector.py` | Modificar | Retry, delay, URL normalization |
| `app/routers/admin.py` | Modificar | Nuevo endpoint `POST /ingestion/run` |
| `app/main.py` | Modificar | Lifespan: startup→scheduler.start(), shutdown→scheduler.shutdown() |
| `pyproject.toml` | Modificar | Mover `httpx` a dependencies principales |
| `alembic/versions/003_*.py` | **Nuevo** | Migración DB |
| `tests/test_scheduler.py` | **Nuevo** | Tests del scheduler |
| `tests/test_runner.py` | **Nuevo** | Tests del runner |

---

## Lo que NO se necesita

| No necesario | Por qué |
|--------------|---------|
| Celery / Redis | 2 tiendas, ~100 URLs, ~5 min/run → APScheduler es suficiente |
| Segundo container / worker | El scheduler corre dentro del mismo uvicorn |
| Tabla de colas / jobs | APScheduler maneja su propio state en memoria |
| Async / asyncio | Los conectores son I/O bound pero HTTP concurrente con threads funciona |
| Cambios a ProductMatcher | Ya funciona correctamente |
| Cambios a CatalogIngestionService | Ya maneja upsert correctamente |
| Cambios a NormalizedOffer / DTO | Sin cambios necesarios |
| URL discovery / sitemap | Se configuran URLs manualmente por ahora |
| `ingestion_sources` table | Se deja como está para uso futuro |

---

## Configuración de URLs por tienda

Las URLs se configuran en `sync_config` JSON de cada store:

```json
// SP Digital
{
  "urls": [
    "https://www.spdigital.cl/consola-playstation-5-slim/...",
    "https://www.spdigital.cl/audifonos-sony/..."
  ],
  "max_concurrent": 3,
  "request_delay": 0.5
}

// Paris
{
  "urls": [
    "https://www.paris.cl/607430.html",
    "https://www.paris.cl/..."
  ],
  "max_concurrent": 2,
  "request_delay": 1.0
}
```

**Por qué JSON en DB y no env vars:** Las URLs pueden cambiar sin redeploy. Se actualizan via admin API o migración.

---

## Orden de implementación

1. **DB migration** — ingestion_runs + store sync columns
2. **Models** — IngestionRun + Store campos nuevos
3. **Runner** — Ejecución puntual con tracking
4. **Pipeline update** — duration_ms, urls_total
5. **Connectors update** — httpx dep fix, retry, delay, URL normalization
6. **Scheduler** — APScheduler integration
7. **Admin endpoint** — POST /ingestion/run
8. **Main.py lifespan** — Startup/shutdown hooks
9. **Tests** — Runner, scheduler, endpoint
10. **Configurar tiendas** — Insert URLs in migration
