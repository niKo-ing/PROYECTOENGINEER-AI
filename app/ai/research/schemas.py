"""Domain models for the Web Research pipeline.

These types are provider-agnostic and never require network access. They reuse
``Evidence`` / ``KnowledgeSourceType`` from ``app.ai.evidence`` so the assistant
never loses provenance between catalog data and external research.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class SearchResult:
    """One link returned by a web search provider."""

    title: str
    url: str
    snippet: str = ""
    source_type: str | None = None
    found_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ResearchTarget:
    """A catalog product that may need external information.

    ``specs`` is the flattened label->value map already delivered to the LLM, so
    the research layer reuses the same facts and never re-asks the model.
    """

    id: int
    name: str
    brand: str | None = None
    model: str | None = None
    category: str | None = None
    specs: dict[str, str] | None = None


@dataclass(frozen=True)
class ResearchQuery:
    """A single search intent with its expected source type."""

    query: str
    expected_type: str
    target_id: int | None = None
    claim: str | None = None


@dataclass
class ResearchReport:
    """Aggregated outcome of one research pass over catalog gaps."""

    used: bool
    evidence: list = field(default_factory=list)  # list[Evidence]
    verdicts: list = field(default_factory=list)  # list[ClaimVerdict]
    queries_run: int = 0
    context: str | None = None
    note: str | None = None

    @property
    def sources(self) -> list[dict]:
        return [item.as_dict() for item in self.evidence]