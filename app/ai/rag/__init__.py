"""Retrieval-Augmented Generation layer for SoloTodo AI.

Provides a persistent knowledge base (``KnowledgeDocument``/``KnowledgeChunk``),
an interchangeable ``EmbeddingProvider``, hybrid retrieval (structured +
keyword + vector), a configurable reranker, a knowledge store facade and a TTL
cache. Nothing here couples the pipeline to a specific vendor or vector store.
"""

from app.ai.rag.cache import TTLCache
from app.ai.rag.embedding import (
    CachedEmbeddingProvider,
    EmbeddingError,
    EmbeddingProvider,
    GeminiEmbeddingProvider,
    LocalHashEmbeddingProvider,
    OpenAIEmbeddingProvider,
    cosine_similarity,
)
from app.ai.rag.factory import get_embedding_provider
from app.ai.rag.knowledge_store import KnowledgeStore
from app.ai.rag.reranker import WeightedReranker, default_weights_from_settings
from app.ai.rag.retrievers import HybridRetriever, KeywordRetriever, RetrievedChunk, VectorRetriever

__all__ = [
    "TTLCache",
    "EmbeddingProvider",
    "EmbeddingError",
    "CachedEmbeddingProvider",
    "GeminiEmbeddingProvider",
    "LocalHashEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "cosine_similarity",
    "get_embedding_provider",
    "KnowledgeStore",
    "WeightedReranker",
    "default_weights_from_settings",
    "HybridRetriever",
    "KeywordRetriever",
    "VectorRetriever",
    "RetrievedChunk",
]