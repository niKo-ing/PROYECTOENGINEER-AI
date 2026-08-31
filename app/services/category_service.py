from sqlalchemy.orm import Session

from app.catalog.taxonomy import INITIAL_TAXONOMY, TaxonomyNode
from app.repositories.category_repository import CategoryRepository
from app.schemas.category import CategoryRead


class CategoryService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = CategoryRepository(db)

    def seed_initial_taxonomy(self) -> None:
        self._seed_node(INITIAL_TAXONOMY, None)
        self._delete_obsolete_empty_categories(self._collect_slugs(INITIAL_TAXONOMY))
        self.db.commit()

    def _seed_node(self, node: TaxonomyNode, parent_id: int | None) -> None:
        existing = self.repository.get_by_slug(node.slug) or self.repository.get_by_name_and_parent(node.name, parent_id)
        if existing is None:
            existing = self.repository.create(
                name=node.name,
                slug=node.slug,
                parent_id=parent_id,
                sort_order=0,
                priority=node.priority,
                is_group=node.is_group,
            )
        else:
            existing.name = node.name
            existing.slug = node.slug
            existing.parent_id = parent_id
            existing.priority = node.priority
            existing.is_group = node.is_group
        for definition in node.specs:
            self.repository.upsert_spec_definition(existing, definition)
        for child in node.children:
            self._seed_node(child, existing.id)

    def _collect_slugs(self, node: TaxonomyNode) -> set[str]:
        slugs = {node.slug}
        for child in node.children:
            slugs.update(self._collect_slugs(child))
        return slugs

    def _delete_obsolete_empty_categories(self, canonical_slugs: set[str]) -> None:
        for category in self.repository.list_all():
            if category.slug in canonical_slugs:
                continue
            if category.children or category.products:
                continue
            self.db.delete(category)
        self.db.flush()

    def list_tree(self) -> list[CategoryRead]:
        return self._build_roots(self.repository.list_all())

    def get_tree(self, category_id: int) -> CategoryRead | None:
        category = self.repository.get(category_id)
        if category is None:
            return None
        return self._build_tree_from(category)

    def get_tree_by_slug(self, slug: str) -> CategoryRead | None:
        category = self.repository.get_by_slug(slug)
        if category is None:
            return None
        return self._build_tree_from(category)

    def _build_roots(self, categories: list) -> list[CategoryRead]:
        children: dict[int | None, list] = {}
        for category in categories:
            children.setdefault(category.parent_id, []).append(category)
        counts = self.repository.product_counts_by_category()
        return [self._to_schema(category, children, counts) for category in children.get(None, [])]

    def _build_tree_from(self, category) -> CategoryRead:
        categories = self.repository.list_all()
        children: dict[int | None, list] = {}
        for item in categories:
            children.setdefault(item.parent_id, []).append(item)
        counts = self.repository.product_counts_by_category()
        return self._to_schema(category, children, counts)

    def _to_schema(self, category, children: dict[int | None, list], counts: dict[int, int]) -> CategoryRead:
        child_schemas = [self._to_schema(child, children, counts) for child in children.get(category.id, [])]
        direct = counts.get(category.id, 0)
        return CategoryRead(
            id=category.id,
            name=category.name,
            slug=category.slug,
            parent_id=category.parent_id,
            priority=category.priority,
            is_group=category.is_group,
            sort_order=category.sort_order,
            enabled=category.enabled,
            product_count=direct,
            total_products=direct + sum(child.total_products for child in child_schemas),
            spec_definitions=list(category.spec_definitions),
            children=child_schemas,
        )
