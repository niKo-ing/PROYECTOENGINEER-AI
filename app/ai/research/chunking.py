"""Document chunking with full traceability.

Converts a fetched document into overlapping plain-text chunks that keep enough
metadata (product, variant, source) to be reranked or stored later without
losing provenance. No embeddings, no vector store.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ai.research.schemas import ResearchTarget

DEFAULT_MAX_CHARS = 900
DEFAULT_OVERLAP = 120


@dataclass(frozen=True)
class ResearchDocument:
    """A normalized fetched document conforming to the ``Document`` protocol."""

    id: str
    title: str | None
    content: str
    source_url: str | None = None
    source_name: str | None = None


@dataclass(frozen=True)
class ResearchChunk:
    """A chunk carrying product/brand/model/category provenance."""

    document_id: str
    text: str
    metadata: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.document_id

    @property
    def title(self) -> str | None:
        return self.metadata.get("title")

    @property
    def content(self) -> str:
        return self.text

    @property
    def source_url(self) -> str | None:
        return self.metadata.get("source_url")


def chunk_text(text: str, *, max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP) -> list[str]:
    """Split ``text`` into plain-text segments of at most ``max_chars``."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    segments: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + max_chars, len(text))
        boundary = _nearest_boundary(text, end)
        if boundary is not None and end - boundary < 120 and boundary > cursor:
            end = boundary
        segment = text[cursor:end].strip()
        if segment:
            segments.append(segment)
        if end >= len(text):
            break
        next_cursor = end - overlap
        if next_cursor <= cursor:
            next_cursor = end
        cursor = max(next_cursor, cursor + 1)
    return segments


def _nearest_boundary(text: str, position: int) -> int | None:
    window = text[max(0, position - 60) : position]
    for delimiter in ("\n\n", "\n", ". ", " "):
        found = window.rfind(delimiter)
        if found >= 0:
            return max(0, position - 60) + found + len(delimiter)
    return None


def document_to_chunks(document: ResearchDocument, target: ResearchTarget | None = None, *, max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP, limit: int = 24) -> list[ResearchChunk]:
    """Build chunk records that retain full product + source provenance."""
    metadata: dict = {
        "source_url": document.source_url,
        "source_name": document.source_name,
        "title": document.title,
        "document_id": document.id,
    }
    if target is not None:
        metadata["product_id"] = target.id
        metadata["product"] = target.name
        metadata["brand"] = target.brand
        metadata["model"] = target.model
        metadata["category"] = target.category
    return [
        ResearchChunk(document_id=document.id, text=part, metadata={**metadata, "chunk_index": index})
        for index, part in enumerate(chunk_text(document.content, max_chars=max_chars, overlap=overlap)[:limit])
    ]