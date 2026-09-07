"""AI V4 — retrieval evaluation harness over the real KnowledgeStore.

Hermetic: a curated corpus (motherboards/GPU/CPU/SSD) is ingested into an
in-memory store and the offline local-hash embeddings score every query.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.rag.embedding import LocalHashEmbeddingProvider
from app.ai.rag.eval_dataset import RAG_EVAL_CASES, RAG_EVAL_CORPUS, eval_cases
from app.ai.rag.evaluation import (
    average_precision,
    evaluate,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.ai.rag import KnowledgeStore
from app.db import Base
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeSource

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


@pytest.fixture(autouse=True)
def _isolated_tables():
    with TestingSession() as db:
        db.execute(delete(KnowledgeChunk))
        db.execute(delete(KnowledgeDocument))
        db.execute(delete(KnowledgeSource))
        db.commit()
    yield
    with TestingSession() as db:
        db.execute(delete(KnowledgeChunk))
        db.execute(delete(KnowledgeDocument))
        db.execute(delete(KnowledgeSource))
        db.commit()


def make_store() -> KnowledgeStore:
    store = KnowledgeStore(TestingSession(), LocalHashEmbeddingProvider(dimensions=64), chunk_max_chars=400, chunk_overlap=40)
    for model, brand, category, doc_type, content in RAG_EVAL_CORPUS:
        store.upsert_document(
            url=f"https://kb.test/{brand.replace(' ', '')}-{model.replace(' ', '-')}",
            title=f"{brand} {model}",
            content=content,
            document_type=doc_type,
            source_name=brand,
            source_type="benchmark" if doc_type == "benchmark" else ("review" if doc_type == "review" else "manufacturer"),
            brand=brand,
            model=model,
        )
    return store


def test_dataset_is_curated_and_bounded():
    cases = RAG_EVAL_CASES
    assert len(cases) >= 30, "dataset must provide 30+ queries for a meaningful eval"
    assert len({c.query for c in cases}) == len(cases)
    # Variant safety: primary keywords must not be substrings of a sibling's
    # keywords, otherwise "RTX 5070" would match the RTX 5070 Ti doc too.
    primaries = [c.relevant_keywords[0].casefold() for c in cases if c.relevant_keywords]
    for primary in primaries:
        assert sum(primary in other for other in primaries) == 1, f"keyword {primary!r} leaks across SKUs"


def test_metric_definitions_on_synthetic_rankings():
    hits = ["a", "b", "c", "d"]
    relevant = {"a", "c"}
    assert precision_at_k(hits, relevant, k=2) == 0.5
    assert recall_at_k(hits, relevant, k=2) == 0.5
    assert reciprocal_rank(hits, relevant) == 1.0
    assert average_precision(hits, relevant) > 0  # AP(a)=1, AP(c)=2/3 → mean 0.833


def test_evaluation_runs_across_curated_dataset():
    store = make_store()
    result = evaluate(store, eval_cases(), top_k=3)
    assert result["count"] == len(RAG_EVAL_CASES)
    overall = result["overall"]
    for key in ("precision_at_k", "recall_at_k", "mrr", "map"):
        assert 0.0 <= overall[key] <= 1.0
    assert overall["mrr"] >= 0.5, "local-hash retrieval must rank the right SKU first most of the time"


def test_evaluation_reports_per_case_metrics():
    store = make_store()
    result = evaluate(store, eval_cases("gpu"), top_k=3)
    assert result["count"] == len(eval_cases("gpu"))
    for case_entry in result["cases"]:
        metrics = case_entry["metrics"]
        assert metrics["precision_at_k"] >= 0.0
        assert "hits" in metrics


def test_evaluation_with_product_filters_never_mixes_variants():
    store = make_store()
    # Both RTX 5070 and RTX 5070 Ti documents exist; asking for the Ti under a
    # model filter must not surface the non-Ti SKU as a hit.
    result = evaluate(
        store,
        [case for case in eval_cases() if case.query.casefold().startswith("benchmark de la rtx 5070 laptop")],
        top_k=3,
        filters={"model": "RTX 5070 Laptop"},
    )
    assert result["count"] == 1
    case_entry = result["cases"][0]
    assert case_entry["metrics"]["precision_at_k"] == 1.0