"""Add ingestion_runs table and store sync configuration columns."""

import sqlalchemy as sa
from alembic import op

revision = "20260825_03"
down_revision = "20260825_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── ingestion_runs table ──
    if not sa.inspect(bind).has_table("ingestion_runs"):
        op.create_table(
            "ingestion_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_name", sa.String(160), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="running"),
            sa.Column("urls_total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("urls_processed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("products_created", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("products_updated", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("price_changes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("errors_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_messages", sa.Text(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
        )
        op.create_index("ix_ingestion_runs_store_id", "ingestion_runs", ["store_id"])
        op.create_index("ix_ingestion_runs_started_at", "ingestion_runs", ["started_at"])

    # ── store sync configuration columns ──
    store_columns = {item["name"] for item in sa.inspect(bind).get_columns("stores")}
    additions = (
        ("sync_enabled", sa.Boolean(), False, "0"),
        ("sync_interval_min", sa.Integer(), True, None),
        ("sync_last_run_at", sa.DateTime(timezone=True), True, None),
        ("sync_config", sa.JSON(), True, None),
    )
    for name, col_type, nullable, default in additions:
        if name not in store_columns:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("stores") as batch:
                    batch.add_column(sa.Column(name, col_type, nullable=nullable, server_default=default))
            else:
                op.add_column("stores", sa.Column(name, col_type, nullable=nullable, server_default=default))

    # ── Configure existing stores for periodic sync ──
    op.execute(
        sa.text(
            "UPDATE stores SET sync_enabled = TRUE, sync_interval_min = 30 "
            "WHERE domain IN ('www.spdigital.cl', 'www.paris.cl')"
        )
    )


def downgrade() -> None:
    pass
