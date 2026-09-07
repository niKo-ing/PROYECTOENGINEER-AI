"""Retrieval layer: keyword, dense vector and hybrid retrieval over the
persistent knowledge base.

All retrievers return plain ``RetrievedChunk`` rows (no LLM involvement) so the
orchestrator and the evidence engine can reason over them deterministically.

Vector search is computed client-side against the JSON-encoded embeddings
stored per chunk; ``pgvector`` is optional and can be enabled later through
``EMBEDDING_USE_PGVECTOR`` without changing these interfaces. A keyword
pre-filter bounds the candidate set so the vector pass never scans the whole
table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai.rag.embedding import EmbeddingProvider, cosine_similarity
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


@dataclass
class RetrievedChunk:
    """One retrieval result with provenance and per-method scores."""

    chunk_id: int | None = None
    chunk_index: int | None = None
    document_id: int | None = None
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    semantic_score: float | None = None
    keyword_score: float | None = None
    method: str = "keyword"
    source_name: str | None = None
    source_url: str | None = None
    document_type: str | None = None
    brand: str | None = None
    model: str | None = None
    product_id: int | None = None
    retrieved_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "content": self.content,
            "metadata": self.metadata,
            "semantic_score": self.semantic_score,
            "keyword_score": self.keyword_score,
            "method": self.method,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "document_type": self.document_type,
            "brand": self.brand,
            "model": self.model,
            "product_id": self.product_id,
        }


_STOPWORDS = {
    "de", "la", "el", "los", "las", "del", "un", "una", "unos", "unas", "y", "o", "a", "en",
    "para", "que", "con", "por", "cuanto", "mejor", "cual", "es", "son", "hay", "me", "te",
    "se", "su", "sus", "esto", "esta", "ese", "esa", "al", "como", "cuales", "quiero", "busco",
    "recomiendame", "y si", "contra", "poco",
}


def query_tokens(query: str, *, limit: int = 10) -> list[str]:
    """Extract meaningful alphanumeric tokens from a user query, deduplicated."""
    seen: set[str] = set()
    tokens: list[str] = []
    for token in re.findall(r"[a-zA-Z0-9]+", query.casefold()):
        if token in seen or len(token) < 2 or token in _STOPWORDS:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= limit:
            break
    return tokens


def _apply_document_filters(stmt, filters: dict[str, Any] | None):
    if not filters:
        return stmt
    doc = KnowledgeDocument
    product_ids = filters.get("product_ids")
    if product_ids:
        stmt = stmt.where(doc.product_id.in_(list(product_ids)))
    elif filters.get("product_id"):
        stmt = stmt.where(doc.product_id == filters["product_id"])
    if filters.get("category_id"):
        stmt = stmt.where(doc.category_id == filters["category_id"])
    if filters.get("document_type"):
        stmt = stmt.where(doc.document_type == filters["document_type"])
    brand = filters.get("brand")
    if brand:
        stmt = stmt.where(doc.brand.ilike(f"%{brand}%"))
    model = filters.get("model")
    if model:
        stmt = stmt.where(doc.model.ilike(f"%{model}%"))
    return stmt


def _token_content_filter(tokens: list[str], maximum: int = 8):
    """Candidate filter over chunk content plus document title/brand/model.

    Matching the product identity columns lets short queries like ``xiaomi``
    surface documents that only mention the model code in their metadata.
    """
    if not tokens:
        return None
    chunk = KnowledgeChunk
    doc = KnowledgeDocument
    return or_(
        *[
            or_(
                chunk.content.ilike(f"%{token}%"),
                doc.title.ilike(f"%{token}%"),
                doc.brand.ilike(f"%{token}%"),
                doc.model.ilike(f"%{token}%"),
            )
            for token in tokens[:maximum]
        ]
    )


def _to_retrieved(chunk: KnowledgeChunk, doc: KnowledgeDocument, **scores: float | None) -> RetrievedChunk:
    extra = dict(chunk.extra or {})
    return RetrievedChunk(
        chunk_id=chunk.id,
        chunk_index=chunk.chunk_index,
        document_id=doc.id,
        content=chunk.content or "",
        metadata=extra,
        semantic_score=scores.get("semantic"),
        keyword_score=scores.get("keyword"),
        source_name=extra.get("source_name") or (doc.source.source_name if doc.source else None),
        source_url=doc.url,
        document_type=doc.document_type,
        brand=doc.brand,
        model=doc.model,
        product_id=doc.product_id,
        retrieved_at=doc.retrieved_at.isoformat() if doc.retrieved_at else None,
    )


class KeywordRetriever:
    """SQL keyword/full-text style retriever with a token-overlap score.

    Uses plain ``ILIKE`` conditions (portable to SQLite and PostgreSQL). On
    PostgreSQL the same method can be swapped for ``tsvector``/``to_tsquery``
    later without touching this interface.
    """

    def __init__(self, db: Session, *, top_k: int = 8, min_score: float = 0.0):
        self.db = db
        self.top_k = top_k
        self.min_score = min_score

    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        tokens: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        tokens = tokens if tokens is not None else query_tokens(query)
        if not tokens:
            return []
        chunk = KnowledgeChunk
        doc = KnowledgeDocument
        stmt = select(chunk, doc).join(doc, chunk.document_id == doc.id)
        stmt = _apply_document_filters(stmt, filters)
        content_filter = _token_content_filter(tokens)
        if content_filter is not None:
            stmt = stmt.where(content_filter)

        results: list[RetrievedChunk] = []
        for row_chunk, row_doc in self.db.execute(stmt).all():
            lower = (row_chunk.content or "").casefold()
            title = (row_doc.title or "").casefold()
            identity = f"{row_doc.brand or ''} {row_doc.model or ''}".casefold()
            content_hits = sum(1 for token in tokens if token in lower)
            title_hits = sum(1 for token in tokens if token in title)
            identity_hits = sum(1 for token in tokens if token in identity)
            if content_hits == 0 and title_hits == 0 and identity_hits == 0:
                continue
            keyword_score = (content_hits + 0.5 * title_hits + 0.75 * identity_hits) / len(tokens)
            if keyword_score <= self.min_score:
                continue
            results.append(_to_retrieved(row_chunk, row_doc, keyword=round(keyword_score, 4)))
        results.sort(key=lambda item: item.keyword_score or 0, reverse=True)
        return results[: (top_k or self.top_k)]


class VectorRetriever:
    """Dense retrieval over stored embeddings (cosine, computed client-side)."""

    def __init__(self, db: Session, embedding_provider: EmbeddingProvider, *, top_k: int = 8, min_score: float = 0.05):
        self.db = db
        self.provider = embedding_provider
        self.top_k = top_k
        self.min_score = min_score

    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        tokens: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        query_vector = self.provider.embed_text(query)
        chunk = KnowledgeChunk
        doc = KnowledgeDocument
        stmt = select(chunk, doc).join(doc, chunk.document_id == doc.id)
        stmt = stmt.where(chunk.embedding.is_not(None))
        stmt = _apply_document_filters(stmt, filters)
        content_filter = _token_content_filter(tokens)
        if content_filter is not None:
            stmt = stmt.where(content_filter)

        scored: list[RetrievedChunk] = []
        for row_chunk, row_doc in self.db.execute(stmt).all():
            vector = row_chunk.embedding
            if not vector:
                continue
            similarity = cosine_similarity(query_vector, list(vector))
            if similarity < self.min_score:
                continue
            scored.append(_to_retrieved(row_chunk, row_doc, semantic=round(similarity, 4)))
        scored.sort(key=lambda item: item.semantic_score or 0, reverse=True)
        return scored[: (top_k or self.top_k)]


class HybridRetriever:
    """Structured + keyword + vector retrieval, merged, deduplicated and reranked."""

    def __init__(
        self,
        db: Session,
        *,
        keyword: KeywordRetriever,
        vector: VectorRetriever,
        reranker,
        top_k: int = 8,
        pool: int = 2,
    ):
        self.db = db
        self.keyword = keyword
        self.vector = vector
        self.reranker = reranker
        self.top_k = top_k
        self.pool = pool

    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        weights: dict[str, float] | None = None,
    ) -> list[RetrievedChunk]:
        limit = top_k or self.top_k
        tokens = query_tokens(query)
        keyword_hits = self.keyword.retrieve(query, top_k=limit * self.pool, filters=filters, tokens=tokens)
        vector_hits = self.vector.retrieve(query, top_k=limit * self.pool, filters=filters, tokens=tokens)

        merged: dict[tuple[int | None, int | None], RetrievedChunk] = {}
        for item in keyword_hits + vector_hits:
            key = (item.document_id, item.chunk_index)
            previous = merged.get(key)
            if previous is None:
                merged[key] = item
                continue
            if item.keyword_score is not None and (previous.keyword_score is None or item.keyword_score > previous.keyword_score):
                previous.keyword_score = item.keyword_score
            if item.semantic_score is not None and (previous.semantic_score is None or item.semantic_score > previous.semantic_score):
                previous.semantic_score = item.semantic_score
            if previous.semantic_score is not None and previous.keyword_score is not None:
                previous.method = "hybrid"

        chunks = list(merged.values())
        ranked = self.reranker.rerank(query, chunks, weights=weights, filters=filters)
        return ranked[:limit]