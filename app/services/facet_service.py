from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Category, CategorySpecificationDefinition, Product, ProductSpecValue, StoreOffer
from app.repositories.category_repository import CategoryRepository
from app.schemas.product import CategoryFacetSpec, CategoryFacets, FacetOption, FacetRange

_NUMERIC_TYPES = {"integer", "number", "decimal", "range", "dimension"}


class FacetService:
    def __init__(self, db: Session):
        self.db = db
        self.category_repository = CategoryRepository(db)

    def category_facets(self, category_query: str | None) -> CategoryFacets | None:
        category = self._resolve_category(category_query)
        if category is None:
            return None
        subtree_ids = self.category_repository.subtree_ids(category.id)
        product_filter = Product.category_id.in_(subtree_ids)

        total = self.db.scalar(
            select(func.count(func.distinct(Product.id)))
            .select_from(Product)
            .join(StoreOffer)
            .where(product_filter)
        ) or 0

        brands: list[FacetOption] = []
        brand_rows = self.db.execute(
            select(Product.brand, func.count(func.distinct(Product.id)))
            .where(product_filter, Product.brand.is_not(None))
            .group_by(Product.brand)
            .order_by(func.count(func.distinct(Product.id)).desc(), Product.brand.asc())
            .limit(20)
        )
        for brand, count in brand_rows:
            if brand:
                brands.append(FacetOption(value=brand, count=count))

        price_range: FacetRange | None = None
        minimum, maximum = self.db.execute(
            select(func.min(StoreOffer.price), func.max(StoreOffer.price))
            .select_from(StoreOffer)
            .join(Product, Product.id == StoreOffer.product_id)
            .where(product_filter)
        ).first()
        if minimum is not None or maximum is not None:
            price_range = FacetRange(minimum=int(minimum) if minimum is not None else None, maximum=int(maximum) if maximum is not None else None)

        specs: list[CategoryFacetSpec] = []
        definitions = list(
            self.db.scalars(
                select(CategorySpecificationDefinition)
                .where(CategorySpecificationDefinition.category_id.in_(subtree_ids), CategorySpecificationDefinition.facetable.is_(True))
                .order_by(CategorySpecificationDefinition.sort_order, CategorySpecificationDefinition.id)
            )
        )
        seen_keys: set[str] = set()
        for definition in definitions:
            if definition.key in seen_keys:
                continue
            seen_keys.add(definition.key)
            facet = self._definition_facet(definition, product_filter)
            if facet is not None:
                specs.append(facet)
        return CategoryFacets(category=category.slug, total=total, brands=brands, price_range=price_range, specs=specs)

    def _definition_facet(self, definition: CategorySpecificationDefinition, product_filter) -> CategoryFacetSpec | None:
        is_numeric = definition.data_type in _NUMERIC_TYPES or definition.filter_type == "range"
        if is_numeric:
            minimum, maximum = self.db.execute(
                select(func.min(ProductSpecValue.value_number), func.max(ProductSpecValue.value_number)).where(
                    ProductSpecValue.definition_id == definition.id,
                    ProductSpecValue.product_id.in_(select(Product.id).where(product_filter)),
                    ProductSpecValue.value_number.is_not(None),
                )
            ).first()
            if minimum is None and maximum is None:
                return None
            return CategoryFacetSpec(
                key=definition.key,
                label=definition.label,
                group=definition.group or "General",
                data_type=definition.data_type,
                unit=definition.unit,
                filter_type=definition.filter_type,
                kind="range",
                range=FacetRange(
                    minimum=float(minimum) if minimum is not None else None,
                    maximum=float(maximum) if maximum is not None else None,
                ),
            )
        rows = self.db.execute(
            select(ProductSpecValue.value_text, func.count(func.distinct(ProductSpecValue.product_id)))
            .where(
                ProductSpecValue.definition_id == definition.id,
                ProductSpecValue.value_text.is_not(None),
                ProductSpecValue.product_id.in_(select(Product.id).where(product_filter)),
            )
            .group_by(ProductSpecValue.value_text)
            .order_by(func.count(func.distinct(ProductSpecValue.product_id)).desc(), ProductSpecValue.value_text.asc())
            .limit(15)
        )
        options = [FacetOption(value=value, count=count) for value, count in rows]
        if not options:
            return None
        return CategoryFacetSpec(
            key=definition.key,
            label=definition.label,
            group=definition.group or "General",
            data_type=definition.data_type,
            unit=definition.unit,
            filter_type=definition.filter_type,
            kind="options",
            options=options,
        )

    def _resolve_category(self, category_query: str | None) -> Category | None:
        if not category_query:
            return None
        category_query = category_query.strip()
        category = self.category_repository.get_by_slug(category_query)
        if category is None:
            category = self.db.scalar(select(Category).where(Category.name == category_query))
        return category