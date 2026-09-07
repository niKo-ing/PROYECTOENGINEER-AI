"""Minimal TTL cache shared by the RAG and Web Research layers.

In-memory, process-local. Survives nothing between restarts, which is exactly
the right boundary for rate limiting, request deduplication and embedding reuse
without adding external infrastructure (no Redis required).
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Any


class TTLCache:
    """Thread-safe fixed-size cache with per-entry TTL and FIFO eviction."""

    def __init__(self, *, ttl_seconds: float = 1800.0, max_entries: int = 2000):
        self._ttl_seconds = float(ttl_seconds)
        self._max_entries = max(int(max_entries), 1)
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires, value = item
            if expires < time.monotonic():
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, *, ttl_seconds: float | None = None) -> None:
        ttl = self._ttl_seconds if ttl_seconds is None else float(ttl_seconds)
        with self._lock:
            if len(self._store) >= self._max_entries:
                self._evict_locked()
            self._store[key] = (time.monotonic() + ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def _evict_locked(self) -> None:
        oldest_key = min(self._store, key=lambda key: self._store[key][0])
        self._store.pop(oldest_key, None)

    @staticmethod
    def key(*parts: Any) -> str:
        raw = "|".join(str(part) for part in parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()