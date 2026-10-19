"""Siembra el catálogo de ejemplo (5 productos con ofertas e historial) en la base SQLite local.

    .venv/bin/python scripts/sembrar_catalogo_demo.py

Sirve para probar el agente en modo «Gemini real» sin haber ingestado tiendas. Solo funciona con
SQLite (nunca toca una base Postgres/Supabase) y no hace nada si el catálogo ya tiene productos.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402,F401
from app.agent.demo_data import seed_demo_catalog  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models.catalog import Product  # noqa: E402


def main() -> None:
    if not settings.sqlalchemy_database_url.startswith("sqlite"):
        sys.exit("Esta base no es SQLite local: no se siembra nada (el script solo es para desarrollo).")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        existentes = db.query(Product).count()
        if existentes:
            print(f"El catálogo ya tiene {existentes} producto(s); no se siembra nada.")
            return
        ids = seed_demo_catalog(db)
    print(f"Catálogo de ejemplo sembrado: {len(ids)} productos en {settings.sqlalchemy_database_url}")


if __name__ == "__main__":
    main()
