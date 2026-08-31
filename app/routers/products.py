from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.product import CategoryFacets, PriceHistoryRead, ProductCreate, ProductRead, ProductSearch, StoreOfferRead
from app.services.facet_service import FacetService
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["products"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: DbSession):
    return ProductService(db).create(payload)


@router.get("", response_model=ProductSearch)
def search_products(
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
    db: DbSession,
    category: str | None = Query(default=None, min_length=1, max_length=100),
):
    facets = FacetService(db).category_facets(category)
    if facets is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")
    return facets


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: DbSession):
    return ProductService(db).get(product_id)


@router.get("/{product_id}/offers", response_model=list[StoreOfferRead])
def get_product_offers(product_id: int, db: DbSession):
    return ProductService(db).offers(product_id)


@router.get("/{product_id}/price-history", response_model=list[PriceHistoryRead])
def get_product_price_history(product_id: int, db: DbSession):
    return ProductService(db).price_history(product_id)
