"""Límites de uso por usuario o IP (ventana fija).

* IA: ``AI_RATE_LIMIT_PER_HOUR`` consultas por usuario, para que un bot no ocupe la GPU.
* Catálogo: ``CATALOG_RATE_LIMIT_PER_MINUTE`` solicitudes por IP, contra scrapers y abusos.

Con Redis el conteo es compartido entre procesos y servidores; sin Redis, cada proceso cuenta aparte.
Si Redis falla, el límite se aplica en memoria (nunca bloquea a todos por un error de Redis).
"""

from __future__ import annotations

import threading
from time import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.core.config import settings
from app.core.redis_client import drop_redis, get_redis
from app.core.security import AuthenticatedUser, get_current_user


class RateLimiter:
    def __init__(self, name: str, limit: int, window_seconds: int):
        self.name = name
        self.limit = limit
        self.window_seconds = window_seconds
        self._counts: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> tuple[bool, int]:
        """Cuenta una solicitud. Devuelve (permitida, segundos para reintentar)."""
        if self.limit <= 0:
            return True, 0
        now = int(time())
        window = now // self.window_seconds
        retry_after = (window + 1) * self.window_seconds - now
        count = self._hit_redis(key, window)
        if count is None:
            count = self._hit_memory(key, window)
        return count <= self.limit, retry_after

    def check(self, key: str) -> None:
        allowed, retry_after = self.hit(key)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiadas solicitudes ({self.name}). Intenta de nuevo en {retry_after} s.",
                headers={"Retry-After": str(retry_after)},
            )

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()

    def _hit_redis(self, key: str, window: int) -> int | None:
        client = get_redis()
        if client is None:
            return None
        redis_key = f"tb:limite:{self.name}:{key}:{window}"
        try:
            pipe = client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, self.window_seconds + 5)
            count, _ = pipe.execute()
            return int(count)
        except Exception:
            drop_redis()
            return None

    def _hit_memory(self, key: str, window: int) -> int:
        with self._lock:
            if len(self._counts) > 50_000:  # limpia ventanas viejas para no crecer sin fin
                self._counts = {k: v for k, v in self._counts.items() if v[0] == window}
            current_window, count = self._counts.get(key, (window, 0))
            count = count + 1 if current_window == window else 1
            self._counts[key] = (window, count)
            return count


ai_limiter = RateLimiter("ia", settings.ai_rate_limit_per_hour, 3600)
catalog_limiter = RateLimiter("catalogo", settings.catalog_rate_limit_per_minute, 60)


def client_ip(request: Request) -> str:
    # Detrás de Caddy/Cloudflare, uvicorn --proxy-headers ya deja aquí la IP real del visitante.
    return request.client.host if request.client else "desconocida"


def limit_catalog(request: Request) -> None:
    catalog_limiter.check(client_ip(request))


def limit_ai(user: Annotated[AuthenticatedUser, Depends(get_current_user)]) -> AuthenticatedUser:
    ai_limiter.check(user.id)
    return user
