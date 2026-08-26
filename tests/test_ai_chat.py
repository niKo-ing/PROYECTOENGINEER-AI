from dataclasses import dataclass, field

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.providers.base import LLMProvider, ProviderError, ProviderResponse, ToolCall
from app.ai.providers.factory import get_llm_provider
from app.core.security import AuthenticatedUser, get_current_user
from app.db import Base, get_db
from app.main import app
from app.models.catalog import Category, Product, Store, StoreOffer
from app.models.user_profile import UserProfile

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)
client = TestClient(app)


@dataclass
class FakeProvider(LLMProvider):
    initial: ProviderResponse
    final: ProviderResponse = field(default_factory=lambda: ProviderResponse(text="Respuesta final."))
    outputs: list[dict] = field(default_factory=list)
    definitions: list[dict] = field(default_factory=list)

    def request_tools(self, message: str, tools: list[dict]) -> ProviderResponse:
        self.definitions = tools
        return self.initial

    def generate_final(self, message: str, initial: ProviderResponse, tool_outputs: list[dict]) -> ProviderResponse:
        self.outputs = tool_outputs
        return self.final


class FailingProvider(LLMProvider):
    def request_tools(self, message: str, tools: list[dict]) -> ProviderResponse:
        raise ProviderError()

    def generate_final(self, message: str, initial: ProviderResponse, tool_outputs: list[dict]) -> ProviderResponse:
        raise ProviderError()


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


def set_context(provider: LLMProvider, user_id: str = "user-one"):
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id)
    app.dependency_overrides[get_llm_provider] = lambda: provider


def reset_database():
    with TestingSession() as db:
        db.execute(delete(UserProfile))
        db.execute(delete(StoreOffer))
        db.execute(delete(Product))
        db.execute(delete(Category))
        db.execute(delete(Store))
        db.commit()


def add_product() -> int:
    with TestingSession() as db:
        category = Category(name="notebook", slug="notebook")
        store = Store(name="Tienda de prueba", domain="test.local")
        product = Product(name="Notebook Gamer", category_entity=category, rating=4.5)
        db.add(product)
        db.add(StoreOffer(product=product, store=store, url="https://test.local/notebook-gamer", price=899990))
        db.commit()
        db.refresh(product)
        return product.id


def add_profile(user_id: str, name: str):
    with TestingSession() as db:
        db.add(UserProfile(user_id=user_id, display_name=name, typical_budget_clp=500000, general_preferences={}, favorite_categories=["notebook"], favorite_brands=[], rejected_brands=[], shopping_preferences={}))
        db.commit()


def test_chat_simple_without_tool_call():
    provider = FakeProvider(initial=ProviderResponse(text="Hola, ¿qué producto buscas?"))
    set_context(provider)
    response = client.post("/api/v1/ai/chat", json={"message": "Hola"})
    assert response.status_code == 200
    assert response.json()["answer"] == "Hola, ¿qué producto buscas?"
    assert response.json()["tools_used"] == []
    assert {item["function"]["name"] for item in provider.definitions} == {"search_products", "get_product", "get_product_offers", "get_price_history", "get_user_profile"}


def test_chat_executes_search_products_tool():
    reset_database()
    add_product()
    provider = FakeProvider(initial=ProviderResponse(text="", tool_calls=[ToolCall(id="call-1", name="search_products", arguments={"query": "gamer"})]))
    set_context(provider)
    response = client.post("/api/v1/ai/chat", json={"message": "Busca un notebook gamer"})
    assert response.status_code == 200
    assert response.json()["tools_used"] == ["search_products"]
    assert provider.outputs[0]["output"]["items"][0]["name"] == "Notebook Gamer"


def test_chat_executes_get_product_tool():
    reset_database()
    product_id = add_product()
    provider = FakeProvider(initial=ProviderResponse(text="", tool_calls=[ToolCall(id="call-1", name="get_product", arguments={"product_id": product_id})]))
    set_context(provider)
    response = client.post("/api/v1/ai/chat", json={"message": "Dame el detalle"})
    assert response.status_code == 200
    assert provider.outputs[0]["output"]["price_clp"] == 899990


def test_chat_executes_get_user_profile_for_authenticated_user():
    reset_database()
    add_profile("user-one", "Ana")
    add_profile("user-two", "Beto")
    provider = FakeProvider(initial=ProviderResponse(text="", tool_calls=[ToolCall(id="call-1", name="get_user_profile", arguments={})]))
    set_context(provider, "user-one")
    response = client.post("/api/v1/ai/chat", json={"message": "¿Cuáles son mis preferencias?"})
    assert response.status_code == 200
    assert provider.outputs[0]["output"]["display_name"] == "Ana"
    assert "user_id" not in provider.outputs[0]["output"]


def test_unknown_tool_and_invalid_arguments_are_returned_as_safe_tool_errors():
    provider = FakeProvider(initial=ProviderResponse(text="", tool_calls=[ToolCall(id="unknown", name="drop_database", arguments={}), ToolCall(id="invalid", name="get_product", arguments={"product_id": 0})]))
    set_context(provider)
    response = client.post("/api/v1/ai/chat", json={"message": "Haz algo"})
    assert response.status_code == 200
    assert all("error" in output["output"] for output in provider.outputs)


def test_chat_requires_authentication():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_llm_provider] = lambda: FakeProvider(initial=ProviderResponse(text="Hola"))
    app.dependency_overrides.pop(get_current_user, None)
    response = client.post("/api/v1/ai/chat", json={"message": "Hola"})
    assert response.status_code == 401


def test_provider_not_configured_and_provider_failure_are_reported():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-one")

    def unavailable_provider():
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY no está configurada")

    app.dependency_overrides[get_llm_provider] = unavailable_provider
    unavailable = client.post("/api/v1/ai/chat", json={"message": "Hola"})
    assert unavailable.status_code == 503

    set_context(FailingProvider())
    failed = client.post("/api/v1/ai/chat", json={"message": "Hola"})
    assert failed.status_code == 502


def test_invalid_provider_response_is_rejected():
    set_context(FakeProvider(initial=ProviderResponse(text="")))
    response = client.post("/api/v1/ai/chat", json={"message": "Hola"})
    assert response.status_code == 502
