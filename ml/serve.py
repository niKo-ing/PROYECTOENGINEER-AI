"""Servidor de inferencia con el contrato de SageMaker (``GET /ping``, ``POST /invocations``).

Es el mismo contenedor para un endpoint de SageMaker y para EC2/Docker. Lee el modelo de ``/opt/ml/model`` (SageMaker)
o de ``MATCH_MODEL_PATH``.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ml.model import MatchModel

SAGEMAKER_DIR = Path("/opt/ml/model/match_model.joblib")
app = FastAPI(title="Modelo de emparejamiento", version="1.0.0")
_model: MatchModel | None = None
_started = time.time()


class Pair(BaseModel):
    a: str = Field(min_length=1, max_length=300, description="Título de la oferta de una tienda")
    b: str = Field(min_length=1, max_length=300, description="Título de la oferta de otra tienda")


class Invocation(BaseModel):
    pairs: list[Pair] = Field(min_length=1, max_length=64)


def model() -> MatchModel:
    global _model
    if _model is None:
        path = os.getenv("MATCH_MODEL_PATH") or (SAGEMAKER_DIR if SAGEMAKER_DIR.exists() else None)
        _model = MatchModel.load(path)
    return _model


@app.get("/ping")
def ping():
    try:
        return {"status": "ok", "model_version": model().version, "uptime_s": round(time.time() - _started)}
    except FileNotFoundError as error:
        raise HTTPException(503, "modelo no cargado") from error


@app.post("/invocations")
def invocations(payload: Invocation):
    return {"predictions": model().predict_many([(p.a, p.b) for p in payload.pairs])}
