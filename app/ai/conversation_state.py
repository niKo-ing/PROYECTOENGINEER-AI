"""Conversation state reconstruction for multi-turn chat.

The backend is intentionally stateless between requests: the client sends the
full prior conversation (``history``) on every call, and this module rebuilds
the assistant's working memory from those turns. This lets the assistant
resolve anaphora ("compararlas", "el primero", "ese producto") without a
persistent chat table, keeping the catalog spec architecture untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.ai.schemas.chat import ChatTurn
from app.catalog.synonyms import normalize_spanish


@dataclass
class ConversationState:
    """Working memory reconstructed from prior turns."""

    turns: list[ChatTurn] = field(default_factory=list)
    product_anchor_id: int | None = None
    active_products: list[dict[str, Any]] = field(default_factory=list)
    last_search_query: str | None = None
    active_category: str | None = None
    current_topic: str | None = None
    constraints: dict[str, Any] = field(default_factory=dict)
    last_recommendation: dict[str, Any] | None = None

    @classmethod
    def build(cls, history: list[ChatTurn], product_id: int | None = None) -> "ConversationState":
        """Reconstruct the state from the client-provided history."""
        state = cls(turns=list(history), product_anchor_id=product_id)

        last_user, last_assistant = "", ""
        for turn in history:
            content = (turn.content or "").strip()
            if turn.role == "user":
                last_user = content
                # A bare follow-up carries forward the active products.
                if _looks_like_follow_up(content):
                    continue
            elif turn.role == "assistant":
                last_assistant = content
                if turn.products:
                    state.active_products = list(turn.products)

        if not state.active_products:
            # Fall back to any prior assistant products if the last one had none.
            for turn in reversed(history):
                if turn.role == "assistant" and turn.products:
                    state.active_products = list(turn.products)
                    break

        state.current_topic = last_user or last_assistant
        if "iphone" in last_user.casefold() or "smartphone" in last_user.casefold() or "celular" in last_user.casefold():
            state.active_category = "smartphone"
        elif state.active_products:
            first = state.active_products[0]
            state.active_category = first.get("category")
        return state

    def active_product_ids(self) -> list[int]:
        ids: list[int] = []
        seen: set[int] = set()
        for product in self.active_products:
            pid = product.get("id")
            if pid is not None and pid not in seen:
                seen.add(pid)
                ids.append(pid)
        return ids

    def has_active_products(self) -> bool:
        return bool(self.active_products)


def _looks_like_follow_up(text: str) -> bool:
    lowered = normalize_spanish(text)
    return any(
        token in lowered
        for token in ("comparal", "comparame", "comparame los", "ese", "esa", "el primero", "el segundo", "la primera", "la segunda", "y contra", "cual es mejor", "cual me conviene", "por que", "que tiene")
    )


_ORDINAL_INDEX = {
    "primero": 0,
    "primera": 0,
    "segundo": 1,
    "segunda": 1,
    "tercero": 2,
    "tercera": 2,
    "cuarto": 3,
    "cuarta": 3,
    "quinto": 4,
    "quinta": 4,
}
_SINGULAR_ANAPHORA = {"ese": 0, "esa": 0, "aquel": 0, "aquel producto": 0, "ese producto": 0}


def reference_indices(text: str, limit: int) -> list[int]:
    """Resolve anaphora in ``text`` to 0-based indices into active products.

    Returns an empty list when the text does not reference a prior product.
    """
    norm = text.casefold().strip()
    if not norm:
        return []

    # "las dos", "ambos", "esas dos", "ese par" → the first two
    if any(token in norm for token in ("las dos", "los dos", "ambas", "ambos", "esas dos", "eses dos", "ese par")):
        return list(range(min(limit, 2)))

    # "todos los", "todas las" → everything
    if any(token in norm for token in ("todos los", "todas las", "todos", "todas")):
        return list(range(limit))

    # ordinal references: "el primero", "la segunda"
    for word, index in _ORDINAL_INDEX.items():
        if re.search(rf"\b{word}\b", norm):
            return [index] if index < limit else []

    # singular demonstrative that is not a general search term
    for phrase, index in _SINGULAR_ANAPHORA.items():
        if phrase in norm and _is_determiner_reference(norm):
            return [index] if index < limit else []

    # "y contra un X" — handled elsewhere (adds a new candidate), returns none here
    return []


def _is_determiner_reference(norm: str) -> bool:
    """'ese'/'esa' is a reference only when it is not part of 'tengo ese modelo' style prose."""
    if any(token in norm for token in ("")):
        return norm.startswith(("ese", "esa", "aquel", "qué tal ese", "ese es", "ese tiene"))
    # A bare demonstrative at the start, or with a known product follow-up verb.
    return norm.startswith(("ese", "esa", "aquel"))