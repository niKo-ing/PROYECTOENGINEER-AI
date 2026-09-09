from typing import Any

from pydantic import BaseModel, Field, model_validator


class ToolExecutionRequest(BaseModel):
    tool: str = Field(min_length=1, max_length=64)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResult(BaseModel):
    tool: str
    data: dict[str, Any]


class SearchProductsInput(BaseModel):
    query: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    min_price_clp: int | None = Field(default=None, ge=0)
    max_price_clp: int | None = Field(default=None, ge=0)
    limit: int = Field(default=10, ge=1, le=20)

    @model_validator(mode="after")
    def validate_price_range(self):
        if self.min_price_clp is not None and self.max_price_clp is not None and self.min_price_clp > self.max_price_clp:
            raise ValueError("min_price_clp no puede ser mayor que max_price_clp")
        return self


class GetProductInput(BaseModel):
    product_id: int = Field(ge=1)


class CompareProductsInput(BaseModel):
    product_ids: list[int] = Field(min_length=2, max_length=5)
    limit_specs: int = Field(default=60, ge=1, le=120)


class GetProductOffersInput(BaseModel):
    product_id: int = Field(ge=1)
    limit: int = Field(default=10, ge=1, le=20)


class GetPriceHistoryInput(BaseModel):
    product_id: int = Field(ge=1)
    limit: int = Field(default=20, ge=1, le=50)


class GetUserProfileInput(BaseModel):
    pass


class ProductToolResult(BaseModel):
    id: int
    name: str
    category: str
    price_clp: int
    rating: float | None
    brand: str | None = None
    image_url: str | None = None
    lowest_price: int | None = None
    lowest_price_store: str | None = None
    offer_count: int = 0


class UserProfileToolResult(BaseModel):
    display_name: str | None
    typical_budget_clp: int | None
    favorite_categories: list[str]
    favorite_brands: list[str]
    rejected_brands: list[str]
    shopping_preferences: dict[str, str]
