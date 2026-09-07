"""Embedding provider selection per configuration.

``EMBEDDING_PROVIDER`` accepts ``auto`` (default), ``gemini``, ``openai`` or
``local``. ``auto`` uses the configured LLM vendor when an API key is present
and falls back to the deterministic local provider otherwise.
"""

from __future__ import annotations

from app.ai.rag.embedding import (
    CachedEmbeddingProvider,
    EmbeddingError,
    EmbeddingProvider,
    GeminiEmbeddingProvider,
    LocalHashEmbeddingProvider,
    OpenAIEmbeddingProvider,
)


def get_embedding_provider(cfg: object | None = None, *, cached: bool = True) -> EmbeddingProvider:
    """Build the embedding provider selected by settings (or ``auto``)."""
    from app.core.config import settings as default_settings

    settings = cfg or default_settings
    provider = (settings.embedding_provider or "auto").lower()
    dims = int(settings.embedding_dimensions or 256)
    model = (settings.embedding_model or "").strip()

    if provider == "gemini":
        if not settings.gemini_api_key:
            raise EmbeddingError("EMBEDDING_PROVIDER=gemini requiere GEMINI_API_KEY")
        base: EmbeddingProvider = GeminiEmbeddingProvider(settings.gemini_api_key, model=model or "gemini-embedding-001", dimensions=dims)
    elif provider == "openai":
        if not settings.openai_api_key:
            raise EmbeddingError("EMBEDDING_PROVIDER=openai requiere OPENAI_API_KEY")
        base = OpenAIEmbeddingProvider(settings.openai_api_key, model=model or "text-embedding-3-small", dimensions=dims)
    elif provider in ("", "auto"):
        if settings.gemini_api_key:
            base = GeminiEmbeddingProvider(settings.gemini_api_key, model=model or "gemini-embedding-001", dimensions=dims)
        elif settings.openai_api_key:
            base = OpenAIEmbeddingProvider(settings.openai_api_key, model=model or "text-embedding-3-small", dimensions=dims)
        else:
            base = LocalHashEmbeddingProvider(dimensions=dims)
    elif provider == "local":
        base = LocalHashEmbeddingProvider(dimensions=dims)
    else:
        raise EmbeddingError(f"EMBEDDING_PROVIDER desconocido: {provider!r}")

    if cached:
        return CachedEmbeddingProvider(base, ttl_seconds=float(settings.research_cache_ttl_seconds or 1800))
    return base