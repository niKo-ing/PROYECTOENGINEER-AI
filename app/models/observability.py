"""Trazas de ejecución de la IA (observabilidad): una fila por ejecución y una por tramo (LLM, herramienta, etapa).

No se guarda el texto del usuario ni la respuesta completos: solo largos, una vista previa con datos personales
enmascarados y un identificador seudónimo del usuario (hash con sal), suficiente para medir y depurar.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_flow_started", "flow", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    flow: Mapped[str] = mapped_column(String(32))  # agente | asistente_pc | revision_pc
    user_hash: Mapped[str | None] = mapped_column(String(16), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    cpu_ms: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | error | fallback | blocked
    error_type: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text())
    model: Mapped[str | None] = mapped_column(String(64))
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_errors: Mapped[int] = mapped_column(Integer, default=0)
    tools: Mapped[list[str]] = mapped_column(JSON, default=list)
    steps: Mapped[int] = mapped_column(Integer, default=0)
    replans: Mapped[int] = mapped_column(Integer, default=0)
    plan_source: Mapped[str | None] = mapped_column(String(16))
    input_chars: Mapped[int] = mapped_column(Integer, default=0)
    output_chars: Mapped[int] = mapped_column(Integer, default=0)
    input_preview: Mapped[str | None] = mapped_column(String(240))
    guardrails: Mapped[dict] = mapped_column(JSON, default=dict)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)  # p. ej. precios citados vs respaldados
    eval_tag: Mapped[str | None] = mapped_column(String(64), index=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentSpan(Base):
    __tablename__ = "agent_spans"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.run_id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))  # llm | tool | stage
    name: Mapped[str] = mapped_column(String(80))
    start_ms: Mapped[float] = mapped_column(Float)
    duration_ms: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
