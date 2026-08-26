"""Migrate the legacy product price/category fields into catalog entities.

This revision is additive by design: legacy ``products.category`` and
``products.price_clp`` columns are retained. No rows or columns are dropped.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "20260825_01"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _columns(bind, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _create_catalog_tables(bind) -> None:
    if not _has_table(bind, "categories"):
        op.create_table("categories", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(100), nullable=False, unique=True), sa.Column("slug", sa.String(120), nullable=False, unique=True), sa.Column("parent_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="SET NULL")), sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
        op.create_index("ix_categories_slug", "categories", ["slug"])
    if not _has_table(bind, "stores"):
        op.create_table("stores", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(160), nullable=False, unique=True), sa.Column("domain", sa.String(255), nullable=False, unique=True), sa.Column("country", sa.String(2), nullable=False, server_default="CL"), sa.Column("logo_url", sa.String(2048)), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("trust_level", sa.Integer(), nullable=False, server_default="0"), sa.Column("store_type", sa.String(32), nullable=False, server_default="retailer"))
        op.create_index("ix_stores_domain", "stores", ["domain"])
    if not _has_table(bind, "product_specifications"):
        op.create_table("product_specifications", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(100), nullable=False), sa.Column("value", sa.String(500), nullable=False), sa.Column("unit", sa.String(32)), sa.Column("normalized_value", sa.String(500)), sa.UniqueConstraint("product_id", "name", name="uq_product_specification_name"))
        op.create_index("ix_product_specifications_product_id", "product_specifications", ["product_id"])
    if not _has_table(bind, "store_offers"):
        op.create_table("store_offers", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False), sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False), sa.Column("url", sa.String(2048), nullable=False), sa.Column("external_id", sa.String(255)), sa.Column("price", sa.Integer(), nullable=False), sa.Column("original_price", sa.Integer()), sa.Column("currency", sa.String(3), nullable=False, server_default="CLP"), sa.Column("stock_status", sa.String(32), nullable=False, server_default="unknown"), sa.Column("availability", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("payment_condition", sa.String(255)), sa.Column("seller_name", sa.String(160)), sa.Column("last_checked_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("store_id", "url", name="uq_store_offer_url"))
        op.create_index("ix_store_offers_product_id", "store_offers", ["product_id"])
        op.create_index("ix_store_offers_store_id", "store_offers", ["store_id"])
        op.create_index("ix_store_offers_price", "store_offers", ["price"])
        op.create_index("ix_store_offer_product_price", "store_offers", ["product_id", "price"])
    if not _has_table(bind, "price_history"):
        op.create_table("price_history", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("store_offer_id", sa.Integer(), sa.ForeignKey("store_offers.id", ondelete="CASCADE"), nullable=False), sa.Column("price", sa.Integer(), nullable=False), sa.Column("original_price", sa.Integer()), sa.Column("currency", sa.String(3), nullable=False, server_default="CLP"), sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.create_index("ix_price_history_store_offer_id", "price_history", ["store_offer_id"])
        op.create_index("ix_price_history_offer_observed", "price_history", ["store_offer_id", "observed_at"])
    if not _has_table(bind, "ingestion_sources"):
        op.create_table("ingestion_sources", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("source_type", sa.String(32), nullable=False), sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id", ondelete="SET NULL")), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("last_synced_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("name", "store_id", name="uq_ingestion_source_name_store"))


def _add_product_columns(bind) -> None:
    columns = _columns(bind, "products")
    additions = [("model", sa.String(160)), ("mpn", sa.String(160)), ("gtin", sa.String(32)), ("manufacturer_sku", sa.String(160)), ("image_url", sa.String(2048)), ("category_id", sa.Integer())]
    missing = [(name, column_type) for name, column_type in additions if name not in columns]
    if not missing:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("products") as batch:
            for name, column_type in missing:
                batch.add_column(sa.Column(name, column_type, nullable=True))
            if "category_id" in {name for name, _ in missing}:
                batch.create_foreign_key("fk_products_category_id", "categories", ["category_id"], ["id"], ondelete="SET NULL")
    else:
        for name, column_type in missing:
            op.add_column("products", sa.Column(name, column_type, nullable=True))
        if "category_id" in {name for name, _ in missing}:
            op.create_foreign_key("fk_products_category_id", "products", "categories", ["category_id"], ["id"], ondelete="SET NULL")
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("products")}
    for name, columns_to_index, unique in (("ix_products_model", ["model"], False), ("ix_products_mpn", ["mpn"], True), ("ix_products_gtin", ["gtin"], True), ("ix_products_manufacturer_sku", ["manufacturer_sku"], False), ("ix_products_category_id", ["category_id"], False)):
        if name not in indexes:
            op.create_index(name, "products", columns_to_index, unique=unique)


def _slug(value: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "sin-categoria"
    candidate, suffix = base, 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _migrate_legacy_data(bind) -> None:
    columns = _columns(bind, "products")
    if "category" not in columns and "price_clp" not in columns:
        return

    categories = {row.name: row.id for row in bind.execute(sa.text("SELECT id, name FROM categories")).mappings()}
    used_slugs = {row.slug for row in bind.execute(sa.text("SELECT slug FROM categories")).mappings()}
    if "category" in columns:
        legacy_categories = bind.execute(sa.text("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND TRIM(category) <> ''")).scalars()
        for name in legacy_categories:
            if name not in categories:
                bind.execute(sa.text("INSERT INTO categories (name, slug, sort_order, enabled) VALUES (:name, :slug, 0, :enabled)"), {"name": name, "slug": _slug(name, used_slugs), "enabled": True})
                categories[name] = bind.execute(sa.text("SELECT id FROM categories WHERE name = :name"), {"name": name}).scalar_one()
        for name, category_id in categories.items():
            bind.execute(sa.text("UPDATE products SET category_id = :category_id WHERE category = :name AND category_id IS NULL"), {"category_id": category_id, "name": name})

    store_id = bind.execute(sa.text("SELECT id FROM stores WHERE domain = :domain"), {"domain": "legacy.solotodo.internal"}).scalar()
    if store_id is None:
        bind.execute(sa.text("INSERT INTO stores (name, domain, country, enabled, trust_level, store_type) VALUES (:name, :domain, 'CL', :enabled, 0, 'retailer')"), {"name": "Catálogo heredado", "domain": "legacy.solotodo.internal", "enabled": False})
        store_id = bind.execute(sa.text("SELECT id FROM stores WHERE domain = :domain"), {"domain": "legacy.solotodo.internal"}).scalar_one()
    source_exists = bind.execute(sa.text("SELECT id FROM ingestion_sources WHERE name = :name AND store_id = :store_id"), {"name": "Migración catálogo heredado", "store_id": store_id}).scalar()
    if source_exists is None:
        bind.execute(sa.text("INSERT INTO ingestion_sources (name, source_type, store_id, enabled) VALUES (:name, 'feed', :store_id, :enabled)"), {"name": "Migración catálogo heredado", "store_id": store_id, "enabled": False})

    if "price_clp" not in columns:
        return
    products = bind.execute(sa.text("SELECT id, price_clp FROM products WHERE price_clp IS NOT NULL")).mappings()
    for product in products:
        url = f"internal://legacy/products/{product.id}"
        offer_id = bind.execute(sa.text("SELECT id FROM store_offers WHERE store_id = :store_id AND url = :url"), {"store_id": store_id, "url": url}).scalar()
        if offer_id is None:
            bind.execute(sa.text("INSERT INTO store_offers (product_id, store_id, url, price, currency, stock_status, availability) VALUES (:product_id, :store_id, :url, :price, 'CLP', 'unknown', :availability)"), {"product_id": product.id, "store_id": store_id, "url": url, "price": product.price_clp, "availability": True})
            offer_id = bind.execute(sa.text("SELECT id FROM store_offers WHERE store_id = :store_id AND url = :url"), {"store_id": store_id, "url": url}).scalar_one()
        history_exists = bind.execute(sa.text("SELECT id FROM price_history WHERE store_offer_id = :offer_id"), {"offer_id": offer_id}).scalar()
        if history_exists is None:
            bind.execute(sa.text("INSERT INTO price_history (store_offer_id, price, currency) VALUES (:offer_id, :price, 'CLP')"), {"offer_id": offer_id, "price": product.price_clp})


def upgrade() -> None:
    bind = op.get_bind()
    _create_catalog_tables(bind)
    _add_product_columns(bind)
    _migrate_legacy_data(bind)


def downgrade() -> None:
    # Deliberately non-destructive: this revision copies legacy data and must not
    # remove offers, history, categories or preserved legacy columns implicitly.
    pass
