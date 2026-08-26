"""Change categories unique constraint from name to (name, parent_id).

Adds priority and is_group columns to categories.
Adds seller_id to store_offers.

Handles existing data: reports conflicts rather than dropping them.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260825_04"
down_revision = "20260825_03"
branch_labels = None
depends_on = None


def _detect_name_conflicts(bind) -> list[dict]:
    rows = bind.execute(
        sa.text("""
            SELECT name, parent_id, COUNT(*) as cnt
            FROM categories
            GROUP BY name, parent_id
            HAVING COUNT(*) > 1
        """)
    ).mappings()
    return [dict(r) for r in rows]


def _constraint_exists(bind, table_name: str, constraint_name: str) -> bool:
    dialect = bind.dialect.name
    if dialect == "sqlite":
        idx = bind.execute(
            sa.text(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='unique' AND tbl_name=:tname AND name=:cname"
            ),
            {"tname": table_name, "cname": constraint_name},
        ).fetchone()
        return idx is not None
    else:
        info = bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.table_constraints "
                "WHERE table_name=:tname AND constraint_name=:cname"
            ),
            {"tname": table_name, "cname": constraint_name},
        ).fetchone()
        return info is not None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ── categories: new columns ──
    cat_columns = {item["name"] for item in sa.inspect(bind).get_columns("categories")}
    for name, col_type, default in [
        ("priority", sa.String(4), "P2"),
        ("is_group", sa.Boolean(), "0"),
    ]:
        if name not in cat_columns:
            if dialect == "sqlite":
                with op.batch_alter_table("categories") as batch:
                    batch.add_column(sa.Column(name, col_type, nullable=False, server_default=default))
            else:
                op.add_column("categories", sa.Column(name, col_type, nullable=False, server_default=default))

    # ── categories: detect conflicts before changing constraint ──
    conflicts = _detect_name_conflicts(bind)
    if conflicts:
        print(f"WARNING: {len(conflicts)} categories with duplicate (name, parent_id):")
        for c in conflicts:
            print(f"  name='{c['name']}', parent_id={c['parent_id']}, count={c['cnt']}")

    # ── categories: swap unique constraint name → (name, parent_id) ──
    has_old = _constraint_exists(bind, "categories", "uq_category_name")
    has_new = _constraint_exists(bind, "categories", "uq_category_name_parent")

    if dialect == "sqlite":
        if has_old and not has_new:
            with op.batch_alter_table("categories") as batch:
                batch.drop_constraint("uq_category_name", type_="unique")
            with op.batch_alter_table("categories") as batch:
                batch.create_unique_constraint("uq_category_name_parent", ["name", "parent_id"])
        elif not has_new:
            with op.batch_alter_table("categories") as batch:
                batch.create_unique_constraint("uq_category_name_parent", ["name", "parent_id"])
    else:
        if has_old and not has_new:
            op.drop_constraint("uq_category_name", "categories", type_="unique")
        if not has_new:
            op.create_unique_constraint("uq_category_name_parent", "categories", ["name", "parent_id"])

    # ── store_offers: seller_id ──
    offer_columns = {item["name"] for item in sa.inspect(bind).get_columns("store_offers")}
    if "seller_id" not in offer_columns:
        if dialect == "sqlite":
            with op.batch_alter_table("store_offers") as batch:
                batch.add_column(sa.Column("seller_id", sa.String(255), nullable=True))
        else:
            op.add_column("store_offers", sa.Column("seller_id", sa.String(255), nullable=True))


def downgrade() -> None:
    pass
