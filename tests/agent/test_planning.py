import json

import pytest
from langchain_core.messages import ToolMessage

from app.agent.planning import (
    REASON_HIGH_PRICE,
    REASON_NO_RESULTS,
    REASON_NO_STOCK,
    REASON_OVER_BUDGET,
    REASON_TOOL_ERROR,
    diagnose,
    extract_budget_clp,
    extract_declared_preferences,
    heuristic_plan,
    mark_progress,
    parse_plan,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Busco un notebook con presupuesto de $800.000", 800_000),
        ("quiero algo hasta 450 mil", 450_000),
        ("tengo 1,5 millones para armar un pc", 1_500_000),
        ("máximo 300 lucas", 300_000),
        ("Notebook de 16 pulgadas, presupuesto 600.000 pesos", 600_000),
        ("quiero un notebook de 16 GB de ram", None),
        ("hola", None),
    ],
)
def test_extract_budget(text, expected):
    assert extract_budget_clp(text) == expected


def test_budget_prefers_amount_next_to_budget_word():
    assert extract_budget_clp("Vi uno de $999.990 pero mi presupuesto es $500.000") == 500_000


def test_parse_plan_accepts_json_inside_fence_and_sorts_by_priority():
    raw = '```json\n{"steps": [{"action": "Responder", "priority": 3}, {"action": "Buscar", "priority": 1}]}\n```'
    plan = parse_plan(raw)
    assert [s["action"] for s in plan] == ["Buscar", "Responder"]
    assert [s["id"] for s in plan] == [1, 2]
    assert all(s["status"] == "pendiente" for s in plan)


@pytest.mark.parametrize("raw", ["", "no sé", "{\"steps\": 3}", "{\"steps\": []}", "{roto"])
def test_parse_plan_rejects_garbage(raw):
    assert parse_plan(raw) is None


def test_parse_plan_clamps_invalid_priority_and_caps_steps():
    raw = json.dumps({"steps": [{"action": f"paso {i}", "priority": 99} for i in range(20)]})
    plan = parse_plan(raw)
    assert len(plan) == 8
    assert {s["priority"] for s in plan} == {2}


def test_heuristic_plan_reflects_the_request():
    plan = heuristic_plan("Armar una lista de notebook y avísame cuando baje", has_memories=False, budget_clp=500_000)
    actions = " ".join(s["action"] for s in plan)
    assert "search_products" in actions and "create_price_alert" in actions and "save_shopping_list" in actions
    assert "$500.000" in actions
    assert [s["priority"] for s in plan] == sorted(s["priority"] for s in plan)


def test_heuristic_plan_for_an_alert_check_is_short_and_has_no_search():
    plan = heuristic_plan("Revisa mis alertas de precio", has_memories=False, budget_clp=None)
    actions = " ".join(s["action"] for s in plan)
    assert "check_price_alerts" in actions and "search_products" not in actions and len(plan) == 3


def test_heuristic_replan_leads_with_the_adaptation():
    plan = heuristic_plan("notebook gamer", has_memories=True, budget_clp=300_000, reason=REASON_NO_RESULTS)
    assert plan[0]["action"].startswith("Adaptación por 'sin_resultados'")
    assert not any("Buscar candidatos" in s["action"] for s in plan)


def test_mark_progress_only_marks_steps_that_name_an_executed_tool():
    plan = parse_plan(json.dumps({"steps": [{"action": "Buscar con search_products", "priority": 1}, {"action": "Comparar con compare_products", "priority": 2}, {"action": "Responder", "priority": 3}]}))
    after = mark_progress(plan, ["search_products"])
    assert [s["status"] for s in after] == ["hecho", "pendiente", "pendiente"]
    assert plan[0]["status"] == "pendiente"  # no muta la entrada
    assert [s["status"] for s in mark_progress(plan, ["otra_herramienta"])] == ["pendiente"] * 3


def tool_msg(name, payload, status="success"):
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return ToolMessage(content=content, tool_call_id="x", name=name, status=status)


def test_diagnose_empty_search():
    assert diagnose([tool_msg("search_products", {"items": [], "total": 0})], 500_000).reason == REASON_NO_RESULTS


def test_diagnose_over_budget():
    found = {"items": [{"id": 1, "lowest_price": 700_000}, {"id": 2, "lowest_price": 650_000}], "total": 2}
    d = diagnose([tool_msg("search_products", found)], 500_000)
    assert d.reason == REASON_OVER_BUDGET and "650.000" in d.detail


def test_diagnose_within_budget_is_fine():
    assert diagnose([tool_msg("search_products", {"items": [{"id": 1, "lowest_price": 400_000}], "total": 1})], 500_000) is None


def test_diagnose_without_budget_never_flags_price():
    assert diagnose([tool_msg("search_products", {"items": [{"id": 1, "lowest_price": 9_000_000}], "total": 1})], None) is None


def test_diagnose_no_stock_only_when_every_offer_is_unavailable():
    all_out = {"items": [{"availability": False, "stock_status": "out_of_stock"}, {"availability": True, "stock_status": "out_of_stock"}]}
    some_in = {"items": [{"availability": False, "stock_status": "out_of_stock"}, {"availability": True, "stock_status": "in_stock"}]}
    assert diagnose([tool_msg("get_product_offers", all_out)], None).reason == REASON_NO_STOCK
    assert diagnose([tool_msg("get_product_offers", some_in)], None) is None


def test_diagnose_high_price_from_trend_verdict():
    assert diagnose([tool_msg("analyze_price_trend", {"verdict": "esperar", "reason": "9% sobre el promedio"})], None).reason == REASON_HIGH_PRICE
    assert diagnose([tool_msg("analyze_price_trend", {"verdict": "buen_momento"})], None) is None


def test_diagnose_tool_error_status():
    assert diagnose([tool_msg("get_product_offers", "Producto no encontrado", status="error")], None).reason == REASON_TOOL_ERROR


def test_declared_preferences_ignore_questions():
    text = "Prefiero Samsung. No quiero Huawei, nunca compro Huawei! ¿Cuál es mejor? Busco un celular."
    found = extract_declared_preferences(text)
    assert "Prefiero Samsung" in found
    assert any("No quiero Huawei" in f for f in found)
    assert not any("?" in f for f in found)
    assert not any(f.startswith("Busco") for f in found)
