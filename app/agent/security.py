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
# Las crea el checkpointer de LangGraph (PostgresSaver) y guardan las conversaciones del agente.
CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations")
PROTECTED_TABLES = AGENT_TABLES + CHECKPOINT_TABLES


def enable_agent_rls(engine: Engine) -> bool:
    """Activa RLS en las tablas del agente y del historial que existan. Idempotente. Devuelve ``True`` si lo aplicó."""
    if engine.dialect.name != "postgresql":
        return False
    try:
        with engine.begin() as connection:
            existing = set(
                connection.execute(
                    text("select tablename from pg_tables where schemaname = 'public' and tablename = any(:names)"),
                    {"names": list(PROTECTED_TABLES)},
                ).scalars()
            )
            for table in PROTECTED_TABLES:
                if table in existing:
                    connection.execute(text(f'alter table public."{table}" enable row level security'))
        return True
    except Exception:  # noqa: BLE001 — no impedir que la app arranque; queda registrado
        log.warning("No se pudo activar RLS en las tablas del agente", exc_info=True)
        return False


def enable_rls_on_connection(connection) -> None:
    """Igual que ``enable_agent_rls`` pero sobre una conexión psycopg abierta (la del checkpointer)."""
    try:
        existing = {row[0] if not isinstance(row, dict) else row["tablename"] for row in connection.execute(
            "select tablename from pg_tables where schemaname = 'public' and tablename = any(%s)", (list(PROTECTED_TABLES),)
        ).fetchall()}
        for table in PROTECTED_TABLES:
            if table in existing:
                connection.execute(f'alter table public."{table}" enable row level security')
    except Exception:  # noqa: BLE001
        log.warning("No se pudo activar RLS en las tablas del historial del agente", exc_info=True)
