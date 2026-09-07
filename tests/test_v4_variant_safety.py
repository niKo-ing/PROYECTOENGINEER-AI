"""AI V4 — variant safety and multi-product retrieval over the KnowledgeStore.

Guards the two regressions the reranker/retriever changes were meant to fix:
retrieval must never surface a sibling SKU (RTX 5070 vs 5070 Ti vs Laptop) as a
hit, and a compare over two products must keep both targets in the filter.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.rag import KnowledgeStore
from app.ai.rag.embedding import LocalHashEmbeddingProvider
from app.ai.research.schemas import ResearchTarget
from app.db import Base
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeSource

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


@pytest.fixture(autouse=True)
def _isolated_tables():
    with TestingSession() as db:
        db.execute(delete(KnowledgeChunk))
        db.execute(delete(KnowledgeDocument))
        db.execute(delete(KnowledgeSource))
        db.commit()
    yield
    with TestingSession() as db:
        db.execute(delete(KnowledgeChunk))
        db.execute(delete(KnowledgeDocument))
        db.execute(delete(KnowledgeSource))
        db.commit()


def make_store(with_product_ids: bool = False) -> tuple[KnowledgeStore, dict[str, int]]:
    store = KnowledgeStore(TestingSession(), LocalHashEmbeddingProvider(dimensions=64), chunk_max_chars=400, chunk_overlap=40)
    pids = {"5070": 1, "5070ti": 2, "5070laptop": 3}
    models = {"5070": "RTX 5070", "5070ti": "RTX 5070 Ti", "5070laptop": "RTX 5070 Laptop"}
    contents = {
        "5070": "La RTX 5070 de escritorio alcanza buena puntuacion en Geekbench 6, DLSS 4 con frame generation y buen rendimiento a 4K.",
        "5070ti": "La RTX 5070 Ti de escritorio rinde fuerte en raster a 1440p.",
        "5070laptop": "La RTX 5070 Laptop 115W es eficiente en notebooks.",
    }
    for key, model in models.items():
        store.upsert_document(
            url=f"https://kb.test/{key}",
            title=f"NVIDIA {model}",
            content=contents[key],
            document_type="benchmark",
            source_name="NVIDIA",
            brand="NVIDIA",
            model=model,
            product_id=pids[key] if with_product_ids else None,
        )
    return store, pids


def test_sibling_models_do_not_leak_into_top_k():
    store, _ = make_store()
    hits = store.search("rendimiento 1440p de la RTX 5070 Ti", top_k=3)
    assert hits
    top_model = hits[0].model or hits[0].title or ""
    assert "ti" in top_model.casefold(), f"expected RTX 5070 Ti on top, got {top_model!r}"


def test_laptop_variant_never_beats_desktop_under_desktop_query():
    store, _ = make_store()
    hits = store.search("escritorio 5070 4k geekbench", top_k=3)
    assert hits
    top_model = (hits[0].model or hits[0].title or "").casefold()
    assert "laptop" not in top_model, f"laptop variant leaked: {top_model}"
    assert top_model == "nvidia rtx 5070" or top_model == "rtx 5070", f"expected RTX 5070, got {top_model}"


def test_model_filter_scopes_retrieval_to_one_variant():
    store, _ = make_store()
    hits = store.search("eficiente notebooks", top_k=3, filters={"model": "RTX 5070 Laptop"})
    assert hits
    for h in hits:
        assert (h.model or h.title or "").casefold() == "rtx 5070 laptop", "leaked model"


def test_compare_query_keeps_both_product_ids_in_filter():
    store, pids = make_store(with_product_ids=True)
    filters = store._target_filters(
        [
            ResearchTarget(id=pids["5070"], name="NVIDIA RTX 5070", brand="NVIDIA", model="RTX 5070", category="gpu"),
            ResearchTarget(id=pids["5070ti"], name="NVIDIA RTX 5070 Ti", brand="NVIDIA", model="RTX 5070 Ti", category="gpu"),
        ]
    )
    assert filters.get("product_ids") == sorted([pids["5070"], pids["5070ti"]]), filters
    hits = store.search("rendimiento escritorio 4k", top_k=4, filters=filters)
    found = {int((h.product_id or 0)) for h in hits if h.product_id}
    assert found == {pids["5070"], pids["5070ti"]}, f"expected both products, got {found}"


def test_single_target_still_uses_strict_product_id_filter():
    store, pids = make_store(with_product_ids=True)
    filters = store._target_filters([ResearchTarget(id=pids["5070"], name="NVIDIA RTX 5070", brand="NVIDIA", model="RTX 5070", category="gpu")])
    assert filters == {"product_id": pids["5070"]}, filters