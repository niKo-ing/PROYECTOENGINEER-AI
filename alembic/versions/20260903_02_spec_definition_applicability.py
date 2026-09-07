"""Add applicability to category specification definitions.

Additive column (String 16) supporting the tri-state spec relevance model:
"required" | "optional" | "conditional". Backfills all existing rows to
"optional" (or "required" where `required` is true). Non-destructive.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260903_02"
down_revision = "20260903_01"
branch_labels = None
depends_on = None

TABLE = "category_specification_definitions"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        # Spec tables are created by other migrations / create_all; nothing to do.
        return
    columns = {c["name"] for c in inspector.get_columns(TABLE)}
    if "applicability" not in columns:
        op.add_column(TABLE, sa.Column("applicability", sa.String(length=16), nullable=True))
    op.execute(
        f"UPDATE {TABLE} SET applicability = 'required' WHERE required = TRUE AND applicability IS NULL"
    )
    op.execute(
        f"UPDATE {TABLE} SET applicability = 'optional' WHERE applicability IS NULL"
    )


def downgrade() -> None:
    # Non-destructive by project convention: keep columns once added.
    pass
