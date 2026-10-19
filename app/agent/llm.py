"""Modelo de chat del agente.

LangGraph/LangChain solo piden un ``BaseChatModel``: producción usa Gemini (el mismo
proveedor y las mismas variables ``GEMINI_*`` del resto de la app); las pruebas y la
demo sin red usan ``ScriptedChatModel`` (ver ``testing.py``).
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from app.core.config import Settings, settings as default_settings


class AgentNotConfiguredError(RuntimeError):
    """Falta la llave o el modelo de Gemini."""


class AgentLLMError(RuntimeError):
    """El proveedor del modelo falló (cuota, red, respuesta inválida). ``rate_limited`` distingue la cuota."""

    def __init__(self, message: str, *, rate_limited: bool = False):
        super().__init__(message)
        self.rate_limited = rate_limited


_PROVIDER_PACKAGES = {"langchain_google_genai", "google", "httpx", "httpcore"}


def is_provider_error(error: BaseException) -> bool:
    """¿La excepción viene de la librería del proveedor (y no de un bug del grafo)?"""
    return type(error).__module__.split(".")[0] in _PROVIDER_PACKAGES


def as_llm_error(error: BaseException) -> AgentLLMError:
    text = str(error)
    limited = "RESOURCE_EXHAUSTED" in text or "429" in text or "RateLimit" in type(error).__name__
    return AgentLLMError("Se agotó la cuota del modelo; intenta de nuevo en un rato." if limited else f"El modelo no respondió: {text[:200]}", rate_limited=limited)


def get_chat_model(cfg: Settings | None = None, *, temperature: float = 0.2) -> BaseChatModel:
    cfg = cfg or default_settings
    if not cfg.gemini_api_key:
        raise AgentNotConfiguredError("GEMINI_API_KEY no está configurada")
    if not cfg.gemini_model:
        raise AgentNotConfiguredError("GEMINI_MODEL no está configurado")
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=cfg.gemini_model,
        google_api_key=cfg.gemini_api_key,
        temperature=temperature,
        timeout=cfg.llm_timeout_seconds,
        max_retries=2,
    )
