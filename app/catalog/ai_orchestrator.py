"""AI Matcher orchestrator — candidate gen → AI call → validate → cache → audit.

This is the entry point for AI-assisted matching. It is ONLY called
when the deterministic ProductMatcher returns AMBIGUOUS.

Flow:
    AMBIGUOUS from deterministic matcher
        ↓
    CandidateGenerator → top K candidates
        ↓
    AIMatchCache check → hit? return cached
        ↓
    AIMatchingProvider.match() → AIMatchResult
        ↓
    Validate result (schema, candidate IDs)
        ↓
    Cache result
        ↓
    Audit persistence (best-effort)
        ↓
    Return AIMatchResult
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.catalog.ai_config import AIMatchingConfig, DEFAULT_AI_CONFIG
from app.catalog.ai_matching import (
    AIMatchCache,
    AIMatchRequest,
    AIMatchResult,
    AIMatchStatus,
    AIMatchingProvider,
    CandidateGenerator,
    build_ai_match_request,
)

log = logging.getLogger(__name__)


class AIMatcher:
    """Orchestrates AI-assisted product matching.

    Dependencies:
    - CandidateGenerator (deterministic, local)
    - AIMatchingProvider (AI, remote)
    - AIMatchCache (local, in-memory)
    - DB session for audit persistence
    """

    def __init__(
        self,
        db: Session,
        provider: AIMatchingProvider,
        config: AIMatchingConfig | None = None,
    ):
        self.db = db
        self.provider = provider
        self.config = config or DEFAULT_AI_CONFIG
        self.candidate_generator = CandidateGenerator(db, self.config.max_candidates)
        self.cache = AIMatchCache() if self.config.cache_enabled else None

    def match(self, incoming: Any) -> AIMatchResult:
        """Run AI matching for an AMBIGUOUS case.

        Returns AIMatchResult with decision, confidence, and evidence.
        On any failure, returns AMBIGUOUS (never crashes the pipeline).
        """
        if not self.config.enabled:
            return AIMatchResult(
                decision=AIMatchStatus.AMBIGUOUS,
                confidence=0.0,
                reason="AI matching disabled",
            )

        try:
            candidates = self.candidate_generator.generate(incoming)
        except Exception as e:
            log.warning("Candidate generation failed: %s", e)
            return AIMatchResult(
                decision=AIMatchStatus.AMBIGUOUS,
                confidence=0.0,
                reason=f"Candidate generation error: {type(e).__name__}",
            )

        if not candidates:
            return AIMatchResult(
                decision=AIMatchStatus.NO_MATCH,
                confidence=0.8,
                reason="No candidates found for AI comparison",
            )

        request = build_ai_match_request(
            incoming, candidates, self.config.prompt_version
        )

        candidate_ids = {c.product_id for c in candidates}

        # Check cache
        if self.cache is not None:
            cached = self.cache.get(request)
            if cached is not None:
                log.debug("AI match cache hit for %s", request.incoming_name)
                return cached

        # Call AI provider
        try:
            result = self.provider.match(request)
        except Exception as e:
            log.warning("AI provider error: %s: %s", type(e).__name__, e)
            return AIMatchResult(
                decision=AIMatchStatus.AMBIGUOUS,
                confidence=0.0,
                reason=f"AI provider error: {type(e).__name__}",
            )

        # Validate matched_product_id is in the candidate set
        if (
            result.matched_product_id is not None
            and result.matched_product_id not in candidate_ids
        ):
            log.warning(
                "AI returned product_id %d not in candidate set %s",
                result.matched_product_id,
                candidate_ids,
            )
            return AIMatchResult(
                decision=AIMatchStatus.AMBIGUOUS,
                confidence=0.0,
                reason=f"AI selected product {result.matched_product_id} not in candidate set",
                evidence=result.evidence,
                model=result.model,
                prompt_version=result.prompt_version,
            )

        # Apply confidence policy
        result = self._apply_confidence_policy(result)

        # Cache result
        if self.cache is not None:
            self.cache.put(request, result)

        # Audit persistence (best-effort, never blocks)
        self._persist_audit(request, result)

        return result

    def _apply_confidence_policy(self, result: AIMatchResult) -> AIMatchResult:
        """Apply confidence thresholds to AI result.

        AI confidence is a signal, not mathematical truth.
        We use thresholds to gate automatic matching.
        """
        if result.confidence >= self.config.auto_match_threshold:
            # High confidence: keep as MATCH
            return result
        elif result.confidence >= self.config.ambiguous_threshold:
            # Medium confidence: AMBIGUOUS regardless of AI decision
            if result.decision == AIMatchStatus.MATCH:
                return AIMatchResult(
                    decision=AIMatchStatus.AMBIGUOUS,
                    confidence=result.confidence,
                    matched_product_id=result.matched_product_id,
                    reason=f"Confidence {result.confidence:.2f} below auto-match threshold: {result.reason}",
                    evidence=result.evidence,
                    model=result.model,
                    prompt_version=result.prompt_version,
                )
            return result
        else:
            # Low confidence: NO_MATCH / unresolved
            return AIMatchResult(
                decision=AIMatchStatus.NO_MATCH,
                confidence=result.confidence,
                reason=f"Confidence {result.confidence:.2f} below ambiguous threshold: {result.reason}",
                evidence=result.evidence,
                model=result.model,
                prompt_version=result.prompt_version,
            )

    def _persist_audit(self, request: AIMatchRequest, result: AIMatchResult) -> None:
        """Persist AI match decision for audit. Best-effort, never blocks."""
        try:
            from app.models.catalog import AiMatchDecision

            decision = AiMatchDecision(
                incoming_name=request.incoming_name,
                incoming_brand=request.incoming_brand,
                incoming_model=request.incoming_model,
                incoming_mpn=request.incoming_mpn,
                incoming_gtin=request.incoming_gtin,
                candidate_ids=[c.product_id for c in request.candidates],
                selected_product_id=result.matched_product_id,
                decision=result.decision.value,
                confidence=result.confidence,
                model=result.model,
                prompt_version=result.prompt_version,
                reason=result.reason,
                evidence=result.evidence,
            )
            self.db.add(decision)
            self.db.flush()
        except Exception as e:
            log.warning("AI audit persistence failed: %s", e)
