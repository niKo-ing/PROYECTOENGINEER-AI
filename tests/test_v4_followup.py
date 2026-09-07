"""AI V4 — follow-up handling and trace-id observability.

Covers the stateless multi-turn rewrite (`_expand_follow_up`), the KB-query
augmentation with detected topics, and the request-scoped ``trace_id`` plumbed
through AITrace + ChatResponse so every reply can be correlated in logs.
"""

from __future__ import annotations

import pytest

from app.ai.observability import AITrace, new_trace_id
from app.ai.orchestrator import _expand_follow_up, _kb_query
from app.ai.research.schemas import ResearchTarget
from app.ai.schemas.chat import ChatTurn, ChatResponse
from app.ai.conversation_state import ConversationState


def test_expand_follow_up_prepends_last_user_turn():
    state = ConversationState(turns=[
        ChatTurn(role="user", content="compara la RTX 5070 con la 5070 Ti"),
        ChatTurn(role="assistant", content="La RTX 5070 Ti es más rápida a 1440p."),
        ChatTurn(role="user", content="¿y cuál consume más?"),
    ])
    rewritten = _expand_follow_up("¿y cuál consume más?", state)
    assert rewritten.startswith("compara la RTX 5070 con la 5070 Ti")
    assert "consume más" in rewritten


def test_expand_follow_up_returns_message_when_no_history():
    state = ConversationState(turns=[])
    assert _expand_follow_up("¿y cuál consume más?", state) == "¿y cuál consume más?"


def test_expand_follow_up_ignores_repeated_same_turn():
    state = ConversationState(turns=[ChatTurn(role="user", content="hola")])
    assert _expand_follow_up("hola", state) == "hola"


def test_kb_query_injects_target_identity_and_topic_mapping():
    target = ResearchTarget(id=1, name="RTX 5070 Ti", brand="NVIDIA", model="RTX 5070 Ti", category="gpu")
    assert _kb_query("cuánto consume", [target], topics=["consumo"]) == "cuánto consume NVIDIA RTX 5070 Ti power"


def test_new_trace_ids_are_unique_and_hex():
    ids = {new_trace_id() for _ in range(100)}
    assert len(ids) == 100
    for trace_id in ids:
        assert len(trace_id) == 16
        int(trace_id, 16)  # must parse as hex


def test_aitrace_holds_request_scope_trace_id():
    trace = AITrace(producer="orchestrator")
    trace.step("intent", {"intent": "compare"})
    summary = trace.summary()
    assert summary["trace_id"] == trace.trace_id
    assert summary["stages"] == ["intent"]


def test_chat_response_plumb_trace_id():
    response = ChatResponse(answer="ok", trace_id="deadbeef12345678")
    assert response.trace_id == "deadbeef12345678"