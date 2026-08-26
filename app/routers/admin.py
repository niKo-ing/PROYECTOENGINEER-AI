"""Admin endpoints for ingestion tools."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select

from app.core.security import AuthenticatedUser, get_current_user
from app.db import SessionLocal
from app.ingestion.discovery.discovery import StoreDiscovery
from app.ingestion.discovery.result import DiscoveryResult, PlatformDetection
from app.ingestion.runner import IngestionRunner

router = APIRouter(prefix="/admin", tags=["admin"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


class DiscoverRequest(BaseModel):
    url: HttpUrl


class PlatformDetectionSchema(BaseModel):
    name: str
    confidence: float
    signals: list[str]


class DiscoveryResultSchema(BaseModel):
    url: str
    final_url: str | None = None
    http_status: int | None = None
    content_type: str | None = None
    title: str | None = None
    detected_platform: PlatformDetectionSchema | None = None

    json_ld_found: bool = False
    json_ld_product_found: bool = False
    json_ld_offer_found: bool = False
    embedded_json_found: bool = False
    meta_data_found: bool = False

    price_found: bool = False
    currency_found: bool = False
    availability_found: bool = False
    sku_found: bool = False
    gtin_found: bool = False
    mpn_found: bool = False
    brand_found: bool = False
    product_name_found: bool = False
    image_found: bool = False
    product_url_found: bool = False

    structured_sources: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []


class IngestionRunSchema(BaseModel):
    id: int
    store_id: int
    source_name: str
    status: str
    urls_total: int
    urls_processed: int
    products_created: int
    products_updated: int
    price_changes: int
    errors_count: int
    duration_ms: int | None = None


def _to_schema(result: DiscoveryResult) -> DiscoveryResultSchema:
    platform_schema = None
    if result.detected_platform:
        platform_schema = PlatformDetectionSchema(
            name=result.detected_platform.name,
            confidence=result.detected_platform.confidence,
            signals=result.detected_platform.signals,
        )
    return DiscoveryResultSchema(
        url=result.url,
        final_url=result.final_url,
        http_status=result.http_status,
        content_type=result.content_type,
        title=result.title,
        detected_platform=platform_schema,
        json_ld_found=result.json_ld_found,
        json_ld_product_found=result.json_ld_product_found,
        json_ld_offer_found=result.json_ld_offer_found,
        embedded_json_found=result.embedded_json_found,
        meta_data_found=result.meta_data_found,
        price_found=result.price_found,
        currency_found=result.currency_found,
        availability_found=result.availability_found,
        sku_found=result.sku_found,
        gtin_found=result.gtin_found,
        mpn_found=result.mpn_found,
        brand_found=result.brand_found,
        product_name_found=result.product_name_found,
        image_found=result.image_found,
        product_url_found=result.product_url_found,
        structured_sources=result.structured_sources,
        warnings=result.warnings,
        errors=result.errors,
    )


@router.post("/ingestion/discover", response_model=DiscoveryResultSchema)
def discover_url(payload: DiscoverRequest, _user: CurrentUser):
    """Analyze a public product URL and extract structured data signals."""
    discovery = StoreDiscovery()
    result = discovery.discover(str(payload.url))
    return _to_schema(result)


@router.post("/ingestion/run", response_model=IngestionRunSchema)
def trigger_ingestion_run(store_domain: str, _user: CurrentUser):
    """Manually trigger a full ingestion sync for a store.

    Supports both modes configured in sync_config:
    - mode="urls": uses manual URL list
    - mode="discovery": discovers URLs from categories
    """
    from app.models.catalog import Store

    db = SessionLocal()
    try:
        store = db.scalar(select(Store).where(Store.domain == store_domain))
        if store is None:
            raise HTTPException(status_code=404, detail=f"Store '{store_domain}' not found")

        config = store.sync_config or {}
        mode = config.get("mode", "urls")

        # Get connector class
        from app.main import _get_connector_class
        connector_cls = _get_connector_class(store.domain)
        if connector_cls is None:
            raise HTTPException(status_code=400, detail=f"No connector for domain '{store_domain}'")

        runner = IngestionRunner()

        if mode == "discovery":
            categories = config.get("categories", [])
            if not categories:
                raise HTTPException(status_code=400, detail=f"Store '{store_domain}' has discovery mode but no categories")

            url_discovery = _get_url_discovery_obj(store.domain)
            if url_discovery is None:
                raise HTTPException(status_code=400, detail=f"No URL discovery for domain '{store_domain}'")

            mapper = _get_mapper(store.domain)
            from app.ingestion.category import CategoryFilter
            category_filter = CategoryFilter()

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
            urls = config.get("urls", [])
            if not urls:
                raise HTTPException(status_code=400, detail=f"Store '{store_domain}' has no URLs configured")

            connector = connector_cls(urls=urls)
            run = runner.run(db, connector, urls)

        return IngestionRunSchema(
            id=run.id,
            store_id=run.store_id,
            source_name=run.source_name,
            status=run.status,
            urls_total=run.urls_total,
            urls_processed=run.urls_processed,
            products_created=run.products_created,
            products_updated=run.products_updated,
            price_changes=run.price_changes,
            errors_count=run.errors_count,
            duration_ms=run.duration_ms,
        )
    finally:
        db.close()


@router.post("/ingestion/discovery/run")
def trigger_discovery_run(
    store_domain: str,
    categories: list[str],
    max_urls_per_category: int = 20,
    _user: CurrentUser = None,
):
    """Manually trigger URL discovery + ingestion for a store and categories."""
    from app.models.catalog import Store

    db = SessionLocal()
    try:
        store = db.scalar(select(Store).where(Store.domain == store_domain))
        if store is None:
            raise HTTPException(status_code=404, detail=f"Store '{store_domain}' not found")

        connector_cls = _get_connector_class(store.domain)
        if connector_cls is None:
            raise HTTPException(status_code=400, detail=f"No connector for domain '{store_domain}'")

        url_discovery = _get_url_discovery_obj(store.domain)
        if url_discovery is None:
            raise HTTPException(status_code=400, detail=f"No URL discovery for domain '{store_domain}'")

        mapper = _get_mapper(store.domain)
        from app.ingestion.category import CategoryFilter
        category_filter = CategoryFilter()

        runner = IngestionRunner()
        run = runner.run_with_discovery(
            db=db,
            connector_factory=connector_cls,
            url_discovery=url_discovery,
            category_mapper=mapper,
            category_filter=category_filter,
            categories=categories,
            store_domain=store.domain,
            max_urls_per_category=max_urls_per_category,
        )

        return IngestionRunSchema(
            id=run.id,
            store_id=run.store_id,
            source_name=run.source_name,
            status=run.status,
            urls_total=run.urls_total,
            urls_processed=run.urls_processed,
            products_created=run.products_created,
            products_updated=run.products_updated,
            price_changes=run.price_changes,
            errors_count=run.errors_count,
            duration_ms=run.duration_ms,
        )
    finally:
        db.close()


def _get_url_discovery_obj(domain: str):
    from app.ingestion.connectors.spdigital.url_discovery import SPDigitalURLDiscovery
    from app.ingestion.connectors.paris.url_discovery import ParisURLDiscovery
    registry = {
        "www.spdigital.cl": SPDigitalURLDiscovery(),
        "www.paris.cl": ParisURLDiscovery(),
    }
    return registry.get(domain)


def _get_mapper(domain: str):
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
