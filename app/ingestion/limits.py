"""Ingestion dev limits — configurable caps via environment variables.

Limits are OFF by default (0 = no limit). Set env vars to > 0 to enable.
Production is unaffected when these vars are not defined.

Env vars:
    INGESTION_MAX_CATEGORIES        Max categories to process (discovery mode).
    INGESTION_MAX_URLS_PER_CATEGORY Max URLs per category (discovery phase).
    INGESTION_MAX_PRODUCTS          Max products to create (pipeline phase).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionLimits:
    max_categories: int = 0
    max_urls_per_category: int = 0
    max_products: int = 0

    @property
    def has_any_limit(self) -> bool:
        return self.max_categories > 0 or self.max_urls_per_category > 0 or self.max_products > 0


def _read_int(env_var: str) -> int:
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        return 0
    try:
        val = int(raw)
        return val if val > 0 else 0
    except ValueError:
        return 0


def get_ingestion_limits() -> IngestionLimits:
    return IngestionLimits(
        max_categories=_read_int("INGESTION_MAX_CATEGORIES"),
        max_urls_per_category=_read_int("INGESTION_MAX_URLS_PER_CATEGORY"),
        max_products=_read_int("INGESTION_MAX_PRODUCTS"),
    )
