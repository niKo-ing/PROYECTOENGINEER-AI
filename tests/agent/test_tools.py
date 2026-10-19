import json

import pytest
from langchain_core.tools import ToolException

from app.agent.memory import LongTermMemory
from app.agent.tools import READ_TOOLS, WRITE_TOOLS, build_tools, trend_verdict
from app.ai.rag.embedding import LocalHashEmbeddingProvider
from app.models.agent import AgentMemory, PriceAlert, ShoppingList
from app.models.catalog import StoreOffer

from agent_support import USER


@pytest.fixture()
def tools(db, catalog):
    memory = LongTermMemory(db, USER, LocalHashEmbeddingProvider())
    return {tool.name: tool for tool in build_tools(db, USER, memory)}


def call(tools, tool_name, /, **args):
    return json.loads(tools[tool_name].invoke(args))


def test_registry_has_read_reasoning_and_write_tools(tools):
    assert set(tools) == set(READ_TOOLS) | set(WRITE_TOOLS)
    assert len(WRITE_TOOLS) == 3


def test_search_returns_lowest_price_and_respects_price_cap(tools, catalog):
    data = call(tools, "search_products", query="Notebook", max_price_clp=400_000)
    names = {i["name"] for i in data["items"]}
    assert "Notebook Lenovo IdeaPad 3" in names
    assert "Notebook ASUS TUF Gaming F15" not in names
    lenovo = next(i for i in data["items"] if i["name"] == "Notebook Lenovo IdeaPad 3")
    assert lenovo["lowest_price"] == 349_990 and lenovo["lowest_price_store"] == "Paris"


def test_business_errors_come_back_as_observations_not_exceptions(tools):
    out = tools["get_product_offers"].invoke({"product_id": 99999})
    assert "items" not in out and "encontrado" in out.lower()


def test_trend_verdict_buen_momento_esperar_normal_and_unknown():
    assert trend_verdict([100, 110, 120, 105], 100)["verdict"] == "buen_momento"
    assert trend_verdict([100, 100, 100, 100], 120)["verdict"] == "esperar"
    assert trend_verdict([100, 100, 100, 100], 102)["verdict"] == "buen_momento"
    assert trend_verdict([90, 110, 100, 100], 101)["verdict"] == "precio_normal"
    assert trend_verdict([100, 100], 100)["verdict"] == "sin_historial_suficiente"
    assert trend_verdict([100, 100, 100], None)["verdict"] == "sin_precio_actual"


def test_analyze_price_trend_on_catalog(tools, catalog):
    assert call(tools, "analyze_price_trend", product_id=catalog["lenovo"])["verdict"] == "buen_momento"
    asus = call(tools, "analyze_price_trend", product_id=catalog["asus"])
    assert asus["verdict"] == "esperar" and asus["vs_avg_pct"] > 5


def test_create_price_alert_writes_and_updates_instead_of_duplicating(tools, db, catalog):
    first = call(tools, "create_price_alert", product_id=catalog["asus"], target_price_clp=700_000)
    assert first["current_price_clp"] == 799_990 and first["already_met"] is False and first["updated_existing"] is False
    second = call(tools, "create_price_alert", product_id=catalog["asus"], target_price_clp=650_000)
    assert second["alert_id"] == first["alert_id"] and second["updated_existing"] is True
    assert db.query(PriceAlert).count() == 1 and db.query(PriceAlert).one().target_price_clp == 650_000


def test_create_price_alert_flags_target_already_met(tools, catalog):
    assert call(tools, "create_price_alert", product_id=catalog["lenovo"], target_price_clp=400_000)["already_met"] is True


def test_alert_fires_when_the_price_drops_and_only_once(tools, db, catalog):
    call(tools, "create_price_alert", product_id=catalog["asus"], target_price_clp=750_000)
    before = call(tools, "check_price_alerts")
    assert before["newly_triggered"] == 0 and before["alerts"][0]["triggered"] is False

    offer = db.query(StoreOffer).filter_by(product_id=catalog["asus"]).one()
    offer.price = 729_990  # bajó el precio en la tienda
    db.commit()

    fired = call(tools, "check_price_alerts")
    assert fired["newly_triggered"] == 1 and fired["alerts"][0]["current_price_clp"] == 729_990
    row = db.query(PriceAlert).one()
    assert row.active is False and row.triggered_price_clp == 729_990 and row.triggered_at is not None
    assert call(tools, "check_price_alerts")["active_checked"] == 0  # no vuelve a avisar


def test_alerts_belong_to_their_user(db, catalog):
    mem = LongTermMemory(db, "otro", LocalHashEmbeddingProvider())
    other = {t.name: t for t in build_tools(db, "otro", mem)}
    mine = {t.name: t for t in build_tools(db, USER, LongTermMemory(db, USER, LocalHashEmbeddingProvider()))}
    mine["create_price_alert"].invoke({"product_id": catalog["asus"], "target_price_clp": 700_000})
    assert json.loads(other["check_price_alerts"].invoke({}))["active_checked"] == 0


def test_save_shopping_list_totals_with_best_offer_and_checks_budget(tools, db, catalog):
    data = call(tools, "save_shopping_list", name="Estudio", product_ids=[catalog["lenovo"], catalog["samsung"]], budget_clp=700_000)
    assert data["total_clp"] == 349_990 + 329_990
    assert data["within_budget"] is True and {i["store"] for i in data["items"]} == {"Paris"}
    saved = db.query(ShoppingList).one()
    assert saved.total_clp == data["total_clp"] and len(saved.items) == 2


def test_save_shopping_list_skips_products_without_offers_and_rejects_empty(tools, db, catalog):
    data = call(tools, "save_shopping_list", name="Mixta", product_ids=[catalog["lenovo"], catalog["hp"], 424242])
    assert len(data["items"]) == 1 and len(data["skipped"]) == 2
    with pytest.raises(ToolException):
        tools["save_shopping_list"].func(name="Vacía", product_ids=[catalog["hp"]])
    assert db.query(ShoppingList).count() == 1


def test_remember_preference_persists_and_recall_finds_it(tools, db):
    saved = call(tools, "remember_preference", content="Prefiero Samsung para celulares", importance=4)
    assert saved["created"] is True
    assert call(tools, "remember_preference", content="Prefiero Samsung para celulares")["created"] is False
    recalled = call(tools, "recall_memory", query="celulares Samsung")
    assert recalled["total"] == 1 and "Samsung" in recalled["memories"][0]["content"]
    assert db.query(AgentMemory).count() == 1


def test_remember_preference_rejects_episode_kind(tools):
    with pytest.raises(ToolException):
        tools["remember_preference"].func(content="algo", kind="episode")
