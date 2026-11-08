from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.cache import cached_json
from app.core.limits import limit_catalog
from app.db import get_db
from app.schemas.category import CategoryRead
from app.services.category_service import CategoryService

router = APIRouter(prefix="/categories", tags=["categories"], dependencies=[Depends(limit_catalog)])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[CategoryRead])
def list_categories(request: Request, db: DbSession):
    return cached_json(request.url.path, lambda: CategoryService(db).list_tree(), list[CategoryRead])


def _found(category):
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")
    return category


@router.get("/by-slug/{category_slug}", response_model=CategoryRead)
def get_category_by_slug(request: Request, category_slug: str, db: DbSession):
    return cached_json(request.url.path, lambda: _found(CategoryService(db).get_tree_by_slug(category_slug)), CategoryRead)


@router.get("/{category_id}", response_model=CategoryRead)
def get_category(request: Request, category_id: int, db: DbSession):
    return cached_json(request.url.path, lambda: _found(CategoryService(db).get_tree(category_id)), CategoryRead)
