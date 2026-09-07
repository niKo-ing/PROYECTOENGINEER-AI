from sqlalchemy.orm import Session

from app.ai.engine.tool_engine import AIEngine
from app.ai.orchestrator import AIOrchestrator
from app.ai.providers.base import LLMProvider
from app.ai.schemas.chat import ChatResponse, ChatTurn
from app.core.security import AuthenticatedUser


class ChatService:
    def __init__(self, db: Session, user: AuthenticatedUser, provider: LLMProvider):
        self.db = db
        self.user = user
        self.provider = provider

    def chat(
        self,
        message: str,
        product_id: int | None = None,
        history: list[ChatTurn] | None = None,
    ) -> ChatResponse:
        orchestrator = AIOrchestrator(self.db, self.user, self.provider, engine=AIEngine(self.db, self.user))
        return orchestrator.chat(message, product_id=product_id, history=history)