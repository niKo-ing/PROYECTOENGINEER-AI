from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class StoreType(StrEnum):
    RETAILER = "retailer"
    MARKETPLACE = "marketplace"
    OFFICIAL_BRAND = "official_brand"


class StockStatus(StrEnum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


class OfferCondition(StrEnum):
    NEW = "new"
    USED = "used"
    SEMI_NEW = "semi_new"
    REFURBISHED = "refurbished"
    OPEN_BOX = "open_box"
    UNKNOWN = "unknown"


class SpecValueKind(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"
    RANGE = "range"
    DIMENSION = "dimension"
    LIST = "list"
    JSON = "json"


class SpecValueSourceType(StrEnum):
    STORE = "store"
    MANUFACTURER = "manufacturer"
    EXTERNAL = "external"
    SCRAPER = "scraper"
    INGESTION = "ingestion"
    AI = "ai"
    AI_RESEARCH = "ai_research"
    ADMIN = "admin"
    UNKNOWN = "unknown"


class SpecVerificationStatus(StrEnum):
    AUTO = "auto"
    REVIEW = "review"
    VERIFIED = "verified"


class SpecConflictStatus(StrEnum):
    NONE = "none"
    PENDING = "pending"
    RESOLVED = "resolved"


class SpecValueHistoryAction(StrEnum):
    CREATED = "created"
    VALUE_CHANGED = "value_changed"
    SOURCE_UPDATED = "source_updated"
    CONFLICT_DETECTED = "conflict_detected"
    VERIFIED = "verified"


class IngestionSourceType(StrEnum):
    API = "api"
    FEED = "feed"
    AFFILIATE_FEED = "affiliate_feed"
    SCRAPER = "scraper"


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("name", "parent_id", name="uq_category_name_parent"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[str] = mapped_column(String(4), default="P2")
    is_group: Mapped[bool] = mapped_column(Boolean, default=False)

    parent: Mapped["Category | None"] = relationship(remote_side="Category.id", back_populates="children")
    children: Mapped[list["Category"]] = relationship(back_populates="parent")
    products: Mapped[list["Product"]] = relationship(back_populates="category_entity")
    spec_definitions: Mapped[list["CategorySpecificationDefinition"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="CategorySpecificationDefinition.sort_order",
    )


class CategorySpecificationDefinition(Base):
    __tablename__ = "category_specification_definitions"
    __table_args__ = (
        UniqueConstraint("category_id", "key", name="uq_category_spec_definition_key"),
        Index("ix_category_spec_definitions_category_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(120))
    group: Mapped[str] = mapped_column("spec_group", String(80), default="General")
    data_type: Mapped[str] = mapped_column(String(32), default="text")
    unit: Mapped[str | None] = mapped_column(String(32))
    filter_type: Mapped[str] = mapped_column(String(32), default="text")
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    comparable: Mapped[bool] = mapped_column(Boolean, default=True)
    facetable: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    options: Mapped[list[str] | None] = mapped_column(JSON)

    category: Mapped[Category] = relationship(back_populates="spec_definitions")


class Product(Base):
    """Canonical product identity; prices belong exclusively to StoreOffer."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    brand: Mapped[str | None] = mapped_column(String(120), index=True)
    model: Mapped[str | None] = mapped_column(String(160), index=True)
    mpn: Mapped[str | None] = mapped_column(String(160), unique=True, index=True)
    gtin: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    manufacturer_sku: Mapped[str | None] = mapped_column(String(160), index=True)
    description: Mapped[str | None] = mapped_column(Text())
    description_ai: Mapped[str | None] = mapped_column(Text())
    specs: Mapped[dict | None] = mapped_column(JSON)
    image_url: Mapped[str | None] = mapped_column(String(2048))
    images: Mapped[list[str] | None] = mapped_column(JSON)
    rating: Mapped[float | None] = mapped_column(Numeric(2, 1))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category_entity: Mapped[Category | None] = relationship(back_populates="products")
    specifications: Mapped[list["ProductSpecification"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    spec_values: Mapped[list["ProductSpecValue"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    offers: Mapped[list["StoreOffer"]] = relationship(back_populates="product", cascade="all, delete-orphan")

    @property
    def category(self) -> str:
        return self.category_entity.name if self.category_entity else "Sin categoría"

    @property
    def price_clp(self) -> int:
        """Compatibility projection for current APIs, derived from active offers."""
        return self.lowest_price or 0

    @property
    def lowest_offer(self) -> "StoreOffer | None":
        eligible = [offer for offer in self.offers if offer.currency == "CLP" and offer.availability]
        return min(eligible, key=lambda offer: offer.price) if eligible else None

    @property
    def lowest_price(self) -> int | None:
        offer = self.lowest_offer
        return int(offer.price) if offer else None

    @property
    def lowest_price_store(self) -> str | None:
        offer = self.lowest_offer
        return offer.store.name if offer and offer.store else None

    @property
    def offer_count(self) -> int:
        return len(self.offers)


class ProductSpecification(Base):
    __tablename__ = "product_specifications"
    __table_args__ = (UniqueConstraint("product_id", "name", name="uq_product_specification_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(String(500))
    unit: Mapped[str | None] = mapped_column(String(32))
    normalized_value: Mapped[str | None] = mapped_column(String(500), index=True)

    product: Mapped[Product] = relationship(back_populates="specifications")


class ProductSpecValue(Base):
    """Canonical current value for one category-defined product specification."""

    __tablename__ = "product_spec_values"
    __table_args__ = (
        UniqueConstraint("product_id", "definition_id", name="uq_product_spec_value_definition"),
        Index("ix_product_spec_values_definition_value", "definition_id", "value_text"),
        Index("ix_product_spec_values_definition_number", "definition_id", "value_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("category_specification_definitions.id", ondelete="CASCADE"), index=True)
    value_kind: Mapped[str] = mapped_column(String(32), default=SpecValueKind.TEXT.value)
    raw_value: Mapped[str | None] = mapped_column(Text())
    value_text: Mapped[str | None] = mapped_column(String(500), index=True)
    value_number: Mapped[float | None] = mapped_column(Numeric(18, 6), index=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)
    value_json: Mapped[dict | list | None] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(32))
    normalized_value: Mapped[dict | None] = mapped_column(JSON)
    source_type: Mapped[str] = mapped_column(String(32), default=SpecValueSourceType.UNKNOWN.value)
    source_name: Mapped[str | None] = mapped_column(String(160))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    extraction_method: Mapped[str | None] = mapped_column(String(120))
    confidence: Mapped[float | None] = mapped_column(Numeric(3, 2))
    verification_status: Mapped[str] = mapped_column(String(32), default=SpecVerificationStatus.AUTO.value)
    conflict_status: Mapped[str] = mapped_column(String(32), default=SpecConflictStatus.NONE.value)
    verified_by: Mapped[str | None] = mapped_column(String(160))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    product: Mapped[Product] = relationship(back_populates="spec_values")
    definition: Mapped[CategorySpecificationDefinition] = relationship()
    history: Mapped[list["ProductSpecValueHistory"]] = relationship(back_populates="spec_value", cascade="all, delete-orphan")


class ProductSpecValueHistory(Base):
    """Audit event for how a canonical specification value changed or conflicted."""

    __tablename__ = "product_spec_value_history"
    __table_args__ = (Index("ix_product_spec_value_history_spec_time", "spec_value_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    spec_value_id: Mapped[int] = mapped_column(ForeignKey("product_spec_values.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("category_specification_definitions.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(32))
    previous_value: Mapped[dict | None] = mapped_column(JSON)
    new_value: Mapped[dict | None] = mapped_column(JSON)
    incoming_value: Mapped[dict | None] = mapped_column(JSON)
    source_type: Mapped[str] = mapped_column(String(32), default=SpecValueSourceType.UNKNOWN.value)
    source_name: Mapped[str | None] = mapped_column(String(160))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    extraction_method: Mapped[str | None] = mapped_column(String(120))
    verification_status: Mapped[str | None] = mapped_column(String(32))
    conflict_status: Mapped[str | None] = mapped_column(String(32))
    changed_by: Mapped[str | None] = mapped_column(String(160))
    note: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    spec_value: Mapped[ProductSpecValue] = relationship(back_populates="history")
    product: Mapped[Product] = relationship()
    definition: Mapped[CategorySpecificationDefinition] = relationship()


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    country: Mapped[str] = mapped_column(String(2), default="CL")
    logo_url: Mapped[str | None] = mapped_column(String(2048))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    trust_level: Mapped[int] = mapped_column(Integer, default=0)
    store_type: Mapped[str] = mapped_column(String(32), default=StoreType.RETAILER.value)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_interval_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sync_last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    offers: Mapped[list["StoreOffer"]] = relationship(back_populates="store")
    ingestion_sources: Mapped[list["IngestionSource"]] = relationship(back_populates="store")
    ingestion_runs: Mapped[list["IngestionRun"]] = relationship(back_populates="store")


class StoreOffer(Base):
    __tablename__ = "store_offers"
    __table_args__ = (
        UniqueConstraint("store_id", "url", name="uq_store_offer_url"),
        Index("ix_store_offer_product_price", "product_id", "price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    price: Mapped[int] = mapped_column(Integer, index=True)
    original_price: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="CLP")
    stock_status: Mapped[str] = mapped_column(String(32), default=StockStatus.UNKNOWN.value)
    condition: Mapped[str] = mapped_column(String(32), default=OfferCondition.UNKNOWN.value)
    availability: Mapped[bool] = mapped_column(Boolean, default=True)
    payment_condition: Mapped[str | None] = mapped_column(String(255))
    seller_name: Mapped[str | None] = mapped_column(String(160))
    seller_id: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(160), default="legacy")
    ingestion_status: Mapped[str] = mapped_column(String(32), default="success")
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped[Product] = relationship(back_populates="offers")
    store: Mapped[Store] = relationship(back_populates="offers")
    price_history: Mapped[list["PriceHistory"]] = relationship(back_populates="store_offer", cascade="all, delete-orphan")


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (Index("ix_price_history_offer_observed", "store_offer_id", "observed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    store_offer_id: Mapped[int] = mapped_column(ForeignKey("store_offers.id", ondelete="CASCADE"), index=True)
    price: Mapped[int] = mapped_column(Integer)
    original_price: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="CLP")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    store_offer: Mapped[StoreOffer] = relationship(back_populates="price_history")


class IngestionSource(Base):
    __tablename__ = "ingestion_sources"
    __table_args__ = (UniqueConstraint("name", "store_id", name="uq_ingestion_source_name_store"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    source_type: Mapped[str] = mapped_column(String(32))
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id", ondelete="SET NULL"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    store: Mapped[Store | None] = relationship(back_populates="ingestion_sources")


class AiMatchDecision(Base):
    """Audit trail for AI-assisted product matching decisions."""

    __tablename__ = "ai_match_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    incoming_name: Mapped[str] = mapped_column(String(255))
    incoming_brand: Mapped[str | None] = mapped_column(String(120))
    incoming_model: Mapped[str | None] = mapped_column(String(160))
    incoming_mpn: Mapped[str | None] = mapped_column(String(160))
    incoming_gtin: Mapped[str | None] = mapped_column(String(32))
    candidate_ids: Mapped[list | None] = mapped_column(JSON)
    selected_product_id: Mapped[int | None] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Numeric(3, 2))
    model: Mapped[str] = mapped_column(String(160))
    prompt_version: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text())
    evidence: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    source_name: Mapped[str] = mapped_column(String(160))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    urls_total: Mapped[int] = mapped_column(Integer, default=0)
    urls_processed: Mapped[int] = mapped_column(Integer, default=0)
    products_created: Mapped[int] = mapped_column(Integer, default=0)
    products_updated: Mapped[int] = mapped_column(Integer, default=0)
    price_changes: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    error_messages: Mapped[str | None] = mapped_column(Text(), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    store: Mapped[Store] = relationship(back_populates="ingestion_runs")
