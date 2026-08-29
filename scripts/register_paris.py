"""Registrar/configurar la Store de Paris en la BD (idempotente).

Uso:
    python scripts/register_paris.py            # aplica los cambios
    python scripts/register_paris.py --dry-run  # muestra cambios sin aplicarlos

Idempotencia:
    - Si www.paris.cl NO existe  → se crea.
    - Si www.paris.cl YA existe  → se actualiza su configuración.
    - Nunca modifica otras Stores.

No usa SQL crudo: solo ORM (SessionLocal + Store).

Durante la prueba controlada se mantiene sync_enabled=False para que el
scheduler NO ejecute la tienda automáticamente.
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models.catalog import Store

DOMAIN = "www.paris.cl"

PARIS_CONFIG: dict = {
    "name": "Paris",
    "domain": DOMAIN,
    "country": "CL",
    "enabled": True,
    "trust_level": 0,
    "store_type": "retailer",
    "sync_enabled": False,
    "sync_interval_min": None,
    "sync_config": {
        "mode": "discovery",
        "categories": ["Computación", "Celulares"],
        "max_urls_per_category": 20,
    },
}


def _diff(action: str, store: Store | None, only_what_changes: bool = False) -> list[str]:
    """Describe the changes that would be applied to the store row.

    With only_what_changes=True, only fields whose value differs from the
    target are reported (used when the store already exists).
    """
    from dataclasses import dataclass

    @dataclass
    class Field:
        label: str
        current: object
        target: object

    if store is None:
        return [
            f"  - CREATE store '{PARIS_CONFIG['name']}' (domain={DOMAIN})",
            f"  - sync_config={PARIS_CONFIG['sync_config']!r}",
        ]

    fields = [
        Field("name", store.name, PARIS_CONFIG["name"]),
        Field("country", store.country, PARIS_CONFIG["country"]),
        Field("enabled", store.enabled, PARIS_CONFIG["enabled"]),
        Field("trust_level", store.trust_level, PARIS_CONFIG["trust_level"]),
        Field("store_type", store.store_type, PARIS_CONFIG["store_type"]),
        Field("sync_enabled", store.sync_enabled, PARIS_CONFIG["sync_enabled"]),
        Field("sync_interval_min", store.sync_interval_min, PARIS_CONFIG["sync_interval_min"]),
        Field("sync_config", store.sync_config, PARIS_CONFIG["sync_config"]),
    ]

    lines = [f"  - UPDATE store id={store.id} (domain={DOMAIN})"]
    changed = 0
    for field in fields:
        if only_what_changes and field.current == field.target:
            continue
        changed += 1
        lines.append(f"    {field.label}: {field.current!r} → {field.target!r}")
    if changed == 0:
        lines.append("    (sin cambios: ya está configurada igual)")
    return lines


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    db = SessionLocal()
    try:
        store = db.scalar(select(Store).where(Store.domain == DOMAIN))

        if store is None:
            action = "CREATE"
            print(f"=== {action} — Store '{PARIS_CONFIG['name']}' ===")
            print("\n".join(_diff(action, None)))
            if dry_run:
                print("\n(dry-run: no se aplicó ningún cambio)")
                return 0
            store = Store(**PARIS_CONFIG)
            db.add(store)
        else:
            action = "UPDATE"
            print(f"=== {action} — Store id={store.id} (domain={DOMAIN}) ===")
            print("\n".join(_diff(action, store, only_what_changes=True)))
            if dry_run:
                print("\n(dry-run: no se aplicó ningún cambio)")
                return 0
            for key, value in PARIS_CONFIG.items():
                setattr(store, key, value)

        db.commit()
        db.refresh(store)
        print(f"\nOK: Store '{store.name}' domain={store.domain}")
        print(f"    sync_enabled = {store.sync_enabled}")
        print(f"    sync_config  = {store.sync_config!r}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())