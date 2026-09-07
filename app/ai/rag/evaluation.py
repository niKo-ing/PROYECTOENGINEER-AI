"""Deterministic retrieval evaluation for the RAG layer (AI V4).

Provides the standard IR metrics (Precision@K, Recall@K, MRR, AP) computed over
the real ``KnowledgeStore.search`` output plus a small harness that aggregates
them across a curated query set (see :mod:`app.ai.rag.eval_dataset`). Everything
runs offline against an injected store — no LLM, no network.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any


def precision_at_k(hits: list[Any], relevant: set[Any], k: int | None = None) -> float:
    top = hits[:k] if k is not None else hits
    if not top:
        return 0.0
    relevant_count = sum(1 for hit in top if _is_relevant(hit, relevant))
    return relevant_count / len(top)


def recall_at_k(hits: list[Any], relevant: set[Any], k: int | None = None) -> float:
    if not relevant:
        return 0.0
    top = hits[:k] if k is not None else hits
    relevant_count = sum(1 for hit in top if _is_relevant(hit, relevant))
    return relevant_count / len(relevant)


def reciprocal_rank(hits: list[Any], relevant: set[Any]) -> float:
    for index, hit in enumerate(hits, start=1):
        if _is_relevant(hit, relevant):
            return 1.0 / index
    return 0.0


def average_precision(hits: list[Any], relevant: set[Any]) -> float:
    if not relevant:
        return 0.0
    hits_count = recall = precision_sum = 0.0
    for index, hit in enumerate(hits, start=1):
        if _is_relevant(hit, relevant):
            hits_count += 1
            recall = hits_count / len(relevant)
            precision_sum += hits_count / index
    return precision_sum / (hits_count or 1)


@dataclass(frozen=True)
class EvalCase:
    """One retrieval query with its ground truth.

    ``relevant_ids`` matches stored documents by ``product_id`` (or ``document_id``
    when the case knows exact rows). ``relevant_keywords`` matches by content:
    any hit whose content/title/model contains ALL the keywords counts as relevant.
    """

    query: str
    category: str = ""
    relevant_ids: list[int] = field(default_factory=list)
    relevant_keywords: list[str] = field(default_factory=list)


def retrieval_metrics(hits: list[Any], relevant: set[Any], *, k: int | None = None) -> dict[str, float]:
    """Full metric set for one ranking, keyed like the V4 eval report."""
    return {
        "precision_at_k": round(precision_at_k(hits, relevant, k=k), 4),
        "recall_at_k": round(recall_at_k(hits, relevant, k=k), 4),
        "mrr": round(reciprocal_rank(hits, relevant), 4),
        "map": round(average_precision(hits, relevant), 4),
        "hits": float(sum(1 for hit in hits[:k] if _is_relevant(hit, relevant)) if k else len(hits)),
    }


def evaluate(
    store: Any,
    cases: list[EvalCase],
    *,
    top_k: int | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run ``cases`` against ``store.search`` and aggregate metrics.

    Returns ``{"overall": {...avg...}, "cases": [{case, metrics}...], "count"}``.
    """
    aggregated: dict[str, list[float]] = {"precision_at_k": [], "recall_at_k": [], "mrr": [], "map": []}
    results: list[dict[str, Any]] = []
    for case in cases:
        hits = store.search(case.query, top_k=top_k, filters=filters) or []
        relevant = _relevant_set(hits, case)
        metrics = retrieval_metrics(hits, relevant, k=top_k)
        for key in aggregated:
            aggregated[key].append(metrics[key])
        results.append({"case": case, "metrics": metrics, "retrieved": len(hits), "relevant": len(relevant)})

    overall = {key: round(statistics.fmean(values), 4) if values else 0.0 for key, values in aggregated.items()}
    return {"overall": overall, "cases": results, "count": len(cases)}


def _is_relevant(hit: Any, relevant: set[Any]) -> bool:
    try:
        if (hit.document_id in relevant) or (hit.product_id in relevant):
            return True
    except AttributeError:
        pass
    try:
        return hit in relevant
    except TypeError:
        return False


def _relevant_set(hits: list[Any], case: EvalCase) -> set[Any]:
    """Build the ground-truth id set, expanding keywords against the hits."""
    relevant: set[Any] = set()
    for hit in hits:
        if case.relevant_ids and (getattr(hit, "document_id", None) in set(case.relevant_ids) or getattr(hit, "product_id", None) in set(case.relevant_ids)):
            relevant.add(getattr(hit, "document_id", hit))
            continue
        if case.relevant_keywords:
            title = (hit.metadata or {}).get("title") if hasattr(hit, "metadata") else ""
            haystack = f"{hit.content or ''} {title or ''} {getattr(hit, 'model', None) or ''}".casefold()
            if all(keyword.casefold() in haystack for keyword in case.relevant_keywords):
                relevant.add(getattr(hit, "document_id", hit))
    return relevant