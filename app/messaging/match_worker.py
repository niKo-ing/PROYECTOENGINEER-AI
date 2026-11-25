"""Worker del flujo asíncrono: entrada (cola) → procesamiento → modelo → resultado guardado.

    python -m app.messaging.match_worker      # consume ``match.requests`` hasta Ctrl+C
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.messaging.broker import MATCH_QUEUE, Broker, get_broker
from app.ml.client import Scorer, get_scorer
from app.models.catalog import AiMatchDecision

log = logging.getLogger(__name__)


def handle_match_request(message: dict[str, Any], db: Session, scorer: Scorer) -> AiMatchDecision:
    """Puntúa el par con el modelo y deja el resultado auditable en ``ai_match_decisions``."""
    prediction = scorer.score([(message["a"], message["b"])])[0]
    decision = AiMatchDecision(
        incoming_name=message["a"][:255],
        decision=prediction["decision"],
        confidence=round(prediction["probability"], 2),
        model=f"match-model-{prediction['model_version']}"[:160],
        prompt_version="n/a",
        reason="; ".join(prediction["reasons"]) or "sin señales claras",
        evidence={"comparado_con": message["b"], "request_id": message.get("request_id"), "scorer": scorer.name},
    )
    db.add(decision)
    db.commit()
    return decision


def run_worker(poll_seconds: float = 0.5, broker: Broker | None = None) -> None:  # pragma: no cover — bucle infinito
    from app.db import SessionLocal

    broker, scorer = broker or get_broker(), get_scorer()
    log.info("Worker de emparejamiento escuchando %s", MATCH_QUEUE)
    while True:
        with SessionLocal() as db:
            if not broker.consume_one(MATCH_QUEUE, lambda m: handle_match_request(m, db, scorer)):
                time.sleep(poll_seconds)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    run_worker()
