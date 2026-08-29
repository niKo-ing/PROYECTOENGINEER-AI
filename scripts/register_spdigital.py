"""Registrar/configurar la Store de SP Digital en la BD (idempotente).

Uso:
    python scripts/register_spdigital.py            # aplica los cambios
    python scripts/register_spdigital.py --dry-run  # muestra cambios sin aplicarlos

Idempotencia:
    - Si www.spdigital.cl NO existe  → se crea.
    - Si www.spdigital.cl YA existe  → se actualiza su configuración.
    - Nunca modifica otras Stores.

No usa SQL crudo: solo ORM (SessionLocal + Store).

La sync usa mode="urls" (lista curada de URLs de producto), porque el
repositorio SP Digital tiene ~66K URLs en sitemap y el descubrimiento por
keywords devuelve accesorios/ruido (sitemap ordenado alfabéticamente). La
lista curada cubre notebooks y celulares, incluyendo modelos idénticos a los
ya ingeridos de Paris (para habilitar comparación de precios entre tiendas).

Durante la prueba controlada se mantiene sync_enabled=False para que el
scheduler NO ejecute la tienda automáticamente.
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models.catalog import Store

DOMAIN = "www.spdigital.cl"

SPDIGITAL_URLS: list[str] = [
    # Notebooks
    "https://www.spdigital.cl/hp-omen-transcend-14-fb0000la-intel-core-ultra-7-356-cm-14-2880-x-1800-pixeles-16-gb-1-tb/",
    "https://www.spdigital.cl/lv-ideapad-slim-3-gen-10-core-i5-13420h-8gb-512gb-14-wuxga-luna-grey/",
    "https://www.spdigital.cl/hp-15-fc0021la-notebook-156-amd-ryzen-7-7730u-8-gb-512-gb-ssd-windows-11-home-1-year/",
    "https://www.spdigital.cl/notebook-hp-victus-15-fa1010la-i5-12450h-rtx-2050-4gb-ram-8gb-led-156-ssd-512gb-w11/",
    "https://www.spdigital.cl/ideapad-slim-3-g10-r7-7735hs-16-512-14in/",
    # Celulares
    "https://www.spdigital.cl/apple-iphone-15-256gb-negro/",
    "https://www.spdigital.cl/xiaomi-redmi-note-15-pro-smartphone-5g-android-512-gb-black-touch/",
    "https://www.spdigital.cl/apple-iphone-16-128gb-61-5g-dual-sim-usb-tipo-c-color-negro-mye73ba/",
    "https://www.spdigital.cl/samsung-galaxy-s24-ultra-smartphone-512gb/",
    "https://www.spdigital.cl/xiaomi-poco-x6-5g-us-8gb-ram-256gb-rom-black/",
]

SPDIGITAL_CONFIG: dict = {
    "name": "SP Digital",
    "domain": DOMAIN,
    "country": "CL",
    "enabled": True,
    "trust_level": 0,
    "store_type": "retailer",
    "sync_enabled": False,
    "sync_interval_min": None,
    "sync_config": {
        "mode": "urls",
        "categories": ["Notebooks", "Celulares"],
        "urls": SPDIGITAL_URLS,
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
            f"  - CREATE store '{SPDIGITAL_CONFIG['name']}' (domain={DOMAIN})",
            f"  - sync_config={SPDIGITAL_CONFIG['sync_config']!r}",
        ]

    fields = [
        Field("name", store.name, SPDIGITAL_CONFIG["name"]),
        Field("country", store.country, SPDIGITAL_CONFIG["country"]),
        Field("enabled", store.enabled, SPDIGITAL_CONFIG["enabled"]),
        Field("trust_level", store.trust_level, SPDIGITAL_CONFIG["trust_level"]),
        Field("store_type", store.store_type, SPDIGITAL_CONFIG["store_type"]),
        Field("sync_enabled", store.sync_enabled, SPDIGITAL_CONFIG["sync_enabled"]),
        Field("sync_interval_min", store.sync_interval_min, SPDIGITAL_CONFIG["sync_interval_min"]),
        Field("sync_config", store.sync_config, SPDIGITAL_CONFIG["sync_config"]),
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
            print(f"=== {action} — Store '{SPDIGITAL_CONFIG['name']}' ===")
            print("\n".join(_diff(action, None)))
            if dry_run:
                print("\n(dry-run: no se aplicó ningún cambio)")
                return 0
            store = Store(**SPDIGITAL_CONFIG)
            db.add(store)
        else:
            action = "UPDATE"
            print(f"=== {action} — Store id={store.id} (domain={DOMAIN}) ===")
            print("\n".join(_diff(action, store, only_what_changes=True)))
            if dry_run:
                print("\n(dry-run: no se aplicó ningún cambio)")
                return 0
            for key, value in SPDIGITAL_CONFIG.items():
                setattr(store, key, value)

        db.commit()
        db.refresh(store)
        print(f"\nOK: Store '{store.name}' domain={store.domain} id={store.id}")
        print(f"    sync_enabled = {store.sync_enabled}")
        print(f"    sync_config  = {store.sync_config!r}")
        print(f"    urls curadas  = {len(SPDIGITAL_URLS)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())