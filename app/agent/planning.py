"""Planificación y toma de decisiones del agente.

Todo lo de este módulo es **determinista y se prueba sin LLM**:

* ``extract_budget_clp``: saca el presupuesto del pedido ("$800.000", "800 mil", "1,5 millones").
* ``heuristic_plan`` / ``parse_plan``: el plan lo propone el LLM como JSON; si responde algo
  inválido se usa el plan heurístico, así el agente nunca queda sin plan.
* ``diagnose``: mira las observaciones de las herramientas y decide si las condiciones
  cambiaron lo bastante como para **replanificar** (sin resultados, sobre presupuesto,
  sin stock, precio alto, error de herramienta).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import ToolMessage

MAX_PLAN_STEPS = 8
STATUS_PENDING, STATUS_DONE = "pendiente", "hecho"

REASON_NO_RESULTS = "sin_resultados"
REASON_OVER_BUDGET = "sobre_presupuesto"
REASON_NO_STOCK = "sin_stock"
REASON_HIGH_PRICE = "precio_alto"
REASON_TOOL_ERROR = "error_herramienta"

REPLAN_HINTS = {
    REASON_NO_RESULTS: "La búsqueda no devolvió productos. Repetir con términos más generales, sin filtro de marca ni de precio mínimo, y avisar al usuario si se relajó algún criterio.",
    REASON_OVER_BUDGET: "Todo lo encontrado supera el presupuesto. Buscar alternativas de gama inferior dentro del presupuesto; si no existen, crear una alerta de precio por el mejor candidato e informar cuánto falta.",
    REASON_NO_STOCK: "La oferta elegida no tiene stock. Descartarla y elegir la siguiente tienda o el siguiente candidato.",
    REASON_HIGH_PRICE: "El análisis histórico dice 'esperar': el precio está alto. No recomendar comprar ahora; crear una alerta de precio con un objetivo cercano al promedio histórico.",
    REASON_TOOL_ERROR: "Una herramienta falló. Corregir los parámetros según el mensaje de error y reintentar una sola vez.",
}


@dataclass(frozen=True)
class Diagnosis:
    reason: str
    detail: str

    @property
    def hint(self) -> str:
        return REPLAN_HINTS[self.reason]


# -- presupuesto -------------------------------------------------------------------------
_BUDGET_WORDS = ("presupuesto", "hasta", "maximo", "máximo", "menos de", "bajo", "no mas de", "no más de", "tope", "gastar")
_AMOUNT = re.compile(
    r"(?P<sym>\$\s*)?(?P<num>\d{1,3}(?:[.\s]\d{3})+|\d+(?:[.,]\d+)?)\s*(?P<unit>millones|millon|millón|mil|lucas|luca|palos|palo|k)?\b",
    re.IGNORECASE,
)


def _amount_to_clp(num: str, unit: str | None) -> int | None:
    unit = (unit or "").lower()
    if re.fullmatch(r"\d{1,3}(?:[.\s]\d{3})+", num):
        value = float(re.sub(r"[.\s]", "", num))
    else:
        value = float(num.replace(",", "."))
    if unit in ("millones", "millon", "millón", "palos", "palo"):
        value *= 1_000_000
    elif unit in ("mil", "lucas", "luca", "k"):
        value *= 1_000
    value = round(value)
    return value if value >= 1000 else None


def extract_budget_clp(text: str) -> int | None:
    """Presupuesto en CLP mencionado en ``text``; prefiere el monto más cercano a una palabra de presupuesto."""
    lowered = text.lower()
    best: tuple[int, int] | None = None  # (distancia a palabra de presupuesto, monto)
    for match in _AMOUNT.finditer(text):
        amount = _amount_to_clp(match.group("num"), match.group("unit"))
        if amount is None:
            continue
        start = match.start()
        distances = [start - (lowered.rfind(word, 0, start) + len(word)) for word in _BUDGET_WORDS if lowered.rfind(word, 0, start) != -1]
        distance = min(distances) if distances else 10_000
        if best is None or distance < best[0]:
            best = (distance, amount)
    return best[1] if best else None


# -- preferencias declaradas -------------------------------------------------------------
_PREFERENCE_CUES = re.compile(
    r"\b(prefiero|no quiero|no me gusta|evito|nunca (?:compro|quiero|uso)|siempre (?:compro|uso|busco)|odio|me encanta|mi presupuesto (?:habitual|normal|t[ií]pico)|compro (?:solo|siempre) en)\b",
    re.IGNORECASE,
)


def extract_declared_preferences(text: str) -> list[str]:
    """Frases en las que el usuario declara un gusto estable. Es la red de seguridad de la memoria:
    se guardan aunque el LLM no llame a ``remember_preference``. Las preguntas se ignoran."""
    found: list[str] = []
    for sentence in re.split(r"(?<=[.;!])\s+|\n+", text):
        sentence = sentence.strip(" .;!")
        if 6 <= len(sentence) <= 200 and "?" not in sentence and _PREFERENCE_CUES.search(sentence):
            found.append(sentence)
    return found[:3]


# -- plan --------------------------------------------------------------------------------
def _step(index: int, action: str, priority: int) -> dict[str, Any]:
    return {"id": index, "action": action, "priority": priority, "status": STATUS_PENDING}


def heuristic_plan(goal: str, *, has_memories: bool, budget_clp: int | None, reason: str | None = None) -> list[dict[str, Any]]:
    """Plan por reglas: sirve de respaldo y de base para las pruebas."""
    text = goal.lower()
    actions: list[tuple[str, int]] = []
    if re.search(r"\balertas?\b.*\b(revis|cumpl|bajar|baj)|\b(revis|mira|chequea)\w*\b.*\balertas?\b", text):
        actions.append(("Revisar las alertas de precio activas con check_price_alerts", 1))
        if not re.search(r"busco|quiero|necesito|recomiend|comprar|armar", text):
            actions.append(("Si alguna se cumplió, decir cuál producto, en qué tienda y a qué precio bajó", 2))
            actions.append(("Responder con el resultado de la revisión", 3))
            return [_step(i + 1, action, priority) for i, (action, priority) in enumerate(actions)]
    if reason:
        actions.append((f"Adaptación por '{reason}': {REPLAN_HINTS[reason]}", 1))
    else:
        if not has_memories:
            actions.append(("Consultar las preferencias guardadas del usuario (get_user_profile / recall_memory)", 1))
        limit = f" con tope de ${budget_clp:,}".replace(",", ".") if budget_clp else ""
        actions.append((f"Buscar candidatos en el catálogo{limit} (search_products)", 1))
    actions.append(("Revisar ofertas y stock de los mejores candidatos (get_product_offers)", 2))
    actions.append(("Juzgar si es buen momento de compra con analyze_price_trend", 2))
    if re.search(r"compar|vs\b|mejor|cu[aá]l", text):
        actions.append(("Comparar los finalistas lado a lado (compare_products)", 2))
    if re.search(r"avis|alerta|notific|cuando baje|espera", text) or reason in (REASON_HIGH_PRICE, REASON_OVER_BUDGET):
        actions.append(("Crear una alerta de precio para lo que no conviene comprar hoy (create_price_alert)", 2))
    if re.search(r"lista|armar|guarda|setup|\bpc\b|kit|canasta", text):
        actions.append(("Guardar la lista de compra con la mejor oferta de cada ítem (save_shopping_list)", 3))
    actions.append(("Si el usuario reveló una preferencia estable, guardarla con remember_preference", 3))
    actions.append(("Responder con la recomendación, el total frente al presupuesto y los datos que la respaldan", 3))
    return [_step(i + 1, action, priority) for i, (action, priority) in enumerate(actions[:MAX_PLAN_STEPS])]


def parse_plan(raw: str) -> list[dict[str, Any]] | None:
    """Convierte la respuesta del LLM en pasos válidos, o ``None`` si no se puede."""
    if not raw:
        return None
    match = re.search(r"\{.*\}|\[.*\]", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    steps = data.get("steps") if isinstance(data, dict) else data
    if not isinstance(steps, list):
        return None
    clean: list[dict[str, Any]] = []
    for item in steps:
        action = item.get("action") if isinstance(item, dict) else item if isinstance(item, str) else None
        if not isinstance(action, str) or not action.strip():
            continue
        priority = item.get("priority", 2) if isinstance(item, dict) else 2
        priority = priority if isinstance(priority, int) and 1 <= priority <= 3 else 2
        clean.append({"action": action.strip()[:240], "priority": priority})
    if not clean:
        return None
    clean = sorted(clean[:MAX_PLAN_STEPS], key=lambda step: step["priority"])  # estable: respeta el orden dentro de cada prioridad
    return [_step(i + 1, step["action"], step["priority"]) for i, step in enumerate(clean)]


def mark_progress(plan: list[dict[str, Any]], executed_tools: list[str]) -> list[dict[str, Any]]:
    """Marca como hechos los pasos pendientes que nombran una herramienta recién ejecutada.

    Un paso que no nombra ninguna herramienta ejecutada queda pendiente: es mejor no marcar
    nada que marcar de más (el plan se le muestra al LLM en cada vuelta).
    """
    updated = [dict(step) for step in plan]
    done_now = set(executed_tools)
    for step in updated:
        if step["status"] == STATUS_PENDING and any(tool in step["action"] for tool in done_now):
            step["status"] = STATUS_DONE
    return updated


def render_plan(plan: list[dict[str, Any]]) -> str:
    return "\n".join(f"{step['id']}. [{step['status']}] (prioridad {step['priority']}) {step['action']}" for step in plan)


# -- diagnóstico -------------------------------------------------------------------------
def _parse(message: ToolMessage) -> Any:
    try:
        return json.loads(message.content if isinstance(message.content, str) else json.dumps(message.content))
    except (json.JSONDecodeError, TypeError):
        return None


def diagnose(tool_messages: list[ToolMessage], budget_clp: int | None) -> Diagnosis | None:
    """Revisa las observaciones de la última ronda de herramientas; ``None`` si todo va bien."""
    for message in tool_messages:
        name = message.name or ""
        data = _parse(message)
        if getattr(message, "status", None) == "error" or (data is None and isinstance(message.content, str) and message.content.lower().startswith("error")):
            return Diagnosis(REASON_TOOL_ERROR, f"{name}: {str(message.content)[:160]}")
        if not isinstance(data, dict):
            continue
        if name == "search_products":
            items = data.get("items") or []
            if not items:
                return Diagnosis(REASON_NO_RESULTS, "search_products devolvió 0 productos")
            prices = [item.get("lowest_price") or item.get("price_clp") for item in items]
            prices = [p for p in prices if p]
            if budget_clp and prices and min(prices) > budget_clp:
                return Diagnosis(REASON_OVER_BUDGET, f"El más barato cuesta ${min(prices):,} y el presupuesto es ${budget_clp:,}".replace(",", "."))
        elif name == "get_product_offers":
            items = data.get("items") or []
            if items and not any(item.get("availability", True) and item.get("stock_status") != "out_of_stock" for item in items):
                return Diagnosis(REASON_NO_STOCK, "Todas las ofertas del producto están sin stock")
        elif name == "analyze_price_trend" and data.get("verdict") == "esperar":
            return Diagnosis(REASON_HIGH_PRICE, data.get("reason", "Precio sobre el promedio histórico"))
    return None
