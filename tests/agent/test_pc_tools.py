"""Herramientas del armador para el agente: consultan el motor de compatibilidad, no lo reemplazan."""

import json

import pytest
from langchain_core.tools import ToolException
from sqlalchemy import select

from app.agent.memory import LongTermMemory
from app.agent.planning import REASON_INCOMPATIBLE, REASON_PC_OVER_BUDGET, diagnose, heuristic_plan
from app.agent.tools import RunContext, build_tools
from app.ai.rag.embedding import LocalHashEmbeddingProvider
from app.models.pc import PcBuild
from app.pcbuilder.catalog import seed_pc_parts
from langchain_core.messages import ToolMessage

from agent_support import USER


@pytest.fixture()
def pc_tools(db):
    seed_pc_parts(db)
    context = RunContext()
    memory = LongTermMemory(db, USER, LocalHashEmbeddingProvider())
    return {tool.name: tool for tool in build_tools(db, USER, memory, context)}, context


def call(tools, name, /, **args):
    return json.loads(tools[name].invoke(args))


def find(tools, query, slot=None, legacy=False):
    items = call(tools, "search_pc_parts", query=query, slot=slot, include_discontinued=legacy)["items"]
    assert items, query
    return items[0]["product_id"]


def test_busca_piezas_por_texto_espacio_y_precio(pc_tools):
    tools, _ = pc_tools
    data = call(tools, "search_pc_parts", slot="gpu", max_price_clp=350_000)
    assert data["items"] and all(i["slot"] == "gpu" and i["price_clp"] <= 350_000 for i in data["items"])
    assert all(not i["discontinued"] for i in data["items"])
    ryzen = call(tools, "search_pc_parts", query="ryzen 5 7600")["items"][0]
    assert ryzen["specs"]["socket"] == "AM5" and "memory_types" in ryzen["specs"]
    assert call(tools, "search_pc_parts", query="GTX 1650")["total"] == 0
    assert call(tools, "search_pc_parts", query="GTX 1650", include_discontinued=True)["total"] == 1


def test_compatibilidad_detecta_socket_distinto(pc_tools):
    tools, _ = pc_tools
    data = call(tools, "check_pc_compatibility", product_ids=[find(tools, "ryzen 5 7600"), find(tools, "B550M", "motherboard")])
    assert data["compatible"] is False and any(i["code"] == "socket" for i in data["issues"])


def test_compatibilidad_de_un_armado_correcto(pc_tools):
    tools, _ = pc_tools
    ids = [find(tools, "ryzen 5 5600", "cpu"), find(tools, "B550M", "motherboard"), find(tools, "16GB (2x8) DDR4"), find(tools, "RTX 4060", "gpu"),
           find(tools, "NV3 1TB"), find(tools, "CV550"), find(tools, "4000D")]
    data = call(tools, "check_pc_compatibility", product_ids=ids)
    assert data["compatible"] is True and data["complete"] is True and data["estimated_watts"] > 0


def test_compatibilidad_rechaza_ids_que_no_son_piezas(pc_tools):
    tools, _ = pc_tools
    with pytest.raises(ToolException, match="no son piezas"):
        tools["check_pc_compatibility"].func(product_ids=[999_999])


def test_recomienda_dentro_del_presupuesto(pc_tools):
    tools, _ = pc_tools
    data = call(tools, "recommend_pc_build", use_case="gaming_1080", budget_clp=800_000)
    assert data["within_budget"] and data["total_clp"] <= 800_000 and {p["slot"] for p in data["parts"]} >= {"cpu", "gpu", "motherboard", "psu"}
    with pytest.raises(ToolException, match="use_case"):
        tools["recommend_pc_build"].func(use_case="minar", budget_clp=800_000)


def test_guardar_solo_si_el_usuario_lo_pidio(pc_tools, db):
    tools, context = pc_tools
    ids = [find(tools, "ryzen 5 5600", "cpu"), find(tools, "B550M", "motherboard")]
    context.goal = "¿qué placa le sirve al ryzen 5 5600?"
    assert call(tools, "save_pc_build", name="Prueba", product_ids=ids)["saved"] is False
    assert db.scalar(select(PcBuild)) is None
    context.goal = "guárdalo en mis computadores"
    saved = call(tools, "save_pc_build", name="Mi proyecto", product_ids=ids, kind="proyecto")
    assert saved["saved"] and saved["url"] == f"/mis-pc/{saved['pc_id']}"
    pcs = call(tools, "list_my_pcs")
    assert pcs["total"] == 1 and pcs["pcs"][0]["name"] == "Mi proyecto"


def test_mejoras_y_guias(pc_tools):
    tools, context = pc_tools
    context.goal = "registra mi pc"
    ids = [find(tools, "ryzen 5 3600", legacy=True), find(tools, "B450M", legacy=True), find(tools, "8GB (1x8) DDR4"), find(tools, "GTX 1650", legacy=True),
           find(tools, "A400"), find(tools, "P450B"), find(tools, "MX330")]
    pc = call(tools, "save_pc_build", name="PC viejo", product_ids=ids, kind="propio", use_case="gaming_1080")
    upgrades = call(tools, "suggest_pc_upgrade", pc_id=pc["pc_id"], budget_clp=300_000)
    assert upgrades["options"] and all(o["cost_clp"] <= 300_000 for o in upgrades["options"])
    guide = call(tools, "search_compatibility_guide", query="¿puedo usar memoria DDR4 en una placa AM5?")
    assert guide["chunks"][0]["url"].startswith("/guias/") and "DDR" in guide["chunks"][0]["content"]


def test_planificador_y_diagnostico_para_pedidos_de_pc():
    plan = [s["action"] for s in heuristic_plan("¿El Ryzen 5 7600 es compatible con la placa B550M?", has_memories=False, budget_clp=None)]
    assert any("check_pc_compatibility" in a for a in plan) and not any("search_products" in a for a in plan)
    ask = [s["action"] for s in heuristic_plan("Ármame un PC", has_memories=False, budget_clp=None)]
    assert any("Preguntar el presupuesto" in a for a in ask)
    bad = ToolMessage(json.dumps({"compatible": False, "issues": [{"level": "error", "code": "socket", "message": "Socket distinto"}]}), tool_call_id="1", name="check_pc_compatibility")
    assert diagnose([bad], None).reason == REASON_INCOMPATIBLE
    over = ToolMessage(json.dumps({"within_budget": False, "total_clp": 420000, "budget_clp": 300000}), tool_call_id="2", name="recommend_pc_build")
    assert diagnose([over], 300000).reason == REASON_PC_OVER_BUDGET
