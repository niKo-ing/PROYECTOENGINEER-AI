from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.engine.tool_engine import AIEngine
from app.ai.providers.base import LLMProvider, ProviderError, ProviderInvalidResponseError, Usage
from app.ai.schemas.chat import ChatResponse, ChatUsage
from app.ai.schemas.tools import ToolExecutionRequest
from app.core.config import settings
from app.core.security import AuthenticatedUser


class ChatService:
    def __init__(self, db: Session, user: AuthenticatedUser, provider: LLMProvider):
        self.tool_engine = AIEngine(db, user)
        self.provider = provider

    def chat(self, message: str) -> ChatResponse:
        try:
            initial = self.provider.request_tools(message, self.tool_engine.tool_definitions())
            if not initial.tool_calls:
                return self._response(initial.text, [], initial.usage)

            calls = initial.tool_calls[: settings.ai_max_tool_calls]
            outputs: list[dict] = []
            used_tools: list[str] = []
            for call in calls:
                try:
                    result = self.tool_engine.execute(ToolExecutionRequest(tool=call.name, parameters=call.arguments))
                    outputs.append({"call_id": call.id, "name": call.name, "output": result.data})
                    used_tools.append(call.name)
                except HTTPException as error:
                    outputs.append({"call_id": call.id, "name": call.name, "output": {"error": {"code": error.status_code, "detail": error.detail}}})

            final = self.provider.generate_final(message, initial, outputs)
            return self._response(final.text, used_tools, self._combine_usage(initial.usage, final.usage))
        except ProviderError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail) from error

    def _response(self, text: str, tools_used: list[str], usage: Usage | None) -> ChatResponse:
        if not text.strip():
            raise HTTPException(status_code=502, detail=ProviderInvalidResponseError.detail)
        response_usage = ChatUsage(model=usage.model, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens, latency_ms=usage.latency_ms) if usage else None
        return ChatResponse(answer=text, tools_used=tools_used, usage=response_usage)

    @staticmethod
    def _combine_usage(first: Usage | None, second: Usage | None) -> Usage | None:
        if first is None:
            return second
        if second is None:
            return first
        return Usage(
            model=second.model,
            input_tokens=(first.input_tokens or 0) + (second.input_tokens or 0),
            output_tokens=(first.output_tokens or 0) + (second.output_tokens or 0),
            latency_ms=(first.latency_ms or 0) + (second.latency_ms or 0),
        )
