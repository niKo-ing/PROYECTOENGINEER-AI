from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import ProductSpecValue, ProductSpecValueHistory


class ProductSpecValueRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_product_definition(self, product_id: int, definition_id: int) -> ProductSpecValue | None:
        return self.db.scalar(
            select(ProductSpecValue)
            .where(ProductSpecValue.product_id == product_id, ProductSpecValue.definition_id == definition_id)
            .options(selectinload(ProductSpecValue.history))
        )

    def get(self, value_id: int) -> ProductSpecValue | None:
        return self.db.scalar(
            select(ProductSpecValue)
            .where(ProductSpecValue.id == value_id)
            .options(selectinload(ProductSpecValue.product), selectinload(ProductSpecValue.definition), selectinload(ProductSpecValue.history))
        )

    def list_for_review(self, *, limit: int = 100) -> list[ProductSpecValue]:
        return list(
            self.db.scalars(
                select(ProductSpecValue)
                .where(
                    (ProductSpecValue.verification_status != "verified")
                    | (ProductSpecValue.conflict_status == "pending")
                )
                .options(
                    selectinload(ProductSpecValue.product),
                    selectinload(ProductSpecValue.definition),
                    selectinload(ProductSpecValue.history),
                )
                .order_by(ProductSpecValue.conflict_status.desc(), ProductSpecValue.updated_at.desc())
                .limit(limit)
            )
        )

    def list_for_product(self, product_id: int) -> list[ProductSpecValue]:
        return list(
            self.db.scalars(
                select(ProductSpecValue)
                .where(ProductSpecValue.product_id == product_id)
                .options(selectinload(ProductSpecValue.definition), selectinload(ProductSpecValue.history))
                .order_by(ProductSpecValue.definition_id)
            )
        )

    def add(self, value: ProductSpecValue) -> ProductSpecValue:
        self.db.add(value)
        self.db.flush()
        return value

    def add_history(self, event: ProductSpecValueHistory) -> ProductSpecValueHistory:
        self.db.add(event)
        self.db.flush()
        return event
