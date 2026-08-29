from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.engine.tool_engine import AIEngine
from app.ai.providers.factory import get_llm_provider
from app.ai.providers.base import LLMProvider
from app.ai.schemas.chat import ChatRequest, ChatResponse
from app.ai.services.chat_service import ChatService
from app.ai.schemas.tools import ToolExecutionRequest, ToolExecutionResult
from app.core.security import AuthenticatedUser, get_current_user
from app.db import get_db

router = APIRouter(prefix="/ai", tags=["ai"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


@router.post("/tools", response_model=ToolExecutionResult)
def execute_tool(payload: ToolExecutionRequest, user: CurrentUser, db: DbSession):
    return AIEngine(db, user).execute(payload)


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, user: CurrentUser, db: DbSession, provider: Annotated[LLMProvider, Depends(get_llm_provider)]):
    return ChatService(db, user, provider).chat(payload.message, product_id=payload.product_id)
