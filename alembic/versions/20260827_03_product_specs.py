"""Add products.specs (structured technical specifications).

The catalog only keeps free-form descriptions; this revision adds a JSON
column holding a structured technical sheet produced by the LLM extractor:

    {
      "highlights": ["16 GB DDR5", "512 GB SSD"],          # key specs up top
      "sections": [                                        # ordered sections
        {"title": "Procesador", "items": [{"label": "CPU", "value": "..."}]}
      ]
    }

Additive and nullable so existing rows keep working. The table
product_specifications is intentionally left unused.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260827_03"
down_revision = "20260827_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("products"):
        return
    columns = {c["name"] for c in sa.inspect(bind).get_columns("products")}
    if "specs" not in columns:
        op.add_column("products", sa.Column("specs", sa.JSON(), nullable=True))


def downgrade() -> None:
    # Non-destructive by codebase convention: generated data is re-creatable.
    pass