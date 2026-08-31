from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.catalog.taxonomy import SpecificationDefinition
from app.models.catalog import Category, CategorySpecificationDefinition, Product


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
        return list(self.db.scalars(select(Category).options(selectinload(Category.spec_definitions)).order_by(Category.sort_order, Category.name)))

    def product_counts_by_category(self) -> dict[int, int]:
        rows = self.db.execute(
            select(Product.category_id, func.count(Product.id)).where(Product.category_id.is_not(None)).group_by(Product.category_id)
        )
        return {category_id: count for category_id, count in rows if category_id is not None}

    def subtree_ids(self, category_id: int) -> set[int]:
        ids = {category_id}
        frontier = [category_id]
        while frontier:
            children = list(self.db.scalars(select(Category.id).where(Category.parent_id.in_(frontier))))
            frontier = [child_id for child_id in children if child_id not in ids]
            ids.update(frontier)
        return ids

    def upsert_spec_definition(self, category: Category, definition: SpecificationDefinition) -> CategorySpecificationDefinition:
        existing = self.db.scalar(
            select(CategorySpecificationDefinition).where(
                CategorySpecificationDefinition.category_id == category.id,
                CategorySpecificationDefinition.key == definition.key,
            )
        )
        options = list(definition.options) if definition.options else None
        if existing is None:
            existing = CategorySpecificationDefinition(category=category, key=definition.key)
            self.db.add(existing)
        existing.label = definition.label
        existing.group = definition.group
        existing.data_type = definition.data_type
        existing.unit = definition.unit
        existing.filter_type = definition.filter_type
        existing.required = definition.required
        existing.comparable = definition.comparable
        existing.facetable = definition.facetable
        existing.sort_order = definition.sort_order
        existing.options = options
        self.db.flush()
        return existing
