"""End-to-end orchestrator integration with the Web Research layer.

Verifies gating: research runs only on catalog gaps or explicit external
requests, never otherwise (``research_calls = 0`` default). Uses a fake
research service so no network is involved.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.evidence import Evidence, EvidenceKind, KnowledgeSourceType
from app.ai.orchestrator import AIOrchestrator
from app.ai.providers.base import LLMProvider, ProviderResponse
from app.ai.research.schemas import ResearchReport, ResearchTarget
from app.ai.schemas.chat import ChatTurn
from app.core.security import AuthenticatedUser
from app.db import Base
from app.models.catalog import Category, CategorySpecificationDefinition, Product, ProductSpecValue, Store, StoreOffer

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


@dataclass
class FakeProvider(LLMProvider):
    initial: ProviderResponse
    final: ProviderResponse = field(default_factory=lambda: ProviderResponse(text="Respuesta final."))
    outputs: list[dict] = field(default_factory=list)
    received_message: str | None = None

    def request_tools(self, message: str, tools: list[dict]) -> ProviderResponse:
        self.received_message = message
        return self.initial

    def generate_final(self, message: str, initial: ProviderResponse, tool_outputs: list[dict]) -> ProviderResponse:
        self.outputs = tool_outputs
        return self.final


class FakeResearchService:
    def __init__(self):
        self.called_with: tuple[list[ResearchTarget], str] | None = None

    def research(self, targets: list[ResearchTarget], message: str = "") -> ResearchReport:
        self.called_with = (targets, message)
        return ResearchReport(
            used=True,
            evidence=[
                Evidence(
                    source_type=KnowledgeSourceType.BENCHMARK,
                    source_name="Geekbench",
                    source_url="https://browser.geekbench.com/x",
                    title="Geekbench 6",
                    content="Geekbench 6 Single-Core 1521, Multi-Core 5412",
                    confidence=0.8,
                    kind=EvidenceKind.EXTRACTED,
                )
            ],
            verdicts=[],
            queries_run=2,
            context="[Evidencia externa recopilada — usala SOLO como apoyo]",
        )


def add_products(*, with_specs: bool) -> tuple[int, int]:
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
        if with_specs:
            ram_def = CategorySpecificationDefinition(key="ram", label="RAM", group="Memoria", category_id=category.id)
            db.add(ram_def)
            db.flush()
            db.add(ProductSpecValue(product=first, definition=ram_def, value_kind="number", value_number=12, unit="GB", raw_value="12 GB", value_text="12 GB", source_type="ai", verification_status="review"))
            db.add(ProductSpecValue(product=second, definition=ram_def, value_kind="number", value_number=8, unit="GB", raw_value="8 GB", value_text="8 GB", source_type="ai", verification_status="review"))
        db.add(StoreOffer(product=first, store=store, url="https://tienda.test/poco", price=299990))
        db.add(StoreOffer(product=second, store=store, url="https://tienda.test/iphone", price=999990))
        db.commit()
        db.refresh(first)
        db.refresh(second)
        return first.id, second.id


def build_orchestrator(provider: FakeProvider, research_service: FakeResearchService) -> AIOrchestrator:
    db = TestingSession()
    return AIOrchestrator(db, AuthenticatedUser(id="user-one"), provider, research_service=research_service)


def reset_database():
    with TestingSession() as db:
        db.execute(delete(StoreOffer))
        db.execute(delete(ProductSpecValue))
        db.execute(delete(Product))
        db.execute(delete(CategorySpecificationDefinition))
        db.execute(delete(Category))
        db.execute(delete(Store))
        db.commit()


def active_history(ids: tuple[int, int]) -> list[ChatTurn]:
    return [
        ChatTurn(role="assistant", content="Estas son las opciones.", products=[{"id": ids[0], "name": "POCO X6 5G"}, {"id": ids[1], "name": "iPhone 15"}])
    ]


def test_research_attached_to_response_when_external_requested():
    reset_database()
    ids = add_products(with_specs=False)
    provider = FakeProvider(initial=ProviderResponse(text="Te comparo las opciones."))
    research_service = FakeResearchService()
    orc = build_orchestrator(provider, research_service)
    response = orc.chat(
        "compará estas opciones y decime sus benchmarks",
        history=active_history(ids),
    )
    assert response.research is True
    assert response.sources
    assert response.sources[0]["source_type"] == "benchmark"
    assert research_service.called_with is not None
    targets, message = research_service.called_with
    assert any(target.id in ids for target in targets)
    assert "benchmark" in message


def test_research_not_triggered_when_catalog_is_complete():
    reset_database()
    ids = add_products(with_specs=True)
    provider = FakeProvider(initial=ProviderResponse(text="Esas son las opciones."))
    research_service = FakeResearchService()
    orc = build_orchestrator(provider, research_service)
    response = orc.chat("compará estas opciones", history=active_history(ids))
    assert response.research is False
    assert response.sources == []
    assert research_service.called_with is None


def test_research_not_triggered_without_identity():
    reset_database()
    with TestingSession() as db:
        category = Category(name="notebook", slug="notebook")
        db.add(category)
        db.flush()
        product = Product(name="Notebook Genérico", category_entity=category)
        db.add(product)
        db.commit()
        product_id = product.id

    provider = FakeProvider(initial=ProviderResponse(text="Detalle."))
    research_service = FakeResearchService()
    orc = build_orchestrator(provider, research_service)
    response = orc.chat(
        "¿cuáles son sus reviews?",
        history=[ChatTurn(role="assistant", content="Opciones:", products=[{"id": product_id, "name": "Notebook Genérico"}])],
    )
    assert response.research is False
    assert research_service.called_with is None