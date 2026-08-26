"""Mock AI matching provider for tests.

Returns configurable results without any external API calls.
"""

from __future__ import annotations

from app.catalog.ai_matching import (
    AIMatchRequest,
    AIMatchResult,
    AIMatchStatus,
    AIMatchingProvider,
)


class MockMatchingProvider(AIMatchingProvider):
    """Configurable mock for testing AI matching."""

    def __init__(
        self,
        decision: AIMatchStatus = AIMatchStatus.AMBIGUOUS,
        confidence: float = 0.8,
        matched_product_id: int | None = None,
        reason: str = "mock decision",
        evidence: dict | None = None,
        error: Exception | None = None,
    ):
        self.decision = decision
        self.confidence = confidence
        self.matched_product_id = matched_product_id
        self.reason = reason
        self.evidence = evidence or {}
        self.error = error
        self.call_count = 0
        self.last_request: AIMatchRequest | None = None

    def match(self, request: AIMatchRequest) -> AIMatchResult:
        self.call_count += 1
        self.last_request = request

        if self.error:
            raise self.error

        return AIMatchResult(
            decision=self.decision,
            confidence=self.confidence,
            matched_product_id=self.matched_product_id,
            reason=self.reason,
            evidence=self.evidence,
            model="mock-model",
            prompt_version=request.prompt_version,
        )
