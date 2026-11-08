"""Índices trigram para la búsqueda de productos.

La búsqueda usa ``ILIKE '%texto%'`` sobre nombre, marca y modelo: sin índice, PostgreSQL lee la
tabla completa en cada búsqueda. Un índice GIN con ``pg_trgm`` permite responder esos ``ILIKE``
sin recorrer todo el catálogo. En SQLite (desarrollo y pruebas) no hace nada.

Revision ID: 20261108_01_search_trigram_indexes
Revises: 20260920_01_agent_tables
"""

from alembic import op

revision = "20261108_01_search_trigram_indexes"
down_revision = "20260920_01_agent_tables"
branch_labels = None
depends_on = None

_INDEXES = {
    "ix_products_name_trgm": "name",
    "ix_products_brand_trgm": "brand",
    "ix_products_model_trgm": "model",
}


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, column in _INDEXES.items():
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON products USING gin ({column} gin_trgm_ops)")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for name in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
