"""Caché del catálogo (búsquedas, facetas, productos, ofertas, historial y categorías).

Los precios solo cambian cuando termina una ingesta, así que repetir la misma consulta a la base en
cada visita es trabajo perdido. Cada respuesta se guarda ``CATALOG_CACHE_TTL_SECONDS`` y la caché
entera se invalida al terminar una ingesta o al cambiar el catálogo (se sube un número de versión).

Con Redis la caché es compartida por todos los procesos y servidores; sin Redis, cada proceso
tiene la suya (y la invalidación solo alcanza a ese proceso: el resto expira por TTL).
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from collections.abc import Callable
from time import monotonic
from typing import Any

from fastapi.responses import JSONResponse
from pydantic import TypeAdapter

from app.core.config import settings
from app.core.redis_client import drop_redis, get_redis

VERSION_KEY = "tb:catalogo:version"


class CatalogCache:
    def __init__(self, ttl_seconds: int, max_items: int = 5_000):
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._version = 0

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0

    def get(self, key: str) -> Any | None:
        if not self.enabled:
            return None
        client = get_redis()
        if client is not None:
            try:
                raw = client.get(self._redis_key(client, key))
                return None if raw is None else json.loads(raw)
            except Exception:
                drop_redis()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires, value = item
            if expires < monotonic():
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        client = get_redis()
        if client is not None:
            try:
                client.setex(self._redis_key(client, key), self.ttl_seconds, json.dumps(value, separators=(",", ":")))
                return
            except Exception:
                drop_redis()
        with self._lock:
            self._items[key] = (monotonic() + self.ttl_seconds, value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)

    def invalidate(self) -> None:
        """El catálogo cambió: las respuestas guardadas dejan de servir."""
        with self._lock:
            self._items.clear()
            self._version += 1
        client = get_redis()
        if client is not None:
            try:
                client.incr(VERSION_KEY)
            except Exception:
                drop_redis()

    def _redis_key(self, client: Any, key: str) -> str:
        version = client.get(VERSION_KEY) or "0"
        return f"tb:catalogo:{version}:{key}"


catalog_cache = CatalogCache(settings.catalog_cache_ttl_seconds)

# El navegador guarda 30 s; Cloudflare (s-maxage) lo que dure la caché del servidor.
BROWSER_MAX_AGE = 30


def cached_json(key: str, build: Callable[[], Any], model: Any) -> JSONResponse:
    """Responde desde la caché o arma la respuesta, la valida con ``model`` y la guarda."""
    data = catalog_cache.get(key)
    state = "HIT"
    if data is None:
        state = "MISS"
        data = TypeAdapter(model).dump_python(TypeAdapter(model).validate_python(build(), from_attributes=True), mode="json")
        catalog_cache.set(key, data)
    headers = {"X-Cache": state}
    if catalog_cache.enabled:
        ttl = catalog_cache.ttl_seconds
        headers["Cache-Control"] = f"public, max-age={min(BROWSER_MAX_AGE, ttl)}, s-maxage={ttl}, stale-while-revalidate=60"
    return JSONResponse(data, headers=headers)
