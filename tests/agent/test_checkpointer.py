"""Selección del checkpointer (SQLite local o Postgres compartido) y, opt-in, Postgres real.

Postgres real: ``TEST_POSTGRES_URL=postgresql://... pytest tests/agent/test_checkpointer.py``.
"""

import os

import pytest
from agent_support import USER
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agent.service import AgentService, checkpointer_kind, make_checkpointer
from app.agent.testing import AhorroPolicy, ScriptedChatModel
from app.ai.rag.embedding import LocalHashEmbeddingProvider


@pytest.mark.parametrize(
    "url,mode,expected",
    [
        ("sqlite:///./x.db", "auto", "sqlite"),
        ("postgresql+psycopg://u:p@h:5432/db", "auto", "postgres"),
        ("postgresql://u:p@h/db", "AUTO", "postgres"),
        ("sqlite:///./x.db", "postgres", "postgres"),
        ("postgresql://u:p@h/db", "sqlite", "sqlite"),
        ("", "", "sqlite"),
    ],
)
def test_checkpointer_kind(url, mode, expected):
    assert checkpointer_kind(url, mode) == expected


def test_sqlite_is_the_local_default(tmp_path):
    saver = make_checkpointer("sqlite:///./x.db", "auto", str(tmp_path / "h.db"))
    assert isinstance(saver, SqliteSaver)


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="requiere TEST_POSTGRES_URL")
def test_two_service_instances_share_threads_through_postgres(db, catalog):
    url = os.environ["TEST_POSTGRES_URL"]

    def service(policy):
        return AgentService(db, USER, llm=ScriptedChatModel(policy=policy), embedder=LocalHashEmbeddingProvider(), checkpointer=make_checkpointer(url, "postgres"))

    first = service(AhorroPolicy(["Lenovo"]))
    first.run("Busco un notebook Lenovo, presupuesto $400.000", "pg-compartido")
    replica = service(AhorroPolicy(["Lenovo"]))  # otra conexión, como una segunda réplica del servidor
    history = replica.history("pg-compartido")
    assert history and history[0]["content"].startswith("Busco un notebook Lenovo")
    replica.run("Revisa mis alertas", "pg-compartido")
    assert len(first.history("pg-compartido")) == len(history) + 2
