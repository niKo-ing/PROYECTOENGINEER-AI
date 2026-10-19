"""Grafo del agente de ahorro (LangGraph).

::

    START → recall → plan → act ──(tool_calls)──→ tools → reflect ─┬─(condiciones cambiaron)─→ plan
                              │                                     └─(todo bien)──────────────→ act
                              ├──(sin tool_calls)──→ remember → END
                              └──(límite de pasos)─→ give_up  → remember → END

* ``recall``  : recupera de la memoria de largo plazo lo relevante para el pedido y fija el presupuesto.
* ``plan``    : el LLM propone un plan priorizado (JSON); si falla, plan heurístico. En un
                replan conserva los pasos ya hechos y agrega la adaptación.
* ``act``     : el LLM con herramientas decide la próxima acción siguiendo el plan.
* ``tools``   : ejecuta las herramientas (consulta, razonamiento y escritura).
* ``reflect`` : lee las observaciones y decide, por reglas, si hay que replanificar.
* ``remember``: consolida en la memoria de largo plazo (episodio + preferencias declaradas).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.agent.memory import LongTermMemory, summarize_dropped, window_messages
from app.agent.planning import (
    REPLAN_HINTS,
    STATUS_DONE,
    Diagnosis,
    diagnose,
    extract_budget_clp,
    extract_declared_preferences,
    heuristic_plan,
    mark_progress,
    parse_plan,
    render_plan,
)

PLAN_MARKER = "PLANIFICADOR"
ACT_MARKER = "AGENTE DE AHORRO"


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    turn: int
    goal: str
    budget_clp: int | None
    memories: list[str]
    plan: list[dict[str, Any]]
    plan_source: str
    adaptation: str
    replan_reason: str | None
    handled: list[str]
    replans: int
    steps: int
    wrote: list[str]
    trace: Annotated[list[dict[str, Any]], operator.add]


PLAN_SYSTEM = f"""Eres el {PLAN_MARKER} de TodoBarato, un comparador de precios de tecnología en Chile.
Devuelve SOLO un JSON con la forma {{"steps": [{{"action": "...", "priority": 1}}]}} (prioridad 1 = hacer primero, 3 = al final, máximo 8 pasos).
Herramientas disponibles: {{tools}}.
Cada paso debe ser una acción concreta que use esas herramientas. No inventes productos ni precios."""

ACT_SYSTEM = f"""Eres el {ACT_MARKER} de TodoBarato, un comparador de precios de tecnología en Chile. Resuelves el objetivo del usuario usando herramientas.
Reglas:
- Los precios están en CLP. Usa SOLO datos devueltos por las herramientas: nunca inventes productos, precios, tiendas ni stock.
- Sigue el plan, un paso a la vez, y no repitas una consulta que ya hiciste.
- Antes de recomendar comprar un producto, revisa su oferta (get_product_offers) y su tendencia (analyze_price_trend).
- Solo escribes (create_price_alert, save_shopping_list, remember_preference) cuando el usuario lo pidió o es claramente lo que necesita. remember_preference es solo para datos estables que el usuario declaró.
- Respeta el presupuesto. Si no alcanza, dilo con la cifra y propón la alternativa.
- Si el usuario pidió que le avisen (o dijo «avísame») y nada cabe en su presupuesto, crea la alerta SIN preguntar: usa create_price_alert sobre el producto que mejor calza con lo pedido, con el presupuesto como precio objetivo, e informa cuánto falta.
- Termina con una respuesta breve en español: qué elegiste, cuánto cuesta, por qué, y qué dejaste guardado."""


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    return str(content or "")


def _last_human(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return _text(message.content)
    return ""


def _tools_of_last_round(messages: list[AnyMessage]) -> list[ToolMessage]:
    out: list[ToolMessage] = []
    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            out.append(message)
        elif out or isinstance(message, AIMessage):
            break
    return list(reversed(out))


def build_agent_graph(
    llm: BaseChatModel,
    tools: list[BaseTool],
    memory: LongTermMemory,
    *,
    checkpointer: Any = None,
    max_steps: int = 10,
    max_replans: int = 2,
    max_window: int = 24,
):
    """Compila el grafo. ``llm`` es cualquier ``BaseChatModel`` de LangChain (Gemini en producción)."""
    llm_with_tools = llm.bind_tools(tools)
    tool_names = ", ".join(tool.name for tool in tools)
    tool_node = ToolNode(tools, handle_tool_errors=True)
    write_tools = {"create_price_alert", "save_shopping_list", "remember_preference"}

    def recall(state: AgentState) -> dict[str, Any]:
        goal = _last_human(state.get("messages", []))
        turn = state.get("turn", 0) + 1
        hits = memory.recall(goal, k=4)
        memories = [f"[{hit.kind}] {hit.content}" for hit in hits]
        budget = extract_budget_clp(goal)
        event = {"turn": turn, "node": "recall", "memories": [{"content": h.content, "relevance": h.score} for h in hits], "budget_clp": budget}
        return {"turn": turn, "goal": goal, "budget_clp": budget, "memories": memories, "plan": [], "adaptation": "", "replan_reason": None, "handled": [], "replans": 0, "steps": 0, "wrote": [], "trace": [event]}

    def plan(state: AgentState) -> dict[str, Any]:
        reason = state.get("replan_reason")
        goal, budget, memories = state.get("goal", ""), state.get("budget_clp"), state.get("memories", [])
        done_before = [dict(step) for step in state.get("plan", []) if step.get("status") == STATUS_DONE]
        lines = [f"Objetivo del usuario: {goal}"]
        if budget:
            lines.append(f"Presupuesto detectado: ${budget:,} CLP".replace(",", "."))
        if memories:
            lines.append("Memoria relevante del usuario:\n" + "\n".join(f"- {m}" for m in memories))
        if reason:
            lines.append(f"REPLANIFICACIÓN. Cambió una condición ({reason}). {REPLAN_HINTS[reason]}")
            if done_before:
                lines.append("Pasos ya hechos (no los repitas):\n" + "\n".join(f"- {s['action']}" for s in done_before))
        try:
            raw = _text(llm.invoke([SystemMessage(PLAN_SYSTEM.replace("{tools}", tool_names)), HumanMessage("\n".join(lines))]).content)
        except Exception:  # noqa: BLE001 — cualquier falla del proveedor cae al plan heurístico
            raw = ""
        steps = parse_plan(raw)
        source = "llm"
        if steps is None:
            steps, source = heuristic_plan(goal, has_memories=bool(memories), budget_clp=budget, reason=reason), "heuristic"
        if done_before:
            already = {s["action"] for s in done_before}
            steps = [{**s, "id": i + 1} for i, s in enumerate(done_before + [{**s, "status": "pendiente"} for s in steps if s["action"] not in already])]
        event = {"turn": state.get("turn", 1), "node": "plan", "source": source, "replan": reason, "plan": [f"{s['priority']}: {s['action']}" for s in steps]}
        return {"plan": steps, "plan_source": source, "adaptation": REPLAN_HINTS[reason] if reason else state.get("adaptation", ""), "replan_reason": None, "trace": [event]}

    def act(state: AgentState) -> dict[str, Any]:
        dropped, window = window_messages(state.get("messages", []), max_window)
        sections = [ACT_SYSTEM, f"Objetivo actual: {state.get('goal', '')}"]
        if state.get("budget_clp"):
            sections.append(f"Presupuesto: ${state['budget_clp']:,} CLP".replace(",", "."))
        if state.get("memories"):
            sections.append("Memoria de largo plazo relevante (úsala sin volver a preguntar):\n" + "\n".join(f"- {m}" for m in state["memories"]))
        summary = summarize_dropped(dropped)
        if summary:
            sections.append(f"Resumen de la conversación anterior: {summary}")
        sections.append("Plan vigente:\n" + render_plan(state.get("plan", [])))
        if state.get("adaptation"):
            sections.append(f"CAMBIO DE CONDICIONES (ya replanificado): {state['adaptation']}")
        response = llm_with_tools.invoke([SystemMessage("\n\n".join(sections)), *window])
        calls = [{"tool": call["name"], "args": call.get("args", {})} for call in (getattr(response, "tool_calls", None) or [])]
        event = {"turn": state.get("turn", 1), "node": "act", "step": state.get("steps", 0) + 1, "tool_calls": calls}
        return {"messages": [response], "steps": state.get("steps", 0) + 1, "trace": [event]}

    def route_after_act(state: AgentState) -> str:
        last = state["messages"][-1]
        if not getattr(last, "tool_calls", None):
            return "remember"
        return "give_up" if state.get("steps", 0) > max_steps else "tools"

    def give_up(state: AgentState) -> dict[str, Any]:
        """Tope de pasos: cierra las llamadas pendientes (el proveedor las exige) y responde con lo logrado."""
        last = state["messages"][-1]
        closing = [ToolMessage(content="Omitida: se alcanzó el límite de pasos de la tarea.", tool_call_id=call["id"], name=call["name"], status="error") for call in last.tool_calls]
        done = ", ".join(state.get("wrote", [])) or "ninguna escritura"
        text = f"Llegué al límite de {max_steps} pasos sin cerrar la tarea. Lo hecho hasta ahora: {done}. Puedes pedirme que continúe."
        return {"messages": [*closing, AIMessage(content=text)], "trace": [{"turn": state.get("turn", 1), "node": "give_up", "max_steps": max_steps}]}

    def after_tools_bookkeeping(state: AgentState) -> list[str]:
        calls = getattr(next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None), "tool_calls", None) or []
        return [call["name"] for call in calls if call["name"] in write_tools]

    def reflect(state: AgentState) -> dict[str, Any]:
        observed = _tools_of_last_round(state["messages"])
        diagnosis: Diagnosis | None = diagnose(observed, state.get("budget_clp"))
        progress = mark_progress(state.get("plan", []), [m.name for m in observed if m.name])
        wrote = state.get("wrote", []) + [n for n in after_tools_bookkeeping(state) if not any(m.name == n and getattr(m, "status", None) == "error" for m in observed)]
        update: dict[str, Any] = {"plan": progress, "wrote": wrote, "replan_reason": None}
        event: dict[str, Any] = {"turn": state.get("turn", 1), "node": "reflect", "observed": [m.name for m in observed], "diagnosis": None}
        if diagnosis is not None:
            event["diagnosis"] = {"reason": diagnosis.reason, "detail": diagnosis.detail}
            handled = state.get("handled", [])
            if state.get("replans", 0) < max_replans and diagnosis.reason not in handled:
                update.update({"replan_reason": diagnosis.reason, "handled": handled + [diagnosis.reason], "replans": state.get("replans", 0) + 1})
                event["decision"] = "replanificar"
            else:
                event["decision"] = "continuar_sin_replan"
        update["trace"] = [event]
        return update

    def route_after_reflect(state: AgentState) -> str:
        return "plan" if state.get("replan_reason") else "act"

    def remember(state: AgentState) -> dict[str, Any]:
        stored: list[str] = []
        final = _text(state["messages"][-1].content) if state.get("messages") else ""
        goal = state.get("goal", "")
        if "remember_preference" not in state.get("wrote", []):
            for sentence in extract_declared_preferences(goal):
                _, created = memory.add(sentence, kind="preference", importance=4)
                if created:
                    stored.append(sentence)
        if state.get("steps", 0) > 1 and final:
            episode = f"Tarea: {goal[:160]} → Resultado: {final[:240]}"
            _, created = memory.add(episode, kind="episode", importance=2)
            if created:
                stored.append(episode)
        return {"trace": [{"turn": state.get("turn", 1), "node": "remember", "stored": stored}]}

    graph = StateGraph(AgentState)
    graph.add_node("recall", recall)
    graph.add_node("plan", plan)
    graph.add_node("act", act)
    graph.add_node("tools", tool_node)
    graph.add_node("reflect", reflect)
    graph.add_node("give_up", give_up)
    graph.add_node("remember", remember)
    graph.add_edge(START, "recall")
    graph.add_edge("recall", "plan")
    graph.add_edge("plan", "act")
    graph.add_conditional_edges("act", route_after_act, {"tools": "tools", "remember": "remember", "give_up": "give_up"})
    graph.add_edge("tools", "reflect")
    graph.add_conditional_edges("reflect", route_after_reflect, {"plan": "plan", "act": "act"})
    graph.add_edge("give_up", "remember")
    graph.add_edge("remember", END)
    return graph.compile(checkpointer=checkpointer)
