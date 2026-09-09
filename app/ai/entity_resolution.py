"""Entity resolution — maps mentions of products/brands/families to catalog.

Follows the order: conversation context → identity match → catalog search →
category/brand/model → fuzzy. When several reasonable candidates exist it
returns them instead of inventing a single answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ai.conversation_state import ConversationState, reference_indices
from app.ai.schemas.intent import AIIntent, AIEntityType
from app.services.product_service import ProductService


@dataclass
class ResolvedProduct:
    product_id: int
    name: str
    brand: str | None = None
    category: str | None = None
    price_clp: int | None = None
    lowest_price: int | None = None
    lowest_price_store: str | None = None
    rating: float | None = None
    offer_count: int = 0
    specs: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "id": self.product_id,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "price_clp": self.price_clp,
            "lowest_price": self.lowest_price,
            "lowest_price_store": self.lowest_price_store,
            "rating": self.rating,
            "offer_count": self.offer_count,
            "specs": self.specs,
        }


@dataclass
class EntityResolution:
    resolved: list[ResolvedProduct] = field(default_factory=list)
    candidates: list[ResolvedProduct] = field(default_factory=list)
    requires_clarification: bool = False
    messages: list[dict] = field(default_factory=list)

    @property
    def ambiguous(self) -> bool:
        return self.requires_clarification or (len(self.candidates) > 1 and not self.resolved)


def _from_product(product) -> ResolvedProduct:
    specs: dict[str, str] = {}
    sheet = getattr(product, "canonical_specs", None)
    if sheet:
        for section in sheet.get("sections") or []:
            for item in section.get("items") or []:
                label = item.get("label")
                value = item.get("value")
                if label and value:
                    specs[label] = value
    return ResolvedProduct(
        product_id=product.id,
        name=product.name,
        brand=product.brand,
        category=getattr(product, "category", None),
        price_clp=product.price_clp,
        lowest_price=product.lowest_price,
        lowest_price_store=product.lowest_price_store,
        rating=float(product.rating) if product.rating is not None else None,
        offer_count=product.offer_count,
        specs=specs,
    )


class EntityResolver:
    def __init__(self, db: Session):
        self.service = ProductService(db)

    def resolve_intent(self, message: str, intent: AIIntent, state: ConversationState) -> EntityResolution:
        """Resolve all product-ish mentions in the intent."""
        result = EntityResolution()

        # 1. Anaphoric references to prior active products (highest priority).
        refs = reference_indices(message, len(state.active_products))
        if refs:
            candidates = [p for p in state.active_products if isinstance(p, dict) and p.get("id") is not None]
            picked = [c for i, c in enumerate(candidates) if i in refs]
            # Only use active products if they exist.
            if picked:
                resolved = []
                for candidate in picked:
                    pid = candidate.get("id")
                    product = self.service.get(pid)
                    if product is not None:
                        resolved.append(_from_product(product))
                if resolved:
                    result.resolved = resolved
                    return result

        # 2. Explicit product details (e.g. "el 15", "este producto").
        mentions = [e for e in intent.entities if e.type in (AIEntityType.PRODUCT, AIEntityType.PRODUCT_FAMILY)]
        explicit_ids: list[int] = []
        for entity in mentions:
            explicit_ids.extend(entity.resolved_product_ids)
        if explicit_ids:
            for pid in explicit_ids:
                product = self.service.get(pid)
                if product is not None:
                    result.resolved.append(_from_product(product))
            if result.resolved:
                return result

        # 3. Brands / families → catalog search for candidates.
        brand_entities = [e for e in intent.entities if e.type == AIEntityType.BRAND]
        family_entities = [e for e in intent.entities if e.type == AIEntityType.PRODUCT_FAMILY]
        product_entities = [e for e in intent.entities if e.type == AIEntityType.PRODUCT]

        # Search each family/model with ITS OWN brand, so multi-brand
        # comparisons ("iphone 15 o el xiaomi m8") don't cross-filter each other.
        term_pairs: list[tuple[str | None, str | None]] = []
        for entity in family_entities:
            if entity.family:
                term_pairs.append((entity.family, entity.brand))
        for entity in product_entities:
            model = entity.model or entity.value
            if model and len(model) >= 3:
                term_pairs.append((model, entity.brand))
        term_pairs = _dedupe_pairs(term_pairs)

        for term, brand in term_pairs:
            result.candidates.extend(self._search(term, brand=brand))

        if brand_entities:
            for brand_term in {e.brand for e in brand_entities if e.brand}:
                result.candidates.extend(self._search(brand_term))

        if not result.candidates:
            # Fall back to a clean search query stripped of stop words.
            candidate_query = _searchable_message(message)
            if candidate_query:
                result.candidates = self._search(candidate_query, brand=next(iter({e.brand for e in brand_entities if e.brand}), None))

        result.candidates = _dedupe_candidates(result.candidates)
        return result

    def _search(self, query: str, brand: str | None = None) -> list[ResolvedProduct]:
        try:
            products, _ = self.service.search(
                query=query,
                brand=brand,
                category=None,
                min_price_clp=None,
                max_price_clp=None,
                limit=5,
                offset=0,
            )
        except Exception:
            return []
        return [_from_product(p) for p in products]


_STOP = {
    "para", "por", "de", "del", "la", "las", "el", "los", "un", "una", "unos", "unas",
    "con", "sin", "en", "como", "que", "cual", "y", "o", "mi", "tu", "me", "te", "se",
    "busca", "busco", "buscar", "busqueda", "quiero", "necesito", "recomendame",
    "hay", "alguna", "alguno", "mejor", "buen", "decime", "cuales", "estos", "me",
}


def _searchable_message(message: str) -> str | None:
    tokens = [
        token
        for token in message.casefold().split(" ")
        if token.strip() and token not in _STOP and any(ch.isalnum() for ch in token)
    ]
    return " ".join(tokens[-5:]) if tokens else None


def _dedupe_pairs(pairs: list[tuple[str | None, str | None]]) -> list[tuple[str | None, str | None]]:
    seen: set[tuple[str | None, str | None]] = set()
    unique: list[tuple[str | None, str | None]] = []
    for pair in pairs:
        if pair not in seen:
            seen.add(pair)
            unique.append(pair)
    return unique


def _dedupe_candidates(candidates: list) -> list:
    seen: set[int] = set()
    unique = []
    for candidate in candidates:
        if candidate.product_id in seen:
            continue
        seen.add(candidate.product_id)
        unique.append(candidate)
    return unique