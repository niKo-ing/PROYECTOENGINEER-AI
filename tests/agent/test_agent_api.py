import pytest
from agent_support import USER
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from app.agent.testing import AhorroPolicy, ScriptedChatModel
from app.ai.rag.embedding import LocalHashEmbeddingProvider
from app.core.security import AuthenticatedUser, get_current_user
from app.db import get_db
from app.main import app
from app.routers.agent import get_agent_checkpointer, get_agent_embedder, get_agent_llm


@pytest.fixture()
def client(session_factory, catalog):
    saver = MemorySaver()

    def override_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=USER)
    app.dependency_overrides[get_agent_llm] = lambda: ScriptedChatModel(policy=AhorroPolicy(["Lenovo"]))
    app.dependency_overrides[get_agent_embedder] = lambda: LocalHashEmbeddingProvider()
    app.dependency_overrides[get_agent_checkpointer] = lambda: saver
    yield TestClient(app)
    for dep in (get_db, get_current_user, get_agent_llm, get_agent_embedder, get_agent_checkpointer):
        app.dependency_overrides.pop(dep, None)


def test_run_returns_answer_plan_tools_and_trace(client):
    response = client.post("/api/v1/agent/run", json={"message": "Quiero un notebook Lenovo, presupuesto $400.000. Arma una lista.", "thread_id": "web-1"})
    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == "web-1"
    assert body["tools_used"][-1] == "save_shopping_list" and body["wrote"] == ["save_shopping_list"]
    assert "Lenovo" in body["answer"] and body["plan"] and body["trace"]


def test_memories_endpoint_lists_what_the_agent_learned(client):
    client.post("/api/v1/agent/run", json={"message": "Prefiero Lenovo. Busco un notebook Lenovo, presupuesto $400.000", "thread_id": "m1"})
    memories = client.get("/api/v1/agent/memories").json()["memories"]
    assert {"preference", "episode"} <= {m["kind"] for m in memories}


@pytest.mark.parametrize("payload", [{"message": "a"}, {"message": "ok ok", "thread_id": "con espacios!"}, {"message": "x" * 1300}, {}])
def test_input_is_validated(client, payload):
    assert client.post("/api/v1/agent/run", json=payload).status_code == 422


def test_provider_quota_error_becomes_429_not_a_stack_trace(client):
    from google.genai.errors import ClientError

    def exhausted(messages, tool_names):
        raise ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})

    app.dependency_overrides[get_agent_llm] = lambda: ScriptedChatModel(policy=exhausted)
    response = client.post("/api/v1/agent/run", json={"message": "Quiero un notebook Lenovo", "thread_id": "q1"})
    assert response.status_code == 429 and "cuota" in response.json()["detail"]


def test_a_bug_in_the_graph_is_not_disguised_as_a_provider_error(client):
    def broken(messages, tool_names):
        raise KeyError("bug propio")

    app.dependency_overrides[get_agent_llm] = lambda: ScriptedChatModel(policy=broken)
    with pytest.raises(KeyError):
        client.post("/api/v1/agent/run", json={"message": "Quiero un notebook Lenovo", "thread_id": "q2"})


def test_requires_authentication(session_factory):
    app.dependency_overrides.pop(get_current_user, None)
    response = TestClient(app).post("/api/v1/agent/run", json={"message": "hola agente"})
    assert response.status_code in (401, 403)
