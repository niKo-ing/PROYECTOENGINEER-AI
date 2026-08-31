"""Apply the canonical taxonomy (categories + per-category spec definitions) to the DB.

Idempotent: categories are keyed by slug and spec definitions are upserted by
(category_id, key). Obsolete empty categories not present in the canonical
taxonomy are removed.

Usage:
    python -m scripts.seed_taxonomy [--dry-run]
"""

from __future__ import annotations

import argparse
import sys

from app.db import SessionLocal
from app.services.category_service import CategoryService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Validate without persisting")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        service = CategoryService(db)
        if args.dry_run:
            db.rollback()
            print("DRY-RUN: taxonomía válida sin cambios persistidos")
            return 0
        service.seed_initial_taxonomy()
        print("Taxonomía aplicada correctamente (categorías y definiciones de specs).")
        return 0
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}")
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())