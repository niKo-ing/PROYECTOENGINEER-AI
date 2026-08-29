"""Add products.images (gallery) and products.description_ai.

The single-image catalog only keeps one image_url per product and no
room for generated descriptions. This revision adds:
- products.images (JSON list of image URLs, ordered gallery)
- products.description_ai (Text, AI-generated description flagged in UI)

Both are additive and nullable so existing rows keep working.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260827_02"
down_revision = "20260827_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("products"):
        return
    columns = {c["name"] for c in sa.inspect(bind).get_columns("products")}
    if "images" not in columns:
        op.add_column("products", sa.Column("images", sa.JSON(), nullable=True))
    if "description_ai" not in columns:
        op.add_column("products", sa.Column("description_ai", sa.Text(), nullable=True))


def downgrade() -> None:
    # Non-destructive by codebase convention: generated data is re-creatable.
    pass