"""Orchestrator ↔ RAG integration: KB-first research and web-service persistence."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.evidence import Evidence, EvidenceKind, KnowledgeSourceType
from app.ai.orchestrator import AIOrchestrator
from app.ai.providers.base import LLMProvider, ProviderResponse
from app.ai.rag import KnowledgeStore, TTLCache
from app.ai.research.chunking import ResearchDocument
from app.ai.research.schemas import ResearchReport, ResearchTarget, SearchResult
from app.ai.research.web_research_service import WebResearchService
from app.ai.schemas.chat import ChatTurn
from app.core.security import AuthenticatedUser
from app.db import Base
from app.models.catalog import Category, Product, Store, StoreOffer
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeSource

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


@dataclass
class FakeProvider(LLMProvider):
    initial: ProviderResponse
    final: ProviderResponse = field(default_factory=lambda: ProviderResponse(text="Respuesta final."))
    received_message: str | None = None

    def request_tools(self, message: str, tools: list[dict]) -> ProviderResponse:
        self.received_message = message
        return self.initial

    def generate_final(self, message: str, initial: ProviderResponse, tool_outputs: list[dict]) -> ProviderResponse:
        return self.final


class CountingResearchService:
    def __init__(self):
        self.calls = 0

    def research(self, targets: list[ResearchTarget], message: str = "") -> ResearchReport:
        self.calls += 1
        return ResearchReport(used=True, evidence=[], queries_run=1, note="debería haberse evitado")


class RecordingSearch:
    def __init__(self, results: list[SearchResult]):
        self.calls = 0
        self._results = results

    def search(self, query: str, *, max_results: int = 5, timeout_seconds: float = 10.0):
        self.calls += 1
        return self._results


class RecordingRetriever:
    def __init__(self, content: str):
        self.retrieved: list[str] = []
        self._content = content

    def retrieve(self, url: str, *, needles=(), timeout_seconds: float = 10.0):
        self.retrieved.append(url)
        return ResearchDocument(id=url, title="Fuente", content=self._content, source_url=url, source_name="fuente")


def _clean():
    with TestingSession() as db:
        db.execute(delete(KnowledgeChunk))
        db.execute(delete(KnowledgeDocument))
        db.execute(delete(KnowledgeSource))
        db.execute(delete(StoreOffer))
        db.execute(delete(Product))
        db.execute(delete(Category))
        db.execute(delete(Store))
        db.commit()


def add_products() -> tuple[int, int]:
    with TestingSession() as db:
        category = Category(name="smartphone", slug="smartphone")
        store = Store(name="Tienda", domain="tienda.test")
        db.add(category)
        db.add(store)
        db.flush()
        first = Product(name="POCO X6 5G", brand="Xiaomi", model="POCO X6", category_entity=category)
        second = Product(name="iPhone 15", brand="Apple", model="iPhone 15", category_entity=category)
        db.add(first)
        db.add(second)
        db.flush()
        db.add(StoreOffer(product=first, store=store, url="https://tienda.test/poco", price=299990))
        db.add(StoreOffer(product=second, store=store, url="https://tienda.test/iphone", price=999990))
        db.commit()
        return first.id, second.id


def active_history(ids: tuple[int, int]) -> list[ChatTurn]:
    return [
        ChatTurn(
            role="assistant",
            content="Estas son las opciones.",
            products=[{"id": ids[0], "name": "POCO X6 5G"}, {"id": ids[1], "name": "iPhone 15"}],
        )
    ]


def test_web_research_service_caches_queries_and_persists_kb():
    _clean()
    store = KnowledgeStore.from_settings(TestingSession())
    search = RecordingSearch([SearchResult(title="POCO X6 5G Geekbench 6, resultados Single-Core", url="https://example.com/source", snippet="dato")])
    service = WebResearchService(
        search,
        RecordingRetriever(content="La Geekbench 6 Single-Core 1521 confirma el buen rendimiento de la CPU."),
        cache=TTLCache(ttl_seconds=60),
        store=store,
        max_queries=1,
        max_sources=1,
        max_documents=1,
    )
    target = ResearchTarget(id=0, name="POCO X6 5G", brand="Xiaomi", model="POCO X6", specs={})
    first = service.research([target], "decime los benchmarks")
    second = service.research([target], "decime los benchmarks")
    assert first.used
    assert second.used
    assert search.calls == 1  # second pass hit the TTL cache
    assert store.document_count() >= 1


def test_web_research_service_blocks_private_urls():
    _clean()
    private = SearchResult(title="Modelo-5000 specs privadas", url="http://127.0.0.1:8000/admin", snippet="no")
    public = SearchResult(title="Modelo-5000 review oficial", url="https://example.com/pg", snippet="dato publico")
    retriever = RecordingRetriever(content="dato publico sobre el producto")
    service = WebResearchService(
        RecordingSearch([private, public]),
        retriever,
        max_queries=1,
        max_sources=2,
        max_documents=2,
    )
    report = service.research([ResearchTarget(id=0, name="M", brand="B", model="Modelo-5000", specs={})], "información externa")
    assert all(item.source_url != private.url for item in report.evidence)
    assert any(item.source_url == public.url for item in report.evidence)
    assert private.url not in retriever.retrieved


def test_orchestrator_prefers_knowledge_base_over_web_research():
    _clean()
    ids = add_products()

    with TestingSession() as db:
        store = KnowledgeStore.from_settings(db)
        store.upsert_document(
            url="https://browser.geekbench.com/poco-x6",
            title="Geekbench 6 POCO X6",
            content="Geekbench 6 Single-Core 1521, Multi-Core 5412 para el POCO X6 5G con Snapdragon 7s.",
            document_type="benchmark",
            source_name="Geekbench",
            source_type="benchmark",
            product_id=ids[0],
            brand="Xiaomi",
            model="POCO X6",
        )
        db.commit()

    research_service = CountingResearchService()
    provider = FakeProvider(initial=ProviderResponse(text="Te resumo los benchmarks encontrados."))
    orchestrator = AIOrchestrator(TestingSession(), AuthenticatedUser(id="user-one"), provider, research_service=research_service)
    response = orchestrator.chat("compará estas opciones y decime sus benchmarks", history=active_history(ids))
    assert research_service.calls == 0  # KB answered first; web research skipped
    assert response.research is True
    assert response.sources
    assert response.evidence
    assert any(item["stage"] == "rag" for item in (response.trace or []))
    assert response.need_clarification is False


def test_orchestrator_uses_web_plus_persists_when_kb_is_empty():
    _clean()
    ids = add_products()

    db = TestingSession()
    store = KnowledgeStore.from_settings(db)
    service = WebResearchService(
        RecordingSearch([SearchResult(title="POCO X6 5G review: rendimiento", url="https://example.com/review", snippet="dato")]),
        RecordingRetriever(content="El POCO X6 5G ofrece buen rendimiento frente a la generación anterior."),
        cache=TTLCache(ttl_seconds=60),
        store=store,
        max_queries=1,
        max_sources=1,
        max_documents=1,
    )
    provider = FakeProvider(initial=ProviderResponse(text="Resumen sin tools."))
    orchestrator = AIOrchestrator(db, AuthenticatedUser(id="user-one"), provider, research_service=service)
    response = orchestrator.chat("compará estas opciones y decime sus reviews", history=active_history(ids))
    assert response.research is True
    assert response.sources
    with TestingSession() as db_check:
        assert db_check.query(KnowledgeDocument).count() >= 1