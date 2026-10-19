"""Seguridad de las tablas del agente en Postgres/Supabase.

Supabase expone el esquema ``public`` por su API REST con la llave pública (``anon``) del frontend.
Las tablas del agente guardan preferencias, alertas y listas de compra de cada usuario, así que se
crean con **RLS activado y sin políticas**: ``anon`` y ``authenticated`` no ven nada, y el backend
(rol ``postgres``, que ignora RLS) sigue funcionando igual. En SQLite no hace nada.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

AGENT_TABLES = ("agent_memories", "price_alerts", "shopping_lists")


def enable_agent_rls(engine: Engine) -> bool:
    """Activa RLS en las tablas del agente que existan. Idempotente. Devuelve ``True`` si lo aplicó."""
    if engine.dialect.name != "postgresql":
        return False
    try:
        with engine.begin() as connection:
            existing = set(
                connection.execute(
                    text("select tablename from pg_tables where schemaname = 'public' and tablename = any(:names)"),
                    {"names": list(AGENT_TABLES)},
                ).scalars()
            )
            for table in AGENT_TABLES:
                if table in existing:
                    connection.execute(text(f'alter table public."{table}" enable row level security'))
        return True
    except Exception:  # noqa: BLE001 — no impedir que la app arranque; queda registrado
        log.warning("No se pudo activar RLS en las tablas del agente", exc_info=True)
        return False
