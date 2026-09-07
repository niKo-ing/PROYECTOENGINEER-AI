"""AI V4 — research escalation policy tests (Planner.decide_research)."""

from __future__ import annotations

from app.ai.planner import (
    RESEARCH_CATALOG_ONLY,
    RESEARCH_DEEP,
    RESEARCH_STANDARD,
    Planner,
    ResearchDepth,
)
from app.ai.schemas.intent import AIIntent, AIIntentType


def _intent(kind: AIIntentType) -> AIIntent:
    return AIIntent(intent=kind, entities=[], constraints={})


def test_price_question_stays_catalog_only():
    # PRICE_CHECK is not a researchable intent: prices come only from the catalog.
    decision = Planner().decide_research(
        _intent(AIIntentType.PRICE_CHECK),
        products_available=True,
        has_spec_gaps=False,
        wants_external=False,
        message="cuánto cuesta la RTX 5070",
    )
    assert decision is None or decision.use_external is False


def test_spec_question_catalog_only_when_complete():
    decision = Planner().decide_research(
        _intent(AIIntentType.SPECIFICATION),
        products_available=True,
        has_spec_gaps=False,
        wants_external=False,
        message="qué RAM soporta la B650E-F",
    )
    assert decision.mode == RESEARCH_CATALOG_ONLY
    assert decision.depth == ResearchDepth.NONE


def test_performance_query_escalates_to_light_research():
    decision = Planner().decide_research(
        _intent(AIIntentType.RECOMMEND),
        products_available=True,
        has_spec_gaps=False,
        wants_external=True,
        message="cómo rinde en benchmarks la RTX 5070 Ti",
    )
    assert decision.use_external is True
    assert decision.mode == RESEARCH_STANDARD
    assert decision.depth == ResearchDepth.LIGHT
    assert 0 <= decision.max_queries <= 3


def test_deep_comparison_escalates_to_deep_research_without_external_keywords():
    decision = Planner().decide_research(
        _intent(AIIntentType.COMPARE),
        products_available=True,
        has_spec_gaps=False,
        wants_external=False,
        message="compárame a fondo la 5070 Ti y la 9070 XT para mi caso de uso",
    )
    assert decision.use_external is True
    assert decision.mode == RESEARCH_DEEP
    assert decision.depth == ResearchDepth.DEEP
    assert decision.max_queries > 0
    assert decision.max_documents >= 1


def test_multi_topic_message_is_deep():
    decision = Planner().decide_research(
        _intent(AIIntentType.RECOMMEND),
        products_available=True,
        has_spec_gaps=False,
        wants_external=False,
        message="rendimiento, precio y consumo de la 7800X3D",
    )
    assert decision.depth == ResearchDepth.DEEP


def test_spec_gaps_alone_escalate_to_deep():
    decision = Planner().decide_research(
        _intent(AIIntentType.PRODUCT_DETAIL),
        products_available=True,
        has_spec_gaps=True,
        wants_external=False,
        message="datos de la B650E-F",
    )
    assert decision.use_external is True
    assert decision.depth == ResearchDepth.DEEP


def test_missing_products_or_foreign_intent_returns_none():
    planner = Planner()
    assert planner.decide_research(_intent(AIIntentType.RECOMMEND), products_available=False, has_spec_gaps=True, wants_external=True) is None
    assert planner.decide_research(_intent(AIIntentType.SEARCH), products_available=True, has_spec_gaps=True, wants_external=True) is None


def test_budgets_are_clamped_and_never_unlimited():
    decision = Planner().decide_research(
        _intent(AIIntentType.COMPARE),
        products_available=True,
        has_spec_gaps=False,
        wants_external=True,
        message="investiga en profundidad",
    )
    assert decision.max_queries >= 0
    assert decision.max_queries <= 10
    assert decision.max_sources <= 10
    assert decision.max_documents <= 10


def test_legacy_research_plan_still_backward_compatible():
    planner = Planner()
    budget = planner.research_plan(_intent(AIIntentType.PRODUCT_DETAIL), products_available=True, has_spec_gaps=True, wants_external=True)
    assert budget is not None
    assert budget.max_queries == 3
    assert budget.max_sources == 5