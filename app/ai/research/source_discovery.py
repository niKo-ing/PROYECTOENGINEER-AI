"""Research query construction.

Builds search queries from catalog gaps: manufacturer documentation first,
then benchmarks, then reviews. Queries are deterministic (no LLM involved) and
each one carries the ``expected_type`` so results are classified consistently.
"""

from __future__ import annotations

from app.ai.evidence import KnowledgeSourceType
from app.ai.research.schemas import ResearchQuery, ResearchTarget
from app.ai.research.sources import MANUFACTURER_HOSTS, source_type_for_url

_BENCHMARK_TERMS = (
    "benchmark",
    "geekbench",
    "score",
    "rendimiento",
    "performance",
    "puntaje",
    "tests",
)


def target_identity(target: ResearchTarget) -> tuple[str | None, str | None]:
    """Return the best (brand, model-ish) identity for a catalog target.

    The model falls back to a compact token slice of the product name when the
    ``model`` column is empty, always excluding the brand tokens so the variant
    identifiers stay distinguishable.
    """
    brand = (target.brand or "").strip() or None
    model = (target.model or "").strip() or None
    if model:
        return brand, model
    name_model = _fallback_model(target.name, brand=brand)
    if name_model:
        return brand, name_model
    return brand, None


def _fallback_model(name: str, brand: str | None = None) -> str | None:
    tokens = [token for token in _tokens(name) if len(token) >= 3]
    if not tokens:
        return None
    brand_tokens = {token.casefold() for token in _tokens(brand or "")}
    meaningful = [
        token
        for token in tokens
        if _probably_meaningful(token) and token.casefold() not in brand_tokens
    ]
    return " ".join(meaningful[:4]) if meaningful else " ".join(tokens[:4])


def _probably_meaningful(token: str) -> bool:
    lowered = token.casefold()
    if any(ch.isdigit() for ch in token):
        return True
    return lowered not in {
        "the", "edition", "version", "with", "for", "and", "gaming", "laptop",
        "desktop", "mobile", "notebook", "smartphone", "phone", "tablet",
    }


def build_queries(targets: list[ResearchTarget], message: str, *, max_queries: int = 3) -> list[ResearchQuery]:
    """Build up to ``max_queries`` research intents for the given targets."""
    queries: list[ResearchQuery] = []
    for target in targets[: max_queries]:
        brand, model = target_identity(target)
        if not model:
            continue
        label = f"{brand} {model}".strip() if brand else model
        queries.append(
            ResearchQuery(query=f"{label} specifications", expected_type=KnowledgeSourceType.MANUFACTURER.value, target_id=target.id)
        )
        if any(term in message.casefold() for term in _BENCHMARK_TERMS):
            queries.append(
                ResearchQuery(query=f"{label} benchmark Geekbench 6", expected_type=KnowledgeSourceType.BENCHMARK.value, target_id=target.id)
            )
        queries.append(
            ResearchQuery(query=f"{label} review", expected_type=KnowledgeSourceType.REVIEW.value, target_id=target.id)
        )
        if len(queries) >= max_queries:
            break
    return queries[:max_queries]


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


def _tokens(value: str) -> list[str]:
    import re

    return re.findall(r"[a-zA-Z0-9]+", value)