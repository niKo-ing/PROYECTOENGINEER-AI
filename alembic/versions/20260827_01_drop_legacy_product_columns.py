"""Drop orphaned legacy products.category and products.price_clp columns.

The new architecture stores category via products.category_id ->
categories and prices exclusively in store_offers/price_history. The
legacy products.category (VARCHAR NOT NULL) and products.price_clp
(INTEGER NOT NULL) columns are not mapped by the Product ORM model, not
read by runtime code, and hold no data. This revision drops them (with
their legacy indexes), finalizing the hand-off started in 20260825_01.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260827_01"
down_revision = "20260826_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("products"):
        return
    dialect = bind.dialect.name
    columns = {c["name"] for c in sa.inspect(bind).get_columns("products")}
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("products")}
    for column in ("category", "price_clp"):
        if column not in columns:
            continue
        index_name = f"ix_products_{column}"
        if index_name in indexes:
            if dialect == "sqlite":
                with op.batch_alter_table("products") as batch:
                    batch.drop_index(index_name)
            else:
                op.drop_index(index_name, "products")
        if dialect == "sqlite":
            with op.batch_alter_table("products") as batch:
                batch.drop_column(column)
        else:
            op.drop_column("products", column)


def downgrade() -> None:
    # Deliberately non-destructive (codebase convention): legacy data was
    # empty, so nothing is lost by not restoring the columns.
    pass