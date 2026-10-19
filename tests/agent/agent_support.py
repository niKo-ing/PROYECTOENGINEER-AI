"""Ayudantes compartidos de las pruebas del agente."""

from __future__ import annotations

import re

from app.agent.demo_data import add_product  # noqa: F401 — reexportado para los tests

USER = "user-ahorro-1"


class ConceptEmbedder:
    """Doble de prueba con 'semántica': palabras de un mismo concepto caen en la misma dimensión.

    Sirve para probar el RANKING semántico de forma determinista (sin red). El comportamiento
    con embeddings reales de Gemini se verifica aparte en ``test_live_gemini.py`` (opt-in).
    """

    CONCEPTS = [
        {"notebook", "notebooks", "laptop", "laptops", "portatil", "portátil", "computador", "pc"},
        {"barato", "baratos", "economico", "económico", "economicos", "ahorrar", "ahorro", "precio", "bajo", "oferta"},
        {"samsung", "galaxy"},
        {"huawei"},
        {"gamer", "gaming", "juegos", "videojuegos", "fps"},
        {"trabajo", "trabajar", "oficina", "estudiar", "universidad"},
        {"celular", "celulares", "smartphone", "telefono", "teléfono"},
        {"liviano", "livianos", "ligero", "ligeros", "portable"},
    ]

    def provider_name(self) -> str:
        return "concept_test"

    def dimensions(self) -> int:
        return len(self.CONCEPTS) + 1

    def embed_text(self, text: str, *, model: str | None = None) -> list[float]:
        words = set(re.findall(r"\w+", text.casefold()))
        vector = [1.0 if words & concept else 0.0 for concept in self.CONCEPTS] + [0.05]
        norm = sum(v * v for v in vector) ** 0.5
        return [v / norm for v in vector]

    def embed_documents(self, texts, *, model: str | None = None):
        return [self.embed_text(t) for t in texts]
