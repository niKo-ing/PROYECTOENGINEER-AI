"""Persistent knowledge base models for the RAG layer.

Hierarchy: ``KnowledgeSource → KnowledgeDocument → KnowledgeChunk``. Each chunk
may carry a dense embedding (JSON-encoded for portability across SQLite and
PostgreSQL). The embedding is computed through an injectable
``EmbeddingProvider``; no vector store is required to read these tables.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class KnowledgeSourceType(StrEnum):
    """Mirrors the source hierarchy used by the rest of the AI layer."""

    CATALOG = "catalog"
    MANUFACTURER = "manufacturer"
    TECHNICAL_DOCUMENT = "technical_document"
    BENCHMARK = "benchmark"
    REVIEW = "review"
    WEB = "web"
    AI_RESEARCH = "ai_research"


class KnowledgeDocumentType(StrEnum):
    SPECIFICATIONS = "specifications"
    BENCHMARK = "benchmark"
    REVIEW = "review"
    TECHNICAL = "technical"
    COMPARISON = "comparison"
    GENERAL = "general"


class KnowledgeSource(Base):
    """An external domain we have consulted (official spec sheet, benchmark DB...)."""

    __tablename__ = "knowledge_sources"
    __table_args__ = (
        UniqueConstraint("domain", "source_type", name="uq_knowledge_source_domain_type"),
        Index("ix_knowledge_sources_type", "source_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), default=KnowledgeSourceType.WEB.value)
    source_name: Mapped[str] = mapped_column(String(255))
    domain: Mapped[str] = mapped_column(String(255), index=True)
    base_url: Mapped[str | None] = mapped_column(String(2048))
    priority: Mapped[int] = mapped_column(Integer, default=20)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str] = mapped_column(String(8), default="es")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documents: Mapped[list["KnowledgeDocument"]] = relationship(back_populates="source")


class KnowledgeDocument(Base):
    """A normalized, deduplicated knowledge item (one web resource)."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("url", name="uq_knowledge_document_url"),
        Index("ix_knowledge_documents_product", "product_id"),
        Index("ix_knowledge_documents_brand_model", "brand", "model"),
        Index("ix_knowledge_documents_type", "document_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_sources.id", ondelete="SET NULL"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(String(500))
    document_type: Mapped[str] = mapped_column(String(32), default=KnowledgeDocumentType.GENERAL.value)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    brand: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(160))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    content: Mapped[str] = mapped_column(Text())
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    language: Mapped[str] = mapped_column(String(8), default="es")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    extra: Mapped[dict | None] = mapped_column("metadata", JSON)

    source: Mapped[KnowledgeSource | None] = relationship(back_populates="documents")
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunk.chunk_index",
    )


class KnowledgeChunk(Base):
    """One retrieval unit of a document, optionally with a dense embedding."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index("ix_knowledge_chunks_document_index", "document_id", "chunk_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text())
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    extra: Mapped[dict | None] = mapped_column("metadata", JSON)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")