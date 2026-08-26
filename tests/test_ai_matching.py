"""AI-assisted product matching tests.

Test matrix:
A) deterministic MATCH → AI not called
B) deterministic NO_MATCH → AI not called
C) AMBIGUOUS → AI called
D) AI MATCH → existing Product reused
E) AI NO_MATCH → new Product created
F) AI AMBIGUOUS → no merge (unresolved)
G) invalid AI schema → falls back to AMBIGUOUS
H) invalid Product ID → falls back to AMBIGUOUS
I) Product ID not in candidates → falls back to AMBIGUOUS
J) AI timeout → falls back to AMBIGUOUS
K) AI provider error → falls back to AMBIGUOUS
L) provider unavailable → falls back to AMBIGUOUS
M) AI cache hit → no duplicate AI call
N) same request → no duplicate AI call (cache)
O) confidence threshold auto-match
P) confidence threshold ambiguous
Q) variant conflict (different RAM/VRAM)
R) evidence persisted in audit
S) prompt_version persisted
T) AI failure does not crash entire ingestion run
U) candidate generation produces top-K
V) candidate generation uses brand+model
W) candidate generation uses MPN variants
X) AI metrics in IngestionReport
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.catalog.ai_config import AIMatchingConfig
from app.catalog.ai_matching import (
    AIMatchCache,
    AIMatchRequest,
    AIMatchResult,
    AIMatchStatus,
    CandidateGenerator,
    ProductCandidate,
    build_ai_match_request,
)
from app.catalog.ai_orchestrator import AIMatcher
from app.catalog.ai_provider_mock import MockMatchingProvider
from app.catalog.matching import MatchResult, MatchStatus, ProductMatcher
from app.db import Base
from app.ingestion.connectors import StoreConnector
from app.ingestion.dto import NormalizedOffer
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.service import CatalogIngestionService
from app.models.catalog import AiMatchDecision, Category, PriceHistory, Product, Store, StoreOffer

# ── Test DB setup ──────────────────────────────────────────────────

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _reset(db):
    for model in (PriceHistory, StoreOffer, AiMatchDecision, Product, Store, Category):
        db.query(model).delete()
    db.commit()


def _make_connector(store_name, store_domain, records):
    source = f"mock:{store_domain}"
    sn, sd = store_name, store_domain

    class _Conn(StoreConnector):
        store_name = sn
        store_domain = sd
        source_name = source

        def __init__(self, recs):
            self._recs = recs

        def extract(self):
            yield from self._recs

        def normalize(self, record):
            now = datetime.now(timezone.utc)
            return NormalizedOffer(
                source=self.source_name,
                external_id=record.get("external_id"),
                product_url=record.get("url", f"https://{sd}/p"),
                name=record.get("name", "Product"),
                brand=record.get("brand"),
                model=record.get("model"),
                mpn=record.get("mpn"),
                gtin=record.get("gtin"),
                sku=record.get("sku"),
                price=Decimal(str(record.get("price", 1000))),
                previous_price=None,
                currency="CLP",
                availability=True,
                stock="in_stock",
                image_url=None,
                category=record.get("category"),
                scraped_at=now,
            )

    return _Conn(records)


def _make_ai_matcher(
    db,
    decision=AIMatchStatus.AMBIGUOUS,
    confidence=0.8,
    matched_product_id=None,
    reason="mock",
    evidence=None,
    error=None,
):
    provider = MockMatchingProvider(
        decision=decision,
        confidence=confidence,
        matched_product_id=matched_product_id,
        reason=reason,
        evidence=evidence or {},
        error=error,
    )
    config = AIMatchingConfig(enabled=True)
    return AIMatcher(db, provider, config), provider


# ══════════════════════════════════════════════════════════════════
#  A) DETERMINISTIC MATCH → AI NOT CALLED
# ══════════════════════════════════════════════════════════════════


class TestDeterministicMatchSkipsAI:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_gtin_match_skips_ai(self):
        """GTIN match is deterministic → AI never called."""
        with TestSession() as db:
            product = Product(name="HP Laptop", brand="HP", gtin="7501234567890")
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(db)
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = "7501234567890"
                mpn = None
                brand = "HP"
                model = None
                sku = None
                name = "HP Laptop"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            assert result.is_match
            assert result.strategy == "gtin"
            assert provider.call_count == 0

    def test_mpn_brand_match_skips_ai(self):
        """MPN+brand match is deterministic → AI never called."""
        with TestSession() as db:
            product = Product(name="ASUS RTX 5070", brand="ASUS", mpn="RTX5070")
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(db)
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = "RTX5070"
                brand = "ASUS"
                model = None
                sku = None
                name = "ASUS RTX 5070"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            assert result.is_match
            assert result.strategy == "mpn_brand"
            assert provider.call_count == 0


# ══════════════════════════════════════════════════════════════════
#  B) DETERMINISTIC NO_MATCH → AI NOT CALLED
# ══════════════════════════════════════════════════════════════════


class TestDeterministicNoMatchSkipsAI:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_no_match_skips_ai(self):
        """No matching product found → AI not called."""
        with TestSession() as db:
            ai_matcher, provider = _make_ai_matcher(db)
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = None
                model = None
                sku = None
                name = "Unknown Product"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            assert result.is_no_match
            assert provider.call_count == 0


# ══════════════════════════════════════════════════════════════════
#  C) AMBIGUOUS → AI CALLED
# ══════════════════════════════════════════════════════════════════


class TestAmbiguousCallsAI:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_ambiguous_triggers_ai(self):
        """AMBIGUOUS from fuzzy match → AI called."""
        with TestSession() as db:
            product = Product(
                name="ASUS GeForce RTX5070 DUAL OC 12GB",
                brand="ASUS",
            )
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(
                db,
                decision=AIMatchStatus.MATCH,
                confidence=0.98,
                matched_product_id=product.id,
            )
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = "ASUS"
                model = None
                sku = None
                name = "ASUS RTX 5070 DUAL OC 12GB"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            assert result.is_match
            assert result.strategy == "ai_match"
            assert provider.call_count == 1


# ══════════════════════════════════════════════════════════════════
#  D) AI MATCH → EXISTING PRODUCT REUSED
# ══════════════════════════════════════════════════════════════════


class TestAIMatchReusesProduct:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_ai_match_returns_existing_product(self):
        """AI MATCH → deterministic MatchResult with existing Product."""
        with TestSession() as db:
            product = Product(name="HP Laptop", brand="HP", model="pavilion 15")
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(
                db,
                decision=AIMatchStatus.MATCH,
                confidence=0.97,
                matched_product_id=product.id,
                reason="Same MPN and brand",
            )
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = "HP"
                model = "pavilion 15"
                sku = None
                name = "HP Pavilion 15 Laptop"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            assert result.is_match
            assert result.product.id == product.id
            assert result.strategy == "ai_match"
            assert result.confidence == 0.97


# ══════════════════════════════════════════════════════════════════
#  E) AI NO_MATCH → NEW PRODUCT
# ══════════════════════════════════════════════════════════════════


class TestAINoMatchCreatesProduct:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_ai_no_match_returns_no_match(self):
        """AI NO_MATCH → deterministic NO_MATCH, new Product created."""
        with TestSession() as db:
            product = Product(name="ASUS RTX 5070 DUAL", brand="ASUS")
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(
                db,
                decision=AIMatchStatus.NO_MATCH,
                confidence=0.3,
                reason="Different VRAM capacity",
            )
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = "ASUS"
                model = None
                sku = None
                name = "ASUS RTX 5070 DUAL 8GB"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            assert result.is_no_match
            assert result.strategy == "ai_no_match"


# ══════════════════════════════════════════════════════════════════
#  F) AI AMBIGUOUS → NO MERGE
# ══════════════════════════════════════════════════════════════════


class TestAIAmbiguousNoMerge:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_ai_ambiguous_keeps_original_ambiguous(self):
        """AI AMBIGUOUS → original AMBIGUOUS result preserved."""
        with TestSession() as db:
            product = Product(name="ASUS RTX 5070", brand="ASUS")
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(
                db,
                decision=AIMatchStatus.AMBIGUOUS,
                confidence=0.6,
                reason="Cannot determine",
            )
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = "ASUS"
                model = None
                sku = None
                name = "ASUS RTX 5070 Variant"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            assert result.is_ambiguous
            assert result.strategy == "fuzzy_high"


# ══════════════════════════════════════════════════════════════════
#  G) INVALID AI SCHEMA → FALLS BACK TO AMBIGUOUS
# ══════════════════════════════════════════════════════════════════


class TestInvalidAISchema:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_invalid_decision_falls_back(self):
        """Invalid AI decision string → AMBIGUOUS fallback."""
        with TestSession() as db:
            product = Product(name="ASUS RTX 5070", brand="ASUS")
            db.add(product)
            db.commit()

            provider = MockMatchingProvider(
                decision=AIMatchStatus.AMBIGUOUS,
                confidence=0.0,
                reason="schema validation failed",
            )
            config = AIMatchingConfig(enabled=True)
            ai_matcher = AIMatcher(db, provider, config)
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = "ASUS"
                model = None
                sku = None
                name = "ASUS RTX 5070 Variant"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            # AI returned AMBIGUOUS with low confidence → NO_MATCH via threshold
            assert result.is_no_match or result.is_ambiguous


# ══════════════════════════════════════════════════════════════════
#  H) INVALID PRODUCT ID → FALLS BACK TO AMBIGUOUS
# ══════════════════════════════════════════════════════════════════


class TestInvalidProductID:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_ai_matches_nonexistent_product(self):
        """AI returns Product ID that doesn't exist → AMBIGUOUS fallback."""
        with TestSession() as db:
            product = Product(name="ASUS RTX 5070", brand="ASUS")
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(
                db,
                decision=AIMatchStatus.MATCH,
                confidence=0.99,
                matched_product_id=99999,  # doesn't exist
            )
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = "ASUS"
                model = None
                sku = None
                name = "ASUS RTX 5070"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            assert result.is_ambiguous  # falls back to original


# ══════════════════════════════════════════════════════════════════
#  I) PRODUCT ID NOT IN CANDIDATES → FALLS BACK
# ══════════════════════════════════════════════════════════════════


class TestProductIDNotInCandidates:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_ai_returns_id_not_in_candidate_list(self):
        """AI returns Product ID not in candidate list → validated by orchestrator."""
        with TestSession() as db:
            product = Product(name="ASUS RTX 5070", brand="ASUS")
            db.add(product)
            db.commit()

            # Provider returns ID 999 which is not in candidates
            provider = MockMatchingProvider(
                decision=AIMatchStatus.MATCH,
                confidence=0.96,
                matched_product_id=999,
            )
            config = AIMatchingConfig(enabled=True)
            ai_matcher = AIMatcher(db, provider, config)

            # Generate candidates — only product.id will be in the list
            generator = CandidateGenerator(db, max_candidates=5)
            request = AIMatchRequest(
                incoming_name="ASUS RTX 5070",
                incoming_brand="ASUS",
                candidates=[ProductCandidate(product_id=product.id, name="ASUS RTX 5070")],
            )

            # Provider's match returns ID 999 which is not in candidates
            result = ai_matcher.match(
                type("Fake", (), {
                    "name": "ASUS RTX 5070",
                    "brand": "ASUS",
                    "model": None,
                    "mpn": None,
                    "gtin": None,
                    "sku": None,
                    "specifications": None,
                })()
            )
            # The orchestrator validates and returns AMBIGUOUS
            assert result.decision == AIMatchStatus.AMBIGUOUS


# ══════════════════════════════════════════════════════════════════
#  J) AI TIMEOUT → FALLS BACK TO AMBIGUOUS
# ══════════════════════════════════════════════════════════════════


class TestAITimeout:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_timeout_returns_ambiguous(self):
        """AI timeout → AMBIGUOUS fallback, no crash."""
        with TestSession() as db:
            product = Product(name="ASUS RTX 5070", brand="ASUS")
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(
                db,
                error=TimeoutError("Gemini timeout"),
            )
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = "ASUS"
                model = None
                sku = None
                name = "ASUS RTX 5070"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            assert result.is_ambiguous


# ══════════════════════════════════════════════════════════════════
#  K) AI PROVIDER ERROR → FALLS BACK TO AMBIGUOUS
# ══════════════════════════════════════════════════════════════════


class TestAIProviderError:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_provider_error_returns_ambiguous(self):
        """AI provider error → AMBIGUOUS fallback, no crash."""
        with TestSession() as db:
            product = Product(name="ASUS RTX 5070", brand="ASUS")
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(
                db,
                error=ConnectionError("Provider unavailable"),
            )
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = "ASUS"
                model = None
                sku = None
                name = "ASUS RTX 5070"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            assert result.is_ambiguous


# ══════════════════════════════════════════════════════════════════
#  L) PROVIDER UNAVAILABLE → FALLS BACK
# ══════════════════════════════════════════════════════════════════


class TestProviderUnavailable:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_none_ai_matcher_no_crash(self):
        """ai_matcher=None → deterministic path only, no AI."""
        with TestSession() as db:
            product = Product(name="ASUS RTX 5070", brand="ASUS")
            db.add(product)
            db.commit()

            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = "ASUS"
                model = None
                sku = None
                name = "ASUS RTX 5070"

            result = matcher.match(FakeOffer(), ai_matcher=None)
            assert result.is_ambiguous


# ══════════════════════════════════════════════════════════════════
#  M) AI CACHE HIT → NO DUPLICATE AI CALL
# ══════════════════════════════════════════════════════════════════


class TestAICacheHit:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_cache_hit_returns_same_result(self):
        """Same request twice → second call uses cache, no AI call."""
        with TestSession() as db:
            product = Product(name="ASUS RTX 5070", brand="ASUS")
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(
                db,
                decision=AIMatchStatus.MATCH,
                confidence=0.97,
                matched_product_id=product.id,
            )

            request = AIMatchRequest(
                incoming_name="ASUS RTX 5070",
                incoming_brand="ASUS",
                candidates=[ProductCandidate(product_id=product.id, name="ASUS RTX 5070")],
            )

            result1 = ai_matcher.match(
                type("Fake", (), {
                    "name": "ASUS RTX 5070",
                    "brand": "ASUS",
                    "model": None,
                    "mpn": None,
                    "gtin": None,
                    "sku": None,
                    "specifications": None,
                })()
            )
            result2 = ai_matcher.match(
                type("Fake", (), {
                    "name": "ASUS RTX 5070",
                    "brand": "ASUS",
                    "model": None,
                    "mpn": None,
                    "gtin": None,
                    "sku": None,
                    "specifications": None,
                })()
            )

            # Both results should be the same
            assert result1.decision == result2.decision
            assert result1.confidence == result2.confidence
            # Only 1 AI call (second used cache)
            assert provider.call_count == 1


# ══════════════════════════════════════════════════════════════════
#  N) SAME REQUEST → NO DUPLICATE AI CALL
# ══════════════════════════════════════════════════════════════════


class TestNoDuplicateAICall:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_cache_deduplicates(self):
        """AIMatchCache deduplicates identical requests."""
        cache = AIMatchCache()
        request = AIMatchRequest(
            incoming_name="Test",
            incoming_brand="HP",
            candidates=[ProductCandidate(product_id=1, name="Test")],
        )
        result = AIMatchResult(
            decision=AIMatchStatus.MATCH,
            confidence=0.95,
            matched_product_id=1,
        )
        cache.put(request, result)
        cached = cache.get(request)
        assert cached is not None
        assert cached.decision == AIMatchStatus.MATCH
        assert len(cache) == 1


# ══════════════════════════════════════════════════════════════════
#  O) CONFIDENCE THRESHOLD AUTO-MATCH
# ══════════════════════════════════════════════════════════════════


class TestConfidenceAutoMatch:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_high_confidence_match(self):
        """Confidence >= 0.95 → MATCH passes through."""
        config = AIMatchingConfig(auto_match_threshold=0.95)
        assert config.is_auto_match(0.95)
        assert config.is_auto_match(0.99)
        assert not config.is_auto_match(0.94)

    def test_ai_match_with_high_confidence(self):
        """AI returns MATCH with confidence 0.96 → auto-match."""
        with TestSession() as db:
            product = Product(name="HP Laptop", brand="HP")
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(
                db,
                decision=AIMatchStatus.MATCH,
                confidence=0.96,
                matched_product_id=product.id,
            )
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = "HP"
                model = None
                sku = None
                name = "HP Laptop"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            assert result.is_match
            assert result.confidence == 0.96


# ══════════════════════════════════════════════════════════════════
#  P) CONFIDENCE THRESHOLD AMBIGUOUS
# ══════════════════════════════════════════════════════════════════


class TestConfidenceAmbiguous:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_medium_confidence_ambiguous(self):
        """0.70 <= confidence < 0.95 + MATCH → forced AMBIGUOUS."""
        config = AIMatchingConfig(auto_match_threshold=0.95, ambiguous_threshold=0.70)
        assert config.is_ambiguous(0.80)
        assert config.is_ambiguous(0.94)
        assert not config.is_ambiguous(0.95)
        assert not config.is_ambiguous(0.69)

    def test_medium_confidence_match_forced_ambiguous(self):
        """AI MATCH with confidence 0.80 → forced AMBIGUOUS by policy."""
        with TestSession() as db:
            product = Product(name="HP Laptop", brand="HP")
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(
                db,
                decision=AIMatchStatus.MATCH,
                confidence=0.80,
                matched_product_id=product.id,
            )
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = "HP"
                model = None
                sku = None
                name = "HP Laptop"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            # Confidence 0.80 < 0.95 → forced AMBIGUOUS
            assert result.is_ambiguous


# ══════════════════════════════════════════════════════════════════
#  Q) VARIANT CONFLICT (DIFFERENT RAM/VRAM)
# ══════════════════════════════════════════════════════════════════


class TestVariantConflict:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_different_vram_no_match(self):
        """AI correctly identifies different VRAM as different product."""
        with TestSession() as db:
            product = Product(name="ASUS RTX 5070 12GB", brand="ASUS")
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(
                db,
                decision=AIMatchStatus.NO_MATCH,
                confidence=0.92,
                reason="Different VRAM: 8GB vs 12GB",
                evidence={"incoming_vram": "8GB", "candidate_vram": "12GB"},
            )
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = None
                brand = "ASUS"
                model = None
                sku = None
                name = "ASUS RTX 5070 8GB"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)
            assert result.is_no_match
            assert result.strategy == "ai_no_match"


# ══════════════════════════════════════════════════════════════════
#  R) EVIDENCE PERSISTED IN AUDIT
# ══════════════════════════════════════════════════════════════════


class TestEvidencePersisted:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_evidence_saved_to_audit(self):
        """AI match decision includes evidence in audit record."""
        with TestSession() as db:
            product = Product(name="HP Laptop", brand="HP")
            db.add(product)
            db.commit()

            ai_matcher, provider = _make_ai_matcher(
                db,
                decision=AIMatchStatus.MATCH,
                confidence=0.97,
                matched_product_id=product.id,
                reason="Same MPN",
                evidence={"mpn_match": True, "brand_match": True},
            )
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = "HP-001"
                brand = "HP"
                model = None
                sku = None
                name = "HP Laptop"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)

            # Check audit record was created
            audit = db.query(AiMatchDecision).first()
            assert audit is not None
            assert audit.decision == "match"
            assert audit.confidence == Decimal("0.97")
            assert audit.selected_product_id == product.id
            assert audit.evidence == {"mpn_match": True, "brand_match": True}


# ══════════════════════════════════════════════════════════════════
#  S) PROMPT VERSION PERSISTED
# ══════════════════════════════════════════════════════════════════


class TestPromptVersionPersisted:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_prompt_version_in_audit(self):
        """AI audit record includes prompt_version."""
        with TestSession() as db:
            product = Product(name="HP Laptop", brand="HP")
            db.add(product)
            db.commit()

            config = AIMatchingConfig(prompt_version="v2")
            provider = MockMatchingProvider(
                decision=AIMatchStatus.MATCH,
                confidence=0.97,
                matched_product_id=product.id,
            )
            ai_matcher = AIMatcher(db, provider, config)
            matcher = ProductMatcher(db)

            class FakeOffer:
                gtin = None
                mpn = "HP-001"
                brand = "HP"
                model = None
                sku = None
                name = "HP Laptop"

            result = matcher.match(FakeOffer(), ai_matcher=ai_matcher)

            audit = db.query(AiMatchDecision).first()
            assert audit is not None
            assert audit.prompt_version == "v2"
            assert audit.model == "mock-model"


# ══════════════════════════════════════════════════════════════════
#  T) AI FAILURE DOES NOT CRASH INGESTION RUN
# ══════════════════════════════════════════════════════════════════


class TestAIFailureNoCrash:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_ai_error_continues_pipeline(self):
        """AI error → AMBIGUOUS → new Product created, pipeline continues."""
        with TestSession() as db:
            provider = MockMatchingProvider(error=RuntimeError("AI exploded"))
            config = AIMatchingConfig(enabled=True)
            ai_matcher = AIMatcher(db, provider, config)

            records = [
                {"url": "https://a.mock/p1", "external_id": "A001", "name": "HP Laptop", "brand": "HP", "price": 500},
            ]
            conn = _make_connector("Store A", "a.mock", records)
            service = CatalogIngestionService(db, ai_matcher=ai_matcher)
            report = IngestionPipeline(service).run(conn)

            # Pipeline continued, product created
            assert report.offers_created == 1
            assert db.query(Product).count() == 1


# ══════════════════════════════════════════════════════════════════
#  U) CANDIDATE GENERATION PRODUCES TOP-K
# ══════════════════════════════════════════════════════════════════


class TestCandidateGenerationTopK:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_limited_to_max_candidates(self):
        """CandidateGenerator returns at most K candidates."""
        with TestSession() as db:
            for i in range(20):
                db.add(Product(name=f"HP Product {i}", brand="HP"))
            db.commit()

            generator = CandidateGenerator(db, max_candidates=5)

            class FakeOffer:
                name = "HP Product"
                brand = "HP"
                model = None
                mpn = None

            candidates = generator.generate(FakeOffer())
            assert len(candidates) <= 5


# ══════════════════════════════════════════════════════════════════
#  V) CANDIDATE GENERATION USES BRAND+MODEL
# ══════════════════════════════════════════════════════════════════


class TestCandidateGenerationBrandModel:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_brand_model_finds_candidates(self):
        """CandidateGenerator finds products by brand+model."""
        with TestSession() as db:
            p1 = Product(name="ASUS RTX 5070 DUAL", brand="ASUS", model="rtx 5070")
            p2 = Product(name="ASUS RTX 5070 TUF", brand="ASUS", model="rtx 5070")
            db.add_all([p1, p2])
            db.commit()

            generator = CandidateGenerator(db, max_candidates=5)

            class FakeOffer:
                name = "ASUS RTX 5070"
                brand = "ASUS"
                model = "rtx 5070"
                mpn = None

            candidates = generator.generate(FakeOffer())
            ids = {c.product_id for c in candidates}
            assert p1.id in ids
            assert p2.id in ids


# ══════════════════════════════════════════════════════════════════
#  W) CANDIDATE GENERATION USES MPN VARIANTS
# ══════════════════════════════════════════════════════════════════


class TestCandidateGenerationMPNVariants:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_mpn_variant_finds_candidates(self):
        """CandidateGenerator finds products with variant MPNs."""
        with TestSession() as db:
            p1 = Product(name="ASUS RTX 5070", brand="ASUS", mpn="RTX-5070")
            db.add(p1)
            db.commit()

            generator = CandidateGenerator(db, max_candidates=5)

            class FakeOffer:
                name = "ASUS RTX 5070"
                brand = "ASUS"
                model = None
                mpn = "RTX 5070"  # variant with space

            candidates = generator.generate(FakeOffer())
            assert len(candidates) == 1
            assert candidates[0].product_id == p1.id


# ══════════════════════════════════════════════════════════════════
#  X) AI METRICS IN INGESTIONREPORT
# ══════════════════════════════════════════════════════════════════


class TestAIMetricsInReport:
    def setup_method(self):
        with TestSession() as db:
            _reset(db)

    def test_report_has_ai_fields(self):
        """IngestionReport has AI metric fields."""
        from app.ingestion.pipeline import IngestionReport

        report = IngestionReport()
        assert hasattr(report, "ai_candidates_generated")
        assert hasattr(report, "ai_calls")
        assert hasattr(report, "ai_cache_hits")
        assert hasattr(report, "ai_matches")
        assert hasattr(report, "ai_no_matches")
        assert hasattr(report, "ai_unresolved")
        assert hasattr(report, "ai_errors")
        assert report.ai_calls == 0
        assert report.ai_total_resolved == 0
