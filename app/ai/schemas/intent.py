"""Intent and entity models for the conversational AI orchestrator.

These are the structured, LLM-independent representations produced by intent
detection and entity resolution. They are intentionally provider-agnostic and
testable without calling any model.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AIIntentType(StrEnum):
    SEARCH = "search"
    PRODUCT_DETAIL = "product_detail"
    COMPARE = "compare"
    RECOMMEND = "recommend"
    PRICE_CHECK = "price_check"
    SPECIFICATION = "specification"
    COMPATIBILITY = "compatibility"
    GENERAL_QUESTION = "general_question"
    FOLLOW_UP = "follow_up"


class AIEntityType(StrEnum):
    PRODUCT = "product"
    PRODUCT_FAMILY = "product_family"
    BRAND = "brand"
    CATEGORY = "category"
    SPECIFICATION = "specification"
    PRICE = "price"
    USE_CASE = "use_case"


class AIEntity(BaseModel):
    """A resolved or resolvable entity mentioned in the user message.

    A product entity may carry an explicit brand/model/family or a list of
    already-resolved catalog product ids (from the conversation context).
    """

    type: AIEntityType
    value: str | None = None
    brand: str | None = None
    model: str | None = None
    family: str | None = None
    category: str | None = None
    specification: str | None = None
    price_clp: int | None = None
    resolved_product_ids: list[int] = Field(default_factory=list)


class AIIntent(BaseModel):
    """Structured interpretation of a user message before any tool runs."""

    intent: AIIntentType
    confidence: float = 1.0
    entities: list[AIEntity] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    requires_clarification: bool = False