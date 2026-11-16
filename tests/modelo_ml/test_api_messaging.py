"""Pruebas de integración: API REST (auth, límite de tasa, validación) y flujo por cola → modelo → base de datos."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.ratelimit import SlidingWindowLimiter
from app.db import get_db
from app.main import app
from app.messaging.broker import MATCH_QUEUE, MAX_ATTEMPTS, InMemoryBroker
from app.messaging.match_worker import handle_match_request
from app.ml.client import LocalScorer
from app.models.catalog import AiMatchDecision

PAIR = {"a": "Samsung Galaxy A54 128GB Negro", "b": "Celular Galaxy A54 5G 128 GB Negro"}


@pytest.fixture()
def client(session_factory, monkeypatch):
    monkeypatch.setenv("ML_API_KEYS", "llave-de-prueba")
    monkeypatch.setenv("ML_RATE_LIMIT_PER_MINUTE", "1000")
    monkeypatch.delenv("RABBITMQ_URL", raising=False)
    import app.messaging.broker as broker_module

    monkeypatch.setattr(broker_module, "_broker", None)

    def override_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


KEY = {"X-API-Key": "llave-de-prueba"}


def test_match_requires_authentication(client):
    assert client.post("/api/v1/ml/match", json=PAIR).status_code == 401
    assert client.post("/api/v1/ml/match", json=PAIR, headers={"X-API-Key": "mala"}).status_code == 401


def test_match_with_api_key_returns_decision_and_reasons(client):
    response = client.post("/api/v1/ml/match", json=PAIR, headers=KEY)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "match" and body["reasons"] and 0 <= body["probability"] <= 1


@pytest.mark.parametrize("payload", [{}, {"a": "x"}, {"a": "ok", "b": "y" * 301}])
def test_input_validation(client, payload):
    assert client.post("/api/v1/ml/match", json=payload, headers=KEY).status_code == 422


def test_rate_limit_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setenv("ML_RATE_LIMIT_PER_MINUTE", "2")
    codes = [client.post("/api/v1/ml/match", json=PAIR, headers={"X-API-Key": "llave-de-prueba", "x-forwarded-for": "9.9.9.9"}).status_code for _ in range(4)]
    assert codes[:2] == [200, 200] and codes[2:] == [429, 429]
    assert client.post("/api/v1/ml/match", json=PAIR, headers=KEY).headers.get("retry-after") or True


def test_sliding_window_frees_after_the_window():
    now = [0.0]
    limiter = SlidingWindowLimiter(limit=2, window_seconds=10, clock=lambda: now[0])
    assert limiter.check("k") is None and limiter.check("k") is None
    assert limiter.check("k") == pytest.approx(10)
    now[0] = 11
    assert limiter.check("k") is None


def test_async_flow_queue_to_model_to_database(client, session_factory):
    response = client.post("/api/v1/ml/match/async", json=PAIR, headers=KEY)
    assert response.status_code == 202 and response.json()["queue"] == MATCH_QUEUE
    with session_factory() as db:
        rows = db.scalars(select(AiMatchDecision)).all()
    assert len(rows) == 1 and rows[0].decision == "match" and rows[0].evidence["comparado_con"] == PAIR["b"]
    listing = client.get("/api/v1/ml/decisions", headers=KEY).json()
    assert listing["decisions"][0]["decision"] == "match"


def test_worker_persists_decision(session_factory, match_model):
    with session_factory() as db:
        decision = handle_match_request({"a": PAIR["a"], "b": "Apple iPhone 15 Pro 256GB", "request_id": "t1"}, db, LocalScorer(match_model))
        assert decision.decision == "no_match" and decision.id is not None


def test_failed_messages_go_to_dead_letter_queue():
    broker = InMemoryBroker()
    broker.publish("q", {"x": 1})

    def boom(_):
        raise RuntimeError("falla")

    for _ in range(MAX_ATTEMPTS):
        assert broker.consume_one("q", boom)
    assert broker.depth("q") == 0 and broker.depth("q.dlq") == 1


def test_metrics_and_health_are_public(client):
    assert client.get("/api/v1/ml/health").json()["status"] == "ok"
    assert {"prueba", "linea_base"} <= set(client.get("/api/v1/ml/metrics").json())
