"""Research query construction.

Builds search queries from catalog gaps: manufacturer documentation first,
then benchmarks, then reviews. Queries are deterministic (no LLM involved) and
each one carries the ``expected_type`` so results are classified consistently.

V4: the query construction now lives in :mod:`app.ai.research.query_planning`,
which also exposes topic-aware deep planning. This module keeps the historical
imports (``build_queries``, ``target_identity``) for backward compatibility.
"""

from __future__ import annotations

from app.ai.evidence import KnowledgeSourceType
from app.ai.research.query_planning import (
    plan_queries,
    target_identity,
    _tokens,
)
from app.ai.research.schemas import ResearchQuery, ResearchTarget
from app.ai.research.sources import MANUFACTURER_HOSTS, source_type_for_url


def build_queries(targets: list[ResearchTarget], message: str, *, max_queries: int = 3) -> list[ResearchQuery]:
    """Build up to ``max_queries`` research intents (light, backward-compatible).

    Delegates to :func:`plan_queries` with the default (light) depth, preserving
    the historical manufacturer > benchmark > review ladder behavior.
    """
    return plan_queries(targets, message, max_queries=max_queries, depth="light")


def manufacturer_first_domains(target: ResearchTarget) -> list[str]:
    """Candidate official domains for the target brand, if known."""
    brand = (target.brand or "").casefold().strip()
    if not brand:
        return []
    if brand in {"apple"}:
        return ["apple.com"]
    if brand in {"samsung", "samsung-electronics"}:
        return ["samsung.com"]
    if brand in {"asus", "asus-rog", "rog"}:
        return ["asus.com", "rog.asus.com"]
    if brand in {"lenovo"}:
        return ["lenovo.com"]
    if brand in {"hp", "hewlett-packard"}:
        return ["hp.com"]
    if brand in {"xiaomi", "poco", "redmi", "mi"}:
        return ["mi.com", "xiaomi.com"]
    try:
        return [host for host in MANUFACTURER_HOSTS if host.startswith(brand)]
    except Exception:
        return []


def is_official_source(url: str | None, target: ResearchTarget) -> bool:
    """True when the URL belongs to the target's own vendor domain."""
    if not url:
        return False
    source_type = source_type_for_url(url)
    domains = manufacturer_first_domains(target)
    if source_type != KnowledgeSourceType.MANUFACTURER or not domains:
        return False
    host = _host_of(url)
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _host_of(url: str) -> str:
    stripped = url.split("://", 1)[-1]
    return stripped.split("/", 1)[0].split(":", 1)[0].casefold()