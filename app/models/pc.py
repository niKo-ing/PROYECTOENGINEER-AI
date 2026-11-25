"""Computadores del usuario: los que ya tiene («propio») y los que está armando o planea comprar («proyecto»)."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PcBuild(Base):
    __tablename__ = "pc_builds"
    __table_args__ = (Index("ix_pc_builds_user_kind", "user_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), default="proyecto")  # propio | proyecto
    use_case: Mapped[str | None] = mapped_column(String(32))
    budget_clp: Mapped[int | None] = mapped_column(Integer)
    # [{slot, product_id?, name, price_clp?, specs?}] — las piezas del catálogo se refrescan al leer; las escritas a
    # mano (equipos viejos que no están en el catálogo) guardan lo que el usuario contó.
    items: Mapped[list[dict]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text())
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual | asistente | agente
    last_report: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
