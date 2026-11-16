"""Escenarios de punta a punta del agente con el modelo guionado (sin red ni cuota): cada uno fija una decisión."""

import pytest
from agent_support import USER
from langgraph.checkpoint.memory import MemorySaver
from modelo_guionado import AhorroPolicy, ScriptedChatModel, queries_from_message
from sqlalchemy import select

from app.agent.service import AgentService
from app.agent.snapshot import snapshot
from app.ai.rag.embedding import LocalHashEmbeddingProvider
from app.models.catalog import StoreOffer


@pytest.fixture()
def run(db, catalog):
    saver, embedder = MemorySaver(), LocalHashEmbeddingProvider()

    def ejecutar(message, thread_id="t"):
        llm = ScriptedChatModel(policy=AhorroPolicy(queries_from_message(message)))
        return AgentService(db, USER, llm=llm, embedder=embedder, checkpointer=saver).run(message, thread_id)

    return ejecutar


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


def test_buen_precio_dentro_del_presupuesto_guarda_la_lista(run, db):
    result = run("Quiero un notebook Lenovo, presupuesto $400.000. Arma una lista.")
    assert result.tools_used[-1] == "save_shopping_list" and "Lenovo" in result.answer and result.replans == 0
    assert snapshot(db, USER)["lists"][0]["total_clp"] == 349_990


def test_sin_resultados_y_sobre_presupuesto_replanifica_y_deja_una_alerta(run, db):
    result = run("Quiero un notebook gamer, presupuesto $300.000. Avísame cuando baje.")
    assert result.replans == 2 and "create_price_alert" in result.wrote
    assert "faltan" in result.answer.lower()
    assert snapshot(db, USER)["alerts"][0]["active"] is True


def test_una_baja_de_precio_cumple_la_alerta_creada_antes(run, db):
    run("Quiero un notebook gamer, presupuesto $300.000. Avísame cuando baje.", "a")
    for offer in db.scalars(select(StoreOffer)):  # la tienda baja el notebook Lenovo
        if offer.product.name.startswith("Notebook Lenovo"):
            offer.price = 289_990
    db.commit()
    later = run("Revisa mis alertas de precio", "a")
    assert "se cumplió" in later.answer.lower()
    assert snapshot(db, USER)["alerts"][0]["active"] is False


def test_precio_alto_segun_el_historial_no_guarda_la_lista(run, db):
    result = run("Necesito el notebook ASUS TUF, presupuesto $900.000. Guarda la lista si conviene.")
    assert "save_shopping_list" not in result.wrote and "create_price_alert" in result.wrote
    assert snapshot(db, USER)["lists"] == [] and "esperar" in result.answer.lower()


def test_preferencia_aprendida_en_un_hilo_se_recuerda_en_otro(run):
    run("Prefiero Samsung. Busco un celular, presupuesto $400.000", "a")
    other = run("Recomiéndame algo bueno", "b")
    assert any("Prefiero Samsung" in m for m in other.memories_used)
