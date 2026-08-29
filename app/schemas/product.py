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


class ProductRead(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    image_url: str | None = None
    images: Annotated[list[str], Field(default_factory=list)]
    description_ai: str | None = None
    specs: ProductSpecs | None = None
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
