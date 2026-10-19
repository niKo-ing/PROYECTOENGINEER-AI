import pytest
from fastapi.testclient import TestClient

from app.agent.demo_runtime import demo_enabled, get_demo_runtime, queries_from_message
from app.main import app

client = TestClient(app)
RUN = "/api/v1/agent/demo/run"


@pytest.fixture(autouse=True)
def fresh_demo(monkeypatch):
    monkeypatch.setenv("AGENT_DEMO_ENABLED", "true")
    get_demo_runtime().reset()
    yield
    get_demo_runtime().reset()


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Quiero un notebook gamer, presupuesto $300.000", ["notebook gamer", "notebook"]),
        ("Necesito el Lenovo IdeaPad", ["Lenovo"]),
        ("Prefiero Samsung, busco un celular", ["Samsung"]),
        ("algo cualquiera", ["notebook"]),
    ],
)
def test_queries_from_message(message, expected):
    assert queries_from_message(message) == expected


def test_demo_works_without_login_and_saves_a_list():
    response = client.post(RUN, json={"message": "Quiero un notebook Lenovo, presupuesto $400.000. Arma una lista.", "thread_id": "d1"})
    assert response.status_code == 200
    body = response.json()
    assert body["tools_used"][-1] == "save_shopping_list" and "Lenovo" in body["answer"]
    state = client.get("/api/v1/agent/demo/estado").json()
    assert state["lists"][0]["total_clp"] == 349_990


def test_price_drop_fulfils_an_alert_created_earlier():
    client.post(RUN, json={"message": "Quiero un notebook gamer, presupuesto $300.000. Avísame cuando baje.", "thread_id": "d2"})
    assert client.get("/api/v1/agent/demo/estado").json()["alerts"][0]["active"] is True
    drop = client.post("/api/v1/agent/demo/bajar-precio").json()
    assert drop["before_clp"] == 349_990 and drop["after_clp"] == 289_990
    later = client.post(RUN, json={"message": "Revisa mis alertas de precio", "thread_id": "d2"}).json()
    assert "se cumplió" in later["answer"].lower()
    assert client.get("/api/v1/agent/demo/estado").json()["alerts"][0]["active"] is False


def test_preference_learned_in_one_thread_is_recalled_in_another():
    client.post(RUN, json={"message": "Prefiero Samsung. Busco un celular, presupuesto $400.000", "thread_id": "a"})
    other = client.post(RUN, json={"message": "Recomiéndame algo bueno", "thread_id": "b"}).json()
    assert any("Prefiero Samsung" in m for m in other["memories_used"])


def test_reset_clears_everything():
    client.post(RUN, json={"message": "Quiero un notebook Lenovo, presupuesto $400.000. Arma una lista.", "thread_id": "r"})
    assert client.post("/api/v1/agent/demo/reiniciar").json() == {"ok": True}
    state = client.get("/api/v1/agent/demo/estado").json()
    assert state == {"alerts": [], "lists": [], "memories": []}


def test_demo_is_off_in_production_unless_forced(monkeypatch):
    monkeypatch.delenv("AGENT_DEMO_ENABLED", raising=False)
    monkeypatch.setattr("app.agent.demo_runtime.settings", type("S", (), {"app_env": "production"})())
    assert demo_enabled() is False
    assert client.post(RUN, json={"message": "hola agente"}).status_code == 404
    assert client.get("/api/v1/agent/demo/disponible").json() == {"enabled": False}
    monkeypatch.setenv("AGENT_DEMO_ENABLED", "true")
    assert demo_enabled() is True


def test_input_is_validated():
    assert client.post(RUN, json={"message": "a"}).status_code == 422
