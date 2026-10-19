"""Modo demo del agente: catálogo de ejemplo en memoria, modelo guionado, sin red ni login.

Existe para probar la pantalla del agente (y exponerla) sin depender de la cuota de Gemini, de
Supabase Auth ni de la base real. Todo vive en la memoria del proceso: reiniciar el servidor o
llamar a ``reset`` lo deja de cero. Está apagado en producción (ver ``demo_enabled``).
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.demo_data import seed_demo_catalog
from app.agent.service import AgentRunResult, AgentService
from app.agent.snapshot import snapshot
from app.agent.testing import AhorroPolicy, ScriptedChatModel
from app.ai.rag.embedding import LocalHashEmbeddingProvider
from app.core.config import settings
from app.db import Base
from app.models.catalog import Product, StoreOffer

DEMO_USER = "demo-usuario"
LENOVO_PRICE_AFTER_DROP = 289_990

# Palabra del pedido → búsquedas que intentaría un comprador (la primera con tope de precio).
_KEYWORDS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"gamer|gaming|juegos"), ["notebook gamer", "notebook"]),
    (re.compile(r"lenovo|ideapad"), ["Lenovo"]),
    (re.compile(r"asus|tuf"), ["ASUS TUF"]),
    (re.compile(r"\bhp\b"), ["HP 250"]),
    (re.compile(r"samsung|galaxy|celular|smartphone|tel[eé]fono"), ["Samsung"]),
    (re.compile(r"huawei"), ["Huawei"]),
    (re.compile(r"notebook|laptop|port[aá]til|universidad|estudi"), ["notebook"]),
]


def demo_enabled() -> bool:
    """Prendido con ``AGENT_DEMO_ENABLED=true``; si no se define, solo fuera de producción."""
    flag = os.getenv("AGENT_DEMO_ENABLED", "").strip().lower()
    if flag:
        return flag in {"1", "true", "yes", "on"}
    return settings.app_env.lower() != "production"


def queries_from_message(message: str) -> list[str]:
    text = message.lower()
    for pattern, queries in _KEYWORDS:
        if pattern.search(text):
            return queries
    return ["notebook"]


class DemoRuntime:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._build()

    def _build(self) -> None:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self._session_factory = sessionmaker(bind=engine)
        with self._session_factory() as db:
            seed_demo_catalog(db)
        self._saver = MemorySaver()
        self._embedder = LocalHashEmbeddingProvider()

    def reset(self) -> None:
        with self._lock:
            self._build()

    def run(self, message: str, thread_id: str | None) -> AgentRunResult:
        with self._lock, self._session_factory() as db:
            service = AgentService(
                db,
                DEMO_USER,
                llm=ScriptedChatModel(policy=AhorroPolicy(queries_from_message(message))),
                embedder=self._embedder,
                checkpointer=self._saver,
            )
            return service.run(message, thread_id)

    def drop_price(self) -> dict[str, Any]:
        """Simula que pasan los días y la tienda baja el Lenovo: sirve para ver cumplirse una alerta."""
        with self._lock, self._session_factory() as db:
            product = db.query(Product).filter(Product.name.like("%Lenovo%")).first()
            offers = db.query(StoreOffer).filter_by(product_id=product.id).all()
            before = min(o.price for o in offers)
            for offer in offers:
                offer.price = LENOVO_PRICE_AFTER_DROP
            db.commit()
            return {"product": product.name, "before_clp": before, "after_clp": LENOVO_PRICE_AFTER_DROP}

    def state(self) -> dict[str, Any]:
        with self._lock, self._session_factory() as db:
            return snapshot(db, DEMO_USER)


_runtime: DemoRuntime | None = None
_runtime_lock = threading.Lock()


def get_demo_runtime() -> DemoRuntime:
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = DemoRuntime()
        return _runtime
