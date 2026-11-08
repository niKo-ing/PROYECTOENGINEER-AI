from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.engine.tool_engine import AIEngine
from app.ai.llm_router import llm_router
from app.ai.providers.factory import get_fallback_llm_provider, get_llm_provider
from app.ai.providers.base import LLMProvider
from app.ai.schemas.chat import ChatRequest, ChatResponse
from app.ai.services.chat_service import ChatService
from app.ai.schemas.tools import ToolExecutionRequest, ToolExecutionResult
from app.core.limits import limit_ai
from app.core.security import AuthenticatedUser, get_current_user
from app.db import get_db

router = APIRouter(prefix="/ai", tags=["ai"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
# Usuario autenticado que además no superó su límite de consultas de IA por hora.
LimitedUser = Annotated[AuthenticatedUser, Depends(limit_ai)]

# Errores del modelo propio que justifican pasar la consulta al respaldo (caído, timeout, respuesta inválida).
_FAILOVER_STATUS = {502, 503, 504}


@router.post("/tools", response_model=ToolExecutionResult)
def execute_tool(payload: ToolExecutionRequest, user: CurrentUser, db: DbSession):
    return AIEngine(db, user).execute(payload)


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    user: LimitedUser,
    db: DbSession,
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    fallback: Annotated[LLMProvider | None, Depends(get_fallback_llm_provider)],
):
    def answer(chosen: LLMProvider) -> ChatResponse:
        return ChatService(db, user, chosen).chat(payload.message, product_id=payload.product_id, history=payload.history)

    with llm_router.turn(has_fallback=fallback is not None) as route:
        if route == "fallback" and fallback is not None:
            return answer(fallback)
        try:
            return answer(provider)
        except HTTPException as error:
            if fallback is None or error.status_code not in _FAILOVER_STATUS:
                raise
            # El modelo propio no respondió: los próximos 30 s van directo al respaldo y esta consulta se reintenta allí.
            llm_router.mark_primary_down()
            return answer(fallback)
