"""Planner — decides which catalog tools to invoke for a given intent.

The planner is deterministic and conservative: it only issues tool calls that
are necessary to gather enough evidence, avoids redundant calls, and can
terminate early when the intent needs no catalog data (greetings).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ai.conversation_state import ConversationState
from app.ai.entity_resolution import EntityResolution
from app.ai.schemas.intent import AIIntent, AIIntentType


@dataclass(frozen=True)
class PlanStep:
    tool: str
    parameters: dict[str, Any]
    purpose: str


@dataclass
class Plan:
    steps: list[PlanStep] = field(default_factory=list)
    finished: bool = False
    note: str | None = None

    @property
    def tools(self) -> list[str]:
        return [step.tool for step in self.steps]

    def add(self, tool: str, parameters: dict[str, Any], purpose: str) -> None:
        self.steps.append(PlanStep(tool=tool, parameters=parameters, purpose=purpose))


class Planner:
    """Builds a minimal execution plan for an AIIntent."""

    def build(
        self,
        intent: AIIntent,
        state: ConversationState,
        resolution: EntityResolution | None = None,
        *,
        searchable_message: str | None = None,
    ) -> Plan:
        kind = intent.intent
        plan = Plan()

        if kind == AIIntentType.GENERAL_QUESTION and not intent.constraints:
            plan.finished = True
            plan.note = "Saludo o pregunta general: no se requieren tools del catálogo."
            return plan

        if kind == AIIntentType.FOLLOW_UP:
            self._plan_follow_up(plan, intent, state)
            return plan

        if kind in (AIIntentType.COMPARE, AIIntentType.RECOMMEND):
            self._plan_compare(plan, intent, state, resolution)
            return plan

        if kind == AIIntentType.SEARCH:
            self._plan_search(plan, intent, state, searchable_message)
            return plan

        if kind == AIIntentType.SPECIFICATION:
            self._plan_specification(plan, intent, state, searchable_message)
            return plan

        if kind == AIIntentType.PRICE_CHECK:
            self._plan_price_check(plan, intent, state, searchable_message)
            return plan

        if kind == AIIntentType.PRODUCT_DETAIL:
            self._plan_product_detail(plan, intent, state)
            return plan

        if kind == AIIntentType.COMPATIBILITY:
            self._plan_search(plan, intent, state, searchable_message)
            return plan

        # GENERAL_QUESTION with constraints → still useful to search.
        self._plan_search(plan, intent, state, searchable_message)
        return plan

    def _plan_follow_up(self, plan: Plan, intent: AIIntent, state: ConversationState) -> None:
        if state.has_active_products():
            ids = state.active_product_ids()
            if len(ids) >= 2:
                plan.add("compare_products", {"product_ids": ids}, "Comparar los productos activos de la conversación")
            elif ids:
                plan.add("get_product", {"product_id": ids[0]}, "Detalle del producto activo")
        elif not intent.entities and not intent.constraints:
            plan.finished = True
            plan.note = "Referencia a contexto sin productos activos; responder sin buscar."

    def _plan_compare(self, plan: Plan, intent: AIIntent, state: ConversationState, resolution: EntityResolution | None) -> None:
        active = state.active_product_ids()
        resolved = [p.product_id for p in (resolution.resolved if resolution else [])]
        combined = _dedupe(active + resolved)
        if len(combined) >= 2:
            plan.add("compare_products", {"product_ids": combined[:5]}, "Comparar productos activos y resueltos")
            return

        # A new candidate is being brought in (e.g. "¿y contra un poco?").
        candidates = [p.product_id for p in (resolution.candidates if resolution else [])]
        target = _dedupe(combined + candidates)
        if len(target) >= 2:
            plan.add("compare_products", {"product_ids": target[:5]}, "Comparar candidatos del catálogo")
            return

        if intent.constraints.get("use_case") or searchable_terms(intent):
            plan.add("search_products", {}, "Buscar candidatos para comparar/recomendar")
            return

        plan.finished = True
        plan.note = "Sin candidatos comparables: se pedirá aclaración."

    def _plan_search(self, plan: Plan, intent: AIIntent, state: ConversationState, searchable_message: str | None) -> None:
        query = self._search_query(intent, searchable_message)
        params: dict[str, Any] = {}
        if query:
            params["query"] = query
        brand = self._first_brand(intent)
        if brand:
            params["brand"] = brand
        category = self._first_category(intent)
        if category:
            params["category"] = category
        max_price = intent.constraints.get("max_price")
        if max_price:
            params["max_price_clp"] = max_price
        params.setdefault("limit", 10)
        plan.add("search_products", params, "Buscar productos del catálogo")

    def _plan_specification(self, plan: Plan, intent: AIIntent, state: ConversationState, searchable_message: str | None) -> None:
        if state.has_active_products():
            ids = state.active_product_ids()
            if len(ids) >= 2:
                plan.add("compare_products", {"product_ids": ids}, "Comparar especificaciones de productos activos")
            elif ids:
                plan.add("get_product", {"product_id": ids[0]}, "Especificaciones del producto activo")
            return
        self._plan_search(plan, intent, state, searchable_message)

    def _plan_price_check(self, plan: Plan, intent: AIIntent, state: ConversationState, searchable_message: str | None) -> None:
        if state.has_active_products() and not intent.constraints.get("max_price"):
            ids = state.active_product_ids()
            if ids:
                plan.add("get_product_offers", {"product_id": ids[0]}, "Obtener ofertas del producto activo")
                return
        self._plan_search(plan, intent, state, searchable_message)

    def _plan_product_detail(self, plan: Plan, intent: AIIntent, state: ConversationState) -> None:
        ids = state.active_product_ids()
        if ids:
            plan.add("get_product", {"product_id": ids[0]}, "Detalle del producto activo")
            return
        explicit = [e.resolved_product_ids for e in intent.entities if e.resolved_product_ids]
        if explicit and explicit[0]:
            plan.add("get_product", {"product_id": explicit[0][0]}, "Detalle del producto mencionado")
        else:
            plan.finished = True
            plan.note = "Sin producto concreto: se solicitará el producto."

    @staticmethod
    def _search_query(intent: AIIntent, searchable_message: str | None) -> str | None:
        if searchable_message:
            return searchable_message
        families = [e.family for e in intent.entities if e.family]
        models = [e.model for e in intent.entities if e.model]
        return families[0] if families else (models[0] if models else None)

    @staticmethod
    def _first_brand(intent: AIIntent) -> str | None:
        for entity in intent.entities:
            if entity.brand:
                return entity.brand[:100]
        return None

    @staticmethod
    def _first_category(intent: AIIntent) -> str | None:
        for entity in intent.entities:
            if entity.category:
                return entity.category[:100]
        return None


def _dedupe(values: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def searchable_terms(intent: AIIntent) -> bool:
    for entity in intent.entities:
        if entity.family or entity.model or entity.brand or entity.category or entity.specification:
            return True
    return False