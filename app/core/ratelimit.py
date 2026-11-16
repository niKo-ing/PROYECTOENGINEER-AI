"""Limitador de tasa (ventana deslizante en memoria) como dependencia de FastAPI.

Con varias réplicas detrás del balanceador cada una limita por su cuenta: es suficiente para frenar abuso y evitar
que un cliente sature el modelo. El valor lo fija ``ML_RATE_LIMIT_PER_MINUTE`` (por usuario, o por IP si no hay sesión).
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window_seconds, clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> float | None:
        """None si la solicitud pasa; si no, los segundos que faltan para poder reintentar."""
        now = self.clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return self.window - (now - hits[0])
            hits.append(now)
            return None


_limiters: dict[str, SlidingWindowLimiter] = {}


def rate_limit(name: str, env_var: str, default: int):
    """Crea una dependencia que responde 429 con ``Retry-After`` al pasarse del límite."""

    def dependency(request: Request) -> None:
        limit = int(os.getenv(env_var, str(default)))
        limiter = _limiters.get(name)
        if limiter is None or limiter.limit != limit:
            limiter = _limiters[name] = SlidingWindowLimiter(limit)
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        key = request.headers.get("authorization", "")[-24:] or forwarded or (request.client.host if request.client else "anon")
        wait = limiter.check(key)
        if wait is not None:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiadas solicitudes. Intenta de nuevo en unos segundos.", headers={"Retry-After": str(int(wait) + 1)})

    return dependency
