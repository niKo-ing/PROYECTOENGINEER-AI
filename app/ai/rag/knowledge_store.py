"""KnowledgeStore — persistent ingestion and retrieval hub for the RAG layer.

Ingests normalized documents split into semantic chunks, computes their
embeddings through the injected provider, deduplicates by URL and content hash,
and answers queries through the hybrid retriever. It also adapts stored
chunks/an external research report into ``Evidence`` items the AI engine can
cite.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.evidence import Evidence, EvidenceKind, KnowledgeSourceType
from app.ai.rag.embedding import EmbeddingError, EmbeddingProvider
from app.ai.rag.reranker import WeightedReranker, default_weights_from_settings
from app.ai.rag.retrievers import HybridRetriever, KeywordRetriever, RetrievedChunk, VectorRetriever
from app.ai.research.chunking import chunk_text
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeSource

_DOCUMENT_TYPE_BY_SOURCE = {
    KnowledgeSourceType.MANUFACTURER.value: "specifications",
    KnowledgeSourceType.DOCUMENT.value: "technical",
    KnowledgeSourceType.BENCHMARK.value: "benchmark",
    KnowledgeSourceType.REVIEW.value: "review",
    KnowledgeSourceType.CATALOG.value: "general",
    KnowledgeSourceType.WEB.value: "general",
}


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _domain_of(url: str) -> str:
    stripped = url.split("://", 1)[-1].split("/", 1)[0]
    return stripped.casefold()


def _approx_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


class KnowledgeStore:
    """Facade over the knowledge tables for ingestion and hybrid retrieval."""

    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider,
        *,
        chunk_max_chars: int = 900,
        chunk_overlap: int = 120,
        max_chunks_per_document: int = 24,
        language: str = "es",
        top_k: int = 6,
    ):
        self.db = db
        self.provider = embedding_provider
        self.chunk_max_chars = chunk_max_chars
        self.chunk_overlap = chunk_overlap
        self.max_chunks_per_document = max_chunks_per_document
        self.language = language
        self._top_k = top_k

    @classmethod
    def from_settings(cls, db: Session, *, settings: object | None = None) -> "KnowledgeStore":
        """Build a store wired to the app configuration (or per-settings override)."""
        from app.core.config import settings as default_settings
        from app.ai.rag.factory import get_embedding_provider

        cfg = settings or default_settings
        return cls(
            db,
            get_embedding_provider(cfg, cached=True),
            max_chunks_per_document=int(getattr(cfg, "max_research_chunks", 24)),
            top_k=int(getattr(cfg, "rag_hybrid_top_k", 6)),
        )

    # ── Ingestion ───────────────────────────────────────────────────────

    def upsert_document(
        self,
        *,
        url: str,
        title: str | None,
        content: str,
        document_type: str = "general",
        source_name: str | None = None,
        domain: str | None = None,
        source_type: str | KnowledgeSourceType | None = None,
        product_id: int | None = None,
        brand: str | None = None,
        model: str | None = None,
        category_id: int | None = None,
        language: str | None = None,
        published_at: datetime | None = None,
        extra: dict[str, Any] | None = None,
    ) -> tuple[KnowledgeDocument, bool]:
        """Insert a document (+ chunks + embeddings) or return an existing one.

        Deduplication happens first on URL and then on content hash, so
        re-fetching a page or re-ingesting the same research evidence is a no-op.
        Returns ``(document, created)``.
        """
        content = _clean_text(content)
        if not content:
            raise ValueError("La knowledge base no almacena documentos vacíos.")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        existing = self.db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.url == url)) or self.db.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.content_hash == content_hash)
        )
        if existing is not None:
            return existing, False

        source_type_value = source_type.value if isinstance(source_type, KnowledgeSourceType) else (source_type or KnowledgeSourceType.WEB.value)
        source = self._get_or_create_source(
            domain=domain or _domain_of(url),
            source_name=source_name,
            source_type=source_type_value,
            base_url=url,
        )

        now = datetime.now(timezone.utc)
        extra = dict(extra or {})
        extra.setdefault("source_name", source_name or source.source_name)
        extra.setdefault("source_type", source_type_value)
        extra.setdefault("title", title)
        extra.setdefault("retrieved_at", now.isoformat())

        document = KnowledgeDocument(
            source=source,
            url=url,
            title=title,
            document_type=document_type,
            product_id=product_id,
            brand=brand,
            model=model,
            category_id=category_id,
            content=content,
            content_hash=content_hash,
            language=language or self.language,
            published_at=published_at,
            retrieved_at=now,
            extra=extra,
        )

        chunk_extra = {
            "product_id": product_id,
            "brand": brand,
            "model": model,
            "category": None,
            "source_type": source_type_value,
            "source_name": source_name or source.source_name,
            "source_priority": self._priority_for(source_type_value),
            "retrieved_at": now.isoformat(),
        }
        texts = chunk_text(content, max_chars=self.chunk_max_chars, overlap=self.chunk_overlap)[: self.max_chunks_per_document]
        embeddings: list[list[float]] | None = None
        try:
            embeddings = self.provider.embed_documents(texts)
        except EmbeddingError:
            embeddings = None
        vectors = embeddings if embeddings is not None else [None] * len(texts)

        for index, text in enumerate(texts):
            document.chunks.append(
                KnowledgeChunk(
                    chunk_index=index,
                    content=text,
                    token_count=_approx_tokens(text),
                    extra=chunk_extra,
                    embedding=vectors[index],
                )
            )

        self.db.add(document)
        self.db.flush()
        return document, True

    def ingest_research_report(self, report, *, product_id: int | None = None, brand: str | None = None, model: str | None = None) -> int:
        """Persist every evidence item of a research report as a document.

        Returns the number of newly created documents (deduplicated by URL/hash).
        """
        created = 0
        if report is None:
            return created
        for item in report.evidence:
            if not item.content:
                continue
            source_type = item.source_type.value if hasattr(item.source_type, "value") else str(item.source_type)
            _doc, inserted = self.upsert_document(
                url=item.source_url or (f"knowledge://{_domain_of(item.source_name)}"),
                title=item.title,
                content=item.content,
                document_type=_DOCUMENT_TYPE_BY_SOURCE.get(source_type, "general"),
                source_name=item.source_name,
                domain=_domain_of(item.source_url) if item.source_url else None,
                source_type=source_type,
                product_id=product_id,
                brand=brand,
                model=model,
            )
            created += int(inserted)
        return created

    # ── Retrieval ───────────────────────────────────────────────────────

    def hybrid(self, *, top_k: int | None = None, weights: dict[str, float] | None = None) -> HybridRetriever:
        limit = top_k or 8
        if weights is None:
            from app.core.config import settings

            weights = default_weights_from_settings(getattr(settings, "rag_rerank_weights", "") or "")
        keyword = KeywordRetriever(self.db, top_k=limit)
        vector = VectorRetriever(self.db, self.provider, top_k=limit)
        reranker = WeightedReranker(weights=weights)
        return HybridRetriever(self.db, keyword=keyword, vector=vector, reranker=reranker, top_k=limit)

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        weights: dict[str, float] | None = None,
    ) -> list[RetrievedChunk]:
        return self.hybrid(top_k=top_k, weights=weights).retrieve(query, top_k=top_k, filters=filters, weights=weights)

    def search_research(self, query: str, targets: list[Any] | None = None, *, top_k: int | None = None):
        """Query the knowledge base and adapt the hits to a ``ResearchReport``.

        Used as the KB-first step of the orchestrator: if the stored knowledge
        already answers the query, no web research is triggered. Returns ``None``
        when there is no usable evidence.
        """
        filters = self._target_filters(targets or [])
        chunks = self.search(query, top_k=top_k or self._top_k, filters=filters or None)
        if not chunks:
            return None
        evidence = self.evidence_for(chunks)
        if not evidence:
            return None
        from app.ai.research.schemas import ResearchReport

        lines = [f"- {item.source_name}: {item.title or item.source_url}" for item in evidence]
        return ResearchReport(
            used=True,
            evidence=evidence,
            verdicts=[],
            queries_run=0,
            context="[Evidencia recuperada de la knowledge base (RAG)]\n" + "\n".join(lines),
            note=f"{len(evidence)} fragmento(s) recuperados de la knowledge base.",
        )

    @staticmethod
    def _target_filters(targets: list[Any]) -> dict[str, Any]:
        """Resolve product identity to filters, most specific signal first.

        A single product id scopes strictly; multiple distinct ids expand to an
        ``IN`` filter so compare/recommend queries never lose the second product.
        Falls back to model, then brand when there is no usable id.
        """
        filters: dict[str, Any] = {}
        if not targets:
            return filters
        product_ids = sorted({getattr(t, "id", None) for t in targets if getattr(t, "id", None)})
        if len(product_ids) == 1:
            filters["product_id"] = product_ids[0]
            return filters
        if len(product_ids) > 1:
            filters["product_ids"] = product_ids
            return filters
        model = next((getattr(t, "model", None) for t in targets if getattr(t, "model", None)), None)
        brand = next((getattr(t, "brand", None) for t in targets if getattr(t, "brand", None)), None)
        if model:
            filters["model"] = model
        elif brand:
            filters["brand"] = brand
        return filters

    def document_count(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0)

    def chunk_count(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(KnowledgeChunk)) or 0)

    # ── Evidence adaptation ─────────────────────────────────────────────

    def evidence_for(self, chunks: list[RetrievedChunk], *, target_model: str | None = None) -> list[Evidence]:
        items: list[Evidence] = []
        for chunk in chunks[:8]:
            meta = chunk.metadata or {}
            source_type = KnowledgeSourceType(meta.get("source_type")) if isinstance(meta.get("source_type"), str) and meta.get("source_type") in KnowledgeSourceType._value2member_map_ else KnowledgeSourceType.WEB
            priority = meta.get("source_priority") or self._priority_for(source_type.value)
            confidence = round(min(0.95, 0.35 + 0.6 * (priority / 60.0)), 3)
            retrieved_at = None
            if chunk.retrieved_at:
                try:
                    retrieved_at = datetime.fromisoformat(chunk.retrieved_at.replace("Z", "+00:00"))
                except ValueError:
                    retrieved_at = None
            items.append(
                Evidence(
                    source_type=source_type,
                    source_name=meta.get("source_name") or chunk.source_name or "Knowledge Base",
                    source_url=chunk.source_url,
                    title=meta.get("title"),
                    content=chunk.content or "",
                    confidence=confidence,
                    kind=EvidenceKind.EXTRACTED,
                    retrieved_at=retrieved_at or datetime.now(timezone.utc),
                )
            )
        return items

    # ── Internals ───────────────────────────────────────────────────────

    def _get_or_create_source(self, *, domain: str, source_name: str | None, source_type: str, base_url: str | None) -> KnowledgeSource:
        source = self.db.scalar(
            select(KnowledgeSource).where(KnowledgeSource.domain == domain, KnowledgeSource.source_type == source_type)
        )
        if source is not None:
            return source
        source = KnowledgeSource(
            source_type=source_type,
            source_name=source_name or domain,
            domain=domain,
            base_url=base_url,
            priority=self._priority_for(source_type),
            is_official=(source_type in {"manufacturer", "technical_document"}),
        )
        self.db.add(source)
        self.db.flush()
        return source

    @staticmethod
    def _priority_for(source_type: str) -> int:
        mapping = {
            "catalog": 60,
            "manufacturer": 50,
            "benchmark": 40,
            "review": 30,
            "technical_document": 25,
            "document": 25,
            "web": 20,
            "ai_research": 15,
        }
        return mapping.get(source_type, 20)