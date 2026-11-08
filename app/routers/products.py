from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.cache import cached_json, catalog_cache
from app.core.limits import limit_catalog
from app.core.security import AuthenticatedUser, get_current_admin
from app.db import get_db
from app.schemas.product import CategoryFacets, PriceHistoryRead, ProductCreate, ProductRead, ProductSearch, StoreOfferRead
from app.services.facet_service import FacetService
from app.services.product_service import ProductService

# Cada IP tiene un máximo de solicitudes por minuto al catálogo (CATALOG_RATE_LIMIT_PER_MINUTE).
router = APIRouter(prefix="/products", tags=["products"], dependencies=[Depends(limit_catalog)])
DbSession = Annotated[Session, Depends(get_db)]
CurrentAdmin = Annotated[AuthenticatedUser, Depends(get_current_admin)]


def _cache_key(request: Request) -> str:
    """La ruta y los parámetros ordenados: la misma búsqueda reutiliza la misma respuesta."""
    return f"{request.url.path}?{sorted(request.query_params.multi_items())}"


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: DbSession, _admin: CurrentAdmin):
    product = ProductService(db).create(payload)
    catalog_cache.invalidate()
    return product


@router.get("", response_model=ProductSearch)
def search_products(
    request: Request,
    db: DbSession,
    query: str | None = Query(default=None, min_length=1, max_length=120),
    category: str | None = Query(default=None, min_length=1, max_length=100),
    brand: str | None = Query(default=None, min_length=1, max_length=120),
    min_price_clp: int | None = Query(default=None, ge=0),
    max_price_clp: int | None = Query(default=None, ge=0),
    sort: str = Query(default="price_asc", pattern="^(price_asc|price_desc|newest|name)$"),
    spec_filters: str | None = Query(default=None, max_length=4000, description="JSON object: {key: 'value1,value2'}"),
    spec_ranges: str | None = Query(default=None, max_length=4000, description="JSON object: {key: 'min-max'}"),
    ids: str | None = Query(default=None, max_length=2000),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    def build() -> ProductSearch:
        items, total = ProductService(db).search(
            query=query,
            category=category,
            brand=brand,
            min_price_clp=min_price_clp,
            max_price_clp=max_price_clp,
            sort=sort,
            spec_filters=_decode_json_dict(spec_filters),
            spec_ranges=_decode_json_dict(spec_ranges),
            ids=ids,
            limit=limit,
            offset=offset,
        )
        return ProductSearch(items=items, total=total)

    return cached_json(_cache_key(request), build, ProductSearch)


def _decode_json_dict(payload: str | None) -> dict[str, str] | None:
    if not payload:
        return None
    import json

    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    return {str(key): str(item) for key, item in value.items()}


@router.get("/facets", response_model=CategoryFacets)
def get_category_facets(
    request: Request,
    db: DbSession,
    category: str | None = Query(default=None, min_length=1, max_length=100),
):
    def build():
        facets = FacetService(db).category_facets(category)
        if facets is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")
        return facets

    return cached_json(_cache_key(request), build, CategoryFacets)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(request: Request, product_id: int, db: DbSession):
    return cached_json(_cache_key(request), lambda: ProductService(db).get(product_id), ProductRead)


@router.get("/{product_id}/offers", response_model=list[StoreOfferRead])
def get_product_offers(request: Request, product_id: int, db: DbSession):
    return cached_json(_cache_key(request), lambda: ProductService(db).offers(product_id), list[StoreOfferRead])


@router.get("/{product_id}/price-history", response_model=list[PriceHistoryRead])
def get_product_price_history(request: Request, product_id: int, db: DbSession):
    return cached_json(_cache_key(request), lambda: ProductService(db).price_history(product_id), list[PriceHistoryRead])
