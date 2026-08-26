from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)


class ChatUsage(BaseModel):
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None


class ChatResponse(BaseModel):
    answer: str
    tools_used: list[str] = Field(default_factory=list)
    usage: ChatUsage | None = None
