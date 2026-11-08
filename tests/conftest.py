"""Fixtures comunes: cada prueba parte con la caché del catálogo, los límites de uso y el reparto
de la IA limpios, para que una prueba no herede respuestas guardadas ni conteos de otra."""

import pytest

from app.ai.llm_router import llm_router
from app.core.cache import catalog_cache
from app.core.limits import ai_limiter, catalog_limiter


@pytest.fixture(autouse=True)
def _estado_limpio():
    catalog_cache.invalidate()
    ai_limiter.reset()
    catalog_limiter.reset()
    llm_router.reset()
    yield
    catalog_cache.invalidate()
