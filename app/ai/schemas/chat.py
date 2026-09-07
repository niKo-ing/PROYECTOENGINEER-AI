from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    """A single prior turn in the conversation, sent by the client.

    ``products`` carries the structured product data the assistant returned in
    a previous turn so the backend can resolve anaphora such as "compararlas",
    "el primero" or "ese producto" across turns.
    """

    role: Literal["user", "assistant"] = "user"
    content: str = ""
    products: list[dict[str, Any]] | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)
    product_id: int | None = Field(default=None, ge=1)
    history: list[ChatTurn] = Field(default_factory=list)


class ChatUsage(BaseModel):
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None


class ChatResponse(BaseModel):
    answer: str
    tools_used: list[str] = Field(default_factory=list)
    usage: ChatUsage | None = None
    products: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Productos estructurados para que el frontend los renderice como cards.",
    )
    comparison: dict[str, Any] | None = None
    intent: str | None = None
    need_clarification: bool = False
    sources: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Fuentes externas de investigación (Evidence estructurado) que respaldan la respuesta.",
    )
    research: bool = Field(
        default=False,
        description="True cuando se usó investigación web externa para complementar el catálogo.",
    )
    recommendation: dict[str, Any] | None = Field(
        default=None,
        description="Recomendación estructurada con winner_id, confidence, evidence y unknowns.",
    )
    evidence: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Evidencia científica/estructural que sustenta la respuesta (catálogo, web o knowledge base).",
    )
    trace: list[dict[str, Any]] | None = Field(
        default=None,
        description="Traza interna del orquestador (rag/web_research/plan) para observabilidad.",
    )
    trace_id: str | None = Field(
        default=None,
        description="Identificador de la traza de esta respuesta para facilitar el debug.",
    )
