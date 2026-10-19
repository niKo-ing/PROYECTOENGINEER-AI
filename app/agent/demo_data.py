"""Catálogo chico y reproducible para pruebas y demos del agente.

Cada producto fija un escenario distinto (mínimo histórico, precio inflado, sin stock...).
No se usa en producción: el agente real consulta el catálogo ingestado de las tiendas.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.catalog import Category, PriceHistory, Product, Store, StoreOffer


def add_product(db: Session, name: str, *, brand: str | None = None, category: str = "notebook", offers: list[tuple], history: list[int] | None = None) -> int:
    """``offers``: lista de ``(tienda, precio[, disponible])``. ``history``: precios del más antiguo al más nuevo."""
    cat = db.query(Category).filter_by(slug=category).first() or Category(name=category, slug=category)
    product = Product(name=name, brand=brand, category_entity=cat, rating=4.5)
    db.add(product)
    first_offer = None
    for entry in offers:
        store_name, price = entry[0], entry[1]
        available = entry[2] if len(entry) > 2 else True
        store = db.query(Store).filter_by(name=store_name).first() or Store(name=store_name, domain=f"{store_name.lower().replace(' ', '')}.test")
        offer = StoreOffer(
            product=product,
            store=store,
            url=f"https://{store.domain}/{name.lower().replace(' ', '-')}",
            price=price,
            availability=available,
            stock_status="in_stock" if available else "out_of_stock",
        )
        db.add(offer)
        first_offer = first_offer or offer
    db.flush()
    now = datetime.now(timezone.utc)
    for i, price in enumerate(history or []):
        db.add(PriceHistory(store_offer_id=first_offer.id, price=price, observed_at=now - timedelta(days=len(history) - i)))
    db.commit()
    return product.id


def seed_demo_catalog(db: Session) -> dict[str, int]:
    return {
        # Precio actual en su mínimo histórico → buen_momento.
        "lenovo": add_product(db, "Notebook Lenovo IdeaPad 3", brand="Lenovo", offers=[("Paris", 349990), ("SP Digital", 359990)], history=[399990, 389990, 379990, 369990, 349990]),
        # Precio actual ~9% sobre su promedio → esperar.
        "asus": add_product(db, "Notebook ASUS TUF Gaming F15", brand="ASUS", offers=[("Paris", 799990)], history=[699990, 709990, 719990, 729990, 799990]),
        # Sin stock en todas las tiendas.
        "hp": add_product(db, "Notebook HP 250 G9", brand="HP", offers=[("Paris", 289990, False), ("SP Digital", 299990, False)], history=[299990, 299990, 289990]),
        "samsung": add_product(db, "Samsung Galaxy A55", brand="Samsung", category="smartphone", offers=[("Paris", 329990)], history=[349990, 339990, 329990]),
        "huawei": add_product(db, "Huawei Nova 12", brand="Huawei", category="smartphone", offers=[("Paris", 249990)], history=[259990, 249990, 249990]),
    }
