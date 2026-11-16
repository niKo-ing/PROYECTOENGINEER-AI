"""Cómo la API consume el modelo de emparejamiento: local (archivo) o remoto (endpoint SageMaker / contenedor en EC2).

``MATCH_MODEL_URL`` apunta al endpoint con el contrato de SageMaker (``POST /invocations``). Si no está definida se
carga el archivo del modelo; así el mismo código corre en el computador, en EC2 y contra SageMaker.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Protocol

import httpx

from ml.model import MatchModel


class ModelUnavailable(RuntimeError):
    pass


class Scorer(Protocol):
    name: str

    def score(self, pairs: list[tuple[str, str]]) -> list[dict]: ...


class LocalScorer:
    name = "local"

    def __init__(self, model: MatchModel):
        self.model = model

    def score(self, pairs):
        return self.model.predict_many(pairs)


class RemoteScorer:
    name = "remote"

    def __init__(self, url: str, timeout: float = 5.0, client: httpx.Client | None = None):
        self.url, self.timeout = url.rstrip("/"), timeout
        self.client = client or httpx.Client(timeout=timeout)

    def score(self, pairs):
        try:
            response = self.client.post(f"{self.url}/invocations", json={"pairs": [{"a": a, "b": b} for a, b in pairs]})
            response.raise_for_status()
            return response.json()["predictions"]
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise ModelUnavailable(f"El endpoint del modelo no respondió: {error}") from error


@lru_cache(maxsize=1)
def get_scorer() -> Scorer:
    url = os.getenv("MATCH_MODEL_URL", "").strip()
    if url:
        return RemoteScorer(url)
    try:
        return LocalScorer(MatchModel.load())
    except FileNotFoundError as error:
        raise ModelUnavailable("No hay modelo entrenado: ejecute `python -m ml.train`.") from error
