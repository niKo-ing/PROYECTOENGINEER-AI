"""Add category spec definitions and offer condition.

This keeps product identity canonical while allowing each store offer to state
its commercial condition (new/used/refurbished/open box). It also adds a
category-scoped specification definition table so filters can evolve per
category without turning attributes into categories.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260829_01"
down_revision = "20260827_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("store_offers"):
        columns = {c["name"] for c in inspector.get_columns("store_offers")}
        if "condition" not in columns:
            op.add_column(
                "store_offers",
                sa.Column("condition", sa.String(32), nullable=False, server_default="unknown"),
            )

    if not inspector.has_table("category_specification_definitions"):
        op.create_table(
            "category_specification_definitions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False),
            sa.Column("key", sa.String(80), nullable=False),
            sa.Column("label", sa.String(120), nullable=False),
            sa.Column("spec_group", sa.String(80), nullable=False, server_default="General"),
            sa.Column("data_type", sa.String(32), nullable=False, server_default="text"),
            sa.Column("unit", sa.String(32), nullable=True),
            sa.Column("filter_type", sa.String(32), nullable=False, server_default="text"),
            sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("comparable", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("facetable", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("options", sa.JSON(), nullable=True),
            sa.UniqueConstraint("category_id", "key", name="uq_category_spec_definition_key"),
        )
        op.create_index(
            "ix_category_spec_definitions_category_id",
            "category_specification_definitions",
            ["category_id"],
        )


def downgrade() -> None:
    # Non-destructive by codebase convention: definitions/conditions are re-creatable.
    pass
