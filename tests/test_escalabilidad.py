"""Mejoras para 10.000 usuarios: seguridad, límites de uso, caché, cola de IA y respaldo del modelo."""

import threading

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pytest

from app.ai.llm_router import LLMRouter, llm_router
from app.ai.providers.base import LLMProvider, ProviderError, ProviderResponse
from app.ai.providers.factory import create_llm_provider, get_fallback_llm_provider, get_llm_provider
from app.ai.providers.openai_provider import OpenAIProvider
from app.core.cache import CatalogCache, catalog_cache
from app.core.limits import RateLimiter, catalog_limiter, limit_ai
from app.core.security import AuthenticatedUser, get_current_user
from app.db import Base, get_db
from app.main import app
from app.models.catalog import Category, PriceHistory, Product, ProductSpecValue, ProductSpecValueHistory, Store, StoreOffer

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)
client = TestClient(app)
ADMIN = AuthenticatedUser(id="admin-user", email="admin@example.com")


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def base_limpia():
    # Otras pruebas dejan reemplazos de dependencias (p. ej. un usuario falso): se parte de cero.
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_get_db
    with TestingSession() as db:
        for model in (PriceHistory, StoreOffer, ProductSpecValueHistory, ProductSpecValue, Product, Store, Category):
            db.execute(delete(model))
        db.commit()
    yield
    app.dependency_overrides.clear()


def crear_producto(name: str):
    app.dependency_overrides[get_current_user] = lambda: ADMIN
    response = client.post("/api/v1/products", json={"name": name, "brand": "Solo", "category": "notebook", "price_clp": 500000})
    app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 201
    return response.json()


# ── 1. Seguridad ─────────────────────────────────────────────────────────────────────────────


def test_crear_producto_exige_login():
    response = client.post("/api/v1/products", json={"name": "Basura", "brand": "X", "category": "x", "price_clp": 1})
    assert response.status_code == 401


# ── 2. Caché del catálogo ────────────────────────────────────────────────────────────────────


def test_busqueda_repetida_sale_de_la_cache_y_se_invalida_al_cambiar_el_catalogo():
    crear_producto("Notebook Uno")
    primera = client.get("/api/v1/products", params={"query": "notebook"})
    segunda = client.get("/api/v1/products", params={"query": "notebook"})
    assert primera.headers["X-Cache"] == "MISS"
    assert segunda.headers["X-Cache"] == "HIT"
    assert segunda.json() == primera.json()
    assert "s-maxage" in segunda.headers["Cache-Control"]

    crear_producto("Notebook Dos")  # cambia el catálogo: la caché se invalida
    tercera = client.get("/api/v1/products", params={"query": "notebook"})
    assert tercera.headers["X-Cache"] == "MISS"
    assert tercera.json()["total"] == 2


def test_un_404_no_se_guarda_en_cache():
    assert client.get("/api/v1/products/999999").status_code == 404
    assert client.get("/api/v1/products/999999").status_code == 404


def test_cache_expira_y_respeta_el_maximo():
    cache = CatalogCache(ttl_seconds=60, max_items=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.get("a") is None  # el más antiguo sale primero
    assert cache.get("c") == 3
    cache.invalidate()
    assert cache.get("c") is None
    assert CatalogCache(ttl_seconds=0).get("x") is None


# ── 3. Límites de uso ────────────────────────────────────────────────────────────────────────


def test_limite_por_ip_en_el_catalogo_responde_429(monkeypatch):
    monkeypatch.setattr(catalog_limiter, "limit", 3)
    codes = [client.get("/api/v1/categories").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    bloqueada = client.get("/api/v1/categories")
    assert int(bloqueada.headers["Retry-After"]) > 0


def test_limite_de_ia_por_usuario():
    limiter = RateLimiter("ia", limit=2, window_seconds=3600)
    assert limiter.hit("ana")[0] and limiter.hit("ana")[0]
    assert not limiter.hit("ana")[0]
    assert limiter.hit("beto")[0]  # cada usuario tiene su propio cupo
    assert RateLimiter("ia", limit=0, window_seconds=60).hit("ana") == (True, 0)


def test_dependencia_de_ia_bloquea_al_superar_el_cupo(monkeypatch):
    from app.core import limits

    monkeypatch.setattr(limits.ai_limiter, "limit", 1)
    user = AuthenticatedUser(id="bot")
    assert limit_ai(user) is user
    with pytest.raises(HTTPException) as error:
        limit_ai(user)
    assert error.value.status_code == 429


# ── 4. Cola de la GPU y respaldo ────────────────────────────────────────────────────────────


def test_gpu_llena_sin_respaldo_responde_503_y_con_respaldo_usa_el_respaldo():
    router = LLMRouter(max_concurrent=1, wait_seconds=0.05)
    dentro, salir = threading.Event(), threading.Event()

    def ocupar():
        with router.turn(has_fallback=False):
            dentro.set()
            salir.wait(2)

    hilo = threading.Thread(target=ocupar)
    hilo.start()
    dentro.wait(2)
    try:
        with pytest.raises(HTTPException) as error:
            with router.turn(has_fallback=False):
                pass
        assert error.value.status_code == 503
        with router.turn(has_fallback=True) as route:
            assert route == "fallback"
    finally:
        salir.set()
        hilo.join()
    with router.turn(has_fallback=True) as route:
        assert route == "primary"  # se liberó el cupo


def test_modelo_caido_manda_todo_al_respaldo_por_un_rato():
    router = LLMRouter(max_concurrent=4, wait_seconds=0.05)
    router.mark_primary_down(60)
    with router.turn(has_fallback=True) as route:
        assert route == "fallback"
    router.reset()
    with router.turn(has_fallback=True) as route:
        assert route == "primary"


class Caido(LLMProvider):
    def request_tools(self, message, tools):
        raise ProviderError()

    def generate_final(self, message, initial, tool_outputs):
        raise ProviderError()


class Respaldo(LLMProvider):
    def request_tools(self, message, tools):
        return ProviderResponse(text="Respuesta del respaldo.")

    def generate_final(self, message, initial, tool_outputs):
        return ProviderResponse(text="Respuesta del respaldo.")


def test_chat_pasa_al_respaldo_si_el_modelo_propio_falla():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-one")
    app.dependency_overrides[get_llm_provider] = lambda: Caido()
    app.dependency_overrides[get_fallback_llm_provider] = lambda: Respaldo()
    response = client.post("/api/v1/ai/chat", json={"message": "Hola"})
    assert response.status_code == 200
    assert "respaldo" in response.json()["answer"]
    assert llm_router.primary_down()  # las próximas consultas van directo al respaldo


def test_chat_sin_respaldo_mantiene_el_error():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-one")
    app.dependency_overrides[get_llm_provider] = lambda: Caido()
    app.dependency_overrides[get_fallback_llm_provider] = lambda: None
    assert client.post("/api/v1/ai/chat", json={"message": "Hola"}).status_code == 502


# ── 5. Modelo propio (vLLM / Ollama) ─────────────────────────────────────────────────────────


def test_openai_compatible_con_servidor_propio_sin_llave():
    provider = create_llm_provider(
        "openai",
        gemini_api_key="",
        gemini_model="",
        openai_api_key="",
        openai_model="Qwen/Qwen2.5-7B-Instruct",
        timeout_seconds=30,
        openai_base_url="http://vllm:8000/v1",
    )
    assert isinstance(provider, OpenAIProvider)
    assert str(provider.client.base_url).rstrip("/") == "http://vllm:8000/v1"


def test_agente_puede_usar_el_modelo_propio():
    from dataclasses import replace

    from app.agent.llm import get_chat_model
    from app.core.config import settings

    cfg = replace(settings, openai_model="qwen", openai_base_url="http://vllm:8000/v1", openai_api_key="")
    model = get_chat_model(cfg, provider="openai")
    assert type(model).__name__ == "ChatOpenAI"
    assert model.openai_api_base == "http://vllm:8000/v1"


def test_cache_global_parte_limpia():
    assert catalog_cache.get("/api/v1/categories?[]") is None
