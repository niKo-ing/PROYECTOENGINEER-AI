"""AI-assisted product matching — core types and candidate generation.

AI is ONLY invoked when the deterministic ProductMatcher returns AMBIGUOUS.
AI never runs for MATCH or NO_MATCH deterministic results.

Architecture:
    Deterministic ProductMatcher
        ├── MATCH      → reuse Product
        ├── NO_MATCH   → create Product
        └── AMBIGUOUS  → AI Matcher
                          ├── MATCH      → reuse Product
                          ├── NO_MATCH   → create Product
                          └── AMBIGUOUS  → unresolved (no merge)
"""

from __future__ import annotations

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.identity import normalize_brand, normalize_model, normalize_mpn
from app.models.catalog import Product, ProductSpecification

log = logging.getLogger(__name__)


# ── AI Match Status ────────────────────────────────────────────────

class AIMatchStatus(StrEnum):
    MATCH = "match"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"


# ── AI Match Request ───────────────────────────────────────────────

@dataclass(frozen=True)
class ProductCandidate:
    """A candidate product for AI comparison."""

    product_id: int
    name: str
    brand: str | None = None
    model: str | None = None
    mpn: str | None = None
    gtin: str | None = None
    manufacturer_sku: str | None = None
    specifications: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AIMatchRequest:
    """Structured input for AI matching."""

    incoming_name: str
    incoming_brand: str | None = None
    incoming_model: str | None = None
    incoming_mpn: str | None = None
    incoming_gtin: str | None = None
    incoming_sku: str | None = None
    incoming_specifications: dict[str, str] = field(default_factory=dict)
    candidates: list[ProductCandidate] = field(default_factory=list)
    prompt_version: str = "v1"


# ── AI Match Result ────────────────────────────────────────────────

@dataclass(frozen=True)
class AIMatchResult:
    """Structured output from AI matching."""

    decision: AIMatchStatus
    confidence: float
    matched_product_id: int | None = None
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    prompt_version: str = "v1"


# ── AI Matching Provider Interface ─────────────────────────────────

class AIMatchingProvider(ABC):
    """Abstract interface for AI matching providers.

    Implementations: GeminiMatchingProvider, MockMatchingProvider.
    ProductMatcher depends on this interface, not on any specific SDK.
    """

    @abstractmethod
    def match(self, request: AIMatchRequest) -> AIMatchResult:
        """Send structured request to AI and return validated result."""
        ...


# ── Candidate Generation ───────────────────────────────────────────

class CandidateGenerator:
    """Deterministic candidate generation before AI call.

    Generates top-K candidates from the database using identity fields.
    Never sends the entire catalog to AI.
    """

    def __init__(self, db: Session, max_candidates: int = 8):
        self.db = db
        self.max_candidates = max_candidates

    def generate(self, incoming: Any) -> list[ProductCandidate]:
        """Generate candidate products for AI comparison.

        Strategy:
        1. Try MPN+brand match (variant-aware)
        2. Try brand+model match
        3. Try same brand fuzzy name
        4. Deduplicate and limit to K
        """
        brand = getattr(incoming, "brand", None)
        mpn = getattr(incoming, "mpn", None)
        model = getattr(incoming, "model", None)
        name = getattr(incoming, "name", None)

        seen_ids: set[int] = set()
        candidates: list[ProductCandidate] = []

        # Strategy 1: MPN variants within same brand
        if mpn and brand:
            norm_mpn = normalize_mpn(mpn)
            if norm_mpn:
                brand_products = list(
                    self.db.scalars(
                        select(Product).where(Product.brand.ilike(brand))
                    ).all()
                )
                for p in brand_products:
                    if p.id not in seen_ids and p.mpn:
                        from app.catalog.identity import mpn_matches
                        if mpn_matches(mpn, p.mpn):
                            candidates.append(self._to_candidate(p))
                            seen_ids.add(p.id)

        # Strategy 2: Brand + model
        if brand and model and len(candidates) < self.max_candidates:
            norm_brand = normalize_brand(brand)
            norm_model = normalize_model(model)
            if norm_brand and norm_model:
                brand_model_products = list(
                    self.db.scalars(
                        select(Product).where(
                            Product.brand.ilike(brand),
                            Product.model.ilike(model),
                        )
                    ).all()
                )
                for p in brand_model_products:
                    if p.id not in seen_ids:
                        candidates.append(self._to_candidate(p))
                        seen_ids.add(p.id)

        # Strategy 3: Same brand, similar name (fuzzy)
        if brand and name and len(candidates) < self.max_candidates:
            from difflib import SequenceMatcher
            brand_products = list(
                self.db.scalars(
                    select(Product).where(Product.brand.ilike(brand))
                ).all()
            )
            name_lower = name.casefold()
            scored = []
            for p in brand_products:
                if p.id not in seen_ids and p.name:
                    score = SequenceMatcher(None, name_lower, p.name.casefold()).ratio()
                    if score >= 0.5:
                        scored.append((p, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            for p, _ in scored[: self.max_candidates - len(candidates)]:
                candidates.append(self._to_candidate(p))
                seen_ids.add(p.id)

        return candidates[: self.max_candidates]

    @staticmethod
    def _to_candidate(product: Product) -> ProductCandidate:
        specs = {}
        for spec in product.specifications:
            specs[spec.name] = spec.value
        return ProductCandidate(
            product_id=product.id,
            name=product.name or "",
            brand=product.brand,
            model=product.model,
            mpn=product.mpn,
            gtin=product.gtin,
            manufacturer_sku=product.manufacturer_sku,
            specifications=specs,
        )


# ── Identity Cache ─────────────────────────────────────────────────

class AIMatchCache:
    """Hash-based cache for AI match decisions.

    Prevents duplicate AI calls for the same (incoming, candidates) pair.
    Cache key = hash(incoming identity + candidate IDs + prompt_version).
    """

    def __init__(self) -> None:
        self._cache: dict[str, AIMatchResult] = {}

    @staticmethod
    def _build_key(request: AIMatchRequest) -> str:
        identity = {
            "name": request.incoming_name,
            "brand": request.incoming_brand,
            "model": request.incoming_model,
            "mpn": request.incoming_mpn,
            "gtin": request.incoming_gtin,
            "sku": request.incoming_sku,
            "candidate_ids": sorted(c.product_id for c in request.candidates),
            "prompt_version": request.prompt_version,
        }
        raw = json.dumps(identity, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def get(self, request: AIMatchRequest) -> AIMatchResult | None:
        key = self._build_key(request)
        return self._cache.get(key)

    def put(self, request: AIMatchRequest, result: AIMatchResult) -> None:
        key = self._build_key(request)
        self._cache[key] = result

    def __len__(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        self._cache.clear()


# ── Build AI Match Request ─────────────────────────────────────────

def build_ai_match_request(
    incoming: Any,
    candidates: list[ProductCandidate],
    prompt_version: str = "v1",
) -> AIMatchRequest:
    """Build a structured AIMatchRequest from an incoming offer."""
    specs = getattr(incoming, "specifications", None)
    incoming_specs = dict(specs) if specs else {}

    return AIMatchRequest(
        incoming_name=getattr(incoming, "name", "") or "",
        incoming_brand=getattr(incoming, "brand", None),
        incoming_model=getattr(incoming, "model", None),
        incoming_mpn=getattr(incoming, "mpn", None),
        incoming_gtin=getattr(incoming, "gtin", None),
        incoming_sku=getattr(incoming, "sku", None),
        incoming_specifications=incoming_specs,
        candidates=candidates,
        prompt_version=prompt_version,
    )
