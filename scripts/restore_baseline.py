"""Controlled, transactional restoration of the post-run-6 baseline.

Authorized cleanup of the 9 accidental products (38-46) plus the extra
price_history row (id 24) and the price revert of offer 15.

All within a single transaction:
  1. DELETE products 38-46                  -> cascades offers 22-30, price_history 25-33
  2. DELETE price_history id=24             (extra row on original offer 15/product 31)
  3. UPDATE store_offer 15.price: 314990 -> 334990
  4. INSERT NOTHING, no other changes.

Hard preconditions are pre-validated; if any fails (including the corrected
product 31 SKU = MK4H0E74CD per user-confirmed typo), the transaction rolls
back and the script exits without committing.

Expected before/after: products 19->10, store_offers 19->10, price_history 20->10.
"""

from __future__ import annotations

from app.db import SessionLocal
from app.models.catalog import PriceHistory, Product, StoreOffer
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session


def _counts(db: Session) -> dict:
    return {
        "products": db.query(func.count(Product.id)).scalar(),
        "store_offers": db.query(func.count(StoreOffer.id)).scalar(),
        "price_history": db.query(func.count(PriceHistory.id)).scalar(),
    }


def _verify_preconditions(db: Session) -> list[str]:
    errors: list[str] = []

    def check(label: str, cond: bool, detail: str = ""):
        if not cond:
            errors.append(f"{label} {detail}".strip())

    prods = [r for (r,) in db.execute(text("SELECT id FROM products WHERE id BETWEEN 38 AND 46"))]
    check("products 38-46 exactamente 9", sorted(prods) == list(range(38, 47)), f"got={sorted(prods)}")

    offers = db.execute(text("SELECT id, product_id FROM store_offers WHERE id BETWEEN 22 AND 30")).all()
    check("offers 22-30 solo hacia 38-46",
          len(offers) == 9 and all(o[1] in range(38, 47) for o in offers), f"got={offers}")

    ph = db.execute(text("SELECT id, store_offer_id FROM price_history WHERE id BETWEEN 25 AND 33")).all()
    check("price_history 25-33 solo hacia offers 22-30",
          len(ph) == 9 and all(p[1] in range(22, 31) for p in ph), f"got={ph}")

    ph24 = db.execute(text("SELECT store_offer_id FROM price_history WHERE id=24")).all()
    check("price_history 24 -> offer 15", len(ph24) == 1 and ph24[0][0] == 15, f"got={ph24}")

    off15 = db.execute(text("SELECT product_id, price FROM store_offers WHERE id=15")).all()
    check("offer 15 -> product 31, price=314990",
          len(off15) == 1 and off15[0][0] == 31 and off15[0][1] == 314990, f"got={off15}")

    p31 = db.execute(text("SELECT manufacturer_sku FROM products WHERE id=31")).all()
    # NOTE: user-confirmed typo; actual product 31 SKU is MK4H0E74CD (Aspire Lite)
    check("product 31 manufacturer_sku=MK4H0E74CD", len(p31) == 1 and p31[0][0] == "MK4H0E74CD", f"got={p31}")

    orig = [r for (r,) in db.execute(text("SELECT id FROM products WHERE id BETWEEN 28 AND 37"))]
    check("products 28-37 intactos (10)", sorted(orig) == list(range(28, 38)), f"got={sorted(orig)}")

    specs = db.execute(text("SELECT count(*) FROM product_specifications WHERE product_id BETWEEN 38 AND 46")).scalar()
    check("no specs hacia 38-46", specs == 0, f"got={specs}")
    ai = db.execute(text("SELECT count(*) FROM ai_match_decisions WHERE selected_product_id BETWEEN 38 AND 46")).scalar()
    check("no ai_match_decisions hacia 38-46", ai == 0, f"got={ai}")

    o31 = [r[0] for r in db.execute(text("SELECT id FROM store_offers WHERE product_id=31"))]
    check("product 31 tiene una sola oferta (15)", o31 == [15], f"got={o31}")

    ph15 = db.execute(text("SELECT id, price FROM price_history WHERE store_offer_id=15 ORDER BY id")).all()
    check("offer 15 tiene price_history [17=334990, 24=314990]",
          [tuple(x) for x in ph15] == [(17, 334990), (24, 314990)], f"got={ph15}")

    c = _counts(db)
    check("conteos actuales products=19 offers=19 price_history=20",
          c["products"] == 19 and c["store_offers"] == 19 and c["price_history"] == 20, f"got={c}")
    runs = db.execute(text("SELECT count(*) FROM ingestion_runs")).scalar()
    check("ingestion_runs=6", runs == 6, f"got={runs}")
    stores = db.execute(text("SELECT count(*) FROM stores")).scalar()
    check("stores=2", stores == 2, f"got={stores}")
    cats = db.execute(text("SELECT count(*) FROM categories")).scalar()
    check("categories=2", cats == 2, f"got={cats}")

    return errors


def main() -> None:
    db = SessionLocal()
    try:
        pre = _verify_preconditions(db)
        if pre:
            print("PRECONDICIONES FALLIDAS — NO SE EJECUTA NADA:")
            for e in pre:
                print("  -", e)
            print("ROLLBACK entre preconditions (no hubo cambios).")
            db.rollback()
            return

        print("PRECONDICIONES: todas satisfechas (SKU product 31 = MK4H0E74CD, typo confirmado).")

        before = _counts(db)
        print("ANTES:", before)

        # 1. DELETE products 38-46 (cascades offers 22-30, price_history 25-33)
        db.execute(text("DELETE FROM products WHERE id IN (38,39,40,41,42,43,44,45,46)"))
        # 2. DELETE price_history id=24
        db.execute(text("DELETE FROM price_history WHERE id=24"))
        # 3. UPDATE offer 15 price 314990 -> 334990
        db.execute(text("UPDATE store_offers SET price=334990 WHERE id=15"))

        # Integrity verification within the transaction (before commit)
        after = _counts(db)
        print("DESPUES-sin-commit:", after)

        integrity_ok = (
            after["products"] == 10
            and after["store_offers"] == 10
            and after["price_history"] == 10
            and before["products"] - after["products"] == 9
            and before["store_offers"] - after["store_offers"] == 9
            and before["price_history"] - after["price_history"] == 10
        )

        # rows left
        still = db.execute(text("SELECT count(*) FROM products WHERE id BETWEEN 38 AND 46")).scalar()
        integrity_ok = integrity_ok and still == 0
        off15 = db.execute(text("SELECT product_id, price FROM store_offers WHERE id=15")).all()
        integrity_ok = integrity_ok and len(off15) == 1 and off15[0][0] == 31 and off15[0][1] == 334990
        ph24 = db.execute(text("SELECT count(*) FROM price_history WHERE id=24")).scalar()
        integrity_ok = integrity_ok and ph24 == 0

        if not integrity_ok:
            print("FALLO DE INTEGRIDAD — ROLLBACK")
            db.rollback()
            print("ROLLBACK confirmado. No se aplicaron cambios.")
            return

        print("INTEGRIDAD OK — COMMIT")
        db.commit()
        print("COMMIT confirmado.")

        # Post-commit read-only verification
        print()
        print("=== POST-COMMIT VERIFICACIÓN (read-only) ===")
        print("conteos:", _counts(db))
        print("product 28 existe:", db.execute(text("SELECT id FROM products WHERE id=28")).first() is not None)
        print("sku 502788999 count:", db.execute(text("SELECT count(*) FROM products WHERE manufacturer_sku='502788999'")).scalar())
        print("ofrece de 28 hacia Paris:",
              db.execute(text("SELECT id, product_id, store_id, external_id FROM store_offers WHERE product_id=28")).all())
        print("products 38-46:", db.execute(text("SELECT id FROM products WHERE id BETWEEN 38 AND 46")).all())
        print("offers 22-30:", db.execute(text("SELECT id FROM store_offers WHERE id BETWEEN 22 AND 30")).all())
        print("price_history 25-33:", db.execute(text("SELECT id FROM price_history WHERE id BETWEEN 25 AND 33")).all())
        print("price_history 24:", db.execute(text("SELECT id FROM price_history WHERE id=24")).all())
        print("offer 15:", db.execute(text("SELECT id, product_id, price FROM store_offers WHERE id=15")).all())
        print("products 28-37:", [r[0] for r in db.execute(text("SELECT id FROM products WHERE id BETWEEN 28 AND 37 ORDER BY id"))])
        print("ingestion_runs:", db.execute(text("SELECT count(*) FROM ingestion_runs")).scalar())
        print("offers 12-21 (originales):", [r[0] for r in db.execute(text("SELECT id FROM store_offers WHERE id BETWEEN 12 AND 21 ORDER BY id"))])
        print("offers originales restantes:", [r[0] for r in db.execute(text("SELECT id FROM store_offers WHERE product_id BETWEEN 28 AND 37 ORDER BY id"))])
        print("price_history restante (product 28-37):",
              db.execute(text("SELECT ph.id, ph.store_offer_id, ph.price FROM price_history ph JOIN store_offers so ON so.id=ph.store_offer_id WHERE so.product_id BETWEEN 28 AND 37 ORDER BY ph.id")).all())
    except Exception as exc:
        print("EXCEPCIÓN — ROLLBACK:", exc)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
