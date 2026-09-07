"""Tests for the embedding abstraction (provider selection + local fallback)."""

from __future__ import annotations

from app.ai.rag import TTLCache, cosine_similarity, get_embedding_provider
from app.ai.rag.embedding import (
    CachedEmbeddingProvider,
    EmbeddingError,
    LocalHashEmbeddingProvider,
)


def test_local_provider_is_deterministic_offline():
    provider = LocalHashEmbeddingProvider(dimensions=64)
    first = provider.embed_text("ASUS ROG STRIX B650E-F GAMING WIFI")
    second = provider.embed_text("ASUS ROG STRIX B650E-F GAMING WIFI")
    assert first == second
    assert len(first) == 64


def test_cosine_similarity_orders_relevant_above_unrelated():
    provider = LocalHashEmbeddingProvider(dimensions=256)
    query = provider.embed_text("ASUS ROG STRIX B650E-F GAMING WIFI")
    relevant = provider.embed_text("ASUS ROG STRIX B650E-F")
    unrelated = provider.embed_text("lasagne recipe kitchen equipment")
    assert cosine_similarity(query, relevant) > cosine_similarity(query, unrelated)
    assert cosine_similarity(query, query) > 0.99


def test_default_provider_is_local_and_offline():
    provider = get_embedding_provider(cached=False)
    assert provider.provider_name() == "local_hash"
    provider.embed_text("sin red ni api keys")  # must not raise


def test_unknown_provider_raises_embedding_error():
    class Settings:
        embedding_provider = "nope"
        embedding_dimensions = 256
        embedding_model = ""
        gemini_api_key = ""
        openai_api_key = ""
        research_cache_ttl_seconds = 30

    try:
        get_embedding_provider(Settings(), cached=False)
        raise AssertionError("should have raised")
    except EmbeddingError:
        pass


def test_gemini_provider_requires_api_key():
    class Settings:
        embedding_provider = "gemini"
        embedding_dimensions = 256
        embedding_model = ""
        gemini_api_key = ""
        openai_api_key = ""
        research_cache_ttl_seconds = 30

    try:
        get_embedding_provider(Settings(), cached=False)
        raise AssertionError("should have raised")
    except EmbeddingError:
        pass


def test_cached_provider_reuses_embeddings():
    class Counting(LocalHashEmbeddingProvider):
        calls = 0

        def embed_text(self, text, *, model=None):
            self.calls += 1
            return super().embed_text(text, model=model)

    provider = CachedEmbeddingProvider(Counting(dimensions=32), ttl_seconds=60, cache=TTLCache(ttl_seconds=60))
    provider.embed_text("un texto")
    provider.embed_text("un texto")
    assert provider._inner.calls == 1