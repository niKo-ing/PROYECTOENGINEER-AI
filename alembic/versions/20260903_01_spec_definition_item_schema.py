"""Add item_schema to category specification definitions.

Allows a definition to describe the shape of a structured (data_type="json")
value, e.g. PCIe slots [{type,generation,lanes,count}], M.2 slots, rear ports,
power connectors or fan headers. This is additive and non-destructive.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260903_01"
down_revision = "20260829_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("category_spec_definitions"):
        # Spec tables are created by other migrations / create_all; nothing to do.
        return
    columns = {c["name"] for c in inspector.get_columns("category_spec_definitions")}
    if "item_schema" not in columns:
        op.add_column("category_spec_definitions", sa.Column("item_schema", sa.JSON(), nullable=True))


def downgrade() -> None:
    # Non-destructive by project convention: keep columns once added.
    pass
