"""Tests for the research escalation planner and the Recommendation extensions."""

from __future__ import annotations

from app.ai.planner import RESEARCH_CATALOG_ONLY, RESEARCH_DEEP, RESEARCH_STANDARD, Planner
from app.ai.recommendation import RecommendationEngine
from app.ai.schemas.intent import AIIntent, AIIntentType


def _intent(kind, **constraints) -> AIIntent:
    return AIIntent(intent=kind, constraints=constraints)


def test_research_plan_skips_without_products_or_non_researchable_intent():
    planner = Planner()
    assert planner.research_plan(_intent(AIIntentType.RECOMMEND), products_available=False, has_spec_gaps=True, wants_external=False) is None
    assert planner.research_plan(_intent(AIIntentType.SEARCH), products_available=True, has_spec_gaps=True, wants_external=False) is None
    assert planner.research_plan(_intent(AIIntentType.GENERAL_QUESTION), products_available=True, has_spec_gaps=True, wants_external=True) is None


def test_research_plan_catalog_only_when_sufficient():
    planner = Planner()
    budget = planner.research_plan(_intent(AIIntentType.RECOMMEND), products_available=True, has_spec_gaps=False, wants_external=False)
    assert budget is not None
    assert budget.profile == RESEARCH_CATALOG_ONLY
    assert budget.max_queries == 0  # no external calls needed


def test_research_plan_standard_when_spec_gaps():
    planner = Planner()
    budget = planner.research_plan(_intent(AIIntentType.COMPARE), products_available=True, has_spec_gaps=True, wants_external=False)
    assert budget.profile == RESEARCH_STANDARD
    assert budget.max_queries == 2


def test_research_plan_deep_on_explicit_external_request_with_gaps():
    planner = Planner()
    budget = planner.research_plan(_intent(AIIntentType.PRODUCT_DETAIL), products_available=True, has_spec_gaps=True, wants_external=True)
    assert budget.profile == RESEARCH_DEEP
    assert budget.max_queries == 3


def test_recommendation_exposes_confidence_unknowns_and_evidence():
    products = [
        {"id": 1, "name": "A", "lowest_price": 300, "rating": 4.0, "specs": {"ram": "8 GB", "bateria": "4000 mAh"}},
        {"id": 2, "name": "B", "lowest_price": 500, "rating": 4.5, "specs": {"ram": "12 GB", "bateria": "5000 mAh"}},
    ]
    recommendation = RecommendationEngine().recommend(products, constraints={"use_case": {"battery": "high"}}, objective=True)
    data = recommendation.as_dict()
    assert isinstance(data["confidence"], float)
    assert 0.0 <= data["confidence"] <= 0.95
    assert "evidence" in data
    assert "unknowns" in data
    assert recommendation.winner_id is not None


def test_recommendation_confidence_lower_when_unknowns():
    products = [
        {"id": 1, "name": "A", "lowest_price": 300},
        {"id": 2, "name": "B", "lowest_price": 500},
    ]
    recommendation = RecommendationEngine().recommend(products, objective=True)
    assert recommendation.unknowns  # price-limited common specs with no data
    assert recommendation.confidence < 0.95