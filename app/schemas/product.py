from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=100)
    price_clp: int = Field(ge=0)
    brand: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    rating: float | None = Field(default=None, ge=0, le=5)


class SpecItem(BaseModel):
    label: str
    value: str


class SpecSection(BaseModel):
    title: str
    items: list[SpecItem] = Field(default_factory=list)


class ProductSpecs(BaseModel):
    highlights: list[str] = Field(default_factory=list)
    sections: list[SpecSection] = Field(default_factory=list)


class CanonicalSpecItem(BaseModel):
    key: str
    label: str
    value: str
    raw_value: str | None = None
    unit: str | None = None
    value_kind: str | None = None
    value_json: dict | list | None = None
    item_schema: dict | None = None
    source_type: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    verification_status: str | None = None
    conflict_status: str | None = None


class CanonicalSpecSection(BaseModel):
    title: str
    items: list[CanonicalSpecItem] = Field(default_factory=list)


class CanonicalProductSpecs(BaseModel):
    sections: list[CanonicalSpecSection] = Field(default_factory=list)


class ProductRead(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    image_url: str | None = None
    images: Annotated[list[str], Field(default_factory=list)]
    description_ai: str | None = None
    specs: ProductSpecs | None = None
    canonical_specs: CanonicalProductSpecs | None = None
    lowest_price: int | None = None
    lowest_price_store: str | None = None
    offer_count: int = 0

    @field_validator("images", mode="before")
    @classmethod
    def _images_not_none(cls, value: object) -> object:
        return value or []


class StoreSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    domain: str
    store_type: str


class StoreOfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    store: StoreSummary
    url: str
    price: int
    original_price: int | None
    currency: str
    stock_status: str
    condition: str
    availability: bool
    payment_condition: str | None
    seller_name: str | None
    last_checked_at: datetime


class PriceHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    price: int
    original_price: int | None
    currency: str
    observed_at: datetime


class ProductSearch(BaseModel):
    items: list[ProductRead]
    total: int


class FacetOption(BaseModel):
    value: str
    count: int


class FacetRange(BaseModel):
    minimum: float | None = None
    maximum: float | None = None


class CategoryFacetSpec(BaseModel):
    key: str
    label: str
    group: str
    data_type: str
    unit: str | None = None
    filter_type: str
    kind: str  # "options" | "range"
    options: list[FacetOption] = Field(default_factory=list)
    range: FacetRange | None = None


class CategoryFacets(BaseModel):
    category: str
    total: int = 0
    brands: list[FacetOption] = Field(default_factory=list)
    price_range: FacetRange | None = None
    specs: list[CategoryFacetSpec] = Field(default_factory=list)
