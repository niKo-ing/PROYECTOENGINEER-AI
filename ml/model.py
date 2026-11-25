"""Modelo de emparejamiento de productos: carga, predicción e interpretación."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import joblib

from ml.features import FEATURE_NAMES, pair_features

DEFAULT_MODEL_PATH = Path(os.getenv("MATCH_MODEL_PATH", Path(__file__).resolve().parent.parent / "EP3_ITY1102" / "modelo" / "match_model.joblib"))
# Zona gris: entre estos umbrales el resultado es «ambiguo» y se deja a la revisión (igual que el emparejador determinista).
THRESHOLD_MATCH = 0.70  # elegido con la tabla de umbrales de metrics.json: precisión ~0,94 con ~82 % de cobertura
THRESHOLD_NO_MATCH = 0.35


def explain(values: list[float]) -> list[str]:
    f = dict(zip(FEATURE_NAMES, values))
    reasons: list[str] = []
    if f["capacidad_en_conflicto"]:
        reasons.append("las capacidades (GB/TB) son distintas: es otra variante")
    elif f["capacidad_igual"]:
        reasons.append("misma capacidad de almacenamiento/memoria")
    if f["modelo_en_conflicto"]:
        reasons.append("los códigos de modelo no coinciden")
    elif f["modelo_igual"]:
        reasons.append("comparten el código de modelo")
    if f["marca_igual"]:
        reasons.append("misma marca")
    if f["ratio_secuencia"] >= 0.8:
        reasons.append(f"títulos muy parecidos (similitud {f['ratio_secuencia']:.2f})")
    elif f["ratio_secuencia"] < 0.4:
        reasons.append(f"títulos muy distintos (similitud {f['ratio_secuencia']:.2f})")
    return reasons


class MatchModel:
    def __init__(self, estimator: Any, version: str = "dev"):
        self.estimator = estimator
        self.version = version

    @classmethod
    def load(cls, path: str | Path | None = None) -> "MatchModel":
        bundle = joblib.load(path or DEFAULT_MODEL_PATH)
        return cls(bundle["estimator"], bundle.get("version", "dev"))

    def predict_many(self, pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
        rows = [pair_features(a, b) for a, b in pairs]
        probabilities = self.estimator.predict_proba(rows)[:, 1]
        out = []
        for values, p in zip(rows, probabilities):
            p = float(p)
            decision = "match" if p >= THRESHOLD_MATCH else "no_match" if p <= THRESHOLD_NO_MATCH else "ambiguous"
            out.append({"decision": decision, "probability": round(p, 4), "reasons": explain(values), "model_version": self.version})
        return out

    def predict(self, a: str, b: str) -> dict[str, Any]:
        return self.predict_many([(a, b)])[0]
