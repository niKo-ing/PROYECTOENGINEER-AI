"""Tests for hybrid retrievers and the weighted reranker."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.rag import KnowledgeStore
from app.ai.rag.embedding import LocalHashEmbeddingProvider
from app.ai.rag.reranker import WeightedReranker, default_weights_from_settings, rerank_chunks
from app.ai.rag.retrievers import HybridRetriever, KeywordRetriever, VectorRetriever
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


def _store_with_docs() -> KnowledgeStore:
    store = KnowledgeStore(TestingSession(), LocalHashEmbeddingProvider(dimensions=64), chunk_max_chars=500, chunk_overlap=50)
    store.upsert_document(
        url="https://example.com/b650e",
        title="ASUS B650E-F",
        content="La ASUS ROG STRIX B650E-F GAMING WIFI soporta DDR5 hasta 8000 MT/s, Wi-Fi 6E, y disipador VRM reforzado.",
        document_type="specifications",
        source_name="ASUS",
        source_type="manufacturer",
        brand="ASUS",
        model="B650E-F",
        category_id=7,
    )
    store.upsert_document(
        url="https://example.com/gpu",
        title="RTX 5070 Ti",
        content="La RTX 5070 Ti mejora el rendimiento en raster vs la generación previa; consume más bajo carga.",
        document_type="review",
        source_name="TechReview",
        source_type="review",
        brand="NVIDIA",
        model="RTX 5070 Ti",
        category_id=9,
    )
    return store


def test_keyword_retriever_scores_token_overlap():
    store = _store_with_docs()
    result = KeywordRetriever(store.db, top_k=5).retrieve("placa ASUS DDR5")
    assert result
    assert any("b650e" in chunk.content.casefold() for chunk in result)


def test_keyword_retriever_document_filter_by_model():
    store = _store_with_docs()
    result = KeywordRetriever(store.db, top_k=5).retrieve("rendimiento", filters={"model": "RTX 5070 Ti"})
    assert result
    assert all(chunk.model == "RTX 5070 Ti" for chunk in result)


def test_vector_retriever_returns_relevant_hits():
    store = _store_with_docs()
    provider = LocalHashEmbeddingProvider(dimensions=64)
    result = VectorRetriever(store.db, provider, top_k=3, min_score=0.0).retrieve("memoria RAM DDR5 8000")
    assert result
    assert any("ddr5" in chunk.content.casefold() for chunk in result)


def test_hybrid_retriever_dedupes_and_reranks():
    store = _store_with_docs()
    keyword = KeywordRetriever(store.db, top_k=3)
    vector = VectorRetriever(store.db, LocalHashEmbeddingProvider(dimensions=64), top_k=3, min_score=-1.0)
    retriever = HybridRetriever(store.db, keyword=keyword, vector=vector, reranker=WeightedReranker(weights=default_weights_from_settings()), top_k=3)
    chunks = retriever.retrieve("placa madre asus")
    assert chunks
    assert len(chunks) == len({(chunk.document_id, chunk.chunk_index) for chunk in chunks})
    assert any(chunk.method == "hybrid" for chunk in chunks)
    assert all("rerank" in (chunk.metadata or {}) for chunk in chunks)


def test_reranker_weights_prefer_catalog_specifications():
    store = _store_with_docs()
    weights = {"semantic": 1.0, "keyword": 0.0, "product_match": 0.0, "source_quality": 0.0, "recency": 0.0}
    chunks = store.search("placa madre asus", top_k=2, weights=weights)
    assert chunks[0].document_type == "specifications"


def test_rerank_chunks_helper_writes_metadata():
    store = _store_with_docs()
    chunks = store.search("rtx 5070", top_k=2)
    reranked = rerank_chunks("rtx 5070", chunks, weights=default_weights_from_settings())
    assert reranked
    assert "rerank" in reranked[0].metadata
    assert "score" in reranked[0].metadata["rerank"]


def test_default_weights_from_settings_parses_json():
    from app.ai.rag.reranker import DEFAULT_WEIGHTS

    weights = default_weights_from_settings('{"semantic": 0.5, "keyword": 0.2, "product_match": 0.1, "source_quality": 0.1, "recency": 0.1}')
    assert weights["semantic"] == 0.5
    assert default_weights_from_settings() == DEFAULT_WEIGHTS


def test_weighted_reranker_normalizes_partial_weights():
    reranker = WeightedReranker(weights={"semantic": 0.4})
    weights = reranker.weights
    assert set(weights) == {"semantic", "keyword", "product_match", "source_quality", "recency"}
    assert weights["semantic"] == max(weights.values())
    assert weights["semantic"] > 0.37 and weights["semantic"] < 0.40
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_weighted_reranker_full_weights_are_preserved():
    weights = {"semantic": 0.5, "keyword": 0.2, "product_match": 0.1, "source_quality": 0.1, "recency": 0.1}
    assert WeightedReranker(weights=weights).weights == weights