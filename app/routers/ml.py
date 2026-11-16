"""API REST del modelo de emparejamiento de productos (documentada en /docs, OpenAPI).

Seguridad: JWT de Supabase **o** llave de API (``X-API-Key``, para integraciones y pruebas con curl/Postman) y límite
de tasa por llamador. TLS lo termina CloudFront/ALB.
"""

from __future__ import annotations

import hmac
import json
import os
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ratelimit import rate_limit
from app.core.security import AuthenticatedUser, bearer_scheme, validate_supabase_token
from app.db import get_db
from app.messaging.broker import MATCH_QUEUE, Broker, InMemoryBroker, get_broker
from app.messaging.match_worker import handle_match_request
from app.ml.client import ModelUnavailable, Scorer, get_scorer
from app.models.catalog import AiMatchDecision

router = APIRouter(prefix="/ml", tags=["ml"])
METRICS_PATH = Path(os.getenv("MATCH_METRICS_PATH", Path(__file__).resolve().parents[2] / "EP3_ITY1102" / "modelo" / "metrics.json"))
DbSession = Annotated[Session, Depends(get_db)]
limited = Depends(rate_limit("ml", "ML_RATE_LIMIT_PER_MINUTE", 60))


def caller(credentials=Depends(bearer_scheme), x_api_key: Annotated[str | None, Header()] = None) -> str:
    """Quién llama: un usuario con sesión o un cliente con llave de API."""
    keys = [k.strip() for k in os.getenv("ML_API_KEYS", "").split(",") if k.strip()]
    if x_api_key and any(hmac.compare_digest(x_api_key, key) for key in keys):
        return "api-key"
    if credentials is not None:
        user: AuthenticatedUser = validate_supabase_token(credentials.credentials)
        return user.id
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta autenticación: Bearer JWT o cabecera X-API-Key", headers={"WWW-Authenticate": "Bearer"})


Caller = Annotated[str, Depends(caller)]


def get_model_scorer() -> Scorer:
    try:
        return get_scorer()
    except ModelUnavailable as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error


ModelScorer = Annotated[Scorer, Depends(get_model_scorer)]


class MatchRequest(BaseModel):
    a: str = Field(min_length=2, max_length=300, examples=["Samsung Galaxy A54 128GB Negro"])
    b: str = Field(min_length=2, max_length=300, examples=["Celular Galaxy A54 5G 128 GB Negro oferta"])


class MatchResponse(BaseModel):
    decision: str = Field(description="match | no_match | ambiguous")
    probability: float
    reasons: list[str]
    model_version: str


class AsyncAccepted(BaseModel):
    request_id: str
    queue: str
    queue_depth: int


@router.get("/health", summary="Estado del servicio y del modelo")
def health():
    try:
        scorer = get_scorer()
        return {"status": "ok", "scorer": scorer.name}
    except ModelUnavailable as error:
        return {"status": "degraded", "detail": str(error)}


@router.get("/metrics", summary="Métricas del modelo (entrenamiento y prueba)")
def model_metrics() -> dict[str, Any]:
    if not METRICS_PATH.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aún no hay métricas: entrene el modelo (python -m ml.train)")
    return json.loads(METRICS_PATH.read_text())


@router.post("/match", response_model=MatchResponse, summary="¿Son el mismo producto? (síncrono)", dependencies=[limited])
def match(payload: MatchRequest, who: Caller, scorer: ModelScorer):
    try:
        return scorer.score([(payload.a, payload.b)])[0]
    except ModelUnavailable as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error)) from error


@router.post("/match/async", response_model=AsyncAccepted, status_code=status.HTTP_202_ACCEPTED, summary="Encola el par para el worker (RabbitMQ)", dependencies=[limited])
def match_async(payload: MatchRequest, who: Caller, db: DbSession, scorer: ModelScorer, background: BackgroundTasks, broker: Annotated[Broker, Depends(get_broker)]):
    request_id = uuid.uuid4().hex[:12]
    broker.publish(MATCH_QUEUE, {"request_id": request_id, "a": payload.a, "b": payload.b, "caller": who})
    if isinstance(broker, InMemoryBroker):  # sin RabbitMQ no hay otro proceso que consuma: se procesa aquí, en segundo plano
        background.add_task(broker.consume_one, MATCH_QUEUE, lambda m: handle_match_request(m, db, scorer))
    return AsyncAccepted(request_id=request_id, queue=MATCH_QUEUE, queue_depth=broker.depth(MATCH_QUEUE))


@router.get("/decisions", summary="Últimas decisiones del modelo (dashboard)", dependencies=[limited])
def decisions(who: Caller, db: DbSession, broker: Annotated[Broker, Depends(get_broker)], limit: int = 20):
    rows = db.scalars(select(AiMatchDecision).order_by(AiMatchDecision.id.desc()).limit(min(max(limit, 1), 100))).all()
    return {
        "queue_depth": broker.depth(MATCH_QUEUE),
        "decisions": [
            {"id": r.id, "a": r.incoming_name, "b": (r.evidence or {}).get("comparado_con"), "decision": r.decision, "probability": float(r.confidence), "reason": r.reason, "model": r.model, "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ],
    }
