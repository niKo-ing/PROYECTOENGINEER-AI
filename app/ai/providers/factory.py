from fastapi import HTTPException, status

from app.ai.providers.base import LLMProvider, ProviderNotConfiguredError
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.core.config import settings


def create_llm_provider(
    provider_name: str,
    *,
    gemini_api_key: str,
    gemini_model: str,
    openai_api_key: str,
    openai_model: str,
    timeout_seconds: float,
) -> LLMProvider:
    if provider_name == "gemini":
        if not gemini_api_key:
            raise ProviderNotConfiguredError("GEMINI_API_KEY no está configurada")
        if not gemini_model:
            raise ProviderNotConfiguredError("GEMINI_MODEL no está configurado")
        return GeminiProvider(gemini_api_key, gemini_model, timeout_seconds)
    if provider_name == "openai":
        if not openai_api_key or not openai_model:
            raise ProviderNotConfiguredError("OpenAI no está configurado")
        return OpenAIProvider(openai_api_key, openai_model, timeout_seconds)
    raise ProviderNotConfiguredError("LLM_PROVIDER no es compatible")


def get_llm_provider() -> LLMProvider:
    try:
        return create_llm_provider(
            settings.llm_provider,
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_model,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    except ProviderNotConfiguredError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=error.detail) from error
