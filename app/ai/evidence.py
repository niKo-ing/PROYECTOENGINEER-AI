"""Knowledge and evidence abstraction.

Phase 8/9/10 scaffolding: types that distinguish structured catalog data from
externally researched information, plus the protocols that a future Web
Research / RAG layer will implement.

No crawling, no embeddings, no vector store are introduced here. The catalog
continues to be the source of truth for structured product data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol


class KnowledgeSourceType(StrEnum):
    CATALOG = "catalog"
    MANUFACTURER = "manufacturer"
    BENCHMARK = "benchmark"
    REVIEW = "review"
    WEB = "web"
    DOCUMENT = "document"


class EvidenceKind(StrEnum):
    """How an evidence item was produced."""

    STRUCTURED = "structured"
    EXTRACTED = "extracted"
    INFERRED = "inferred"


@dataclass(frozen=True)
class Evidence:
    """A single traceable support item behind an assistant answer."""

    source_type: KnowledgeSourceType
    source_name: str
    source_url: str | None = None
    title: str | None = None
    content: str | None = None
    confidence: float = 1.0
    kind: EvidenceKind = EvidenceKind.STRUCTURED
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict:
        return {
            "source_type": self.source_type.value,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "title": self.title,
            "content": self.content,
            "confidence": self.confidence,
            "kind": self.kind.value,
            "retrieved_at": self.retrieved_at.isoformat(),
        }


class KnowledgeSearch(Protocol):
    """Interface for future external knowledge lookups.

    Concrete implementations (web search, manufacturer specs, benchmarks,
    review aggregation) will be added in the Web Research phase. Until then the
    catalog resolver is the only wired implementation.
    """

    def search(self, query: str, **kwargs: object) -> list[Evidence]:
        """Return ranked evidence for ``query``."""
        ...

    def retrieve(self, url: str, **kwargs: object) -> Evidence | None:
        """Fetch and normalize a single document, if supported."""
        ...


class CatalogKnowledgeSearch:
    """Minimal conforming implementation backed by structured catalog data.

    This is deliberately conservative: it resolves queries against catalog
    product/spec data and annotates every item with ``KnowledgeSourceType.CATALOG``
    so the assistant never confuses internal data with external research.
    """

    def __init__(self, resolver: object):
        self._resolver = resolver

    def search(self, query: str, **kwargs: object) -> list[Evidence]:
        resolution = self._resolver.resolve_query(query)
        evidence: list[Evidence] = []
        for product in resolution:
            evidence.append(
                Evidence(
                    source_type=KnowledgeSourceType.CATALOG,
                    source_name="SoloTodo Catálogo",
                    title=product.get("name"),
                    content=repr(product.get("specs") or {}),
                    confidence=0.9,
                )
            )
        return evidence

    def retrieve(self, url: str, **kwargs: object) -> Evidence | None:
        return None


# ── RAG preparation (interfaces only, no implementation) ───────────────

class Document(Protocol):
    id: str
    title: str | None
    content: str
    source_url: str | None


class DocumentChunk(Protocol):
    document_id: str
    text: str
    metadata: dict


class KnowledgeIndex(Protocol):
    """Future registry for domain corpora (catalog docs, reviews, benchmarks)."""

    def add(self, document: Document) -> None: ...
    def remove(self, document_id: str) -> None: ...


class Retriever(Protocol):
    """Future hybrid retrieval (structured + vector)."""

    def retrieve(self, query: str, top_k: int = 8) -> list[DocumentChunk]: ...
    def rerank(self, query: str, chunks: list[DocumentChunk]) -> list[DocumentChunk]: ...


class Reranker(Protocol):
    """Future cross-encoder / LLM reranker."""

    def rerank(self, query: str, chunks: list[DocumentChunk]) -> list[DocumentChunk]: ...