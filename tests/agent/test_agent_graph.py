"""Escenarios de extremo a extremo del agente (grafo LangGraph + herramientas reales + BD).

El LLM es ``ScriptedChatModel``: reacciona a las observaciones, pero es determinista. Lo que
se verifica es el comportamiento del sistema: orquestación, memoria, replanificación,
escrituras y límites.
"""

import pytest
from agent_support import USER, ConceptEmbedder
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agent.service import AgentService
from app.agent.testing import AhorroPolicy, ScriptedChatModel
from app.ai.rag.embedding import LocalHashEmbeddingProvider
from app.models.agent import AgentMemory, PriceAlert, ShoppingList
from app.models.catalog import StoreOffer


def service(db, policy=None, *, user=USER, embedder=None, checkpointer=None, **kwargs):
    llm = ScriptedChatModel(policy=policy or AhorroPolicy())
    return AgentService(db, user, llm=llm, embedder=embedder or LocalHashEmbeddingProvider(), checkpointer=checkpointer or MemorySaver(), **kwargs), llm


def events(result, node):
    return [e for e in result.trace if e["node"] == node]


def test_parallel_tool_calls_in_one_step_all_succeed(db, catalog):
    """Gemini pidió «Samsung» y «Xiaomi» en un mismo paso: las dos búsquedas corren y ninguna falla."""

    def policy(messages, tool_names):
        if "PLANIFICADOR" in str(messages[0].content)[:80]:
            return AIMessage(content='{"steps": [{"action": "Buscar con search_products", "priority": 1}]}')
        if not any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {"name": "search_products", "args": {"brand": "Samsung"}, "id": "p1"},
                    {"name": "search_products", "args": {"brand": "Lenovo"}, "id": "p2"},
                ],
            )
        return AIMessage(content="Listo: busqué en las dos marcas.")

    svc, _ = service(db, policy)
    result = svc.run("Quiero un celular Samsung o un notebook Lenovo", "paralelo")
    assert result.tools_used == ["search_products", "search_products"]
    assert [e for e in events(result, "reflect") if e["diagnosis"]] == []  # ninguna falló
    assert result.answer.startswith("Listo")


# -- orquestación: consulta → razonamiento → escritura --------------------------------------
def test_happy_path_searches_reasons_and_writes_a_shopping_list(db, catalog):
    svc, _ = service(db, AhorroPolicy(["Lenovo"]))
    result = svc.run("Quiero un notebook Lenovo para la universidad, presupuesto $400.000. Arma una lista de compra.", "t1")

    assert result.tools_used == ["search_products", "get_product_offers", "analyze_price_trend", "save_shopping_list"]
    assert result.replans == 0 and result.plan_source == "llm"
    saved = db.query(ShoppingList).one()
    assert saved.user_id == USER and saved.total_clp == 349_990 and saved.budget_clp == 400_000
    assert "Lenovo IdeaPad 3" in result.answer and "349.990" in result.answer
    assert result.wrote == ["save_shopping_list"]
    # El presupuesto salió del texto y se filtró la búsqueda con él.
    search_call = events(result, "act")[0]["tool_calls"][0]
    assert search_call["args"]["max_price_clp"] == 400_000


def test_plan_is_priority_ordered_and_progress_is_tracked(db, catalog):
    svc, _ = service(db, AhorroPolicy(["Lenovo"]))
    result = svc.run("Busco un notebook Lenovo, presupuesto $400.000. Guarda la lista.", "t1")
    priorities = [s["priority"] for s in result.plan]
    assert priorities == sorted(priorities)
    assert any(s["status"] == "hecho" for s in result.plan)


def test_invalid_llm_plan_falls_back_to_heuristic_plan(db, catalog):
    svc, _ = service(db, AhorroPolicy(["Lenovo"], bad_plan=True))
    result = svc.run("Busco un notebook Lenovo, presupuesto $400.000", "t1")
    assert result.plan_source == "heuristic" and len(result.plan) >= 3
    assert "Lenovo" in result.answer


# -- planificación adaptativa ----------------------------------------------------------------
def test_replans_when_search_is_empty_then_when_everything_is_over_budget(db, catalog):
    svc, _ = service(db, AhorroPolicy(["notebook gamer", "notebook"]))
    result = svc.run("Quiero un notebook gamer, presupuesto $300.000. Avísame cuando baje.", "t1")

    decisions = [(e["diagnosis"]["reason"], e["decision"]) for e in events(result, "reflect") if e["diagnosis"]]
    # 1) sin resultados → replanifica; 2) repite el mismo problema → NO replanifica otra vez
    # (anti-bucle); 3) todo sobre presupuesto → replanifica con otra estrategia.
    assert decisions[0] == ("sin_resultados", "replanificar")
    assert ("sin_resultados", "continuar_sin_replan") in decisions
    assert ("sobre_presupuesto", "replanificar") in decisions
    assert result.replans == 2

    plans = events(result, "plan")
    assert [p["replan"] for p in plans] == [None, "sin_resultados", "sobre_presupuesto"]
    assert any("Adaptación por 'sin_resultados'" in step for step in plans[1]["plan"])
    assert "search_products" in plans[1]["plan"][0]  # el paso ya hecho se conserva al replanificar

    alert = db.query(PriceAlert).one()
    assert alert.target_price_clp == 300_000 and alert.price_at_creation_clp == 349_990
    assert "49.990" in result.answer  # cuánto falta
    assert db.query(ShoppingList).count() == 0  # no armó una lista que no puede pagar


def test_replan_keeps_the_steps_already_done(db, catalog):
    svc, _ = service(db, AhorroPolicy(["notebook gamer", "notebook"]))
    result = svc.run("Quiero un notebook gamer, presupuesto $300.000", "t1")
    last_plan = events(result, "plan")[-1]["plan"]
    assert len(last_plan) >= 2
    final = {s["id"]: s for s in result.plan}
    assert any(s["status"] == "hecho" for s in final.values())
    assert [s["id"] for s in result.plan] == list(range(1, len(result.plan) + 1))


def test_high_price_verdict_turns_a_purchase_into_a_price_alert(db, catalog):
    svc, _ = service(db, AhorroPolicy(["ASUS TUF"]))
    result = svc.run("Necesito el notebook ASUS TUF para jugar, presupuesto $900.000. Guarda la lista si conviene.", "t1")
    assert any(e["diagnosis"] and e["diagnosis"]["reason"] == "precio_alto" and e["decision"] == "replanificar" for e in events(result, "reflect"))
    alert = db.query(PriceAlert).one()
    assert 700_000 < alert.target_price_clp < 799_990  # apunta al promedio histórico
    assert db.query(ShoppingList).count() == 0
    assert "esperar" in result.answer.lower() and result.wrote == ["create_price_alert"]


def test_out_of_stock_triggers_replan_and_honest_answer(db, catalog):
    svc, _ = service(db, AhorroPolicy(["HP 250"]))
    result = svc.run("Quiero el notebook HP 250, presupuesto $300.000", "t1")
    assert any(e["diagnosis"] and e["diagnosis"]["reason"] == "sin_stock" for e in events(result, "reflect"))
    assert "stock" in result.answer.lower()
    assert db.query(ShoppingList).count() == 0


def test_step_limit_closes_pending_tool_calls_and_the_thread_stays_usable(db, catalog):
    class LoopThenNormal:
        loop = True

        def __init__(self):
            self.normal = AhorroPolicy(["Lenovo"])
            self.n = 0

        def __call__(self, messages, tool_names):
            if self.loop and "PLANIFICADOR" not in str(messages[0].content)[:80]:
                self.n += 1
                return AIMessage(content="", tool_calls=[{"name": "search_products", "args": {"query": f"x{self.n}"}, "id": f"loop{self.n}"}])
            return self.normal(messages, tool_names)

    policy = LoopThenNormal()
    svc, _ = service(db, policy, max_steps=3)
    first = svc.run("Busca algo, presupuesto $100.000", "t1")
    assert "límite" in first.answer and events(first, "give_up")

    state = svc.graph.get_state({"configurable": {"thread_id": f"{USER}:t1"}}).values["messages"]
    answered = {m.tool_call_id for m in state if isinstance(m, ToolMessage)}
    asked = {c["id"] for m in state if isinstance(m, AIMessage) for c in m.tool_calls}
    assert asked <= answered  # ninguna llamada quedó sin respuesta

    policy.loop = False
    second = svc.run("Ahora sí: notebook Lenovo, presupuesto $400.000", "t1")
    assert "Lenovo" in second.answer


def test_tool_error_is_observed_and_triggers_one_retry_plan(db, catalog):
    class BadIdThenGood:
        def __init__(self):
            self.good = AhorroPolicy(["Lenovo"])

        def __call__(self, messages, tool_names):
            if "PLANIFICADOR" in str(messages[0].content)[:80]:
                return self.good(messages, tool_names)
            if not any(isinstance(m, ToolMessage) for m in messages):
                return AIMessage(content="", tool_calls=[{"name": "get_product_offers", "args": {"product_id": 99999}, "id": "bad1"}])
            if sum(isinstance(m, ToolMessage) for m in messages) == 1:
                return AIMessage(content="", tool_calls=[{"name": "search_products", "args": {"query": "Lenovo"}, "id": "ok1"}])
            return AIMessage(content="Listo: encontré el Lenovo.")

    svc, _ = service(db, BadIdThenGood())
    result = svc.run("Dame el Lenovo", "t1")
    reasons = [e["diagnosis"]["reason"] for e in events(result, "reflect") if e["diagnosis"]]
    assert reasons == ["error_herramienta"] and result.replans == 1
    assert result.answer.startswith("Listo")


# -- memoria de largo plazo ------------------------------------------------------------------
def test_repeating_the_same_request_keeps_a_single_episode(db, catalog):
    pedido = "Busco un notebook Lenovo, presupuesto $400.000. Arma una lista de compra."
    for i in range(3):
        svc, _ = service(db, AhorroPolicy(["Lenovo"]))
        svc.run(pedido, f"repetido-{i}")
    episodios = db.query(AgentMemory).filter_by(kind="episode").all()
    assert len(episodios) == 1 and "Lenovo" in episodios[0].content


def test_preference_is_learned_in_one_thread_and_recalled_in_another(db, catalog):
    first, _ = service(db, AhorroPolicy(["Samsung"]))
    first.run("Prefiero Samsung y no quiero Huawei. Busco un celular, presupuesto $400.000", "hilo-a")
    stored = [m.content for m in db.query(AgentMemory).filter_by(kind="preference")]
    assert any("Prefiero Samsung" in s for s in stored) and any("no quiero Huawei" in s for s in stored)
    assert db.query(AgentMemory).filter_by(kind="episode").count() == 1

    second, _ = service(db, AhorroPolicy(["Samsung"]))  # servicio nuevo + hilo nuevo
    result = second.run("Recomiéndame un celular Samsung", "hilo-b")
    assert any("Prefiero Samsung" in m for m in result.memories_used)
    assert events(result, "recall")[0]["memories"]


def test_core_preferences_are_recalled_even_when_the_request_shares_no_words(db, catalog):
    first, _ = service(db, AhorroPolicy(["Samsung"]))
    first.run("Prefiero Samsung y no quiero Huawei. Busco un celular, presupuesto $400.000", "a")
    second, _ = service(db, AhorroPolicy(["Samsung"]))
    result = second.run("Recomiéndame algo bueno", "b")  # cero palabras en común, embeddings solo léxicos
    assert any("Prefiero Samsung" in m for m in result.memories_used)


def test_replanning_does_not_duplicate_steps(db, catalog):
    svc, _ = service(db, AhorroPolicy(["ASUS TUF"]))
    result = svc.run("Necesito el notebook ASUS TUF, presupuesto $900.000. Guarda la lista si conviene.", "t1")
    assert result.replans == 1
    actions = [s["action"] for s in result.plan]
    assert len(actions) == len(set(actions))


def test_semantic_recall_works_across_different_wording(db, catalog):
    embedder = ConceptEmbedder()
    first, _ = service(db, AhorroPolicy(["Lenovo"]), embedder=embedder)
    first.run("Prefiero notebooks baratos para la universidad. Busco el Lenovo, presupuesto $400.000", "a")
    second, _ = service(db, AhorroPolicy(["Lenovo"]), embedder=embedder)
    result = second.run("Necesito un laptop económico para estudiar", "b")  # ninguna palabra en común
    assert any("notebooks baratos" in m for m in result.memories_used)


def test_remember_tool_and_safety_net_do_not_double_store(db, catalog):
    svc, _ = service(db, AhorroPolicy(["Samsung"], use_remember_tool=True))
    result = svc.run("Prefiero Samsung. Busco un celular, presupuesto $400.000", "t1")
    assert "remember_preference" in result.tools_used and "remember_preference" in result.wrote
    assert db.query(AgentMemory).filter_by(kind="preference").count() == 1


def test_memories_do_not_leak_between_users(db, catalog):
    alice, _ = service(db, AhorroPolicy(["Samsung"]), user="alice")
    alice.run("Prefiero Samsung. Busco un celular, presupuesto $400.000", "t1")
    bob, _ = service(db, AhorroPolicy(["Samsung"]), user="bob")
    assert bob.run("Quiero un celular Samsung", "t1").memories_used == []


# -- memoria de corto plazo y continuidad ----------------------------------------------------
def test_alert_created_in_one_turn_fires_in_a_later_turn_of_the_same_thread(db, catalog):
    svc, _ = service(db, AhorroPolicy(["notebook gamer", "notebook"]))
    svc.run("Quiero un notebook gamer, presupuesto $300.000. Avísame cuando baje.", "t1")
    assert db.query(PriceAlert).filter_by(active=True).count() == 1

    # Pasa el tiempo: la tienda baja el precio.
    for offer in db.query(StoreOffer).filter_by(product_id=catalog["lenovo"]):
        offer.price = 289_990
    db.commit()

    later = svc.run("Revisa mis alertas de precio", "t1")
    assert later.tools_used == ["check_price_alerts"]
    assert "se cumplió" in later.answer.lower() and "289.990" in later.answer
    assert db.query(PriceAlert).one().active is False
    assert [m["role"] for m in svc.history("t1")] == ["human", "ai", "human", "ai"]


def test_short_term_memory_survives_a_process_restart(db, catalog, tmp_path):
    path = str(tmp_path / "hilos.db")
    first, _ = service(db, AhorroPolicy(["Lenovo"]), checkpointer=SqliteSaver(__import__("sqlite3").connect(path, check_same_thread=False)))
    first.run("Busco un notebook Lenovo, presupuesto $400.000", "persistente")

    reborn, _ = service(db, AhorroPolicy(["Lenovo"]), checkpointer=SqliteSaver(__import__("sqlite3").connect(path, check_same_thread=False)))
    history = reborn.history("persistente")
    assert history and history[0]["content"].startswith("Busco un notebook Lenovo")
    reborn.run("Revisa mis alertas", "persistente")
    assert len(reborn.history("persistente")) == len(history) + 2


def test_threads_are_bound_to_the_user(db, catalog):
    mine, _ = service(db, AhorroPolicy(["Lenovo"]), user="alice")
    mine.run("Busco un notebook Lenovo, presupuesto $400.000", "compartido")
    saver = MemorySaver()
    a, _ = service(db, AhorroPolicy(["Lenovo"]), user="alice", checkpointer=saver)
    b, _ = service(db, AhorroPolicy(["Lenovo"]), user="bob", checkpointer=saver)
    a.run("Busco un notebook Lenovo, presupuesto $400.000", "mismo-id")
    assert a.history("mismo-id") and b.history("mismo-id") == []


def test_long_conversations_are_windowed_without_breaking_the_provider_contract(db, catalog):
    svc, llm = service(db, AhorroPolicy(["Lenovo"]), max_steps=10)
    for i in range(7):
        svc.run(f"Busco un notebook Lenovo {i}, presupuesto $400.000", "larga")
    seen = [c for c in llm.calls if c["mode"] == "act"]
    assert len(seen) >= 7
    messages = svc.graph.get_state({"configurable": {"thread_id": f"{USER}:larga"}}).values["messages"]
    assert len(messages) > 24  # el historial completo se conserva en el checkpoint; solo la ventana se recorta
