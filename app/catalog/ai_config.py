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


@dataclass(frozen=True)
class AIResearchConfig:
    """Configuration for external technical spec research (stage 2).

    Centralizes how missing specifications are investigated and cross-validated
    across trusted sources. Only missing keys are researched; important keys can
    be cross-validated against a second source when one exists.
    """

    # Keys treated as important enough to cross-validate against 2+ sources.
    cross_validation_keys: tuple[str, ...] = (
        "processor",
        "processor_cores",
        "processor_threads",
        "processor_base_frequency",
        "processor_boost_frequency",
        "processor_cache",
        "processor_tdp",
        "gpu",
        "gpu_vram",
        "ram_capacity",
        "storage_capacity",
        "battery_capacity",
        "charging_wattage",
        "screen_size",
    )
    # Confidence when two independent sources agree.
    agreement_confidence: float = 0.95
    # Confidence for a single-source value.
    single_source_confidence: float = 0.90
    # Source priority tiers (lower number = consulted first / more trusted).
    # Filled from SpecSource.priority at runtime; these are the defaults used
    # when a priority is not explicitly set on the source.
    default_source_priority: int = 100


# Default research configuration
DEFAULT_RESEARCH_CONFIG = AIResearchConfig()
