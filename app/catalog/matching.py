"""Product matching — deterministic identity-first strategy.

Priority:
1. GTIN exact (strongest signal)
2. MPN + brand (with normalized variant comparison)
3. manufacturer_sku + brand (if it represents manufacturer identity)
4. normalized brand + model
5. fuzzy name similarity (candidates only, never auto-confirm)

Returns MatchResult with explicit status: MATCH, NO_MATCH, AMBIGUOUS.
Never converts AMBIGUOUS to MATCH automatically.

Conflict detection:
- GTIN points to product A, MPN points to product B → AMBIGUOUS with conflict info.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.identity import (
    normalize_brand,
    normalize_gtin,
    normalize_manufacturer_sku,
    normalize_model,
    normalize_mpn,
    mpn_matches,
)
from app.models.catalog import Product

log = logging.getLogger(__name__)


# ── Match result types ─────────────────────────────────────────────

class MatchStatus(StrEnum):
    MATCH = "match"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class MatchCandidate:
    """A fuzzy candidate with similarity score."""

    product: Product
    score: float
    strategy: str


@dataclass(frozen=True)
class MatchResult:
    """Result of product matching attempt."""

    status: MatchStatus
    product: Product | None = None
    strategy: str | None = None
    confidence: float = 0.0
    candidates: list[MatchCandidate] = field(default_factory=list)
    conflict: str | None = None

    @property
    def is_match(self) -> bool:
        return self.status == MatchStatus.MATCH

    @property
    def is_ambiguous(self) -> bool:
        return self.status == MatchStatus.AMBIGUOUS

    @property
    def is_no_match(self) -> bool:
        return self.status == MatchStatus.NO_MATCH


# ── Confidence thresholds ──────────────────────────────────────────

HIGH_CONFIDENCE = 0.92
MEDIUM_CONFIDENCE = 0.80


# ── ProductMatcher ─────────────────────────────────────────────────

class ProductMatcher:
    """Deterministic identity-first product matching.

    Returns MatchResult with explicit status.
    Never auto-merges AMBIGUOUS results.
    """

    def __init__(
        self,
        db: Session,
        high_threshold: float = HIGH_CONFIDENCE,
        medium_threshold: float = MEDIUM_CONFIDENCE,
    ):
        self.db = db
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold

    def match(self, incoming: Any, ai_matcher: Any | None = None) -> MatchResult:
        """Match incoming offer against existing products.

        Tries strategies in priority order. Returns first definitive result.
        Falls back to fuzzy candidates if no deterministic match found.

        If ai_matcher is provided and result is AMBIGUOUS, delegates to AI.
        AI is ONLY called for AMBIGUOUS — never for MATCH or NO_MATCH.
        """
        gtin = getattr(incoming, "gtin", None)
        mpn = getattr(incoming, "mpn", None)
        brand = getattr(incoming, "brand", None)
        model = getattr(incoming, "model", None)
        sku = getattr(incoming, "sku", None)
        sku_is_identity = getattr(incoming, "sku_is_identity", False)
        name = getattr(incoming, "name", None)

        # Strategy 1: GTIN (strongest)
        result = self.match_by_gtin(gtin)
        if result.status != MatchStatus.NO_MATCH:
            return result

        # Strategy 2: MPN + brand
        result = self.match_by_mpn_brand(mpn, brand)
        if result.status != MatchStatus.NO_MATCH:
            return result

        # Strategy 3: manufacturer_sku (only if it looks like a manufacturer ID)
        result = self.match_by_manufacturer_sku(sku, brand, sku_is_identity)
        if result.status != MatchStatus.NO_MATCH:
            return result

        # Strategy 4: normalized brand + model
        result = self.match_by_brand_model(brand, model)
        if result.status != MatchStatus.NO_MATCH:
            return result

        # Strategy 5: fuzzy candidates (never auto-confirm)
        candidates = self.find_candidates(name, brand)
        if candidates:
            best = candidates[0]
            if best.score >= self.high_threshold:
                result = MatchResult(
                    status=MatchStatus.AMBIGUOUS,
                    product=best.product,
                    strategy="fuzzy_high",
                    confidence=best.score,
                    candidates=candidates,
                )
            elif best.score >= self.medium_threshold:
                result = MatchResult(
                    status=MatchStatus.AMBIGUOUS,
                    strategy="fuzzy_medium",
                    confidence=best.score,
                    candidates=candidates,
                )
            else:
                result = MatchResult(
                    status=MatchStatus.NO_MATCH,
                    candidates=candidates,
                )
        else:
            result = MatchResult(status=MatchStatus.NO_MATCH)

        # AI fallback: ONLY for AMBIGUOUS
        if result.status == MatchStatus.AMBIGUOUS and ai_matcher is not None:
            return self._ai_fallback(incoming, result, ai_matcher)

        return result

    def _ai_fallback(
        self, incoming: Any, ambiguous_result: MatchResult, ai_matcher: Any
    ) -> MatchResult:
        """Delegate AMBIGUOUS case to AI matcher.

        Converts AIMatchResult back to MatchResult.
        On AI failure, returns the original AMBIGUOUS result (no merge).
        """
        from app.catalog.ai_matching import AIMatchStatus

        try:
            ai_result = ai_matcher.match(incoming)
        except Exception as e:
            log.warning("AI matcher error in fallback: %s", e)
            return ambiguous_result

        if ai_result.decision == AIMatchStatus.MATCH and ai_result.matched_product_id:
            # Verify the product still exists
            product = self.db.get(Product, ai_result.matched_product_id)
            if product is None:
                log.warning(
                    "AI matched product %d not found", ai_result.matched_product_id
                )
                return ambiguous_result
            return MatchResult(
                status=MatchStatus.MATCH,
                product=product,
                strategy="ai_match",
                confidence=ai_result.confidence,
                candidates=ambiguous_result.candidates,
                conflict=ai_result.reason,
            )
        elif ai_result.decision == AIMatchStatus.NO_MATCH:
            return MatchResult(
                status=MatchStatus.NO_MATCH,
                strategy="ai_no_match",
                confidence=ai_result.confidence,
                candidates=ambiguous_result.candidates,
                conflict=ai_result.reason,
            )
        else:
            # AI returned AMBIGUOUS or error → keep original
            return ambiguous_result

    def match_by_gtin(self, gtin: str | None) -> MatchResult:
        """Match by GTIN/EAN/UPC. Strongest signal."""
        norm = normalize_gtin(gtin)
        if not norm:
            return MatchResult(status=MatchStatus.NO_MATCH)

        product = self.db.scalar(select(Product).where(Product.gtin == norm))
        if product:
            return MatchResult(
                status=MatchStatus.MATCH,
                product=product,
                strategy="gtin",
                confidence=1.0,
            )
        return MatchResult(status=MatchStatus.NO_MATCH)

    def match_by_mpn_brand(
        self, mpn: str | None, brand: str | None
    ) -> MatchResult:
        """Match by MPN + brand using normalized variant comparison."""
        norm_mpn = normalize_mpn(mpn)
        norm_brand = normalize_brand(brand)
        if not norm_mpn or not norm_brand:
            return MatchResult(status=MatchStatus.NO_MATCH)

        # Find all products with matching brand
        brand_products = self.db.scalars(
            select(Product).where(Product.brand.ilike(brand))
        ).all()

        matches: list[Product] = []
        for product in brand_products:
            if product.mpn and mpn_matches(mpn, product.mpn):
                matches.append(product)

        if len(matches) == 1:
            return MatchResult(
                status=MatchStatus.MATCH,
                product=matches[0],
                strategy="mpn_brand",
                confidence=0.95,
            )
        if len(matches) > 1:
            return MatchResult(
                status=MatchStatus.AMBIGUOUS,
                strategy="mpn_brand",
                conflict=f"Multiple products with MPN={mpn}, brand={brand}: {[p.id for p in matches]}",
            )
        return MatchResult(status=MatchStatus.NO_MATCH)

    def match_by_manufacturer_sku(
        self, sku: str | None, brand: str | None, numeric_is_identity: bool = False
    ) -> MatchResult:
        """Match by manufacturer SKU + brand.

        Only matches if the SKU looks like a manufacturer identifier
        (not a store-internal numeric ID), UNLESS the source declared its
        numeric SKUs as reliable identity (numeric_is_identity=True).
        """
        norm_sku = normalize_manufacturer_sku(sku)
        if not norm_sku:
            return MatchResult(status=MatchStatus.NO_MATCH)

        if not numeric_is_identity:
            # Skip pure numeric IDs — those are store-internal
            if norm_sku.isdigit():
                return MatchResult(status=MatchStatus.NO_MATCH)

            # Must contain letters + digits (manufacturer SKU pattern)
            has_alpha = any(c.isalpha() for c in norm_sku)
            has_digit = any(c.isdigit() for c in norm_sku)
            if not (has_alpha and has_digit):
                return MatchResult(status=MatchStatus.NO_MATCH)

        norm_brand = normalize_brand(brand)
        if norm_brand:
            product = self.db.scalar(
                select(Product).where(
                    Product.manufacturer_sku == norm_sku,
                    Product.brand.ilike(brand),
                )
            )
        else:
            product = self.db.scalar(
                select(Product).where(Product.manufacturer_sku == norm_sku)
            )

        if product:
            return MatchResult(
                status=MatchStatus.MATCH,
                product=product,
                strategy="manufacturer_sku",
                confidence=0.90,
            )
        return MatchResult(status=MatchStatus.NO_MATCH)

    def match_by_brand_model(
        self, brand: str | None, model: str | None
    ) -> MatchResult:
        """Match by normalized brand + model."""
        norm_brand = normalize_brand(brand)
        norm_model = normalize_model(model)
        if not norm_brand or not norm_model:
            return MatchResult(status=MatchStatus.NO_MATCH)

        products = self.db.scalars(
            select(Product).where(
                Product.brand.ilike(brand),
                Product.model.ilike(model),
            )
        ).all()

        if len(products) == 1:
            return MatchResult(
                status=MatchStatus.MATCH,
                product=products[0],
                strategy="brand_model",
                confidence=0.85,
            )
        if len(products) > 1:
            return MatchResult(
                status=MatchStatus.AMBIGUOUS,
                strategy="brand_model",
                conflict=f"Multiple products with brand={brand}, model={model}: {[p.id for p in products]}",
            )
        return MatchResult(status=MatchStatus.NO_MATCH)

    def find_candidates(
        self,
        name: str | None,
        brand: str | None,
        limit: int = 5,
    ) -> list[MatchCandidate]:
        """Find fuzzy matching candidates by name similarity.

        Only searches within the same brand if brand is provided.
        Returns candidates sorted by score descending.
        Never auto-confirms — caller must decide.
        """
        if not name or not brand:
            return []

        norm_brand = normalize_brand(brand)
        if not norm_brand:
            return []

        # Fetch all products from same brand
        brand_products = list(
            self.db.scalars(
                select(Product).where(Product.brand.ilike(brand))
            ).all()
        )

        if not brand_products:
            return []

        name_lower = name.casefold()
        scored: list[MatchCandidate] = []

        for product in brand_products:
            product_name = product.name
            if not product_name:
                continue
            score = SequenceMatcher(
                None, name_lower, product_name.casefold()
            ).ratio()
            if score >= self.medium_threshold:
                scored.append(
                    MatchCandidate(
                        product=product,
                        score=score,
                        strategy="fuzzy_name",
                    )
                )

        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:limit]

    def check_conflict(
        self, incoming: Any
    ) -> str | None:
        """Check if incoming offer has conflicting identity signals.

        Example: GTIN points to product A, MPN+brand points to product B.
        Returns conflict description or None.
        """
        gtin = getattr(incoming, "gtin", None)
        mpn = getattr(incoming, "mpn", None)
        brand = getattr(incoming, "brand", None)

        gtin_result = self.match_by_gtin(gtin)
        mpn_result = self.match_by_mpn_brand(mpn, brand)

        if (
            gtin_result.is_match
            and mpn_result.is_match
            and gtin_result.product
            and mpn_result.product
            and gtin_result.product.id != mpn_result.product.id
        ):
            return (
                f"CONFLICT: GTIN={gtin} points to product {gtin_result.product.id}, "
                f"MPN={mpn}+brand={brand} points to product {mpn_result.product.id}"
            )

        return None

    # ── Backward compatibility ─────────────────────────────────────

    def match_legacy(self, incoming: Any) -> Product | None:
        """Legacy interface: returns Product or None.

        Prefer match() for new code.
        """
        result = self.match(incoming)
        if result.is_match:
            return result.product
        return None
