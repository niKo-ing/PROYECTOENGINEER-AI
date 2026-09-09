import logging
from time import perf_counter
from typing import Any

from google import genai
from google.genai import types

from app.ai.providers.base import LLMProvider, ProviderError, ProviderInvalidResponseError, ProviderResponse, ProviderTimeoutError, ToolCall, Usage
from app.ai.system_instructions import SYSTEM_INSTRUCTIONS

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, timeout_seconds: float, client: Any | None = None):
        self.client = client or genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)))
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._active_tool_config: types.GenerateContentConfig | None = None

    def request_tools(self, message: str, tools: list[dict[str, Any]]) -> ProviderResponse:
        config = self._tool_config(tools)
        self._active_tool_config = config
        try:
            started = perf_counter()
            response = self.client.models.generate_content(
                model=self.model,
                contents=[types.Content(role="user", parts=[types.Part(text=message)])],
                config=config,
            )
            return self._parse_response(response, int((perf_counter() - started) * 1000))
        except ProviderInvalidResponseError:
            raise
        except Exception as error:
            self._raise_provider_error(error, "Gemini request failed")

    def generate_final(self, message: str, initial: ProviderResponse, tool_outputs: list[dict[str, Any]]) -> ProviderResponse:
        if tool_outputs:
            if initial.continuation is None:
                raise ProviderInvalidResponseError()
            response_parts = [
                types.Part.from_function_response(name=item["name"], response={"result": item["output"]})
                for item in tool_outputs
            ]
            contents = [
                types.Content(role="user", parts=[types.Part(text=message)]),
                initial.continuation,
                types.Content(role="user", parts=response_parts),
            ]
        else:
            # No function responses to feed back. The message already carries the
            # deterministic evidence (products/comparison); answer over it as a
            # single fresh user turn to avoid a malformed multi-part sequence.
            contents = [types.Content(role="user", parts=[types.Part(text=message)])]
        try:
            started = perf_counter()
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=self._tool_config([]),
            )
            return self._parse_response(response, int((perf_counter() - started) * 1000))
        except ProviderInvalidResponseError:
            raise
        except Exception as error:
            self._raise_provider_error(error, "Gemini final response failed")

    def _tool_config(self, tools: list[dict[str, Any]]) -> types.GenerateContentConfig:
        declarations = [
            types.FunctionDeclaration(
                name=item["function"]["name"],
                description=item["function"]["description"],
                parametersJsonSchema=item["function"]["parameters"],
            )
            for item in tools
        ]
        return types.GenerateContentConfig(
            systemInstruction=SYSTEM_INSTRUCTIONS,
            tools=[types.Tool(functionDeclarations=declarations)] if declarations else None,
            automaticFunctionCalling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def _parse_response(self, response: Any, latency_ms: int) -> ProviderResponse:
        candidates = getattr(response, "candidates", None)
        if not candidates:
            raise ProviderInvalidResponseError()
        candidate = candidates[0]
        content = getattr(candidate, "content", None)
        if content is None:
            raise ProviderInvalidResponseError()
        calls = self._function_calls(response, content)
        text = getattr(response, "text", "") or ""
        usage_metadata = getattr(response, "usage_metadata", None) or getattr(response, "usageMetadata", None)
        usage = Usage(
            model=self.model,
            input_tokens=getattr(usage_metadata, "prompt_token_count", None) if usage_metadata else None,
            output_tokens=getattr(usage_metadata, "candidates_token_count", None) if usage_metadata else None,
            latency_ms=latency_ms,
        )
        return ProviderResponse(text=text, tool_calls=calls, usage=usage, continuation=content)

    @staticmethod
    def _function_calls(response: Any, content: Any) -> list[ToolCall]:
        raw_calls = getattr(response, "function_calls", None) or getattr(response, "functionCalls", None)
        if raw_calls is None:
            raw_calls = [getattr(part, "function_call", None) or getattr(part, "functionCall", None) for part in getattr(content, "parts", [])]
        calls = []
        for index, call in enumerate(raw_calls):
            if call is None:
                continue
            name = getattr(call, "name", None)
            arguments = getattr(call, "args", None)
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise ProviderInvalidResponseError()
            calls.append(ToolCall(id=getattr(call, "id", None) or f"gemini-call-{index}", name=name, arguments=arguments))
        return calls

    @staticmethod
    def _raise_provider_error(error: Exception, log_message: str) -> None:
        if isinstance(error, TimeoutError) or "timeout" in type(error).__name__.lower():
            raise ProviderTimeoutError() from error
        logger.warning("%s: %s", log_message, type(error).__name__)
        raise ProviderError() from error
