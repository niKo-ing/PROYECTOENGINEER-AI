"""Topic-aware research query planning (AI V4).

Deep research does not reuse the fixed ``manufacturer > benchmark > review``
ladder blindly: the incoming message is scanned for its dominant topics
(performance, gaming, price, power draw, compatibility, ...) and one query is
generated per topic with the *expected source type* chosen by :func:`source_strategy`.
Everything stays deterministic (no LLM) and bounded by ``max_queries``.
"""

from __future__ import annotations

import re

from app.ai.evidence import KnowledgeSourceType
from app.ai.research.schemas import ResearchQuery, ResearchTarget

# topic -> marker terms (casefolded at call time).
_TOPIC_MARKERS: dict[str, tuple[str, ...]] = {
    "benchmarks": (
        "benchmark", "geekbench", "rendimiento", "performance", "puntaje",
        "fps", "tests", "score", "compara", "comparacion", "comparación",
    ),
    "reviews": (
        "review", "comentarios", "opiniones", "reseña", "reseñas",
        "experiencia", "usuarios",
    ),
    "especificaciones": (
        "especificacion", "especificaciones", "caracteristica", "características",
        "soporta", "soporte", "compatible",
    ),
    "precio": (
        "precio", "costo", "cuesta", "presupuesto", "barata", "barato",
        "oferta", "valor", "pvp",
    ),
    "gaming": (
        "gaming", "juego", "juegos", "jug", "1440p", "1080p", "4k",
    ),
    "productividad": (
        "edición", "edicion", "video", "render", "render", "workstation",
        "compilación", "compilacion", "compile", "streaming", "oficina",
        "productividad",
    ),
    "consumo": (
        "consumo", "potencia", "watts", "watt", "tdp", "temperatura",
        "refrigeración", "refrigeracion", "ruido",
    ),
    "compatibilidad": (
        "compatible con", "funciona con", "sirve para", "compatib",
    ),
}

TOPIC_PRIORITY = (
    "benchmarks", "reviews", "especificaciones", "precio", "gaming",
    "productividad", "consumo", "compatibilidad",
)

# Search suffix per topic, paired with the preferred evidence source type.
_QUERY_SUFFIX: dict[str, str] = {
    "benchmarks": "benchmark Geekbench 6",
    "reviews": "review",
    "especificaciones": "specifications",
    "precio": "price",
    "gaming": "gaming performance",
    "productividad": "productivity",
    "consumo": "power consumption",
    "compatibilidad": "compatibility",
}

_SOURCE_STRATEGY: dict[str, tuple[str, ...]] = {
    "especificaciones": (
        KnowledgeSourceType.MANUFACTURER.value,
        KnowledgeSourceType.DOCUMENT.value,
        KnowledgeSourceType.REVIEW.value,
        KnowledgeSourceType.WEB.value,
    ),
    "compatibilidad": (
        KnowledgeSourceType.MANUFACTURER.value,
        KnowledgeSourceType.DOCUMENT.value,
        KnowledgeSourceType.REVIEW.value,
        KnowledgeSourceType.WEB.value,
    ),
    "benchmarks": (
        KnowledgeSourceType.BENCHMARK.value,
        KnowledgeSourceType.REVIEW.value,
        KnowledgeSourceType.MANUFACTURER.value,
        KnowledgeSourceType.WEB.value,
    ),
    "reviews": (
        KnowledgeSourceType.REVIEW.value,
        KnowledgeSourceType.WEB.value,
        KnowledgeSourceType.MANUFACTURER.value,
    ),
    "gaming": (
        KnowledgeSourceType.BENCHMARK.value,
        KnowledgeSourceType.REVIEW.value,
        KnowledgeSourceType.WEB.value,
    ),
    "productividad": (
        KnowledgeSourceType.BENCHMARK.value,
        KnowledgeSourceType.REVIEW.value,
        KnowledgeSourceType.WEB.value,
    ),
    "precio": (
        KnowledgeSourceType.WEB.value,
        KnowledgeSourceType.MANUFACTURER.value,
        KnowledgeSourceType.REVIEW.value,
    ),
    "consumo": (
        KnowledgeSourceType.MANUFACTURER.value,
        KnowledgeSourceType.BENCHMARK.value,
        KnowledgeSourceType.WEB.value,
    ),
}


def detect_topics(message: str) -> list[str]:
    """Return the research topics present in ``message``, by priority order."""
    low = (message or "").casefold()
    return [topic for topic in TOPIC_PRIORITY if any(marker in low for marker in _TOPIC_MARKERS[topic])]


def source_strategy(topic: str) -> list[str]:
    """Ordered preferred source types for a topic (best first)."""
    return list(_SOURCE_STRATEGY.get(topic, (KnowledgeSourceType.MANUFACTURER.value,)))


def expected_source_for_topic(topic: str) -> str:
    """The first (best) expected source type for a topic."""
    return source_strategy(topic)[0]


def plan_queries(
    targets: list[ResearchTarget],
    message: str = "",
    *,
    max_queries: int = 3,
    depth: str = "light",
) -> list[ResearchQuery]:
    """Build up to ``max_queries`` research intents, scaled by depth.

    * ``light`` (default) keeps the historical manufacturer > benchmark > review
      ladder for backwards compatibility;
    * ``deep`` expands one query per detected topic so each source strategy gets
      a bounded chance to contribute.
    """
    deep = str(getattr(depth, "value", depth)).lower() == "deep"
    topics = detect_topics(message)
    queries: list[ResearchQuery] = []
    for target in targets:
        brand, model = target_identity(target)
        if not model:
            continue
        label = f"{brand} {model}".strip() if brand else model
        if deep and topics:
            for topic in topics:
                queries.append(
                    ResearchQuery(
                        query=f"{label} {_QUERY_SUFFIX[topic]}",
                        expected_type=expected_source_for_topic(topic),
                        target_id=target.id,
                        topic=topic,
                        priority=TOPIC_PRIORITY.index(topic) + 1,
                    )
                )
                if len(queries) >= max_queries:
                    return queries[:max_queries]
            continue

        queries.append(
            ResearchQuery(
                query=f"{label} specifications",
                expected_type=KnowledgeSourceType.MANUFACTURER.value,
                target_id=target.id,
                topic="especificaciones",
                priority=1,
            )
        )
        if any(term in message.casefold() for term in _BENCHMARK_TERMS):
            queries.append(
                ResearchQuery(
                    query=f"{label} benchmark Geekbench 6",
                    expected_type=KnowledgeSourceType.BENCHMARK.value,
                    target_id=target.id,
                    topic="benchmarks",
                    priority=2,
                )
            )
        queries.append(
            ResearchQuery(
                query=f"{label} review",
                expected_type=KnowledgeSourceType.REVIEW.value,
                target_id=target.id,
                topic="reviews",
                priority=3,
            )
        )
        if len(queries) >= max_queries:
            return queries[:max_queries]
    return queries[:max_queries]


_BENCHMARK_TERMS = (
    "benchmark",
    "geekbench",
    "score",
    "rendimiento",
    "performance",
    "puntaje",
    "tests",
)


def target_identity(target: ResearchTarget) -> tuple[str | None, str | None]:
    """Return the best (brand, model-ish) identity for a catalog target."""
    brand = (target.brand or "").strip() or None
    model = (target.model or "").strip() or None
    if model:
        return brand, model
    name_model = _fallback_model(target.name, brand=brand)
    if name_model:
        return brand, name_model
    return brand, None


def _fallback_model(name: str, brand: str | None = None) -> str | None:
    tokens = [token for token in _tokens(name) if len(token) >= 3]
    if not tokens:
        return None
    brand_tokens = {token.casefold() for token in _tokens(brand or "")}
    meaningful = [
        token
        for token in tokens
        if _probably_meaningful(token) and token.casefold() not in brand_tokens
    ]
    return " ".join(meaningful[:4]) if meaningful else " ".join(tokens[:4])


def _probably_meaningful(token: str) -> bool:
    lowered = token.casefold()
    if any(ch.isdigit() for ch in token):
        return True
    return lowered not in {
        "the", "edition", "version", "with", "for", "and", "gaming", "laptop",
        "desktop", "mobile", "notebook", "smartphone", "phone", "tablet",
    }


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+", value)