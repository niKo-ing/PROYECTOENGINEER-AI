"""Re-ranking of research candidates.

Combines semantic product/variant match, source quality (manufacturer-first)
and freshness into a single deterministic score — no embeddings required.
"""

from __future__ import annotations

import re
import unicodedata

from app.ai.evidence import KnowledgeSourceType
from app.ai.research.schemas import ResearchTarget, SearchResult
from app.ai.research.source_discovery import is_official_source
from app.ai.research.sources import source_priority, source_type_for_url, variant_matches

_HAYSTACK_STOP = {
    "with", "the", "a", "an", "for", "and", "vs", "review", "specs", "specifications",
    "benchmark", "geekbench", "score", "laptop", "desktop", "mobile", "smartphone",
    "phone", "tablet", "buy", "price", "test", "tests", "results", "performance",
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _normalize(value))) - _HAYSTACK_STOP


def score_result(result: SearchResult, target: ResearchTarget) -> float:
    """Deterministic relevance score for one search result against a target."""
    brand, model = (target.brand or "").casefold(), (target.model or "").casefold()
    if not model:
        model = _fallback_model(target.name)
    haystack_tokens = _tokens(f"{result.title} {result.snippet}" + (f" {result.url}" if result.url else ""))

    model_tokens = _tokens(model)
    brand_tokens = _tokens(brand)
    covered = len(model_tokens & haystack_tokens)
    if model_tokens and covered == 0:
        return 0.0
    brand_hit = 1.0 if brand and brand_tokens & haystack_tokens else 0.0

    semantic_score = covered / max(len(model_tokens), 1) * 0.7 + brand_hit * 0.3
    source_type = source_for_result(result)
    source_score = 0.35 * (source_priority(source_type) / 50.0)
    official = 0.15 if is_official_source(result.url, target) else 0.0
    variant_score = 1.0 if variant_matches(model, [result.title, result.snippet], strict=False) else 0.0
    return round(0.6 * semantic_score + source_score + official + 0.2 * variant_score, 3)


def _fallback_model(name: str) -> str:
    tokens = [token for token in re.findall(r"[a-zA-Z0-9]+", name) if not _HAYSTACK_STOP.intersection({token.casefold()})]
    return " ".join(tokens[:4])


def rerank(results: list[SearchResult], target: ResearchTarget, *, top_k: int = 5) -> list[SearchResult]:
    """Sort results by relevance and keep the top ``top_k``."""
    scored = [(score_result(result, target), result) for result in results]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [result for score, result in scored if score > 0][:top_k]


def source_for_result(result: SearchResult) -> KnowledgeSourceType | None:
    if result.source_type:
        try:
            return KnowledgeSourceType(result.source_type)
        except ValueError:
            pass
    return source_type_for_url(result.url)