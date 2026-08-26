from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(100))
    typical_budget_clp: Mapped[int | None] = mapped_column(Integer)
    general_preferences: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    favorite_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    favorite_brands: Mapped[list[str]] = mapped_column(JSON, default=list)
    rejected_brands: Mapped[list[str]] = mapped_column(JSON, default=list)
    shopping_preferences: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
