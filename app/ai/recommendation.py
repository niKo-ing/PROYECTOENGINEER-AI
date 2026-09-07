"""Recommendation engine — evidence-driven, not LLM-only.

Produces a structured comparison that explains *why* one product wins, what it
loses, and what the user trades off. Weights shift according to the detected
use case (gaming, camera, battery, price/value, ...), hard constraints
(max price) and whether the question is objective ("¿cuál es mejor?") or
prioritized ("¿cuál me conviene?").

Spec labels common across the compared products are scored too, so the engine
is category-agnostic (works for smartphones, GPUs, notebooks...) without
hardcoding dimensions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Recommendation:
    """Structured, explainable decision support for a product comparison."""

    products: list[dict[str, Any]] = field(default_factory=list)
    criteria: dict[str, str] = field(default_factory=dict)
    per_criterion: dict[str, dict[str, Any]] = field(default_factory=dict)
    winner_id: int | None = None
    winner_reason: str | None = None
    advantages: dict[int, list[str]] = field(default_factory=dict)
    tradeoffs: dict[int, list[str]] = field(default_factory=dict)
    missing_specs: list[str] = field(default_factory=list)
    applied_constraints: dict[str, Any] = field(default_factory=dict)
    rationale: str | None = None

    def as_dict(self) -> dict:
        return {
            "products": [
                {"id": p.get("id"), "name": p.get("name"), "brand": p.get("brand"), "lowest_price": p.get("lowest_price"), "rating": p.get("rating")}
                for p in self.products
            ],
            "criteria": self.criteria,
            "per_criterion": self.per_criterion,
            "winner_id": self.winner_id,
            "winner_reason": self.winner_reason,
            "advantages": {str(k): v for k, v in self.advantages.items()},
            "tradeoffs": {str(k): v for k, v in self.tradeoffs.items()},
            "missing_specs": self.missing_specs,
            "applied_constraints": self.applied_constraints,
            "rationale": self.rationale,
        }


def _number(value: str | int | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    match = re.search(r"[-+]?[\d][\d.,\s]*", text)
    if not match:
        return None
    cleaned = match.group(0).replace(".", "").replace(" ", "")
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


# Labels that conventionally mean the opposite direction from the default.
_HIGHER_BETTER_TERMS = {
    "ram", "memoria", "nucleo", "core", "ghz", "mhz", "frecuencia", "almacenamiento",
    "storage", "camara", "megapixele", "bateria", "mah", "duracion", "pantalla",
    "resolucion", "hz", "refresh", "velocidad", "gs", "tasa", "puerto", "usb", "ssd",
    "grafica", "vram", "cuda", "rendimiento", "performance", "tacto", "soporte",
}
_LOWER_BETTER_TERMS = {
    "consumo", "tdp", "peso", "latencia", "grosor", "time", "acceso", "disipador",
}
_CRITERION_DIRECTION: dict[str, int] = {"price": -1, "value": 1, "rating": 1}


def _direction(label: str) -> int:
    if label in _CRITERION_DIRECTION:
        return _CRITERION_DIRECTION[label]
    lowered = label.casefold()
    if any(term in lowered for term in _LOWER_BETTER_TERMS):
        return -1
    if any(term in lowered for term in _HIGHER_BETTER_TERMS):
        return 1
    return 1


def _criterion_score(products: list[dict[str, Any]], label: str, weight: str) -> dict[str, Any]:
    """Score every product on a criterion; higher number is better."""
    values: dict[int, str | int | float | None] = {}
    for product in products:
        spec_value = dict(product.get("specs") or {}).get(label)
        if spec_value is not None:
            values[product.get("id")] = spec_value
            continue
        if label == "price":
            values[product.get("id")] = product.get("lowest_price") or product.get("price_clp")
        elif label == "rating":
            values[product.get("id")] = product.get("rating")
        elif label == "value":
            price = product.get("lowest_price") or product.get("price_clp") or 1
            rating = product.get("rating") or 0.0
            values[product.get("id")] = round(rating / max(price, 1) * 1_000_000, 4) if price else None

    entries: dict[str, Any] = {"label": label, "values": {str(k): v for k, v in values.items()}, "missing": []}
    grades: dict[int, float] = {}
    direction = _direction(label)
    for product in products:
        pid = product.get("id")
        value = values.get(pid)
        if value is None:
            entries["missing"].append(pid)
            continue
        number = _number(value)
        if number is None:
            continue
        grades[pid] = number * direction
    entries["grades"] = grades
    if grades:
        best = max(grades, key=grades.get)
        entries["best"] = best
    entries["weight"] = weight
    return entries


class RecommendationEngine:
    """Deterministic, weighted product recommendation over catalog specs."""

    _BASE_WEIGHTS = {"value": "high", "price": "high", "rating": "medium"}

    # Maps a detected use case to extra weighted dimensions.
    _USE_COLUMN_WEIGHTS: dict[str, dict[str, str]] = {
        "gaming": {"gaming": "high", "performance": "high", "price_value": "high"},
        "camera": {"camera": "high", "performance": "medium", "price_value": "medium"},
        "battery": {"battery": "high", "price_value": "medium"},
        "productivity": {"performance": "high", "price_value": "high", "productivity": "high"},
        "price_value": {"price_value": "high", "value": "high"},
        "longevity": {"longevity": "high", "performance": "medium"},
    }

    def recommend(
        self,
        products: list[dict[str, Any]],
        *,
        constraints: dict[str, Any] | None = None,
        objective: bool = False,
    ) -> Recommendation:
        """Recommend among ``products`` given the inferred constraints/priorities."""
        constraints = constraints or {}
        use_cases = constraints.get("use_case") or {}
        max_price = constraints.get("max_price")

        weights: dict[str, str] = dict(self._BASE_WEIGHTS)
        for use_case, level in use_cases.items():
            for metric, metric_weight in self._USE_COLUMN_WEIGHTS.get(use_case, {}).items():
                weights[metric] = _max_weight(weights.get(metric), metric_weight)

        common_specs = self._common_spec_labels(products)
        if objective:
            for label in common_specs:
                weights[label] = "high"
        else:
            for label in common_specs:
                weights.setdefault(label, "medium")

        eligible = self._filter_by_price(products, max_price)

        per_criterion: dict[str, dict[str, Any]] = {}
        advantages: dict[int, list[str]] = {p.get("id"): [] for p in products}
        tradeoffs: dict[int, list[str]] = {p.get("id"): [] for p in products}
        missing_specs: list[str] = []

        for label, weight in weights.items():
            score = _criterion_score(products, label, weight)
            per_criterion[label] = score
            if score["missing"]:
                missing_specs.append(label)
            best = score.get("best")
            if best is not None:
                for product in products:
                    pid = product.get("id")
                    if pid == best:
                        advantages[pid].append(label if label in common_specs else label)
                    else:
                        tradeoffs[pid].append(label)

        winner_id = self._pick_winner(eligible, per_criterion, weights)
        winner_reason = self._build_reason(winner_id, per_criterion, products)

        rationale = (
            "Comparación basada en las especificaciones y precios del catálogo. "
            + ("Criterio objetivo (mejor rendimiento/capacidad)." if objective else "Prioridades según tu uso y presupuesto.")
            + self._constraint_summary(max_price, use_cases)
        )

        return Recommendation(
            products=products,
            criteria=weights,
            per_criterion=per_criterion,
            winner_id=winner_id,
            winner_reason=winner_reason,
            advantages=advantages,
            tradeoffs=tradeoffs,
            missing_specs=missing_specs,
            applied_constraints={"max_price": max_price, "use_case": use_cases},
            rationale=rationale,
        )

    @staticmethod
    def _common_spec_labels(products: list[dict[str, Any]]) -> list[str]:
        counts: dict[str, int] = {}
        total = len(products)
        if total < 2:
            return []
        for product in products:
            for label in dict(product.get("specs") or {}):
                if _number(dict(product.get("specs") or {}).get(label)) is not None:
                    counts[label] = counts.get(label, 0) + 1
        return [label for label, count in counts.items() if count >= 2]

    @staticmethod
    def _filter_by_price(products: list[dict[str, Any]], max_price: int | None) -> list[dict[str, Any]]:
        if max_price is None:
            return products
        eligible = [p for p in products if (p.get("lowest_price") or p.get("price_clp") or 0) <= max_price]
        return eligible or products

    def _pick_winner(self, products: list[dict[str, Any]], per_criterion: dict[str, dict[str, Any]], weights: dict[str, str]) -> int | None:
        if not products:
            return None
        scores: dict[int, float] = {p.get("id"): 0.0 for p in products}
        for label, score in per_criterion.items():
            weight = _weight_value(weights.get(label, "medium"))
            grades = score.get("grades") or {}
            best = max(grades.values(), default=None)
            if best is None:
                continue
            for pid, grade in grades.items():
                if pid in scores:
                    scores[pid] += (grade / best) * weight
        return max(scores, key=scores.get) if scores else products[0].get("id")

    def _build_reason(self, winner_id: int | None, per_criterion: dict[str, dict[str, Any]], products: list[dict[str, Any]]) -> str | None:
        if winner_id is None:
            return None
        strengths = [label for label, score in per_criterion.items() if score.get("best") == winner_id]
        winner = next((p.get("name") for p in products if p.get("id") == winner_id), None)
        if not strengths:
            return f"{winner} es la opción más equilibrada según los datos del catálogo." if winner else None
        return f"{winner} se destaca en: {', '.join(strengths)}."

    @staticmethod
    def _constraint_summary(max_price: int | None, use_cases: dict[str, str]) -> str:
        parts: list[str] = []
        if max_price:
            parts.append(f"Presupuesto máximo de ${max_price:,} CLP".replace(",", "."))
        if use_cases:
            parts.append("Uso priorizado: " + ", ".join(use_cases.keys()))
        return " " + " · ".join(parts) if parts else ""


def _weight_value(weight: str) -> float:
    return {"high": 3.0, "medium": 1.5, "low": 0.5}.get(weight, 1.0)


def _max_weight(current: str | None, incoming: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    current_val = order.get(current or "low", 0)
    incoming_val = order.get(incoming, 1)
    return incoming if incoming_val > current_val else (current or incoming)