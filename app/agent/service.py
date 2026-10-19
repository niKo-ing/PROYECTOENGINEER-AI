"""Servicio que ejecuta el agente: arma herramientas, memoria y grafo, y devuelve un resultado trazable."""

from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from sqlalchemy.orm import Session

from app.agent.graph import _text, build_agent_graph
from app.agent.llm import as_llm_error, get_chat_model, is_provider_error
from app.agent.memory import LongTermMemory
from app.agent.tools import build_tools
from app.agent.security import enable_rls_on_connection
from app.ai.rag.embedding import EmbeddingProvider
from app.ai.rag.factory import get_embedding_provider
from app.core.config import settings

DEFAULT_CHECKPOINT_DB = os.getenv("AGENT_CHECKPOINT_DB", "agent_checkpoints.db")


@dataclass
class AgentRunResult:
    thread_id: str
    answer: str
    plan: list[dict[str, Any]] = field(default_factory=list)
    plan_source: str = ""
    tools_used: list[str] = field(default_factory=list)
    wrote: list[str] = field(default_factory=list)
    replans: int = 0
    memories_used: list[str] = field(default_factory=list)
    steps: int = 0
    trace: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def checkpointer_kind(database_url: str, mode: str = "auto") -> str:
    """``postgres`` o ``sqlite``. ``AGENT_CHECKPOINT=auto`` sigue a la base de la app: con Postgres
    (Supabase) varias réplicas comparten los hilos; con SQLite local, un archivo."""
    mode = (mode or "auto").lower()
    if mode in ("postgres", "sqlite"):
        return mode
    return "postgres" if database_url.startswith("postgresql") else "sqlite"


def make_checkpointer(database_url: str | None = None, mode: str | None = None, sqlite_path: str | None = None) -> Any:
    """Memoria de corto plazo persistente: el hilo sobrevive a reinicios del proceso."""
    url = database_url if database_url is not None else settings.sqlalchemy_database_url
    if checkpointer_kind(url, mode or os.getenv("AGENT_CHECKPOINT", "auto")) == "postgres":
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row

        # prepare_threshold=0: compatible con el pooler de Supabase (modo transacción).
        conn = psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://", 1), autocommit=True, row_factory=dict_row, prepare_threshold=0)
        saver = PostgresSaver(conn)
        saver.setup()
        enable_rls_on_connection(conn)  # las tablas del historial guardan conversaciones: nunca expuestas por la API pública
        return saver
    return SqliteSaver(sqlite3.connect(sqlite_path or DEFAULT_CHECKPOINT_DB, check_same_thread=False))


@lru_cache(maxsize=1)
def default_checkpointer() -> Any:
    return make_checkpointer()


class AgentService:
    def __init__(
        self,
        db: Session,
        user_id: str,
        *,
        llm: BaseChatModel | None = None,
        embedder: EmbeddingProvider | None = None,
        checkpointer: Any = None,
        max_steps: int = 10,
        max_replans: int = 2,
    ):
        self.user_id = user_id
        self.memory = LongTermMemory(db, user_id, embedder or get_embedding_provider())
        self.tools = build_tools(db, user_id, self.memory)
        self.graph = build_agent_graph(
            llm or get_chat_model(),
            self.tools,
            self.memory,
            checkpointer=checkpointer if checkpointer is not None else default_checkpointer(),
            max_steps=max_steps,
            max_replans=max_replans,
        )

    def history(self, thread_id: str) -> list[dict[str, str]]:
        """Mensajes guardados del hilo (memoria de corto plazo), p. ej. tras reiniciar el proceso."""
        snapshot = self.graph.get_state({"configurable": {"thread_id": f"{self.user_id}:{thread_id}"}})
        messages = (snapshot.values or {}).get("messages", [])
        return [{"role": m.type, "content": _text(m.content)} for m in messages if m.type in ("human", "ai") and _text(m.content)]

    def run(self, message: str, thread_id: str | None = None) -> AgentRunResult:
        thread = thread_id or uuid.uuid4().hex[:12]
        # El hilo se ata al usuario: dos usuarios con el mismo thread_id nunca comparten historial.
        config = {"configurable": {"thread_id": f"{self.user_id}:{thread}"}, "recursion_limit": 80}
        try:
            # durability="exit": el historial se guarda UNA vez al terminar la tarea y no en cada paso. Con una base
            # remota (Supabase, ~150 ms por consulta) escribir en cada paso sumaba segundos a cada respuesta.
            state = self.graph.invoke({"messages": [HumanMessage(message)]}, config, durability="exit")
        except Exception as error:  # noqa: BLE001 — solo se traducen los fallos del proveedor; un bug propio sigue subiendo
            if is_provider_error(error):
                raise as_llm_error(error) from error
            raise
        turn = state.get("turn", 1)
        trace = [event for event in state.get("trace", []) if event.get("turn") == turn]
        tools_used = [call["tool"] for event in trace if event["node"] == "act" for call in event["tool_calls"]]
        final = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
        return AgentRunResult(
            thread_id=thread,
            answer=_text(final.content) if final else "",
            plan=state.get("plan", []),
            plan_source=state.get("plan_source", ""),
            tools_used=tools_used,
            wrote=state.get("wrote", []),
            replans=state.get("replans", 0),
            memories_used=state.get("memories", []),
            steps=state.get("steps", 0),
            trace=trace,
        )
