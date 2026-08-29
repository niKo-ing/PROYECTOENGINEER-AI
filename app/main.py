import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app import models  # noqa: F401 - registers SQLAlchemy models
from app.db import Base, SessionLocal, engine
from app.routers.products import router as products_router
from app.routers.categories import router as categories_router
from app.routers.user_profile import router as user_profile_router
from app.routers.ai import router as ai_router
from app.routers.admin import router as admin_router

log = logging.getLogger(__name__)


def _run_store_sync(store_id: int) -> None:
    """Callback invoked by the scheduler for each store sync job."""
    from app.ingestion.runner import IngestionRunner
    from app.models.catalog import Store
    from sqlalchemy import select

    db = SessionLocal()
    try:
        store = db.get(Store, store_id)
        if store is None or not store.sync_enabled:
            return

        config = store.sync_config or {}
        mode = config.get("mode", "urls")

        # Determine connector class from domain
        connector_cls = _get_connector_class(store.domain)
        if connector_cls is None:
            log.error("No connector registered for domain %s", store.domain)
            return

        runner = IngestionRunner()

        if mode == "discovery":
            # Discovery mode: categories → discover URLs → connector → pipeline
            categories = config.get("categories", [])
            if not categories:
                log.warning("Store %s has discovery mode but no categories", store.domain)
                return

            url_discovery = _get_url_discovery(store.domain)
            if url_discovery is None:
                log.error("No URL discovery registered for domain %s", store.domain)
                return

            mapper = _get_category_mapper(store.domain)
            from app.ingestion.category import CategoryFilter
            category_filter = CategoryFilter()

            log.info("Starting discovery sync for %s (%d categories)", store.domain, len(categories))
            run = runner.run_with_discovery(
                db=db,
                connector_factory=connector_cls,
                url_discovery=url_discovery,
                category_mapper=mapper,
                category_filter=category_filter,
                categories=categories,
                store_domain=store.domain,
                max_urls_per_category=config.get("max_urls_per_category", 20),
            )
        else:
            # Legacy mode: manual URL list
            urls = config.get("urls", [])
            if not urls:
                log.warning("Store %s has no URLs configured in sync_config", store.domain)
                return

            connector = connector_cls(urls=urls)
            log.info("Starting sync for %s (%d URLs)", store.domain, len(urls))
            run = runner.run(db, connector, urls)

        log.info(
            "Sync finished for %s: status=%s processed=%d errors=%d duration=%dms",
            store.domain, run.status, run.urls_processed, run.errors_count, run.duration_ms or 0,
        )
    except Exception:
        log.exception("Unhandled error in sync job for store_id=%d", store_id)
    finally:
        db.close()


def _get_connector_class(domain: str):
    """Map a store domain to its connector class. Returns None if unknown."""
    from app.ingestion.connectors.spdigital.connector import SPDigitalConnector
    from app.ingestion.connectors.paris.connector import ParisConnector

    registry: dict[str, type] = {
        "www.spdigital.cl": SPDigitalConnector,
        "www.paris.cl": ParisConnector,
    }
    return registry.get(domain)


def _get_url_discovery(domain: str):
    """Map a store domain to its URLDiscovery instance. Returns None if unknown."""
    from app.ingestion.connectors.spdigital.url_discovery import SPDigitalURLDiscovery
    from app.ingestion.connectors.paris.url_discovery import ParisURLDiscovery

    registry: dict[str, object] = {
        "www.spdigital.cl": SPDigitalURLDiscovery(),
        "www.paris.cl": ParisURLDiscovery(),
    }
    return registry.get(domain)


def _get_category_mapper(domain: str):
    """Map a store domain to its CategoryMapper."""
    from app.ingestion.category import CategoryMapper

    mappers = {
        "www.spdigital.cl": CategoryMapper.build("www.spdigital.cl", {
            "Tarjetas de Video": "tarjetas-graficas",
            "Notebooks": "notebooks",
            "Procesadores": "procesadores",
            "Memoria RAM": "memoria-ram",
            "SSD": "almacenamiento-ssd",
            "Monitores": "monitores",
            "Placas Madre": "placas-madre",
            "Computadores de Escritorio": "pcs-de-escritorio",
            "Celulares": "celulares",
            "Consolas": "consolas",
        }),
        "www.paris.cl": CategoryMapper.build("www.paris.cl", {
            "Computación": "notebooks",
            "Procesadores": "procesadores",
            "Tarjetas de Video": "tarjetas-graficas",
            "Memoria RAM": "memoria-ram",
            "SSD": "almacenamiento-ssd",
            "Monitores": "monitores",
            "Placas Madre": "placas-madre",
            "Escritorio": "pcs-de-escritorio",
            "Celulares": "celulares",
            "Consolas": "consolas",
        }),
    }
    return mappers.get(domain, CategoryMapper(domain))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan — start/stop the ingestion scheduler."""
    from app.ingestion.scheduler import IngestionScheduler

    scheduler = IngestionScheduler(
        session_factory=SessionLocal,
        job_callback=_run_store_sync,
    )
    try:
        scheduler.start()
    except Exception:
        log.warning("Ingestion scheduler could not start", exc_info=True)
    app.state.ingestion_scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="SoloTodo AI", version="0.1.0", lifespan=lifespan)
    app.include_router(products_router, prefix="/api/v1")
    app.include_router(categories_router, prefix="/api/v1")
    app.include_router(user_profile_router, prefix="/api/v1")
    app.include_router(ai_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


Base.metadata.create_all(bind=engine)
app = create_app()
