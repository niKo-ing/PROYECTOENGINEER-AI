"""El chat y el agente son uno solo: el agente devuelve las tarjetas de producto que consultó."""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.service import MAX_CARDS, collect_products


def _tool(name: str, payload: dict) -> ToolMessage:
    return ToolMessage(content=json.dumps(payload), tool_call_id="x", name=name)


def _item(i: int, **extra) -> dict:
    return {"id": i, "name": f"Producto {i}", "brand": "Marca", "category": "notebooks", "lowest_price": 100_000 + i, **extra}


def test_collects_cards_from_search_of_this_turn_only():
    messages = [
        HumanMessage("turno anterior"),
        _tool("search_products", {"items": [_item(99)]}),
        AIMessage("listo"),
        HumanMessage("turno actual"),
        _tool("search_products", {"items": [_item(1), _item(2)], "total": 2}),
        AIMessage("respuesta"),
    ]
    cards, comparison = collect_products(messages)
    assert [c["id"] for c in cards] == [1, 2]
    assert comparison is None


def test_deduplicates_and_caps_cards():
    messages = [
        HumanMessage("hola"),
        _tool("search_products", {"items": [_item(i) for i in range(1, 12)]}),
        _tool("compare_products", {"products": [_item(1), {"error": {"product_id": 7}}], "comparison": {"dimensions": []}}),
    ]
    cards, comparison = collect_products(messages)
    assert len(cards) == MAX_CARDS
    assert len({c["id"] for c in cards}) == len(cards)
    assert comparison == {"dimensions": []}


def test_ignores_other_tools_and_bad_json():
    messages = [
        HumanMessage("hola"),
        ToolMessage(content="no es json", tool_call_id="a", name="search_products"),
        _tool("get_price_history", {"items": [_item(5)]}),
    ]
    assert collect_products(messages) == ([], None)
