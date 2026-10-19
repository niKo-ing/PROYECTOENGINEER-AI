import pytest
from agent_support import USER
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph import ACT_SYSTEM
from app.agent.service import AgentService, _clean_answer
from app.agent.testing import ScriptedChatModel
from app.ai.rag.embedding import LocalHashEmbeddingProvider


@pytest.mark.parametrize(
    "raw,expected",
    [
        (".He revisado tus alertas de precio activas:", "He revisado tus alertas de precio activas:"),
        (" . ,Hola", "Hola"),
        ("He revisado tus alertas.", "He revisado tus alertas."),  # el punto final no se toca
        ("- Primer punto\n- Segundo", "- Primer punto\n- Segundo"),  # las viñetas se conservan
        ("**Resultado:** listo", "**Resultado:** listo"),
        ("", ""),
        ("...", "..."),  # solo puntuación: no se deja la respuesta vacía
    ],
)
def test_clean_answer(raw, expected):
    assert _clean_answer(raw) == expected


def test_service_returns_the_answer_without_a_stray_leading_dot(db):
    def policy(messages, tool_names):
        if "PLANIFICADOR" in str(messages[0].content)[:80]:
            return AIMessage(content='{"steps": [{"action": "Responder", "priority": 1}]}')
        return AIMessage(content=".Hola, esto es una respuesta.")

    svc = AgentService(db, USER, llm=ScriptedChatModel(policy=policy), embedder=LocalHashEmbeddingProvider(), checkpointer=MemorySaver())
    assert svc.run("Dime hola", "limpio").answer == "Hola, esto es una respuesta."


def test_prompt_only_allows_saving_lists_when_asked():
    assert "save_shopping_list SOLO si el usuario pidió una lista" in ACT_SYSTEM


# -- guardar listas solo si el usuario las pidió (regla en código, no solo en el prompt) ------
@pytest.mark.parametrize(
    "pedido,pide_lista",
    [
        ("Quiero un celular Samsung o Xiaomi, presupuesto $320.000. Arma una lista de compra.", True),
        ("Necesito el notebook ASUS TUF. Guarda la lista si conviene.", True),
        ("Anótalo en mi lista", True),
        ("Agrega este celular a la lista", True),
        ("Prefiero Samsung y no quiero Xiaomi. Busco un celular, presupuesto $350.000.", False),
        ("Compara el Xiaomi Redmi Note 15 Pro entre las tiendas", False),
        ("Avísame cuando baje el HP Victus", False),
        ("Revisa mis alertas de precio", False),
    ],
)
def test_list_intent(pedido, pide_lista):
    from app.agent.tools import LIST_INTENT

    assert bool(LIST_INTENT.search(pedido)) is pide_lista


def _save(db, goal):
    import json

    from app.agent.demo_data import seed_demo_catalog
    from app.agent.memory import LongTermMemory
    from app.agent.tools import RunContext, build_tools

    ids = seed_demo_catalog(db)
    context = RunContext()
    context.goal = goal
    memory = LongTermMemory(db, USER, LocalHashEmbeddingProvider())
    tools = {t.name: t for t in build_tools(db, USER, memory, context)}
    return json.loads(tools["save_shopping_list"].invoke({"name": "Mi lista", "product_ids": [ids["lenovo"]]}))


def test_tool_does_not_save_a_list_nobody_asked_for(db):
    from app.models.agent import ShoppingList

    out = _save(db, "Busco un celular, presupuesto $350.000")
    assert out["saved"] is False and "ofrécele guardarla" in out["reason"]
    assert db.query(ShoppingList).count() == 0


def test_tool_saves_the_list_when_asked(db):
    from app.models.agent import ShoppingList

    out = _save(db, "Quiero un notebook Lenovo. Arma una lista de compra.")
    assert out["list_id"] and db.query(ShoppingList).count() == 1


def test_graph_does_not_count_a_refused_write_nor_replan_for_it(db, catalog):
    from langchain_core.messages import ToolMessage

    from app.models.agent import ShoppingList

    def policy(messages, tool_names):
        if "PLANIFICADOR" in str(messages[0].content)[:80]:
            return AIMessage(content='{"steps": [{"action": "Buscar con search_products", "priority": 1}]}')
        if not any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(content="", tool_calls=[{"name": "save_shopping_list", "args": {"name": "Lista", "product_ids": [catalog["lenovo"]]}, "id": "s1"}])
        return AIMessage(content="Te recomiendo el Lenovo. ¿Quieres que lo guarde en una lista?")

    svc = AgentService(db, USER, llm=ScriptedChatModel(policy=policy), embedder=LocalHashEmbeddingProvider(), checkpointer=MemorySaver())
    result = svc.run("Busco un notebook Lenovo, presupuesto $400.000", "sin-lista")
    assert result.wrote == [] and result.replans == 0
    assert db.query(ShoppingList).count() == 0
    assert "guarde" in result.answer
