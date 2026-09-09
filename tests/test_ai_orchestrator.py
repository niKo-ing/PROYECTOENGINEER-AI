"""Test suite for the conversational AI orchestrator (SOLOTODO AI V2).

Covers: intent detection, entity resolution, conversation state / anaphora,
price constraints, compare enrichment, recommendation engine and the end-to-end
orchestrator path with a mocked LLM provider (no real Gemini calls).
"""

from dataclasses import dataclass, field

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.conversation_state import ConversationState, reference_indices
from app.ai.entity_resolution import EntityResolver
from app.ai.intent import detect_intent, parse_price_clp
from app.ai.providers.base import LLMProvider, ProviderResponse
from app.ai.recommendation import RecommendationEngine
from app.ai.schemas.chat import ChatTurn
from app.ai.schemas.intent import AIIntentType
from app.core.security import AuthenticatedUser, get_current_user
from app.db import Base, get_db
from app.main import app
from app.models.catalog import Category, CategorySpecificationDefinition, Product, ProductSpecValue, Store, StoreOffer
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeSource
from app.models.user_profile import UserProfile

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine)
Base.metadata.create_all(engine)
client = TestClient(app)


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


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


def set_context(provider: LLMProvider):
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id="user-one")
    app.dependency_overrides.pop("llm_provider", None)
    from app.ai.providers.factory import get_llm_provider

    app.dependency_overrides[get_llm_provider] = lambda: provider


def reset_database():
    app.dependency_overrides[get_db] = override_get_db
    with TestingSession() as db:
        db.execute(delete(KnowledgeChunk))
        db.execute(delete(KnowledgeDocument))
        db.execute(delete(KnowledgeSource))
        db.execute(delete(UserProfile))
        db.execute(delete(StoreOffer))
        db.execute(delete(ProductSpecValue))
        db.execute(delete(Product))
        db.execute(delete(CategorySpecificationDefinition))
        db.execute(delete(Category))
        db.execute(delete(Store))
        db.commit()


def add_product(name: str, price: int, brand: str | None = None, ram: int | None = None, rating: float = 4.2) -> int:
    with TestingSession() as db:
        category = db.scalar(select(Category).where(Category.slug == "smartphone")) or Category(name="smartphone", slug="smartphone")
        db.add(category)
        db.flush()
        store = Store(name=f"Tienda {name}", domain=f"{name.lower().replace(' ', '-').replace('.', '')}.test")
        product = Product(name=name, brand=brand, category_entity=category, rating=rating)
        db.add(product)
        db.flush()
        if ram is not None:
            ram_def = db.scalar(select(CategorySpecificationDefinition).where(CategorySpecificationDefinition.key == "ram")) or CategorySpecificationDefinition(
                key="ram", label="RAM", group="Memoria", category_id=category.id
            )
            db.add(ProductSpecValue(product=product, definition=ram_def, value_kind="number", value_number=ram, unit="GB", raw_value=f"{ram} GB", value_text=f"{ram} GB", source_type="ai", verification_status="review"))
        db.add(StoreOffer(product=product, store=store, url=f"https://{store.domain}/producto", price=price))
        db.commit()
        db.refresh(product)
        return product.id


def active_state(products: list[dict]) -> ConversationState:
    return ConversationState.build([ChatTurn(role="assistant", content="Te muestro las opciones.", products=products)])


# ── Intent detection ────────────────────────────────────────────────────

def test_intent_detection_basic_cases():
    assert detect_intent("busco un iphone").intent == AIIntentType.SEARCH
    assert detect_intent("comparalas").intent == AIIntentType.COMPARE
    assert detect_intent("dame el precio").intent == AIIntentType.PRICE_CHECK
    assert detect_intent("hola").intent == AIIntentType.GENERAL_QUESTION


def test_intent_detection_bare_catalog_nouns_search():
    for message in ("telefonos", "telefono", "celulares", "notebooks", "gpu", "tarjeta grafica", "samsung"):
        assert detect_intent(message).intent == AIIntentType.SEARCH, f"{message!r} debería ser SEARCH"
    for greeting in ("hola", "buenas", "gracias"):
        assert detect_intent(greeting).intent == AIIntentType.GENERAL_QUESTION, f"{greeting!r} debería ser GENERAL_QUESTION"


def test_intent_detection_follow_ups_need_active_products():
    plain = detect_intent("comparalas")
    assert plain.intent != AIIntentType.COMPARE or not plain.constraints

    state = active_state([{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])
    assert detect_intent("comparalas", state).intent == AIIntentType.COMPARE
    assert detect_intent("¿cuál es mejor?", state).intent == AIIntentType.RECOMMEND
    assert detect_intent("y contra un poco", state).intent == AIIntentType.COMPARE


def test_intent_detection_use_case_and_price_constraints():
    gaming = detect_intent("quiero algo para jugar")
    assert gaming.constraints["use_case"]["gaming"]

    price = detect_intent("menos de 500 lucas")
    assert price.constraints["max_price"] == 500000

    combined = detect_intent("un celu para jugar de menos de 300 lucas")
    assert combined.constraints["max_price"] == 300000
    assert "gaming" in combined.constraints["use_case"]


# ── Price constraints ───────────────────────────────────────────────────

def test_price_constraint_parsing():
    assert parse_price_clp("menos de 500 lucas") == 500000
    assert parse_price_clp("500 mil") == 500000
    assert parse_price_clp("500.000") == 500000
    assert parse_price_clp("500000") == 500000
    assert parse_price_clp("presupuesto 1500") == 1500
    assert parse_price_clp("hola") is None


# ── Conversation state & anaphora ───────────────────────────────────────

def test_conversation_state_reconstruction():
    products = [{"id": 1, "name": "iPhone 15"}, {"id": 2, "name": "POCO X6"}]
    state = ConversationState.build(
        [
            ChatTurn(role="user", content="busco un iphone"),
            ChatTurn(role="assistant", content="Encontré estas opciones.", products=products),
        ]
    )
    assert state.active_product_ids() == [1, 2]
    assert state.has_active_products()

    anchored = ConversationState.build([], product_id=7)
    assert anchored.product_anchor_id == 7


def test_followup_reference_resolution():
    assert reference_indices("el primero", 3) == [0]
    assert reference_indices("la segunda", 3) == [1]
    assert reference_indices("esas dos", 3) == [0, 1]
    assert reference_indices("comparalas", 3) == []
    assert reference_indices("mostrame el detalle", 3) == []

    state = active_state([{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])
    assert detect_intent("ese tiene mejor pantalla", state).intent == AIIntentType.FOLLOW_UP


# ── Entity resolution ───────────────────────────────────────────────────

def test_entity_resolution_resolves_brand_and_family():
    reset_database()
    add_product("iPhone 15 Pro", 999990, brand="Apple", ram=8)
    add_product("POCO X6 5G", 299990, brand="POCO", ram=12)

    context = active_state([{"id": 1, "name": "iPhone 15 Pro"}])
    intent = detect_intent("y contra un poco", context)
    with TestingSession() as db:
        resolution = EntityResolver(db).resolve_intent("y contra un poco", intent, context)

    names = [candidate.name for candidate in resolution.candidates]
    assert any("POCO" in name for name in names)
    assert resolution.resolved == [] or all(product.name == "iPhone 15 Pro" for product in resolution.resolved)


# ── Compare & recommendation engine ─────────────────────────────────────

def test_recommendation_engine_winner_and_tradeoffs():
    products = [
        {"id": 1, "name": "Gamer 16", "lowest_price": 899990, "rating": 4.5, "specs": {"RAM": "16 GB", "Almacenamiento": "512 GB"}},
        {"id": 2, "name": "Económico 8", "lowest_price": 399990, "rating": 4.1, "specs": {"RAM": "8 GB", "Almacenamiento": "256 GB"}},
    ]
    objective = RecommendationEngine().recommend(products, objective=True)
    assert objective.winner_id == 1
    assert "RAM" in objective.criteria
    assert objective.winner_reason is not None

    constrained = RecommendationEngine().recommend(products, constraints={"max_price": 500000})
    assert constrained.winner_id == 2

    games = RecommendationEngine().recommend(products, constraints={"use_case": {"gaming": "high"}}, objective=False)
    assert games.advantages is not None


def test_recommendation_rationale_is_explainable():
    products = [
        {"id": 1, "name": "A", "lowest_price": 100, "rating": 4.0, "specs": {"RAM": "8 GB"}},
        {"id": 2, "name": "B", "lowest_price": 100, "rating": 4.0, "specs": {"RAM": "16 GB"}},
    ]
    rec = RecommendationEngine().recommend(products, objective=True)
    assert rec.winner_id == 2
    assert rec.rationale
    assert rec.per_criterion["RAM"]["values"]["2"] == "16 GB"


def test_compare_products_tool_is_enriched():
    reset_database()
    set_context(FakeProvider(initial=ProviderResponse(text="ok")))
    first = add_product("iPhone 15 Pro", 999990, brand="Apple", ram=8)
    second = add_product("POCO X6 5G", 299990, brand="POCO", ram=None)

    response = client.post("/api/v1/ai/tools", json={"tool": "compare_products", "parameters": {"product_ids": [first, second]}})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["comparison"]["dimensions"]["RAM"]["present"][str(first)] == "8 GB"
    assert data["comparison"]["dimensions"]["RAM"]["missing"] == [second]
    assert "RAM" not in data["comparison"]["common_specs"]
    assert "RAM" in data["comparison"]["missing_specs"]
    assert data["comparison"]["advantages"] is not None


# ── End-to-end orchestrator (mocked provider) ───────────────────────────

def test_orchestrator_context_preservation_follow_up_compare():
    reset_database()
    iphone = add_product("iPhone 15 Pro", 999990, brand="Apple", ram=8)
    poco = add_product("POCO X6 5G", 299990, brand="POCO", ram=12, rating=4.4)

    provider = FakeProvider(initial=ProviderResponse(text="Encontré el iPhone 15 Pro."))
    set_context(provider)
    first = client.post("/api/v1/ai/chat", json={"message": "busco un iphone"})
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["intent"] == "search"
    assert first_body["products"] and first_body["products"][0]["id"] == iphone

    history = [
        ChatTurn(role="user", content="busco un iphone"),
        ChatTurn(role="assistant", content=first_body["answer"], products=first_body["products"]),
    ]
    second = client.post(
        "/api/v1/ai/chat",
        json={"message": "y contra un poco", "history": [turn.model_dump() for turn in history]},
    )
    assert second.status_code == 200
    body = second.json()
    assert body["intent"] == "compare"
    assert body["need_clarification"] is False
    ids = {item["id"] for item in body["products"]}
    assert ids == {iphone, poco}
    assert "RAM" in body["comparison"]["dimensions"]
    assert body["comparison"]["price"][str(poco)].startswith("299990")


def test_orchestrator_recommendation_flow():
    reset_database()
    first = add_product("iPhone 15 Pro", 999990, brand="Apple", ram=8, rating=4.6)
    second = add_product("POCO X6 5G", 299990, brand="POCO", ram=12, rating=4.2)

    with TestingSession() as db:
        products = [
            {"id": first, "name": "iPhone 15 Pro"},
            {"id": second, "name": "POCO X6 5G"},
        ]

    provider = FakeProvider(initial=ProviderResponse(text="La POCO gana en RAM y vale mucho menos."))
    set_context(provider)
    response = client.post(
        "/api/v1/ai/chat",
        json={
            "message": "¿cuál es mejor?",
            "history": [ChatTurn(role="assistant", content="Estas son las opciones.", products=products).model_dump()],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "recommend"
    assert body["comparison"]["winner_id"] in {first, second}
    assert "criteria" in body["comparison"]
    assert body["comparison"]["applied_constraints"] is not None
    assert body["need_clarification"] is False


def test_orchestrator_asks_for_clarification_without_domain():
    reset_database()
    provider = FakeProvider(initial=ProviderResponse(text=""))
    set_context(provider)
    response = client.post("/api/v1/ai/chat", json={"message": "¿cuál es mejor?"})
    assert response.status_code == 200
    body = response.json()
    assert body["need_clarification"] is True
    assert body["intent"] in ("recommend", "compare")


def test_orchestrator_follow_up_compare_without_provider_tool_calls():
    """A bare follow-up ("comparalos") must surface the deterministic comparison
    even when the LLM answers without requesting tools: the final text is written
    over the real catalog products, never over a generic "which products?" line."""
    reset_database()
    first = add_product("iPhone 15 128GB", 669990, brand="Apple", ram=8)
    second = add_product("iPhone 16 128GB", 1136750, brand="Apple", ram=8)

    provider = FakeProvider(
        initial=ProviderResponse(text="Para poder comparar, necesito que me digas cuáles son."),
        final=ProviderResponse(text="El iPhone 15 128GB es más barato que el iPhone 16."),
    )
    set_context(provider)
    history = [
        ChatTurn(role="user", content="iphones"),
        ChatTurn(role="assistant", content="Encontré dos opciones.", products=[
            {"id": first, "name": "iPhone 15 128GB", "brand": "Apple", "category": "celulares", "lowest_price": 669990, "offer_count": 2},
            {"id": second, "name": "iPhone 16 128GB", "brand": "Apple", "category": "celulares", "lowest_price": 1136750, "offer_count": 1},
        ]),
    ]
    response = client.post(
        "/api/v1/ai/chat",
        json={"message": "comparalos", "history": [turn.model_dump() for turn in history]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "compare"
    assert body["need_clarification"] is False
    assert body["answer"] == "El iPhone 15 128GB es más barato que el iPhone 16."
    ids = {item["id"] for item in body["products"]}
    assert ids == {first, second}
    assert body["comparison"]["count"] == 2