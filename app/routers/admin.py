"""Admin endpoints for ingestion tools."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, select

from app.core.security import AuthenticatedUser, get_current_user
from app.catalog.catalog_quality import CatalogQualityService
from app.db import SessionLocal, get_db
from app.ingestion.discovery.discovery import StoreDiscovery
from app.ingestion.discovery.result import DiscoveryResult, PlatformDetection
from app.ingestion.runner import IngestionRunner
from app.models.catalog import Product, ProductSpecValue, ProductSpecValueHistory, Store, StoreOffer
from app.repositories.product_spec_value_repository import ProductSpecValueRepository
from app.services.product_spec_value_service import ProductSpecValueService

router = APIRouter(prefix="/admin", tags=["admin"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


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


class AdminSpecValueSchema(BaseModel):
    id: int
    product_id: int
    product_name: str
    category: str | None
    definition_key: str
    label: str
    group: str
    value: str
    raw_value: str | None
    source_type: str
    source_name: str | None
    source_url: str | None
    extraction_method: str | None
    verification_status: str
    conflict_status: str
    history_count: int


class AdminSpecReviewResponse(BaseModel):
    items: list[AdminSpecValueSchema]


class VerifySpecValueRequest(BaseModel):
    note: str | None = None
    value_kind: str | None = None
    raw_value: str | None = None
    value_text: str | None = None
    value_number: int | float | None = None
    value_boolean: bool | None = None
    value_json: dict | list | None = None
    unit: str | None = None
    source_type: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    extraction_method: str | None = None


class AdminDashboardMetrics(BaseModel):
    products: int
    offers: int
    stores: int
    specs_pending: int
    conflicts: int
    products_without_specs: int
    products_unverified: int
    products_verified: int


class AdminActivityItem(BaseModel):
    id: int
    action: str
    product_id: int
    product_name: str
    label: str
    group: str
    previous_value: dict | None = None
    new_value: dict | None = None
    incoming_value: dict | None = None
    source_type: str
    changed_by: str | None = None
    created_at: str


class AdminDashboardResponse(BaseModel):
    metrics: AdminDashboardMetrics
    recent_activity: list[AdminActivityItem]


class AdminCatalogQualityResponse(BaseModel):
    summary: dict
    categories: list[dict]
    products: list[dict]
    products_incomplete: list[dict]
    products_complete: list[dict]
    definitions_used: list[dict]
    definitions_always_empty: list[dict]
    definitions_low_coverage: list[dict]
    sources: list[dict]
    source_names: list[dict]
    extraction_methods: list[dict]
    provenance_summary: dict
    verification: list[dict]
    conflicts_by_source: list[dict]
    conflicts: list[dict]


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


def _format_value(value: ProductSpecValue) -> str:
    from app.catalog.spec_sheet import format_spec_value

    return format_spec_value(value)


def _spec_value_to_admin_schema(value: ProductSpecValue) -> AdminSpecValueSchema:
    product = value.product
    definition = value.definition
    return AdminSpecValueSchema(
        id=value.id,
        product_id=value.product_id,
        product_name=product.name if product else f"Producto #{value.product_id}",
        category=product.category if product else None,
        definition_key=definition.key if definition else "unknown",
        label=definition.label if definition else "Especificación",
        group=definition.group if definition else "General",
        value=_format_value(value),
        raw_value=value.raw_value,
        source_type=value.source_type,
        source_name=value.source_name,
        source_url=value.source_url,
        extraction_method=value.extraction_method,
        verification_status=value.verification_status,
        conflict_status=value.conflict_status,
        history_count=len(value.history or []),
    )


def _activity_to_schema(event: ProductSpecValueHistory) -> AdminActivityItem:
    product = event.product
    definition = event.definition
    return AdminActivityItem(
        id=event.id,
        action=event.action,
        product_id=event.product_id,
        product_name=product.name if product else f"Producto #{event.product_id}",
        label=definition.label if definition else "Especificación",
        group=definition.group if definition else "General",
        previous_value=event.previous_value,
        new_value=event.new_value,
        incoming_value=event.incoming_value,
        source_type=event.source_type,
        changed_by=event.changed_by,
        created_at=event.created_at.isoformat(),
    )


@router.post("/ingestion/discover", response_model=DiscoveryResultSchema)
def discover_url(payload: DiscoverRequest, _user: CurrentUser):
    """Analyze a public product URL and extract structured data signals."""
    discovery = StoreDiscovery()
    result = discovery.discover(str(payload.url))
    return _to_schema(result)


@router.get("/dashboard", response_model=AdminDashboardResponse)
def get_admin_dashboard(_user: CurrentUser, db: DbSession):
    total_products = db.scalar(select(func.count(Product.id))) or 0
    total_offers = db.scalar(select(func.count(StoreOffer.id))) or 0
    total_stores = db.scalar(select(func.count(Store.id))) or 0
    specs_pending = db.scalar(select(func.count(ProductSpecValue.id)).where(ProductSpecValue.verification_status != "verified")) or 0
    conflicts = db.scalar(select(func.count(ProductSpecValue.id)).where(ProductSpecValue.conflict_status == "pending")) or 0
    products_with_specs = set(db.scalars(select(ProductSpecValue.product_id).distinct()))
    all_products = set(db.scalars(select(Product.id)))
    products_without_specs = len(all_products - products_with_specs)

    unverified_product_ids = set(
        db.scalars(
            select(ProductSpecValue.product_id)
            .where((ProductSpecValue.verification_status != "verified") | (ProductSpecValue.conflict_status == "pending"))
            .distinct()
        )
    )
    products_verified = len(products_with_specs - unverified_product_ids)

    activity = list(
        db.scalars(
            select(ProductSpecValueHistory)
            .options(selectinload(ProductSpecValueHistory.product), selectinload(ProductSpecValueHistory.definition))
            .order_by(ProductSpecValueHistory.created_at.desc(), ProductSpecValueHistory.id.desc())
            .limit(12)
        )
    )
    return AdminDashboardResponse(
        metrics=AdminDashboardMetrics(
            products=total_products,
            offers=total_offers,
            stores=total_stores,
            specs_pending=specs_pending,
            conflicts=conflicts,
            products_without_specs=products_without_specs,
            products_unverified=len(unverified_product_ids),
            products_verified=products_verified,
        ),
        recent_activity=[_activity_to_schema(event) for event in activity],
    )


@router.get("/catalog/quality", response_model=AdminCatalogQualityResponse)
def get_catalog_quality(_user: CurrentUser, db: DbSession):
    return CatalogQualityService(db).build_report()


@router.get("/spec-values/review", response_model=AdminSpecReviewResponse)
def list_spec_values_for_review(_user: CurrentUser, db: DbSession, limit: int = Query(default=100, ge=1, le=500)):
    values = ProductSpecValueRepository(db).list_for_review(limit=limit)
    return AdminSpecReviewResponse(items=[_spec_value_to_admin_schema(value) for value in values])


@router.post("/spec-values/{value_id}/verify", response_model=AdminSpecValueSchema)
def verify_spec_value(value_id: int, payload: VerifySpecValueRequest, user: CurrentUser, db: DbSession):
    repository = ProductSpecValueRepository(db)
    value = repository.get(value_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Specification value not found")
    verified_by = user.email or user.id
    correction = None
    if payload.value_kind is not None:
        from app.models.catalog import SpecVerificationStatus
        from app.services.product_spec_value_service import SpecValueInput

        correction = SpecValueInput(
            product_id=value.product_id,
            definition_id=value.definition_id,
            value_kind=payload.value_kind,
            raw_value=payload.raw_value,
            value_text=payload.value_text,
            value_number=payload.value_number,
            value_boolean=payload.value_boolean,
            value_json=payload.value_json,
            unit=payload.unit,
            source_type=payload.source_type or value.source_type,
            source_name=payload.source_name or value.source_name,
            source_url=payload.source_url,
            extraction_method=payload.extraction_method or value.extraction_method,
            verification_status=SpecVerificationStatus.VERIFIED.value,
        )
    value = ProductSpecValueService(db).verify(value, verified_by=verified_by, note=payload.note, correction=correction)
    value = repository.get(value.id) or value
    return _spec_value_to_admin_schema(value)


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
