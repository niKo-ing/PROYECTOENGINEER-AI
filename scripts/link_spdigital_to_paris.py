"""Link SP Digital offers onto existing Paris products for identical models.

Goal: habilitar comparación de precios entre tiendas. Los productos de SP
Digital se ingirieron como nuevos porque el matching determinista no encontró
identidad (los productos de Paris no tenían model/mpn/gtin). Este script
reapunta (one-off) las ofertas de los modelos idénticos SP Digital ↔ Paris
sobre el mismo Product canónico (el de Paris) y borra los Product huérfanos.

También backfillea `model` en los productos de Paris (derivado de su nombre)
para que la búsqueda por modelo y futuras ingestas tengan identidad.

Uso:
    python scripts/link_spdigital_to_paris.py            # aplica los cambios
    python scripts/link_spdigital_to_paris.py --dry-run  # muestra cambios

Idempotente: mover ofertas al producto ya canónico no tiene efecto si ya se
corrió; no re-borra productos que ya no existen.
"""

from __future__ import annotations

import sys

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.catalog import Product, StoreOffer

# Producto Paris -> model canónico (derivado del nombre)
PARIS_MODELS: dict[int, str] = {
    30: "OMEN 14",
    36: "Redmi Note 15 Pro",
    51: "iPhone 15",
}

# Pares (producto SP Digital, producto Paris, model canónico en Paris)
PAIRS: list[tuple[int, int, str]] = [
    (52, 30, "OMEN 14"),          # HP OMEN Transcend 14 (Ultra 7/16GB/1TB/RTX4060)
    (57, 51, "iPhone 15"),        # iPhone 15 Negra (256GB vs 128GB, misma línea)
    (58, 36, "Redmi Note 15 Pro"),  # Redmi Note 15 Pro 5G (512GB vs 256GB)
]


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    db = SessionLocal()
    try:
        def counts() -> dict:
            return {
                "products": db.query(func.count(Product.id)).scalar(),
                "offers": db.query(func.count(StoreOffer.id)).scalar(),
                "offers_paris": db.query(func.count(StoreOffer.id)).filter(StoreOffer.store_id == 2).scalar(),
                "offers_sp": db.query(func.count(StoreOffer.id)).filter(StoreOffer.store_id == 3).scalar(),
            }

        before = counts()
        print("STATE_BEFORE:", before)

        planned: list[str] = []
        for sp_id, paris_id, model in PAIRS:
            sp = db.get(Product, sp_id)
            paris = db.get(Product, paris_id)
            if sp is None or paris is None:
                print(f"  ! PAR {sp_id}>{paris_id}: missing product (sp={sp is not None}, paris={paris is not None})")
                continue
            offers = db.execute(select(StoreOffer).where(StoreOffer.product_id == sp_id)).scalars().all()
            planned.append(
                f"  - product SP id={sp_id} ('{sp.name[:50]}') -> product Paris id={paris_id} "
                f"('{paris.name[:40]}')  ({len(offers)} ofertas), model='{model}'"
            )
        print("PLAN:")
        print("\n".join(planned))
        if dry_run:
            print("\n(dry-run: no se aplicó ningún cambio)")
            return 0

        for sp_id, paris_id, model in PAIRS:
            sp = db.get(Product, sp_id)
            paris = db.get(Product, paris_id)
            if sp is None or paris is None:
                continue

            # 1) Reapuntar las ofertas SP al producto canónico (Paris)
            offers = db.execute(select(StoreOffer).where(StoreOffer.product_id == sp_id)).scalars().all()
            for offer in offers:
                offer.product_id = paris.id

            # 2) Model canónico en el producto Paris (para búsqueda/identidad)
            paris.model = model

            db.flush()

            # 3) Verificar que ya no quedan ofertas sobre el huérfano
            remaining = db.query(func.count(StoreOffer.id)).filter(StoreOffer.product_id == sp_id).scalar()
            if remaining:
                print(f"  ! product SP id={sp_id}: {remaining} ofertas sin mover; no se borra")
                continue

            # 4) Borrar el Product huérfano de SP Digital
            db.delete(sp)
            print(f"  - linked SP id={sp_id} -> Paris id={paris_id} (model={model}), borrado huérfano")

        db.commit()

        after = counts()
        print("STATE_AFTER:", after)
        print(f"VERDICT: products {before['products']} -> {after['products']} "
              f"({after['products'] - before['products']}), "
              f"ofertas SP {before['offers_sp']} -> {after['offers_sp']} "
              f"({after['offers_sp'] - before['offers_sp']})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())