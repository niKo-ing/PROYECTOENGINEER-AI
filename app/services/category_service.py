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
        categories = self.repository.list_all()
        children: dict[int | None, list] = {}
        for category in categories:
            children.setdefault(category.parent_id, []).append(category)
        return [self._to_schema(category, children) for category in children.get(None, [])]

    def get_tree(self, category_id: int) -> CategoryRead | None:
        category = self.repository.get(category_id)
        if category is None:
            return None
        categories = self.repository.list_all()
        children: dict[int | None, list] = {}
        for item in categories:
            children.setdefault(item.parent_id, []).append(item)
        return self._to_schema(category, children)

    def _to_schema(self, category, children: dict[int | None, list]) -> CategoryRead:
        return CategoryRead(
            id=category.id,
            name=category.name,
            slug=category.slug,
            parent_id=category.parent_id,
            priority=category.priority,
            is_group=category.is_group,
            spec_definitions=list(category.spec_definitions),
            children=[self._to_schema(child, children) for child in children.get(category.id, [])],
        )
