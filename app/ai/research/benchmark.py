"""Benchmark normalization — Geekbench and friends.

Preserves the full provenance of ``BenchmarkResult`` so the assistant can say
"Geekbench 6 Single 1234 (measured 2026-08-01, source X)" without inventing a
score. No duplicate implementation: it only parses the free text already
collected as evidence.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.ai.evidence import Evidence

_GEKEBENCH_PATTERNS = ()


_SCORE_MARKS = (
    (re.compile(r"single[- ]core(?: score)?\s*[:=]?\s*(\d{2,6})"), "single_core"),
    (re.compile(r"multi[- ]core(?: score)?\s*[:=]?\s*(\d{2,6})"), "multi_core"),
)
_VERSION_BEHIND = 40


@dataclass(frozen=True)
class BenchmarkResult:
    """One traceable benchmark score extracted from external documents."""

    benchmark_name: str
    score: float
    score_type: str
    benchmark_version: str | None = None
    unit: str | None = "points"
    test_configuration: str | None = None
    source: str | None = None
    source_url: str | None = None
    confidence: float = 1.0
    measured_at: datetime | None = None
    verification_status: str = "review"

    def as_dict(self) -> dict[str, Any]:
        return {
            "benchmark_name": self.benchmark_name,
            "benchmark_version": self.benchmark_version,
            "score": self.score,
            "score_type": self.score_type,
            "unit": self.unit,
            "test_configuration": self.test_configuration,
            "source": self.source,
            "source_url": self.source_url,
            "confidence": self.confidence,
            "measured_at": self.measured_at.isoformat() if self.measured_at else None,
            "verification_status": self.verification_status,
        }


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value


def extract_geekbench(text: str, *, evidence: Evidence | None = None) -> list[BenchmarkResult]:
    """Extract measurable Geekbench scores from a text fragment."""
    if not text:
        return []
    normalized = _normalize(text)
    results: list[BenchmarkResult] = []
    seen: set[tuple[str, str, str | None]] = set()
    for pattern, score_type in _SCORE_MARKS:
        for match in re.finditer(pattern, normalized):
            try:
                score = float(match.group(1))
            except ValueError:
                continue
            name, version = _version_ahead_of(normalized, match.start())
            marker = (name, score_type, version)
            if marker in seen:
                continue
            seen.add(marker)
            results.append(
                BenchmarkResult(
                    benchmark_name=name,
                    benchmark_version=version,
                    score=score,
                    score_type=score_type,
                    source=evidence.source_name if evidence else None,
                    source_url=evidence.source_url if evidence else None,
                    confidence=evidence.confidence if evidence else 1.0,
                    verification_status="review",
                )
            )
    results.sort(key=lambda item: (item.benchmark_name, item.score_type))
    return results


def _version_ahead_of(normalized: str, position: int) -> tuple[str, str | None]:
    window = normalized[max(0, position - _VERSION_BEHIND) : position]
    mark = window.rfind("geekbench")
    if mark < 0:
        return "Geekbench", None
    rest = window[mark + len("geekbench") :]
    version_match = re.match(r"\s*(\d+)", rest)
    version = version_match.group(1) if version_match else None
    name = "Geekbench" if not version else f"Geekbench {version}"
    return name, version


def find_scores_in_evidence(items: list[Evidence]) -> list[BenchmarkResult]:
    """Scan collected evidence for comparable benchmark scores."""
    results: list[BenchmarkResult] = []
    for item in items:
        source_text = " ".join(part for part in (item.title, item.content) if part)
        results.extend(extract_geekbench(source_text, evidence=item))
    return results