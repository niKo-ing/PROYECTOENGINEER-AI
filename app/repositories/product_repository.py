import re
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.catalog.synonyms import expand_query, expand_token, normalize_spanish
from app.models.catalog import Category, CategorySpecificationDefinition, Product, ProductSpecValue, Store, StoreOffer
from app.repositories.category_repository import CategoryRepository
from app.schemas.product import ProductCreate


class ProductRepository:
    """Product identity queries. Offer prices are queried from StoreOffer, never Product."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, payload: ProductCreate) -> Product:
        category = self._get_or_create_category(payload.category)
        product_data = payload.model_dump(exclude={"category", "price_clp"})
        product = Product(**product_data, category_entity=category)
        self.db.add(product)
        self.db.flush()

        # Keeps the existing simple product endpoint usable while modelling its
        # supplied price as an offer rather than a product attribute.
        legacy_store = self._get_or_create_legacy_store()
        self.db.add(StoreOffer(product=product, store=legacy_store, url=f"internal://products/{product.id}", price=payload.price_clp, currency="CLP"))
        self.db.commit()
        return self.get(product.id)  # type: ignore[return-value]

    def get(self, product_id: int) -> Product | None:
        statement = select(Product).where(Product.id == product_id).options(selectinload(Product.category_entity), selectinload(Product.spec_values).selectinload(ProductSpecValue.definition), selectinload(Product.offers).selectinload(StoreOffer.store))
        return self.db.scalar(statement)

    def search(
        self,
        *,
        query: str | None,
        category: str | None,
        min_price_clp: int | None,
        max_price_clp: int | None,
        limit: int,
        offset: int,
        brand: str | None = None,
        sort: str = "price_asc",
        spec_filters: dict[str, str] | None = None,
        spec_ranges: dict[str, str] | None = None,
        ids: str | None = None,
    ) -> tuple[list[Product], int]:
        statement = select(Product).join(StoreOffer).outerjoin(Category)
        filters = []
        category_ids = self._resolve_category_ids(category) if category else None
        if category_ids is not None:
            if not category_ids:
                return [], 0
            filters.append(Product.category_id.in_(category_ids))
        if query:
            token_sets = expand_query(query)
            if token_sets:
                token_conditions = [
                    or_(
                        *(
                            Product.name.ilike(f"%{term}%")
                            | Product.brand.ilike(f"%{term}%")
                            | Product.model.ilike(f"%{term}%")
                            | Category.name.ilike(f"%{term}%")
                            for term in token_set
                        )
                    )
                    for token_set in token_sets
                ]
                filters.append(and_(*token_conditions))
        if brand:
            brand_values = [value.strip() for value in brand.split(",") if value.strip()]
            if len(brand_values) == 1:
                filters.append(Product.brand.ilike(brand_values[0]))
            elif brand_values:
                filters.append(or_(*(Product.brand.ilike(value) for value in brand_values)))
        if min_price_clp is not None:
            filters.append(StoreOffer.price >= min_price_clp)
        if max_price_clp is not None:
            filters.append(StoreOffer.price <= max_price_clp)
        if spec_filters:
            for key, values in spec_filters.items():
                value_list = [value.strip() for value in values.split(",") if value.strip()]
                if value_list:
                    filters.append(self._spec_value_exists(key, value_list))
        if spec_ranges:
            for key, range_value in spec_ranges.items():
                bounds = self._parse_range(range_value)
                if bounds is None:
                    continue
                filters.append(self._spec_value_in_range(key, *bounds))
        if ids:
            parsed_ids = [int(item) for item in ids.split(",") if item.strip().isdigit()]
            if not parsed_ids:
                return [], 0
            filters.append(Product.id.in_(parsed_ids))
        if filters:
            statement = statement.where(*filters)

        count_statement = select(func.count(func.distinct(Product.id))).select_from(Product).join(StoreOffer).outerjoin(Category)
        if filters:
            count_statement = count_statement.where(*filters)
        total = self.db.scalar(count_statement) or 0

        order_criteria: Any = func.min(StoreOffer.price).asc()
        if ids:
            order_criteria = Product.id.asc()
        elif sort == "price_desc":
            order_criteria = func.min(StoreOffer.price).desc()
        elif sort == "newest":
            order_criteria = Product.created_at.desc()
        elif sort == "name":
            order_criteria = Product.name.asc()

        items = list(
            self.db.scalars(
                statement.group_by(Product.id)
                .order_by(order_criteria, Product.id.asc())
                .options(selectinload(Product.category_entity), selectinload(Product.spec_values).selectinload(ProductSpecValue.definition), selectinload(Product.offers).selectinload(StoreOffer.store))
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

    def _resolve_category_ids(self, category: str) -> list[int]:
        category_repository = CategoryRepository(self.db)
        term = category.strip()
        match = category_repository.get_by_slug(term)
        if match is None:
            match = self.db.scalar(select(Category).where(Category.name == term))
        if match is None and term:
            match = self._match_category_by_synonyms(term)
        if match is None:
            return []
        return list(category_repository.subtree_ids(match.id))

    def _match_category_by_synonyms(self, term: str) -> Category | None:
        """Resolve a category placeholder ("smartphone", "gpu", "telefonos"...)
        against the real catalog taxonomy using the commercial synonym groups."""
        normalized = normalize_spanish(term)
        for candidate in self.db.scalars(select(Category)).all():
            labels = {candidate.slug, candidate.name}
            for label in labels:
                if not label:
                    continue
                flat = normalize_spanish(label).replace("-", " ").strip()
                for fragment in {flat, *flat.split()}:
                    if not fragment:
                        continue
                    if normalized in expand_token(fragment):
                        return candidate
        return None

    def _spec_value_exists(self, key: str, values: list[str]):
        return (
            select(ProductSpecValue.id)
            .join(CategorySpecificationDefinition, CategorySpecificationDefinition.id == ProductSpecValue.definition_id)
            .where(
                CategorySpecificationDefinition.key == key,
                ProductSpecValue.product_id == Product.id,
                ProductSpecValue.value_text.in_(values),
            )
            .exists()
        )

    def _spec_value_in_range(self, key: str, minimum: int | None, maximum: int | None):
        conditions = [CategorySpecificationDefinition.key == key, ProductSpecValue.product_id == Product.id]
        if minimum is not None:
            conditions.append(ProductSpecValue.value_number >= minimum)
        if maximum is not None:
            conditions.append(ProductSpecValue.value_number <= maximum)
        return (
            select(ProductSpecValue.id)
            .join(CategorySpecificationDefinition, CategorySpecificationDefinition.id == ProductSpecValue.definition_id)
            .where(*conditions)
            .exists()
        )

    @staticmethod
    def _parse_range(value: str) -> tuple[int | None, int | None] | None:
        parts = value.split("-", 1)
        if len(parts) != 2:
            return None
        minimum_text, maximum_text = parts
        try:
            minimum = int(minimum_text) if minimum_text.strip() else None
            maximum = int(maximum_text) if maximum_text.strip() else None
        except ValueError:
            return None
        if minimum is None and maximum is None:
            return None
        if minimum is not None and maximum is not None and minimum > maximum:
            return None
        return minimum, maximum

    def _get_or_create_category(self, name: str) -> Category:
        category = self.db.scalar(select(Category).where(Category.name == name))
        if category:
            return category
        base_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "sin-categoria"
        slug = base_slug
        suffix = 2
        while self.db.scalar(select(Category.id).where(Category.slug == slug)):
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        category = Category(name=name, slug=slug)
        self.db.add(category)
        self.db.flush()
        return category

    def _get_or_create_legacy_store(self) -> Store:
        store = self.db.scalar(select(Store).where(Store.domain == "internal.solotodo.local"))
        if store:
            return store
        store = Store(name="Catálogo interno", domain="internal.solotodo.local", enabled=False)
        self.db.add(store)
        self.db.flush()
        return store
