from datetime import datetime, timedelta, timezone

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.memory import LongTermMemory, summarize_dropped, window_messages
from app.ai.rag.embedding import EmbeddingError, LocalHashEmbeddingProvider
from app.models.agent import AgentMemory

from agent_support import ConceptEmbedder


def test_semantic_search_finds_meaning_without_shared_words(db):
    memory = LongTermMemory(db, "u1", ConceptEmbedder())
    memory.add("Prefiero notebooks baratos para la universidad", kind="preference")
    memory.add("Nunca compro Huawei", kind="preference")
    memory.add("Mi consola favorita es la Switch", kind="fact")
    hits = memory.search("busco un laptop económico para estudiar")
    assert hits and "notebooks baratos" in hits[0].content
    assert all("Huawei" not in h.content for h in hits)


def test_core_memory_returns_only_important_preferences_and_recall_merges_it(db):
    memory = LongTermMemory(db, "u1", LocalHashEmbeddingProvider())
    memory.add("Nunca compro Huawei", importance=5)
    memory.add("Me gustan los colores oscuros", importance=2)
    memory.add("Tarea: busqué un notebook", kind="episode", importance=5)
    assert [h.content for h in memory.core()] == ["Nunca compro Huawei"]
    recalled = memory.recall("notebook")
    assert recalled[0].content == "Nunca compro Huawei"
    assert len({h.id for h in recalled}) == len(recalled)


def test_exact_duplicate_is_not_stored_twice_but_refreshes_importance(db):
    memory = LongTermMemory(db, "u1", LocalHashEmbeddingProvider())
    first, created = memory.add("Prefiero Samsung", importance=2)
    again, created_again = memory.add("  prefiero   samsung ", importance=5)
    assert created and not created_again
    assert first.id == again.id and again.importance == 5
    assert len(memory.all()) == 1


def test_repeating_a_task_updates_its_episode_instead_of_piling_up_copies(db):
    memory = LongTermMemory(db, "u1", LocalHashEmbeddingProvider())
    goal = "Quiero un celular Samsung o Xiaomi, presupuesto $320.000"
    first, created = memory.upsert_episode(goal, f"Tarea: {goal} → Resultado: Galaxy A57 a $299.990")
    second, created_again = memory.upsert_episode(goal, f"Tarea: {goal} → Resultado: Redmi Note 15 Pro a $309.990")
    assert created and not created_again
    assert first.id == second.id
    assert len(memory.all()) == 1
    assert "Redmi Note 15 Pro" in memory.all()[0].content  # quedó el resultado más reciente
    memory.upsert_episode("Revisa mis alertas", "Tarea: Revisa mis alertas → Resultado: sin alertas")
    assert len(memory.all()) == 2  # otra tarea sí es otro episodio


def test_episodes_of_different_users_are_not_merged(db):
    goal = "Quiero un celular"
    LongTermMemory(db, "alice", LocalHashEmbeddingProvider()).upsert_episode(goal, f"Tarea: {goal} → Resultado: A")
    LongTermMemory(db, "bob", LocalHashEmbeddingProvider()).upsert_episode(goal, f"Tarea: {goal} → Resultado: B")
    assert len(LongTermMemory(db, "alice", LocalHashEmbeddingProvider()).all()) == 1
    assert len(LongTermMemory(db, "bob", LocalHashEmbeddingProvider()).all()) == 1


def test_near_duplicate_is_merged_by_embedding_similarity(db):
    memory = LongTermMemory(db, "u1", ConceptEmbedder())
    memory.add("Prefiero notebooks baratos")
    _, created = memory.add("Quiero un laptop económico")  # mismos conceptos, otras palabras
    assert not created
    assert len(memory.all()) == 1


def test_memories_are_isolated_per_user(db):
    LongTermMemory(db, "alice", LocalHashEmbeddingProvider()).add("Prefiero Samsung")
    assert LongTermMemory(db, "bob", LocalHashEmbeddingProvider()).search("Samsung") == []


def test_importance_and_recency_break_ties(db):
    memory = LongTermMemory(db, "u1", ConceptEmbedder())
    old, _ = memory.add("Evito Huawei para celular", importance=2)
    old.created_at = datetime.now(timezone.utc) - timedelta(days=400)
    db.commit()
    new, _ = memory.add("Odio Samsung para celular", importance=5)
    hits = memory.search("celular", k=2)
    assert [h.id for h in hits] == [new.id, old.id]


def test_provider_switch_reembeds_lazily(db):
    LongTermMemory(db, "u1", LocalHashEmbeddingProvider()).add("Prefiero notebooks baratos")
    switched = LongTermMemory(db, "u1", ConceptEmbedder())
    assert switched.search("laptop económico")
    row = db.query(AgentMemory).one()
    assert row.embedding_provider == "concept_test"


def test_keyword_fallback_when_embeddings_fail(db):
    class Broken:
        def provider_name(self):
            return "broken"

        def embed_text(self, text, *, model=None):
            raise EmbeddingError("sin red")

    memory = LongTermMemory(db, "u1", Broken())
    memory.add("Prefiero Samsung para celulares")
    hits = memory.search("celulares Samsung")
    assert hits and "Samsung" in hits[0].content


def test_invalid_input_is_rejected(db):
    memory = LongTermMemory(db, "u1", LocalHashEmbeddingProvider())
    with pytest.raises(ValueError):
        memory.add("   ")
    with pytest.raises(ValueError):
        memory.add("algo", kind="rumor")


def convo(n_rounds):
    msgs = []
    for i in range(n_rounds):
        msgs.append(HumanMessage(f"pedido {i}"))
        msgs.append(AIMessage(content="", tool_calls=[{"name": "search_products", "args": {}, "id": f"c{i}"}]))
        msgs.append(ToolMessage(content="{}", tool_call_id=f"c{i}", name="search_products"))
        msgs.append(AIMessage(content=f"respuesta {i}"))
    return msgs


def test_short_history_is_untouched():
    msgs = convo(2)
    dropped, window = window_messages(msgs, 24)
    assert dropped == [] and window == msgs


def test_window_never_starts_with_orphan_tool_message_and_keeps_last_human():
    msgs = convo(10)
    dropped, window = window_messages(msgs, 7)
    assert not isinstance(window[0], ToolMessage)
    assert any(isinstance(m, HumanMessage) and m.content == "pedido 9" for m in window)
    assert len(dropped) + len(window) == len(msgs)


def test_window_keeps_the_current_turn_even_if_it_is_longer_than_the_limit():
    msgs = [HumanMessage("viejo"), AIMessage(content="ok"), HumanMessage("actual")]
    for i in range(6):
        msgs.append(AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": f"k{i}"}]))
        msgs.append(ToolMessage(content="{}", tool_call_id=f"k{i}", name="t"))
    _, window = window_messages(msgs, 4)
    assert window[0].content == "actual"


def test_summary_mentions_requests_and_tools_but_not_answers():
    dropped, _ = window_messages(convo(10), 7)
    summary = summarize_dropped(dropped)
    assert "pedido 8" in summary and "search_products" in summary  # conserva lo más reciente de lo descartado
    assert "respuesta" not in summary
    assert summarize_dropped([]) == ""
