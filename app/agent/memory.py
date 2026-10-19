"""Memoria del agente.

* **Corto plazo**: el historial del hilo vive en el checkpointer de LangGraph (ver
  ``service.py``). Aquí solo está la política de ventana: ``window_messages`` recorta lo
  que se le manda al modelo y ``summarize_dropped`` deja un resumen determinista de lo
  recortado para no perder el hilo de una tarea larga.
* **Largo plazo**: ``LongTermMemory`` guarda recuerdos por usuario con su embedding y los
  recupera por similitud semántica, combinada con importancia y recencia.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.rag.embedding import EmbeddingError, EmbeddingProvider, cosine_similarity
from app.models.agent import AgentMemory

MEMORY_KINDS = ("preference", "fact", "episode")
DUPLICATE_THRESHOLD = 0.93
# Pesos del puntaje de recuperación: lo semántico manda, importancia y recencia desempatan.
W_SIMILARITY, W_IMPORTANCE, W_RECENCY = 0.75, 0.15, 0.10
RECENCY_HALF_LIFE_DAYS = 45.0
_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class MemoryHit:
    id: int
    kind: str
    content: str
    score: float
    similarity: float


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _hash(text: str) -> str:
    return hashlib.sha256(_normalize(text).casefold().encode("utf-8")).hexdigest()


def _tokens(text: str) -> set[str]:
    return {token for token in _WORD.findall(text.casefold()) if len(token) > 2}


def _keyword_similarity(query: str, content: str) -> float:
    """Respaldo cuando no hay embedding: solapamiento de palabras (Jaccard sesgado a la consulta)."""
    q, c = _tokens(query), _tokens(content)
    if not q or not c:
        return 0.0
    return len(q & c) / math.sqrt(len(q) * len(c))


def _as_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class LongTermMemory:
    """Recuerdos persistentes de un usuario con recuperación semántica."""

    def __init__(self, db: Session, user_id: str, embedder: EmbeddingProvider):
        self.db = db
        self.user_id = user_id
        self.embedder = embedder

    # -- escritura ---------------------------------------------------------------------
    def add(self, content: str, *, kind: str = "preference", importance: int = 3) -> tuple[AgentMemory, bool]:
        """Guarda un recuerdo. Devuelve ``(recuerdo, creado)``; un duplicado exacto o casi exacto
        no se vuelve a guardar: se refresca su importancia y su fecha de uso."""
        content = _normalize(content)[:600]
        if not content:
            raise ValueError("El recuerdo no puede estar vacío")
        if kind not in MEMORY_KINDS:
            raise ValueError(f"kind debe ser uno de {MEMORY_KINDS}")
        importance = max(1, min(5, int(importance)))
        digest = _hash(content)

        existing = self.db.scalar(select(AgentMemory).where(AgentMemory.user_id == self.user_id, AgentMemory.content_hash == digest))
        if existing is not None:
            return self._refresh(existing, importance), False

        vector, provider = self._embed(content)
        if vector is not None:
            for row in self._rows(kind):
                row_vector = self._vector_of(row)
                if row_vector is not None and cosine_similarity(vector, row_vector) >= DUPLICATE_THRESHOLD:
                    return self._refresh(row, importance), False

        memory = AgentMemory(user_id=self.user_id, kind=kind, content=content, content_hash=digest, embedding=vector, embedding_provider=provider, importance=importance)
        self.db.add(memory)
        self.db.commit()
        self.db.refresh(memory)
        return memory, True

    def _refresh(self, memory: AgentMemory, importance: int) -> AgentMemory:
        memory.importance = max(memory.importance or 1, importance)
        memory.last_used_at = datetime.now(timezone.utc)
        self.db.commit()
        return memory

    # -- lectura -----------------------------------------------------------------------
    def search(self, query: str, *, k: int = 4, kinds: tuple[str, ...] | None = None, min_similarity: float = 0.12) -> list[MemoryHit]:
        """Los ``k`` recuerdos más relevantes para ``query`` (puntaje = similitud + importancia + recencia)."""
        rows = self._rows(*(kinds or ()))
        if not rows or not _normalize(query):
            return []
        query_vector, _ = self._embed(query)
        now = datetime.now(timezone.utc)
        hits: list[MemoryHit] = []
        for row in rows:
            row_vector = self._vector_of(row) if query_vector is not None else None
            if query_vector is not None and row_vector is not None:
                similarity = max(0.0, cosine_similarity(query_vector, row_vector))
            else:
                similarity = _keyword_similarity(query, row.content)
            if similarity < min_similarity:
                continue
            created = _as_aware(row.created_at) or now
            age_days = max(0.0, (now - created).total_seconds() / 86400)
            recency = 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)
            score = W_SIMILARITY * similarity + W_IMPORTANCE * ((row.importance or 3) / 5) + W_RECENCY * recency
            hits.append(MemoryHit(id=row.id, kind=row.kind, content=row.content, score=round(score, 4), similarity=round(similarity, 4)))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        top = hits[:k]
        if top:
            for row in rows:
                if row.id in {hit.id for hit in top}:
                    row.last_used_at = now
            self.db.commit()
        return top

    def upsert_episode(self, goal: str, content: str, *, importance: int = 2) -> tuple[AgentMemory, bool]:
        """Un episodio por tarea: si el usuario repite el mismo pedido se actualiza el resultado en vez de
        acumular copias (que llenaban los cupos de recuerdo y desplazaban información útil)."""
        prefix = _normalize(f"Tarea: {goal[:160]} →")
        for row in self._rows("episode"):
            if row.content.startswith(prefix):
                text_ = _normalize(content)[:600]
                vector, provider = self._embed(text_)
                row.content, row.content_hash = text_, _hash(text_)
                row.embedding, row.embedding_provider = vector, provider
                row.importance = max(row.importance or 1, importance)
                row.last_used_at = datetime.now(timezone.utc)
                self.db.commit()
                return row, False
        return self.add(content, kind="episode", importance=importance)

    def core(self, *, k: int = 3, min_importance: int = 4) -> list[MemoryHit]:
        """Memoria núcleo: las preferencias más importantes se cargan SIEMPRE, sin depender de que la
        consulta se parezca a ellas ("recomiéndame un celular" no comparte palabras con "prefiero Samsung")."""
        rows = [r for r in self._rows("preference") if (r.importance or 0) >= min_importance]
        rows.sort(key=lambda r: ((r.importance or 0), r.id), reverse=True)
        return [MemoryHit(id=r.id, kind=r.kind, content=r.content, score=1.0, similarity=1.0) for r in rows[:k]]

    def recall(self, query: str, *, k: int = 4) -> list[MemoryHit]:
        """Lo que el agente debe saber para este pedido: memoria núcleo + los más relevantes por significado."""
        merged = self.core()
        seen = {hit.id for hit in merged}
        merged += [hit for hit in self.search(query, k=k) if hit.id not in seen]
        return merged

    def all(self) -> list[AgentMemory]:
        return self._rows()

    # -- internos ----------------------------------------------------------------------
    def _rows(self, *kinds: str) -> list[AgentMemory]:
        stmt = select(AgentMemory).where(AgentMemory.user_id == self.user_id).order_by(AgentMemory.id)
        if kinds:
            stmt = stmt.where(AgentMemory.kind.in_(kinds))
        return list(self.db.scalars(stmt))

    def _embed(self, text: str) -> tuple[list[float] | None, str | None]:
        try:
            return self.embedder.embed_text(text), self.embedder.provider_name()
        except EmbeddingError:
            return None, None

    def _vector_of(self, row: AgentMemory) -> list[float] | None:
        """Embedding del recuerdo; si se guardó con otro proveedor se recalcula con el actual."""
        if row.embedding and row.embedding_provider == self.embedder.provider_name():
            return row.embedding
        vector, provider = self._embed(row.content)
        if vector is not None:
            row.embedding, row.embedding_provider = vector, provider
            self.db.commit()
        return vector


# -- corto plazo -------------------------------------------------------------------------
def window_messages(messages: list[AnyMessage], max_messages: int = 24) -> tuple[list[AnyMessage], list[AnyMessage]]:
    """Divide el historial en ``(descartados, ventana)``.

    La ventana nunca empieza con un ``ToolMessage`` huérfano (el proveedor rechaza una
    respuesta de herramienta sin su llamada) y siempre incluye el último mensaje humano.
    """
    if len(messages) <= max_messages:
        return [], list(messages)
    start = len(messages) - max_messages
    last_human = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=0)
    start = min(start, last_human)
    while start < len(messages) and isinstance(messages[start], ToolMessage):
        start += 1
    return list(messages[:start]), list(messages[start:])


def summarize_dropped(dropped: list[AnyMessage], *, max_items: int = 6) -> str:
    """Resumen determinista (sin LLM) de lo que salió de la ventana: qué pidió el usuario y qué herramientas se usaron."""
    if not dropped:
        return ""
    asks = [_normalize(str(m.content))[:140] for m in dropped if isinstance(m, HumanMessage) and str(m.content).strip()]
    tools = sorted({m.name for m in dropped if isinstance(m, ToolMessage) and m.name})
    parts = []
    if asks:
        parts.append("El usuario pidió antes: " + " | ".join(asks[-max_items:]))
    if tools:
        parts.append("Herramientas ya usadas: " + ", ".join(tools))
    return ". ".join(parts)
