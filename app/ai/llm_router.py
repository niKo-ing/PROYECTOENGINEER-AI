"""Reparto de las consultas de IA entre la GPU propia y el proveedor de respaldo.

La GPU atiende bien unas pocas decenas de respuestas a la vez; si se le mandan más, todas se
vuelven lentas. Por eso cada proceso de la API deja entrar como máximo ``AI_MAX_CONCURRENT``
consultas al modelo propio y las demás esperan hasta ``AI_QUEUE_TIMEOUT_SECONDS``. Si no se
libera un cupo, la consulta va al respaldo (``LLM_FALLBACK_PROVIDER``, p. ej. Gemini) o, sin
respaldo, recibe 503 con ``Retry-After`` en vez de quedarse colgada.

Si el modelo propio falla (GPU o vLLM caídos), se marca como caído por ``PRIMARY_COOLDOWN_SECONDS``
y mientras tanto todo va al respaldo (un "cortacircuitos"), en vez de que cada usuario espere su
propio timeout.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from time import monotonic
from typing import Literal

from fastapi import HTTPException, status

from app.core.config import settings

Route = Literal["primary", "fallback"]
PRIMARY_COOLDOWN_SECONDS = 30.0


class LLMRouter:
    def __init__(self, max_concurrent: int, wait_seconds: float):
        self.max_concurrent = max_concurrent
        self.wait_seconds = wait_seconds
        self._slots = threading.BoundedSemaphore(max_concurrent) if max_concurrent > 0 else None
        self._down_until = 0.0
        self._lock = threading.Lock()
        self.in_use = 0

    def primary_down(self) -> bool:
        return monotonic() < self._down_until

    def mark_primary_down(self, seconds: float = PRIMARY_COOLDOWN_SECONDS) -> None:
        self._down_until = monotonic() + seconds

    def reset(self) -> None:
        self._down_until = 0.0

    @contextmanager
    def turn(self, *, has_fallback: bool) -> Iterator[Route]:
        if has_fallback and self.primary_down():
            yield "fallback"
            return
        if self._slots is None:
            yield "primary"
            return
        if not self._slots.acquire(timeout=self.wait_seconds):
            if has_fallback:
                yield "fallback"
                return
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="La IA está ocupada. Intenta de nuevo en unos segundos.",
                headers={"Retry-After": "5"},
            )
        with self._lock:
            self.in_use += 1
        try:
            yield "primary"
        finally:
            with self._lock:
                self.in_use -= 1
            self._slots.release()


llm_router = LLMRouter(settings.ai_max_concurrent, settings.ai_queue_timeout_seconds)
