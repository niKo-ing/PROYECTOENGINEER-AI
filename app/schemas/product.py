from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=100)
    price_clp: int = Field(ge=0)
    brand: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    rating: float | None = Field(default=None, ge=0, le=5)


class ProductRead(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    lowest_price: int | None = None
    lowest_price_store: str | None = None
    offer_count: int = 0


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
