from types import SimpleNamespace

import pytest

from app.ai.providers.base import ProviderError, ProviderInvalidResponseError, ProviderNotConfiguredError, ProviderTimeoutError
from app.ai.providers.factory import create_llm_provider
from app.ai.providers.gemini_provider import GeminiProvider


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def generate_content(self, **kwargs):
        self.requests.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def response(text="Hola", function_calls=None):
    return SimpleNamespace(
        text=text,
        function_calls=function_calls,
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[]))],
        usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=4),
    )


def test_gemini_is_constructed_when_configured():
    provider = create_llm_provider("gemini", gemini_api_key="test-key", gemini_model="test-model", openai_api_key="", openai_model="", timeout_seconds=10)
    assert isinstance(provider, GeminiProvider)
    assert provider.model == "test-model"


@pytest.mark.parametrize(("api_key", "model", "message"), [("", "gemini-test", "GEMINI_API_KEY"), ("test-key", "", "GEMINI_MODEL")])
def test_gemini_requires_key_and_model(api_key, model, message):
    with pytest.raises(ProviderNotConfiguredError, match=message):
        create_llm_provider("gemini", gemini_api_key=api_key, gemini_model=model, openai_api_key="", openai_model="", timeout_seconds=10)


def test_gemini_parses_normal_response_and_usage():
    models = FakeModels(response())
    provider = GeminiProvider("test-key", "gemini-test", 10, client=SimpleNamespace(models=models))
    result = provider.request_tools("Hola", [])
    assert result.text == "Hola"
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 4
    assert "timeout" not in models.requests[0]


def test_gemini_sends_tool_output_back_with_original_tool_definitions():
    models = FakeModels(response(text="Respuesta final"))
    provider = GeminiProvider("test-key", "gemini-test", 10, client=SimpleNamespace(models=models))
    tools = [{"type": "function", "function": {"name": "get_product", "description": "Obtiene un producto", "parameters": {"type": "object", "properties": {}}}}]
    initial = provider.request_tools("Consulta", tools)
    final = provider.generate_final("Consulta", initial, [{"call_id": "call-1", "name": "get_product", "output": {"id": 1}}])
    assert final.text == "Respuesta final"
    # request_tools exposes the tools; the final answering turn is text-only so
    # the model cannot re-call tools and leave the final answer empty.
    assert models.requests[0]["config"].tools is not None
    assert models.requests[1]["config"].tools is None


@pytest.mark.parametrize("name,arguments", [("search_products", {"query": "notebook"}), ("get_product", {"product_id": 1}), ("get_user_profile", {})])
def test_gemini_parses_registered_tool_calls(name, arguments):
    call = SimpleNamespace(id="call-1", name=name, args=arguments)
    provider = GeminiProvider("test-key", "gemini-test", 10, client=SimpleNamespace(models=FakeModels(response(text="", function_calls=[call]))))
    result = provider.request_tools("Consulta", [])
    assert result.tool_calls[0].name == name
    assert result.tool_calls[0].arguments == arguments


def test_gemini_maps_provider_error_and_timeout():
    failing = GeminiProvider("test-key", "gemini-test", 10, client=SimpleNamespace(models=FakeModels(error=RuntimeError("service unavailable"))))
    with pytest.raises(ProviderError):
        failing.request_tools("Hola", [])

    timeout = GeminiProvider("test-key", "gemini-test", 10, client=SimpleNamespace(models=FakeModels(error=TimeoutError())))
    with pytest.raises(ProviderTimeoutError):
        timeout.request_tools("Hola", [])


def test_gemini_rejects_invalid_response():
    provider = GeminiProvider("test-key", "gemini-test", 10, client=SimpleNamespace(models=FakeModels(SimpleNamespace(text="", candidates=[]))))
    with pytest.raises(ProviderInvalidResponseError):
        provider.request_tools("Hola", [])


def test_gemini_generate_final_without_tool_calls_sends_single_turn():
    """When the model answers without requesting tools but the orchestrator has
    deterministic evidence to surface, generate_final must answer over the
    augmented message as one user turn (no empty function-response sequence)."""
    models = FakeModels(response(text="El iPhone 15 128GB es más barato."))
    provider = GeminiProvider("test-key", "gemini-test", 10, client=SimpleNamespace(models=models))
    initial = provider.request_tools("comparalos", [])
    assert initial.tool_calls == []

    final = provider.generate_final("comparalos\n\nProductos relevantes: iPhone 15, iPhone 16", initial, [])
    assert final.text == "El iPhone 15 128GB es más barato."
    assert len(models.requests) == 2
    contents = models.requests[1]["contents"]
    assert len(contents) == 1
    assert contents[0].role == "user"
