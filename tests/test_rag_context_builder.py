"""Tests for the bounded AIContextBuilder."""

from __future__ import annotations

from app.ai.context_builder import AIContextBuilder, build_sectioned_prompt


def test_appends_only_non_empty_sections():
    prompt = "Pregunta"
    result = AIContextBuilder().build(prompt, [("catalog", "datos del catálogo"), ("empty", None), ("research", "")])
    assert "datos del catálogo" in result
    assert "None" not in result
    assert result.startswith(prompt)


def test_respects_token_budget_and_truncates():
    big = "palabra " * 4000
    builder = AIContextBuilder(token_limit=200, reserved_for_answer=100)
    result = builder.build("p", [("research", big)])
    assert len(result) <= len("p") + builder.budget_chars() + 128
    assert result.rstrip().endswith("…")


def test_keeps_short_sections_within_budget():
    builder = AIContextBuilder(token_limit=1000)
    result = builder.build("p", [("research", "a few. " * 10)])
    assert "a few. " in result


def test_header_labelling_of_evidence():
    result = build_sectioned_prompt(prompt="q", sections=[("catalog", "uno")], token_limit=600)
    assert "[Evidencia determinística" in result
    assert "uno" in result


def test_budget_never_negative_for_small_limits():
    builder = AIContextBuilder(token_limit=250, reserved_for_answer=240)
    assert builder.budget_chars() > 0