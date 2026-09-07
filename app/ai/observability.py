"""Observability — structured, request-scoped AI pipeline tracing.

Every orchestrator stage appends a compact record (stage + payload) to the
request trace exposed on ``ChatResponse.trace``, and mirrors a JSON line to the
application logger. Consumers (frontend debug views, log pipelines) can rely on
stable ``stage`` names: ``plan``, ``rag``, ``web_research``, ``research_profile``.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

logger = logging.getLogger("solotodo.ai")

_KNOWN_STAGES = {
    "plan",
    "rag",
    "web_research",
    "research_profile",
    "research_plan",
    "intent",
    "planner",
    "query_rewrite",
    "recommendation",
    "evidence",
    "grounding",
    "conflict",
}


def new_trace_id() -> str:
    """Short, collision-resistant request id (no crypto, no secrets)."""
    digest = hashlib.sha256(f"{time.time_ns()}".encode("utf-8")).hexdigest()
    return digest[:16]


class AITrace:
    """Immutable-ish request-scoped event accumulator."""

    def __init__(self, *, producer: str = "orchestrator", started_at: float | None = None, trace_id: str | None = None):
        self.producer = producer
        self.trace_id = trace_id or new_trace_id()
        self.started_at = started_at if started_at is not None else time.monotonic()
        self._events: list[dict[str, Any]] = []

    def step(self, stage: str, data: dict[str, Any] | None = None) -> None:
        event = {"stage": stage, "ts_ms": round(time.monotonic() - self.started_at, 2), **(data or {})}
        self._events.append(event)
        logger.info("ai trace id=%s stage=%s data=%s", self.trace_id, stage, event)

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    @property
    def stages(self) -> list[str]:
        return [event["stage"] for event in self._events]

    def as_dict(self) -> list[dict[str, Any]]:
        return [{"stage": event["stage"], "ts_ms": event["ts_ms"], **{k: v for k, v in event.items() if k not in {"stage", "ts_ms"}}} for event in self._events]

    def summary(self) -> dict[str, Any]:
        """Compact, safe-to-expose debug summary (no raw catalog internals)."""
        return {
            "trace_id": self.trace_id,
            "producer": self.producer,
            "stages": self.stages,
            "events": len(self._events),
        }


def trace_step(events: list[dict[str, Any]] | None, stage: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Best-effort append to a plain list trace (backward compatible helper)."""
    if stage not in _KNOWN_STAGES:
        logger.debug("ai trace unknown stage=%s", stage)
    event = {"stage": stage, **(data or {})}
    if events is not None:
        events.append(event)
    return event