import re

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.catalog.synonyms import expand_query
from app.models.catalog import Category, Product, ProductSpecValue, Store, StoreOffer
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

    def search(self, *, query: str | None, category: str | None, min_price_clp: int | None, max_price_clp: int | None, limit: int, offset: int, brand: str | None = None) -> tuple[list[Product], int]:
        statement = select(Product).join(StoreOffer).outerjoin(Category)
        filters = []
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
        if category:
            filters.append(Category.name.ilike(category.strip()))
        if brand:
            filters.append(Product.brand.ilike(brand.strip()))
        if min_price_clp is not None:
            filters.append(StoreOffer.price >= min_price_clp)
        if max_price_clp is not None:
            filters.append(StoreOffer.price <= max_price_clp)
        if filters:
            statement = statement.where(*filters)

        count_statement = select(func.count(func.distinct(Product.id))).select_from(Product).join(StoreOffer).outerjoin(Category)
        if filters:
            count_statement = count_statement.where(*filters)
        total = self.db.scalar(count_statement) or 0
        items = list(
            self.db.scalars(
                statement.group_by(Product.id)
                .order_by(func.min(StoreOffer.price).asc())
                .options(selectinload(Product.category_entity), selectinload(Product.spec_values).selectinload(ProductSpecValue.definition), selectinload(Product.offers).selectinload(StoreOffer.store))
                .limit(limit)
                .offset(offset)
            )
        )
        return items, total

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
