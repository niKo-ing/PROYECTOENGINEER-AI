import json
import logging
from time import perf_counter
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from app.ai.providers.base import LLMProvider, ProviderError, ProviderInvalidResponseError, ProviderResponse, ProviderTimeoutError, ToolCall, Usage

logger = logging.getLogger(__name__)
SYSTEM_INSTRUCTIONS = (
    "Responde en español basándote solo en los datos del catálogo y las herramientas. "
    "No inventes productos, precios ni preferencias. "
    "Cuando la búsqueda no devuelva resultados, o el usuario pregunte por tiendas, "
    "categorías o marcas que no están en el catálogo, respondé que ese artículo/tienda "
    "no está en el catálogo actual y que no hay más productos fuera de él. "
    "Nunca hables de 'iniciar sesión', 'cuenta', 'perfil' ni 'sesión'. "
    "Usá get_user_profile únicamente si el usuario pregunta por sus preferencias o presupuesto personales."
)


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, timeout_seconds: float):
        self.client = OpenAI(api_key=api_key, timeout=timeout_seconds)
        self.model = model

    def request_tools(self, message: str, tools: list[dict[str, Any]]) -> ProviderResponse:
        try:
            started = perf_counter()
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": SYSTEM_INSTRUCTIONS}, {"role": "user", "content": message}],
                tools=tools,
                tool_choice="auto",
            )
            return self._parse_response(completion, int((perf_counter() - started) * 1000))
        except APITimeoutError as error:
            raise ProviderTimeoutError() from error
        except (APIConnectionError, APIStatusError) as error:
            logger.warning("OpenAI request failed: %s", type(error).__name__)
            raise ProviderError() from error

    def generate_final(self, message: str, initial: ProviderResponse, tool_outputs: list[dict[str, Any]]) -> ProviderResponse:
        assistant_message = {
            "role": "assistant",
            "content": initial.text or None,
            "tool_calls": [
                {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments)}}
                for call in initial.tool_calls
            ],
        }
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": message},
            assistant_message,
            *[{"role": "tool", "tool_call_id": item["call_id"], "content": json.dumps(item["output"])} for item in tool_outputs],
        ]
        try:
            started = perf_counter()
            completion = self.client.chat.completions.create(model=self.model, messages=messages)
            return self._parse_response(completion, int((perf_counter() - started) * 1000))
        except APITimeoutError as error:
            raise ProviderTimeoutError() from error
        except (APIConnectionError, APIStatusError) as error:
            logger.warning("OpenAI final response failed: %s", type(error).__name__)
            raise ProviderError() from error

    def _parse_response(self, completion: Any, latency_ms: int) -> ProviderResponse:
        if not completion.choices:
            raise ProviderInvalidResponseError()
        message = completion.choices[0].message
        calls: list[ToolCall] = []
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments)
            except (TypeError, json.JSONDecodeError) as error:
                raise ProviderInvalidResponseError() from error
            if not isinstance(arguments, dict):
                raise ProviderInvalidResponseError()
            calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
        usage = completion.usage
        return ProviderResponse(
            text=message.content or "",
            tool_calls=calls,
            usage=Usage(model=self.model, input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens, latency_ms=latency_ms) if usage else Usage(model=self.model, latency_ms=latency_ms),
        )
