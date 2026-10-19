"""Tablas del agente de ahorro (EP2): memoria de largo plazo, alertas de precio y listas de compra."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260920_01_agent_tables"
down_revision = "20260907_01_knowledge_base"
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "agent_memories"):
        op.create_table(
            "agent_memories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False, server_default="preference"),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("embedding", sa.JSON()),
            sa.Column("embedding_provider", sa.String(32)),
            sa.Column("importance", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("last_used_at", sa.DateTime(timezone=True)),
        )
        op.create_index("ix_agent_memories_user_id", "agent_memories", ["user_id"])
        op.create_index("ix_agent_memories_user_kind", "agent_memories", ["user_id", "kind"])
    if not _has_table(bind, "price_alerts"):
        op.create_table(
            "price_alerts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
            sa.Column("target_price_clp", sa.Integer(), nullable=False),
            sa.Column("price_at_creation_clp", sa.Integer()),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("triggered_at", sa.DateTime(timezone=True)),
            sa.Column("triggered_price_clp", sa.Integer()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_price_alerts_user_id", "price_alerts", ["user_id"])
        op.create_index("ix_price_alerts_product_id", "price_alerts", ["product_id"])
        op.create_index("ix_price_alerts_user_active", "price_alerts", ["user_id", "active"])
    if not _has_table(bind, "shopping_lists"):
        op.create_table(
            "shopping_lists",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("items", sa.JSON(), nullable=False),
            sa.Column("total_clp", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("budget_clp", sa.Integer()),
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_shopping_lists_user_id", "shopping_lists", ["user_id"])


def downgrade() -> None:
    op.drop_table("shopping_lists")
    op.drop_table("price_alerts")
    op.drop_table("agent_memories")
