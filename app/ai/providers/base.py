from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ProviderError(Exception):
    status_code = 502
    detail = "Error al comunicarse con el proveedor LLM"


class ProviderNotConfiguredError(ProviderError):
    status_code = 503
    detail = "Proveedor LLM no configurado"

    def __init__(self, detail: str | None = None):
        if detail:
            self.detail = detail


class ProviderTimeoutError(ProviderError):
    status_code = 504
    detail = "El proveedor LLM excedió el tiempo de espera"


class ProviderInvalidResponseError(ProviderError):
    detail = "El proveedor LLM devolvió una respuesta inválida"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None
    continuation: Any = None


class LLMProvider(ABC):
    @abstractmethod
    def request_tools(self, message: str, tools: list[dict[str, Any]]) -> ProviderResponse:
        """Ask the model whether one of the registered tools is necessary."""

    @abstractmethod
    def generate_final(self, message: str, initial: ProviderResponse, tool_outputs: list[dict[str, Any]]) -> ProviderResponse:
        """Generate the final user-facing text after tool execution."""
