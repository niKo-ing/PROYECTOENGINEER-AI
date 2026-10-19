"""Modelo de chat guionado para pruebas y demos sin red.

``ScriptedChatModel`` cumple la interfaz ``BaseChatModel`` de LangChain (incluido
``bind_tools``), así que el grafo no sabe que no es Gemini. Su ``policy`` **lee los
mensajes y las observaciones de las herramientas** y decide la siguiente llamada, como lo
haría un LLM razonable: no es una lista fija de respuestas. Esto vuelve deterministas las
pruebas de lo que realmente importa probar (el grafo, la memoria, la replanificación),
sin gastar cuota ni depender de la red. La demo en vivo (``--live``) usa Gemini.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.agent.graph import PLAN_MARKER
from app.agent.planning import extract_budget_clp, extract_declared_preferences, heuristic_plan

Policy = Callable[[list[BaseMessage], list[str]], AIMessage]


class ScriptedChatModel(BaseChatModel):
    policy: Any
    bound_tools: list[str] = Field(default_factory=list)
    calls: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        message = self.policy(messages, self.bound_tools)
        self.calls.append({"mode": "plan" if _is_plan_request(messages) else "act", "tool_calls": [c["name"] for c in message.tool_calls]})
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        names = [getattr(tool, "name", None) or tool["name"] for tool in tools]
        return self.model_copy(update={"bound_tools": names})


def _is_plan_request(messages: list[BaseMessage]) -> bool:
    return bool(messages) and isinstance(messages[0], SystemMessage) and PLAN_MARKER in str(messages[0].content)[:80]


def _call(tool_name: str, /, **args: Any) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": tool_name, "args": args, "id": uuid.uuid4().hex[:10]}])


def _money(value: int) -> str:
    return f"${value:,}".replace(",", ".")


class AhorroPolicy:
    """Política de un comprador razonable para los escenarios de TodoBarato.

    ``queries``: búsquedas a intentar en orden (la primera con tope de precio; las siguientes,
    más generales y sin tope, solo si la anterior no devolvió nada). ``use_remember_tool``:
    si es ``False`` no llama a ``remember_preference`` y la preferencia solo se guarda por la
    red de seguridad del grafo. ``bad_plan``: responde basura al planificador (prueba el respaldo).
    """

    def __init__(self, queries: list[str] | None = None, *, use_remember_tool: bool = False, bad_plan: bool = False):
        self.queries = queries or ["notebook"]
        self.use_remember_tool = use_remember_tool
        self.bad_plan = bad_plan

    def __call__(self, messages: list[BaseMessage], tool_names: list[str]) -> AIMessage:
        if _is_plan_request(messages):
            return self._plan(messages)
        return self._act(messages)

    # -- planificador ------------------------------------------------------------------
    def _plan(self, messages: list[BaseMessage]) -> AIMessage:
        if self.bad_plan:
            return AIMessage(content="Claro, primero buscaría algo y luego vemos.")
        prompt = str(messages[-1].content)
        goal = prompt.split("Objetivo del usuario:", 1)[-1].split("\n", 1)[0].strip()
        reason = re.search(r"Cambió una condición \((\w+)\)", prompt)
        steps = heuristic_plan(goal, has_memories="Memoria relevante" in prompt, budget_clp=extract_budget_clp(goal), reason=reason.group(1) if reason else None)
        return AIMessage(content=json.dumps({"steps": [{"action": s["action"], "priority": s["priority"]} for s in steps]}, ensure_ascii=False))

    # -- actor -------------------------------------------------------------------------
    def _act(self, messages: list[BaseMessage]) -> AIMessage:
        start = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=0)
        goal = str(messages[start].content) if messages else ""
        turn = messages[start + 1 :]
        made: list[tuple[str, dict]] = []
        results: dict[str, list[Any]] = {}
        pending: dict[str, tuple[str, dict]] = {}
        for m in turn:
            if isinstance(m, AIMessage):
                for c in m.tool_calls:
                    made.append((c["name"], c["args"]))
                    pending[c["id"]] = (c["name"], c["args"])
            elif isinstance(m, ToolMessage):
                try:
                    data = json.loads(m.content)
                except (TypeError, json.JSONDecodeError):
                    data = {"error": str(m.content)}
                results.setdefault(m.name or pending.get(m.tool_call_id, ("?",))[0], []).append(data)
        done = lambda name: any(n == name for n, _ in made)  # noqa: E731
        budget = extract_budget_clp(goal)
        lowered = goal.lower()

        if re.search(r"alertas?", lowered) and re.search(r"revis|cumpl|bajaron|chequea", lowered):
            if not done("check_price_alerts"):
                return _call("check_price_alerts")
            report = results["check_price_alerts"][-1]
            hit = [a for a in report.get("alerts", []) if a.get("triggered")]
            if hit:
                lines = [f"{a['product']} bajó a {_money(a['current_price_clp'])} en {a['store']} (tu objetivo era {_money(a['target_price_clp'])})." for a in hit]
                return AIMessage(content="¡Se cumplió una alerta! " + " ".join(lines) + " Es buen momento para comprar.")
            return AIMessage(content=f"Revisé {report.get('active_checked', 0)} alerta(s) y ninguna se cumple todavía.")

        searches = results.get("search_products", [])
        if not searches:
            args: dict[str, Any] = {"query": self.queries[0]}
            if budget:
                args["max_price_clp"] = budget
            return _call("search_products", **args)
        last = searches[-1]
        if not (last.get("items") or []):
            attempts = [(self.queries[0], budget)] + [(q, None) for q in self.queries]
            tried = len(searches)
            if tried < len(attempts):
                query, cap = attempts[tried]
                return _call("search_products", query=query, **({"max_price_clp": cap} if cap else {}))
            return AIMessage(content="No encontré productos que calcen con tu pedido en el catálogo, ni relajando los filtros.")

        def price_of(item: dict) -> int:
            return item.get("lowest_price") or item.get("price_clp") or 0

        pool = [i for i in last["items"] if price_of(i)] or last["items"]
        pick = min(pool, key=lambda i: price_of(i) or 10**12)
        price = price_of(pick)
        pid = pick["id"]
        if not done("get_product_offers"):
            return _call("get_product_offers", product_id=pid)
        if not done("analyze_price_trend"):
            return _call("analyze_price_trend", product_id=pid)
        trend = results["analyze_price_trend"][-1]
        verdict = trend.get("verdict")
        if verdict == "sin_precio_actual":
            return AIMessage(content=f"{pick['name']} no tiene ninguna oferta con stock ahora mismo, así que no puedo recomendarlo ni calcular su precio.")
        over_budget = bool(budget and price > budget)

        if (verdict == "esperar" or over_budget) and not done("create_price_alert"):
            target = budget if over_budget else int(trend.get("avg_clp") or price)
            return _call("create_price_alert", product_id=pid, target_price_clp=target)
        if not (verdict == "esperar" or over_budget) and re.search(r"lista|guarda|armar|compra", lowered) and not done("save_shopping_list"):
            return _call("save_shopping_list", name=f"Compra: {pick['name']}"[:120], product_ids=[pid], budget_clp=budget)
        if self.use_remember_tool and not done("remember_preference"):
            sentences = extract_declared_preferences(goal)
            if sentences:
                return _call("remember_preference", content=sentences[0], importance=4)

        if over_budget:
            return AIMessage(content=f"{pick['name']} cuesta {_money(price)} y tu presupuesto es {_money(budget)}: faltan {_money(price - budget)}. Dejé una alerta para avisarte cuando baje a {_money(budget)}.")
        if verdict == "esperar":
            return AIMessage(content=f"{pick['name']} está en {_money(price)}. {trend.get('reason', '')} Te recomiendo esperar: dejé una alerta de precio.")
        tail = " Lo dejé guardado en tu lista." if done("save_shopping_list") else ""
        return AIMessage(content=f"Te recomiendo {pick['name']} a {_money(price)} en {pick.get('lowest_price_store') or 'la mejor tienda'}. {trend.get('reason', '')}{tail}")
