"""Deterministic, configurable reranker for retrieved chunks.

Weights (defaults follow the brief): semantic 0.35, keyword 0.20, product
match 0.20, source quality 0.15, recency 0.10. They are namespace-configurable
through ``RAG_RERANK_WEIGHTS`` (a JSON object) or passed per-call.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.ai.rag.retrievers import RetrievedChunk

DEFAULT_WEIGHTS: dict[str, float] = {
    "semantic": 0.35,
    "keyword": 0.20,
    "product_match": 0.20,
    "source_quality": 0.15,
    "recency": 0.10,
}

# document_type → base quality (0..1) reused as source_quality fallback.
_SOURCE_QUALITY_BY_TYPE = {
    "specifications": 0.9,
    "benchmark": 0.7,
    "technical": 0.6,
    "review": 0.5,
    "comparison": 0.4,
    "general": 0.3,
}


def default_weights_from_settings(raw: str | None = None) -> dict[str, float]:
    """Parse ``RAG_RERANK_WEIGHTS`` JSON or fall back to the defaults."""
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {key: float(value) for key, value in parsed.items() if key in DEFAULT_WEIGHTS}
        except (TypeError, ValueError):
            pass
    return dict(DEFAULT_WEIGHTS)


def _normalize(weights: dict[str, float] | None) -> dict[str, float]:
    merged = dict(DEFAULT_WEIGHTS)
    if weights:
        merged.update({key: float(value) for key, value in weights.items() if key in merged})
    total = sum(merged.values())
    if total <= 0:
        return merged
    return {key: value / total for key, value in merged.items()}


def _model_tokens(model: str | None) -> set[str]:
    if not model:
        return set()
    return {token.casefold() for token in re.findall(r"[a-zA-Z0-9]+", model) if len(token) >= 2}


def _variant_model_score(chunk_model: str | None, query_model: str | None) -> float:
    """Score how well a chunk's model identity matches the requested one.

    Variant-safe: an exact token match is ideal, a document that only covers a
    wider family ("RTX 5070" answering "RTX 5070 Ti") is ranked below an exact
    match but above an unrelated variant, and a document that accidentally
    includes an extra variant token is penalized so "5070" does not surface
    "5070 Ti" first.
    """
    chunk_tokens = _model_tokens(chunk_model)
    query_tokens = _model_tokens(query_model)
    if not query_tokens or not chunk_tokens:
        return 0.5
    if chunk_tokens == query_tokens:
        return 1.0
    if chunk_tokens.issubset(query_tokens):
        return 0.5
    if query_tokens.issubset(chunk_tokens):
        return 0.35
    overlap = len(chunk_tokens & query_tokens)
    if overlap == 0:
        return 0.0
    return min(0.3, 0.3 * overlap / len(query_tokens))


def _score_product_match(chunk: RetrievedChunk, filters: dict[str, Any] | None) -> float:
    wanted = (filters or {}).get("product_id")
    if wanted is not None:
        return 1.0 if chunk.product_id == wanted else 0.0
    if (filters or {}).get("product_ids"):
        ids = set((filters or {}).get("product_ids") or [])
        return 1.0 if chunk.product_id in ids else 0.0
    wanted_model = (filters or {}).get("model")
    if wanted_model and chunk.model:
        return _variant_model_score(chunk.model, wanted_model)
    wanted_brand = (filters or {}).get("brand")
    if wanted_brand and chunk.brand:
        return 1.0 if wanted_brand.casefold() == chunk.brand.casefold() else 0.0
    # No explicit product scope: lightly favor chunks that are anchored to one.
    return 0.5 if chunk.product_id is not None else 0.0


def _score_source_quality(chunk: RetrievedChunk) -> float:
    meta = chunk.metadata or {}
    priority = meta.get("source_priority")
    if isinstance(priority, (int, float)):
        return max(0.0, min(1.0, float(priority) / 60.0))
    return _SOURCE_QUALITY_BY_TYPE.get(chunk.document_type or "general", 0.3)


def _score_recency(chunk: RetrievedChunk) -> float:
    raw = chunk.retrieved_at
    if not raw:
        return 0.5
    try:
        retrieved = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if retrieved.tzinfo is None:
            retrieved = retrieved.replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.5
    days = max(0.0, (datetime.now(timezone.utc) - retrieved).total_seconds() / 86400.0)
    return max(0.0, 1.0 - days / 90.0)


class WeightedReranker:
    """Configurable weighted fusion used after hybrid retrieval."""

    def __init__(self, weights: dict[str, float] | None = None):
        self._weights = _normalize(weights)

    @property
    def weights(self) -> dict[str, float]:
        return dict(self._weights)

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        weights: dict[str, float] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        effective = _normalize(weights) if weights else self._weights
        for chunk in chunks:
            semantic = chunk.semantic_score or 0.0
            keyword = chunk.keyword_score or 0.0
            product_match = _score_product_match(chunk, filters)
            source_quality = _score_source_quality(chunk)
            recency = _score_recency(chunk)
            chunk.metadata["rerank"] = {
                "semantic": round(semantic, 4) if chunk.semantic_score is not None else None,
                "keyword": round(keyword, 4) if chunk.keyword_score is not None else None,
                "product_match": round(product_match, 4),
                "source_quality": round(source_quality, 4),
                "recency": round(recency, 4),
            }
            combined = (
                effective["semantic"] * semantic
                + effective["keyword"] * keyword
                + effective["product_match"] * product_match
                + effective["source_quality"] * source_quality
                + effective["recency"] * recency
            )
            chunk.metadata["rerank"]["score"] = round(combined, 4)
            chunk.metadata["rerank"]["weight"] = chunk.method
        return sorted(chunks, key=lambda item: (item.metadata.get("rerank") or {}).get("score", 0.0), reverse=True)


def rerank_chunks(query: str, chunks: list[RetrievedChunk], *, weights: dict[str, float] | None = None, filters: dict[str, Any] | None = None) -> list[RetrievedChunk]:
    return WeightedReranker(weights=weights).rerank(query, chunks, filters=filters)