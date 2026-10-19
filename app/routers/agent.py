from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.llm import AgentLLMError, AgentNotConfiguredError, get_chat_model
from app.agent.memory import LongTermMemory
from app.agent.service import AgentService, default_checkpointer
from app.ai.rag.embedding import EmbeddingProvider
from app.ai.rag.factory import get_embedding_provider
from app.core.security import AuthenticatedUser, get_current_user
from app.db import get_db

router = APIRouter(prefix="/agent", tags=["agent"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


class AgentRunRequest(BaseModel):
    message: str = Field(min_length=2, max_length=1200)
    thread_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


def get_agent_llm() -> BaseChatModel:
    try:
        return get_chat_model()
    except AgentNotConfiguredError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


def get_agent_embedder() -> EmbeddingProvider:
    return get_embedding_provider()


def get_agent_checkpointer() -> Any:
    return default_checkpointer()


@router.post("/run")
def run_agent(
    payload: AgentRunRequest,
    user: CurrentUser,
    db: DbSession,
    llm: Annotated[BaseChatModel, Depends(get_agent_llm)],
    embedder: Annotated[EmbeddingProvider, Depends(get_agent_embedder)],
    checkpointer: Annotated[Any, Depends(get_agent_checkpointer)],
):
    """Ejecuta el agente de ahorro sobre un pedido. Devuelve respuesta, plan, herramientas y traza."""
    service = AgentService(db, user.id, llm=llm, embedder=embedder, checkpointer=checkpointer)
    try:
        return service.run(payload.message, payload.thread_id).as_dict()
    except AgentLLMError as error:
        code = status.HTTP_429_TOO_MANY_REQUESTS if error.rate_limited else status.HTTP_503_SERVICE_UNAVAILABLE
        raise HTTPException(status_code=code, detail=str(error)) from error


@router.get("/memories")
def list_memories(user: CurrentUser, db: DbSession, embedder: Annotated[EmbeddingProvider, Depends(get_agent_embedder)]):
    """Lo que el agente recuerda del usuario autenticado (solo lectura)."""
    memory = LongTermMemory(db, user.id, embedder)
    return {"memories": [{"id": m.id, "kind": m.kind, "content": m.content, "importance": m.importance} for m in memory.all()]}
