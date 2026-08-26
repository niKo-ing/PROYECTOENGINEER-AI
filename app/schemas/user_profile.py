from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

PreferenceMap = dict[str, str]


class ProfileCreate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    typical_budget_clp: int | None = Field(default=None, ge=0, le=100_000_000)
    general_preferences: PreferenceMap = Field(default_factory=dict)
    favorite_categories: list[str] = Field(default_factory=list, max_length=30)
    favorite_brands: list[str] = Field(default_factory=list, max_length=30)
    rejected_brands: list[str] = Field(default_factory=list, max_length=30)
    shopping_preferences: PreferenceMap = Field(default_factory=dict)


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    typical_budget_clp: int | None = Field(default=None, ge=0, le=100_000_000)
    general_preferences: PreferenceMap | None = None
    favorite_categories: list[str] | None = Field(default=None, max_length=30)
    favorite_brands: list[str] | None = Field(default=None, max_length=30)
    rejected_brands: list[str] | None = Field(default=None, max_length=30)
    shopping_preferences: PreferenceMap | None = None


class ProfileRead(ProfileCreate):
    model_config = ConfigDict(from_attributes=True)
    user_id: str
    created_at: datetime
    updated_at: datetime
