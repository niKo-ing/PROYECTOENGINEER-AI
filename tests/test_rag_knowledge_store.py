"""Tests for the KnowledgeStore (ingestion, dedupe, hybrid retrieval, evidence)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.evidence import Evidence, EvidenceKind, KnowledgeSourceType as EvidenceSourceType
from app.ai.rag import KnowledgeStore
from app.ai.rag.embedding import LocalHashEmbeddingProvider
from app.ai.research.schemas import ResearchReport, ResearchTarget
from app.db import Base
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeSource

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _clean_tables():
    with TestingSession() as db:
        db.execute(delete(KnowledgeChunk))
        db.execute(delete(KnowledgeDocument))
        db.execute(delete(KnowledgeSource))
        db.commit()


@pytest.fixture(autouse=True)
def _isolated_tables():
    _clean_tables()
    yield
    _clean_tables()


def make_store(session=None) -> KnowledgeStore:
    return KnowledgeStore(
        session or TestingSession(),
        LocalHashEmbeddingProvider(dimensions=64),
        chunk_max_chars=400,
        chunk_overlap=40,
    )


def add_docs(store) -> None:
    store.upsert_document(
        url="https://example.com/b650e",
        title="ASUS ROG STRIX B650E-F GAMING WIFI",
        content="La ASUS ROG STRIX B650E-F GAMING WIFI soporta DDR5 hasta 8000 MT/s con perfiles EXPO. Tiene Wi-Fi 6E y un disipador VRM reforzado.",
        document_type="specifications",
        source_name="ASUS",
        source_type="manufacturer",
        domain="example.com",
        brand="ASUS",
        model="B650E-F",
    )
    store.upsert_document(
        url="https://example.com/gpu",
        title="RTX 5070 Ti review",
        content="La RTX 5070 Ti mejora el rendimiento en raster frente a la generación anterior. Consumo pico alto bajo carga.",
        document_type="review",
        source_name="TechReview",
        source_type="review",
        brand="NVIDIA",
        model="RTX 5070 Ti",
    )


def test_upsert_deduplicates_by_url_and_content_hash():
    session = TestingSession()
    store = make_store(session)
    _doc, created = store.upsert_document(
        url="https://example.com/repeat",
        title="Repeated",
        content="Contenido único del documento. " * 4,
        source_name="Fuente",
        source_type="web",
    )
    assert created is True
    _same_url, created_same_url = store.upsert_document(
        url="https://example.com/repeat",
        title="Repeated",
        content="Contenido único del documento. " * 4,
        source_name="Fuente",
        source_type="web",
    )
    assert created_same_url is False
    _same_content, created_same_content = store.upsert_document(
        url="https://example.com/other",
        title="Repeated 2",
        content="Contenido único del documento. " * 4,
        source_name="Fuente",
        source_type="web",
    )
    assert created_same_content is False
    assert store.document_count() == 1


def test_store_rejects_empty_content():
    import pytest

    store = make_store(TestingSession())
    with pytest.raises(ValueError):
        store.upsert_document(url="https://example.com/x", title="", content="   ", source_type="web")


def test_upsert_stores_chunks_and_embeddings():
    store = make_store(TestingSession())
    document, _ = store.upsert_document(
        url="https://example.com/long",
        title="Long",
        content="Texto largo con muchas palabras para generar varios fragmentos de contenido dividido. " * 40,
        source_name="Fuente",
        source_type="web",
    )
    assert len(document.chunks) > 1
    assert any(chunk.embedding is not None for chunk in document.chunks)
    assert store.chunk_count() == len(document.chunks)


def test_hybrid_search_finds_relevant_document_first():
    store = make_store(TestingSession())
    add_docs(store)
    chunks = store.search("memoria RAM DDR5 8000 EXPO", top_k=3)
    assert chunks, "should retrieve at least one chunk"
    top = chunks[0]
    assert "b650e" in top.content.casefold() or top.model == "B650E-F"


def test_search_respects_model_filter():
    store = make_store(TestingSession())
    add_docs(store)
    chunks = store.search("rendimiento grafico", top_k=3, filters={"model": "RTX 5070 Ti"})
    assert chunks
    assert all(chunk.model == "RTX 5070 Ti" for chunk in chunks)


def test_evidence_for_produces_citable_evidence():
    store = make_store(TestingSession())
    add_docs(store)
    chunks = store.search("DDR5 8000", top_k=2)
    evidence = store.evidence_for(chunks, target_model="B650E-F")
    assert evidence
    item = evidence[0]
    assert isinstance(item, Evidence)
    assert item.kind == EvidenceKind.EXTRACTED
    assert item.confidence > 0.3
    assert item.as_dict()["source_url"]


def test_ingest_research_report_is_idempotent():
    store = make_store(TestingSession())
    report = ResearchReport(
        used=True,
        evidence=[
            Evidence(
                source_type=EvidenceSourceType.BENCHMARK,
                source_name="Geekbench",
                source_url="https://browser.geekbench.com/b650e",
                title="Geekbench 6",
                content="Geekbench 6 Single-Core 1521, Multi-Core 5412",
                confidence=0.8,
                kind=EvidenceKind.EXTRACTED,
            ),
            Evidence(
                source_type=EvidenceSourceType.REVIEW,
                source_name="ReviewSite",
                source_url="https://example.com/review",
                title="Review",
                content="Buen disipador y buena conectividad frente a modelos similares.",
                confidence=0.6,
                kind=EvidenceKind.EXTRACTED,
            ),
        ],
        queries_run=2,
    )
    first = store.ingest_research_report(report, brand="ASUS", model="B650E-F")
    second = store.ingest_research_report(report, brand="ASUS", model="B650E-F")
    assert first == 2
    assert second == 0
    assert store.document_count() == 2


def test_search_research_returns_report_when_evidence_found():
    store = make_store(TestingSession())
    add_docs(store)
    report = store.search_research("asSUS placa madre ddr5", targets=[ResearchTarget(id=0, name="ASUS B650E-F", brand="ASUS", model="B650E-F")])
    assert report is not None
    assert report.used is True
    assert report.evidence
    assert report.context.startswith("[Evidencia recuperada de la knowledge base")


def test_search_research_returns_none_when_empty():
    store = make_store(TestingSession())
    assert store.search_research("no existe nada sobre esto", top_k=3) is None


def test_sources_created_with_priority():
    store = make_store(TestingSession())
    add_docs(store)
    session = store.db
    manufacturer = session.query(KnowledgeSource).filter_by(source_type="manufacturer").one()
    catalog = session.query(KnowledgeSource).filter_by(source_type="catalog").first()
    assert manufacturer.priority == 50
    assert catalog is None


def test_store_from_settings_builds_offline_store():
    store = KnowledgeStore.from_settings(TestingSession())  # default provider is local/offline
    assert store.provider.provider_name() == "local_hash"
    assert store._top_k > 0