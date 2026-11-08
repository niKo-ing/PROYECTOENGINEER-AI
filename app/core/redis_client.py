"""Cliente Redis compartido (caché, límites de uso).

Si ``REDIS_URL`` está vacío, falta la librería o Redis no responde, devuelve ``None`` y cada
módulo usa su respaldo en memoria: la app sigue funcionando, solo que cada proceso cuenta aparte.
"""

from __future__ import annotations

import logging
import threading
from time import monotonic
from typing import Any

from app.core.config import settings

log = logging.getLogger(__name__)

_lock = threading.Lock()
_client: Any = None
_retry_at = 0.0
RETRY_SECONDS = 30.0


def get_redis() -> Any | None:
    global _client, _retry_at
    if not settings.redis_url:
        return None
    if _client is not None:
        return _client
    if monotonic() < _retry_at:
        return None
    with _lock:
        if _client is not None:
            return _client
        try:
            import redis

            client = redis.Redis.from_url(settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5, decode_responses=True)
            client.ping()
            _client = client
        except Exception:
            _retry_at = monotonic() + RETRY_SECONDS
            log.warning("Redis no disponible en %s; se usa memoria local por %ss", settings.redis_url, RETRY_SECONDS, exc_info=True)
            return None
    return _client


def drop_redis() -> None:
    """Olvida el cliente tras un error para reintentar la conexión más tarde."""
    global _client, _retry_at
    _client = None
    _retry_at = monotonic() + RETRY_SECONDS
