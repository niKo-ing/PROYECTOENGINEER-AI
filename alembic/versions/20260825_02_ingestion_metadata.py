"""Add non-destructive ingestion observation metadata to store offers."""

import sqlalchemy as sa
from alembic import op

revision = "20260825_02"
down_revision = "20260825_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("store_offers")}
    additions = (
        ("source", sa.Column("source", sa.String(160), nullable=False, server_default="legacy")),
        ("ingestion_status", sa.Column("ingestion_status", sa.String(32), nullable=False, server_default="success")),
        ("error_count", sa.Column("error_count", sa.Integer(), nullable=False, server_default="0")),
        ("last_seen_at", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True)),
    )
    for name, column in additions:
        if name not in columns:
            op.add_column("store_offers", column)
    op.execute(sa.text("UPDATE store_offers SET last_seen_at = last_checked_at WHERE last_seen_at IS NULL"))


def downgrade() -> None:
    # Observation metadata is retained to avoid losing ingestion audit data.
    pass
