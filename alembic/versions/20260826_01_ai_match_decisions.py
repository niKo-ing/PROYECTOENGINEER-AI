"""Add ai_match_decisions table for AI-assisted product matching audit."""

import sqlalchemy as sa
from alembic import op

revision = "20260826_01"
down_revision = "20260825_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("ai_match_decisions"):
        op.create_table(
            "ai_match_decisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("incoming_name", sa.String(255), nullable=False),
            sa.Column("incoming_brand", sa.String(120), nullable=True),
            sa.Column("incoming_model", sa.String(160), nullable=True),
            sa.Column("incoming_mpn", sa.String(160), nullable=True),
            sa.Column("incoming_gtin", sa.String(32), nullable=True),
            sa.Column("candidate_ids", sa.JSON(), nullable=True),
            sa.Column("selected_product_id", sa.Integer(), nullable=True),
            sa.Column("decision", sa.String(32), nullable=False),
            sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
            sa.Column("model", sa.String(160), nullable=False),
            sa.Column("prompt_version", sa.String(32), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("evidence", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(
            "ix_ai_match_decisions_created_at",
            "ai_match_decisions",
            ["created_at"],
        )
        op.create_index(
            "ix_ai_match_decisions_decision",
            "ai_match_decisions",
            ["decision"],
        )


def downgrade() -> None:
    pass
