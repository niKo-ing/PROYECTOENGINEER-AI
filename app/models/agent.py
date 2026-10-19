"""Tablas del agente de ahorro: memoria de largo plazo, alertas y listas de compra.

Aditivo: no toca el catálogo. Los embeddings se guardan como lista JSON (igual que
``knowledge_chunks``) para no depender de pgvector.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AgentMemory(Base):
    """Recuerdo persistente de un usuario (preferencia, hecho o episodio de una tarea)."""

    __tablename__ = "agent_memories"
    __table_args__ = (Index("ix_agent_memories_user_kind", "user_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="preference")  # preference | fact | episode
    content: Mapped[str] = mapped_column(Text())
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    embedding_provider: Mapped[str | None] = mapped_column(String(32))
    importance: Mapped[int] = mapped_column(Integer, default=3)  # 1 (menor) a 5 (mayor)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PriceAlert(Base):
    """Aviso 'avísame cuando X baje de $Y'. ``triggered_at`` queda fijo al cumplirse."""

    __tablename__ = "price_alerts"
    __table_args__ = (Index("ix_price_alerts_user_active", "user_id", "active"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    target_price_clp: Mapped[int] = mapped_column(Integer)
    price_at_creation_clp: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(default=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_price_clp: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShoppingList(Base):
    """Lista de compra armada por el agente; ``items`` guarda producto, tienda y precio al momento."""

    __tablename__ = "shopping_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120))
    items: Mapped[list[dict]] = mapped_column(JSON, default=list)
    total_clp: Mapped[int] = mapped_column(Integer, default=0)
    budget_clp: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
