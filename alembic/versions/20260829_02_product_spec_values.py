"""Add canonical product specification values and history.

Product.specs JSON remains in place. These tables introduce a structured,
auditable representation that can be populated progressively from existing JSON,
ingestion, manufacturer data, AI or admin review.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260829_02"
down_revision = "20260829_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("product_spec_values"):
        op.create_table(
            "product_spec_values",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
            sa.Column("definition_id", sa.Integer(), sa.ForeignKey("category_specification_definitions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("value_kind", sa.String(32), nullable=False, server_default="text"),
            sa.Column("raw_value", sa.Text(), nullable=True),
            sa.Column("value_text", sa.String(500), nullable=True),
            sa.Column("value_number", sa.Numeric(18, 6), nullable=True),
            sa.Column("value_boolean", sa.Boolean(), nullable=True),
            sa.Column("value_json", sa.JSON(), nullable=True),
            sa.Column("unit", sa.String(32), nullable=True),
            sa.Column("normalized_value", sa.JSON(), nullable=True),
            sa.Column("source_type", sa.String(32), nullable=False, server_default="unknown"),
            sa.Column("source_name", sa.String(160), nullable=True),
            sa.Column("source_url", sa.String(2048), nullable=True),
            sa.Column("extraction_method", sa.String(120), nullable=True),
            sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
            sa.Column("verification_status", sa.String(32), nullable=False, server_default="auto"),
            sa.Column("conflict_status", sa.String(32), nullable=False, server_default="none"),
            sa.Column("verified_by", sa.String(160), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("product_id", "definition_id", name="uq_product_spec_value_definition"),
        )
        op.create_index("ix_product_spec_values_product_id", "product_spec_values", ["product_id"])
        op.create_index("ix_product_spec_values_definition_id", "product_spec_values", ["definition_id"])
        op.create_index("ix_product_spec_values_value_text", "product_spec_values", ["value_text"])
        op.create_index("ix_product_spec_values_value_number", "product_spec_values", ["value_number"])
        op.create_index("ix_product_spec_values_definition_value", "product_spec_values", ["definition_id", "value_text"])
        op.create_index("ix_product_spec_values_definition_number", "product_spec_values", ["definition_id", "value_number"])

    if not inspector.has_table("product_spec_value_history"):
        op.create_table(
            "product_spec_value_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("spec_value_id", sa.Integer(), sa.ForeignKey("product_spec_values.id", ondelete="CASCADE"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
            sa.Column("definition_id", sa.Integer(), sa.ForeignKey("category_specification_definitions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("action", sa.String(32), nullable=False),
            sa.Column("previous_value", sa.JSON(), nullable=True),
            sa.Column("new_value", sa.JSON(), nullable=True),
            sa.Column("incoming_value", sa.JSON(), nullable=True),
            sa.Column("source_type", sa.String(32), nullable=False, server_default="unknown"),
            sa.Column("source_name", sa.String(160), nullable=True),
            sa.Column("source_url", sa.String(2048), nullable=True),
            sa.Column("extraction_method", sa.String(120), nullable=True),
            sa.Column("verification_status", sa.String(32), nullable=True),
            sa.Column("conflict_status", sa.String(32), nullable=True),
            sa.Column("changed_by", sa.String(160), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_product_spec_value_history_spec_value_id", "product_spec_value_history", ["spec_value_id"])
        op.create_index("ix_product_spec_value_history_product_id", "product_spec_value_history", ["product_id"])
        op.create_index("ix_product_spec_value_history_definition_id", "product_spec_value_history", ["definition_id"])
        op.create_index("ix_product_spec_value_history_spec_time", "product_spec_value_history", ["spec_value_id", "created_at"])


def downgrade() -> None:
    # Non-destructive by project convention: keep audit data once created.
    pass
