"""Planner — decides which catalog tools to invoke for a given intent.

The planner is deterministic and conservative: it only issues tool calls that
are necessary to gather enough evidence, avoids redundant calls, and can
terminate early when the intent needs no catalog data (greetings).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.ai.conversation_state import ConversationState
from app.ai.entity_resolution import EntityResolution
from app.ai.research.query_planning import detect_topics
from app.ai.schemas.intent import AIIntent, AIIntentType
from app.core.config import settings


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


class ResearchDepth(str, Enum):
    """How deep external research may go for a given request."""

    NONE = "none"
    LIGHT = "light"
    DEEP = "deep"


@dataclass(frozen=True)
class ResearchBudget:
    """Cost ceiling for a research pass, per escalation profile."""
    profile: str
    max_queries: int
    max_sources: int
    max_documents: int
    reason: str


@dataclass(frozen=True)
class ResearchDecision:
    """Single source of truth for a research pass (mode, depth and budgets).

    Keeps the escalation decision explicit and measurable: every research run
    carries a deterministic, configurable budget and never an unlimited one.
    """
    mode: str
    depth: ResearchDepth
    max_queries: int
    max_sources: int
    max_documents: int
    use_rag: bool
    use_external: bool
    reason: str


# Escalation profiles for external research (see Planner.research_plan).
RESEARCH_CATALOG_ONLY = "catalog_only"
RESEARCH_STANDARD = "catalog_plus_research"
RESEARCH_DEEP = "deep_research"


_RESEARCHABLE_KINDS = {
    AIIntentType.COMPARE,
    AIIntentType.RECOMMEND,
    AIIntentType.PRODUCT_DETAIL,
    AIIntentType.SPECIFICATION,
}


_DEEP_TERMS = (
    "investiga",
    "investigue",
    "en profundidad",
    "especifica",
    "a fondo",
    "para mi caso de uso",
    "para mi caso",
    "benchmarks y reviews",
    "benchmarks y comentarios",
    "relacion precio/rendimiento",
    "relación precio/rendimiento",
    "relacion rendimiento/precio",
    "relación rendimiento/precio",
    "comentarios de usuarios",
    "opiniones de usuarios",
    "cuantos fps",
    "cuántos fps",
    "vale la pena",
    "profundiza",
    "comparativa detallada",
    "analisis en detalle",
    "análisis en detalle",
)


class Planner:
    """Builds a minimal execution plan for an AIIntent."""

    def research_plan(self, intent: AIIntent, *, products_available: bool, has_spec_gaps: bool, wants_external: bool) -> ResearchBudget | None:
        """Choose how much external research a query merits (cost control).

        Returns ``None`` when external research should not run at all.
        Escalation: no identity/catalog data → skip; explicit external request
        or spec gaps → standard/deep; complete catalog → minimal or skip.
        """
        if not products_available or intent.intent not in _RESEARCHABLE_KINDS:
            return None
        if wants_external:
            return ResearchBudget(
                profile=RESEARCH_DEEP if has_spec_gaps else RESEARCH_STANDARD,
                max_queries=3 if has_spec_gaps else 2,
                max_sources=5 if has_spec_gaps else 3,
                max_documents=3 if has_spec_gaps else 2,
                reason="solicitud explícita de información externa" + (" con huecos de especificaciones" if has_spec_gaps else ""),
            )
        if has_spec_gaps:
            return ResearchBudget(
                profile=RESEARCH_STANDARD,
                max_queries=2,
                max_sources=3,
                max_documents=2,
                reason="catálogo incompleto; investigación complementaria",
            )
        return ResearchBudget(
            profile=RESEARCH_CATALOG_ONLY,
            max_queries=0,
            max_sources=1,
            max_documents=1,
            reason="catálogo suficiente; sin llamadas externas",
        )

    def decide_research(
        self,
        intent: AIIntent,
        *,
        products_available: bool,
        has_spec_gaps: bool,
        wants_external: bool,
        message: str = "",
    ) -> ResearchDecision | None:
        """V4 policy: deterministic, message-aware research escalation.

        Unlike :meth:`research_plan` (kept for backward compatibility), this
        decision separates three orthogonal signals:

        * ``has_spec_gaps`` — the catalog alone cannot answer;
        * ``wants_external`` — the user explicitly asked for out-of-catalog data;
        * ``message`` — lexical depth: "investiga", multiple topics, etc.

        RESEARCH_DEEP is reached either through explicit wording or a broad
        question (several distinct topics) that requires multiple external
        sources. Budgets come from settings and are always bounded.
        """
        if not products_available or intent.intent not in _RESEARCHABLE_KINDS:
            return None

        deep = self._is_deep(message)
        if wants_external or has_spec_gaps or deep:
            if deep or has_spec_gaps:
                return self._decision(
                    RESEARCH_DEEP,
                    depth=ResearchDepth.DEEP,
                    queries=settings.research_deep_max_queries,
                    sources=settings.research_deep_max_sources,
                    documents=settings.research_deep_max_documents,
                    reason="investigación en profundidad solicitada" if deep else "catálogo insuficiente o solicitud externa con huecos",
                )
            return self._decision(
                RESEARCH_STANDARD,
                depth=ResearchDepth.LIGHT,
                queries=settings.research_light_max_queries,
                sources=settings.research_light_max_sources,
                documents=settings.research_light_max_documents,
                reason="solicitud explícita de información externa",
            )

        return ResearchDecision(
            mode=RESEARCH_CATALOG_ONLY,
            depth=ResearchDepth.NONE,
            max_queries=0,
            max_sources=1,
            max_documents=1,
            use_rag=True,
            use_external=False,
            reason="catálogo o RAG suficientes; sin llamadas externas",
        )

    def _is_deep(self, message: str) -> bool:
        low = (message or "").lower()
        if any(term in low for term in _DEEP_TERMS):
            return True
        return len(detect_topics(message)) >= 2

    @staticmethod
    def _decision(
        mode: str,
        *,
        depth: ResearchDepth,
        queries: int,
        sources: int,
        documents: int,
        reason: str,
    ) -> ResearchDecision:
        queries = max(0, min(queries, settings.max_research_queries))
        sources = max(0, min(sources, settings.max_research_sources))
        documents = max(0, min(documents, settings.max_research_documents))
        return ResearchDecision(
            mode=mode,
            depth=depth,
            max_queries=queries,
            max_sources=sources,
            max_documents=documents,
            use_rag=True,
            use_external=True,
            reason=reason,
        )

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