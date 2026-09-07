"""Knowledge base tables for the RAG layer.

Additive: creates ``knowledge_sources``, ``knowledge_documents`` and
``knowledge_chunks`` with plain columns and JSON metadata. Embeddings are stored
as JSON lists for portability; no pgvector dependency is introduced.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260907_01_knowledge_base"
down_revision = "20260903_02"
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "knowledge_sources"):
        op.create_table(
            "knowledge_sources",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_type", sa.String(32), nullable=False, server_default="web"),
            sa.Column("source_name", sa.String(255), nullable=False),
            sa.Column("domain", sa.String(255), nullable=False),
            sa.Column("base_url", sa.String(2048)),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="20"),
            sa.Column("is_official", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("language", sa.String(8), nullable=False, server_default="es"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("domain", "source_type", name="uq_knowledge_source_domain_type"),
        )
        op.create_index("ix_knowledge_sources_type", "knowledge_sources", ["source_type"])
        op.create_index("ix_knowledge_sources_domain", "knowledge_sources", ["domain"])

    if not _has_table(bind, "knowledge_documents"):
        op.create_table(
            "knowledge_documents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_id", sa.Integer(), sa.ForeignKey("knowledge_sources.id", ondelete="SET NULL")),
            sa.Column("url", sa.String(2048), nullable=False),
            sa.Column("title", sa.String(500)),
            sa.Column("document_type", sa.String(32), nullable=False, server_default="general"),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="SET NULL")),
            sa.Column("brand", sa.String(120)),
            sa.Column("model", sa.String(160)),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("language", sa.String(8), nullable=False, server_default="es"),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("metadata", sa.JSON()),
            sa.UniqueConstraint("url", name="uq_knowledge_document_url"),
        )
        op.create_index("uk_knowledge_documents_content_hash", "knowledge_documents", ["content_hash"], unique=True)
        op.create_index("ix_knowledge_documents_product", "knowledge_documents", ["product_id"])
        op.create_index("ix_knowledge_documents_brand_model", "knowledge_documents", ["brand", "model"])
        op.create_index("ix_knowledge_documents_type", "knowledge_documents", ["document_type"])
        op.create_index("ix_knowledge_documents_source_id", "knowledge_documents", ["source_id"])

    if not _has_table(bind, "knowledge_chunks"):
        op.create_table(
            "knowledge_chunks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON()),
            sa.Column("embedding", sa.JSON()),
        )
        op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
        op.create_index("ix_knowledge_chunks_document_index", "knowledge_chunks", ["document_id", "chunk_index"])


def downgrade() -> None:
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_sources")