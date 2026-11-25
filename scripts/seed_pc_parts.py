"""Carga (o actualiza) las piezas del armador de PC en la base de DATABASE_URL.

    DATABASE_URL=sqlite:///./todobarato.db .venv/bin/python -m scripts.seed_pc_parts
"""

from app import models  # noqa: F401 - registra los modelos
from app.db import Base, SessionLocal, engine
from app.pcbuilder.catalog import seed_pc_parts

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        print(seed_pc_parts(db))
