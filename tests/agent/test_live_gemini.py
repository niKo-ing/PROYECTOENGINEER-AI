"""Pruebas contra Gemini real. Opt-in: ``RUN_LIVE=1 pytest -m live tests/agent/test_live_gemini.py``.

Gastan cuota de la API, por eso no corren en la suite normal ni en CI.
"""

import os

import pytest
from agent_support import USER
from langgraph.checkpoint.memory import MemorySaver

from app.agent.llm import get_chat_model
from app.agent.memory import LongTermMemory
from app.agent.service import AgentService
from app.ai.rag.embedding import GeminiEmbeddingProvider
from app.core.config import settings

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not (os.getenv("RUN_LIVE") == "1" and settings.gemini_api_key and settings.gemini_model), reason="requiere RUN_LIVE=1 y GEMINI_API_KEY/GEMINI_MODEL"),
]


def test_real_embeddings_rank_by_meaning_not_by_words(db):
    memory = LongTermMemory(db, "u1", GeminiEmbeddingProvider(settings.gemini_api_key, dimensions=256))
    memory.add("Prefiero notebooks baratos para la universidad")
    memory.add("Mi equipo de fútbol favorito es Colo-Colo")
    memory.add("Nunca compro celulares Huawei")
    hits = memory.search("necesito un laptop económico para estudiar", k=3, min_similarity=0.0)
    assert "notebooks baratos" in hits[0].content
    assert hits[0].similarity > hits[-1].similarity


def test_gemini_agent_completes_a_purchase_task_within_budget(db, catalog):
    service = AgentService(
        db,
        USER,
        llm=get_chat_model(),
        embedder=GeminiEmbeddingProvider(settings.gemini_api_key, dimensions=256),
        checkpointer=MemorySaver(),
    )
    result = service.run("Quiero un notebook liviano para la universidad, presupuesto $400.000. Si hay uno bueno, guárdalo en una lista de compra.", "live-1")
    assert "search_products" in result.tools_used
    assert result.answer
    assert result.steps <= 10
    assert all(event["node"] != "give_up" for event in result.trace)
