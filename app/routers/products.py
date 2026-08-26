from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.product import PriceHistoryRead, ProductCreate, ProductRead, ProductSearch, StoreOfferRead
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
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    items, total = ProductService(db).search(query=query, category=category, brand=brand, min_price_clp=min_price_clp, max_price_clp=max_price_clp, limit=limit, offset=offset)
    return ProductSearch(items=items, total=total)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: DbSession):
    return ProductService(db).get(product_id)


@router.get("/{product_id}/offers", response_model=list[StoreOfferRead])
def get_product_offers(product_id: int, db: DbSession):
    return ProductService(db).offers(product_id)


@router.get("/{product_id}/price-history", response_model=list[PriceHistoryRead])
def get_product_price_history(product_id: int, db: DbSession):
    return ProductService(db).price_history(product_id)
