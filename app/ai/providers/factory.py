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
    openai_base_url: str = "",
) -> LLMProvider:
    if provider_name == "gemini":
        if not gemini_api_key:
            raise ProviderNotConfiguredError("GEMINI_API_KEY no está configurada")
        if not gemini_model:
            raise ProviderNotConfiguredError("GEMINI_MODEL no está configurado")
        return GeminiProvider(gemini_api_key, gemini_model, timeout_seconds)
    if provider_name == "openai":
        # Un servidor propio (vLLM/Ollama) no exige llave: basta con la dirección y el modelo.
        if not openai_model or not (openai_api_key or openai_base_url):
            raise ProviderNotConfiguredError("OpenAI no está configurado")
        return OpenAIProvider(openai_api_key, openai_model, timeout_seconds, base_url=openai_base_url or None)
    raise ProviderNotConfiguredError("LLM_PROVIDER no es compatible")


def _from_settings(provider_name: str) -> LLMProvider:
    return create_llm_provider(
        provider_name,
        gemini_api_key=settings.gemini_api_key,
        gemini_model=settings.gemini_model,
        openai_api_key=settings.openai_api_key,
        openai_model=settings.openai_model,
        timeout_seconds=settings.llm_timeout_seconds,
        openai_base_url=settings.openai_base_url,
    )


def get_llm_provider() -> LLMProvider:
    try:
        return _from_settings(settings.llm_provider)
    except ProviderNotConfiguredError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=error.detail) from error


def get_fallback_llm_provider() -> LLMProvider | None:
    """Proveedor de respaldo (``LLM_FALLBACK_PROVIDER``) o ``None`` si no hay uno configurado."""
    name = settings.llm_fallback_provider
    if not name or name == settings.llm_provider:
        return None
    try:
        return _from_settings(name)
    except ProviderNotConfiguredError:
        return None
