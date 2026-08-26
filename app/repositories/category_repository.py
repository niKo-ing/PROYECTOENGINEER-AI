from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Category


class CategoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_slug(self, slug: str) -> Category | None:
        return self.db.scalar(select(Category).where(Category.slug == slug))

    def get_by_name_and_parent(self, name: str, parent_id: int | None) -> Category | None:
        return self.db.scalar(
            select(Category).where(Category.name == name, Category.parent_id == parent_id)
        )

    def create(
        self,
        *,
        name: str,
        slug: str,
        parent_id: int | None,
        sort_order: int,
        priority: str = "P2",
        is_group: bool = False,
    ) -> Category:
        category = Category(
            name=name,
            slug=slug,
            parent_id=parent_id,
            sort_order=sort_order,
            priority=priority,
            is_group=is_group,
        )
        self.db.add(category)
        self.db.flush()
        return category

    def get(self, category_id: int) -> Category | None:
        return self.db.get(Category, category_id)

    def list_all(self) -> list[Category]:
        return list(self.db.scalars(select(Category).order_by(Category.sort_order, Category.name)))
