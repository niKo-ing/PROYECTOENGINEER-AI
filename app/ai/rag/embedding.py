"""Embedding provider abstraction.

The RAG layer never couples directly to Gemini (or any vendor): it talks to an
``EmbeddingProvider`` protocol with three pluggable implementations plus a TTL
caching wrapper. ``EMBEDDING_PROVIDER`` steers the selection (``auto`` falls
back to the deterministic local provider when no API key is configured, keeping
tests and first-run development offline).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

from app.ai.rag.cache import TTLCache


class EmbeddingError(Exception):
    """Raised when an embedding backend cannot produce a vector."""


class EmbeddingProvider(Protocol):
    def embed_text(self, text: str, *, model: str | None = None) -> list[float]: ...
    def embed_documents(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]: ...
    def dimensions(self) -> int: ...
    def provider_name(self) -> str: ...


def _stable_hash(token: str) -> int:
    return int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:8], "big")


def _hash_tokens(text: str, limit: int) -> list[int]:
    tokens = re.findall(r"[\w]+", text.casefold())
    seen: set[str] = set()
    hashes: list[int] = []
    for token in tokens:
        if len(hashes) >= limit:
            break
        if token in seen:
            continue
        seen.add(token)
        hashes.append(_stable_hash(token))
    return hashes


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


class LocalHashEmbeddingProvider:
    """Deterministic, dependency-free bag-of-hashes embedding.

    Every token is mapped to a fixed-dimension signed bucket. It has no
    semantic power, but it is real, offline, stable across processes and lets
    the whole vector pipeline run without any API key.
    """

    def __init__(self, *, dimensions: int = 256, max_features: int = 30000):
        self._dim = max(int(dimensions), 16)
        self._max_features = max(int(max_features), 64)

    def embed_text(self, text: str, *, model: str | None = None) -> list[float]:
        vector = [0.0] * self._dim
        for index_hash in _hash_tokens(text, self._max_features):
            index = index_hash % self._dim
            sign = (index_hash // self._dim) % 2
            vector[index] += 1.0 if sign else -1.0
        return _l2_normalize(vector)

    def embed_documents(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        return [self.embed_text(text, model=model) for text in texts]

    def dimensions(self) -> int:
        return self._dim

    def provider_name(self) -> str:
        return "local_hash"


class GeminiEmbeddingProvider:
    """Gemini ``embed_content`` backend through the project's google-genai SDK."""

    def __init__(self, api_key: str, *, model: str = "gemini-embedding-001", dimensions: int | None = None, client: object | None = None):
        from google import genai

        self._api_key = api_key
        self._model = model or "gemini-embedding-001"
        self._dimensions = dimensions
        self._client = client or genai.Client(api_key=api_key)

    def embed_documents(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        texts = list(texts)
        if not texts:
            return []
        from google.genai import types

        config = types.EmbedContentConfig(output_dimensionality=self._dimensions) if self._dimensions else None
        try:
            response = self._client.models.embed_content(model=model or self._model, contents=texts, config=config)
        except Exception as exc:  # noqa: BLE001 — surface any transport/API failure as EmbeddingError
            raise EmbeddingError(f"Gemini embedding falló: {exc}") from exc
        returned = getattr(response, "embeddings", None) or []
        return [list(item.values) for item in returned]

    def embed_text(self, text: str, *, model: str | None = None) -> list[float]:
        return self.embed_documents([text], model=model)[0]

    def dimensions(self) -> int:
        return self._dimensions or 768

    def provider_name(self) -> str:
        return "gemini"


class OpenAIEmbeddingProvider:
    """OpenAI embeddings backend through the installed openai SDK."""

    def __init__(self, api_key: str, *, model: str = "text-embedding-3-small", dimensions: int | None = None, client: object | None = None):
        from openai import OpenAI

        self._api_key = api_key
        self._model = model or "text-embedding-3-small"
        self._dimensions = dimensions
        self._client = client or OpenAI(api_key=api_key)

    def embed_documents(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        texts = list(texts)
        if not texts:
            return []
        kwargs = {"dimensions": self._dimensions} if self._dimensions else {}
        try:
            response = self._client.embeddings.create(model=model or self._model, input=texts, **kwargs)
        except Exception as exc:  # noqa: BLE001 — surface transport/API failures as EmbeddingError
            raise EmbeddingError(f"OpenAI embedding falló: {exc}") from exc
        return [list(item.embedding) for item in (response.data or [])]

    def embed_text(self, text: str, *, model: str | None = None) -> list[float]:
        return self.embed_documents([text], model=model)[0]

    def dimensions(self) -> int:
        return self._dimensions or 1536

    def provider_name(self) -> str:
        return "openai"


class CachedEmbeddingProvider:
    """Wraps any provider adding a TTL cache keyed by content hash.

    Recomputation of identical strings (documents re-ingested, queries repeated
    within a session) is skipped; the underlying backend is only hit on miss.
    """

    def __init__(self, inner: EmbeddingProvider, *, ttl_seconds: float = 1800.0, cache: TTLCache | None = None):
        self._inner = inner
        self._cache = cache or TTLCache(ttl_seconds=ttl_seconds)

    def embed_text(self, text: str, *, model: str | None = None) -> list[float]:
        key = TTLCache.key("embedding", model or "", text)
        hit = self._cache.get(key)
        if hit is not None:
            return list(hit)
        vector = self._inner.embed_text(text, model=model)
        self._cache.set(key, vector)
        return vector

    def embed_documents(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        return [self.embed_text(text, model=model) for text in texts]

    def dimensions(self) -> int:
        return self._inner.dimensions()

    def provider_name(self) -> str:
        return self._inner.provider_name()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity between two embedding vectors."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)