"""AI matching configuration — thresholds, prompt version, provider settings.

All AI matching configuration centralized here.
No hardcoded values spread across files.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AIMatchingConfig:
    """Configuration for AI-assisted product matching."""

    # Confidence thresholds
    auto_match_threshold: float = 0.95
    ambiguous_threshold: float = 0.70

    # Candidate generation
    max_candidates: int = 8

    # Prompt versioning (increment when prompt changes)
    prompt_version: str = "v1"

    # Provider settings
    enabled: bool = True
    timeout_seconds: float = 15.0

    # Cache
    cache_enabled: bool = True

    def is_auto_match(self, confidence: float) -> bool:
        return confidence >= self.auto_match_threshold

    def is_ambiguous(self, confidence: float) -> bool:
        return self.ambiguous_threshold <= confidence < self.auto_match_threshold

    def is_no_match(self, confidence: float) -> bool:
        return confidence < self.ambiguous_threshold


# Default configuration
DEFAULT_AI_CONFIG = AIMatchingConfig()
