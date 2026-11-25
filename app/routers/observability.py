"""Panel de observabilidad de la IA (solo administradores): métricas, objetivos de servicio, trazas y Prometheus."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser, get_current_admin
from app.db import get_db
from app.models.observability import AgentRun, AgentSpan
from app.observability.metrics import dashboard, load_runs, prometheus_text, run_view, summarize

router = APIRouter(prefix="/observability", tags=["observabilidad"])
DbSession = Annotated[Session, Depends(get_db)]
Admin = Annotated[AuthenticatedUser, Depends(get_current_admin)]
FLOW = Query(default=None, pattern="^(agente|asistente_pc|revision_pc)$")


@router.get("/metrics", summary="Métricas clave, objetivos de servicio y serie de tiempo")
def metrics(_admin: Admin, db: DbSession, hours: Annotated[float, Query(gt=0, le=24 * 90)] = 24 * 7, flow: str | None = FLOW,
            include_eval: bool = False, eval_tag: Annotated[str | None, Query(max_length=64)] = None) -> dict[str, Any]:
    return dashboard(db, hours=hours, flow=flow, include_eval=include_eval, eval_tag=eval_tag)


@router.get("/runs", summary="Ejecuciones recientes (sin datos personales)")
def runs(_admin: Admin, db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50, flow: str | None = FLOW,
         status_filter: Annotated[str | None, Query(alias="status", pattern="^(ok|error|fallback|blocked)$")] = None) -> dict[str, Any]:
    stmt = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
    if flow:
        stmt = stmt.where(AgentRun.flow == flow)
    if status_filter:
        stmt = stmt.where(AgentRun.status == status_filter)
    return {"items": [run_view(r) for r in db.scalars(stmt)]}


@router.get("/runs/{run_id}", summary="Traza de una ejecución: tramos de modelo, herramientas y etapas")
def run_detail(run_id: str, _admin: Admin, db: DbSession) -> dict[str, Any]:
    run = db.scalar(select(AgentRun).where(AgentRun.run_id == run_id))
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ejecución no encontrada")
    spans = db.scalars(select(AgentSpan).where(AgentSpan.run_id == run_id).order_by(AgentSpan.seq))
    return {**run_view(run), "cpu_ms": run.cpu_ms, "error_message": run.error_message, "extra": run.extra,
            "spans": [{"seq": s.seq, "kind": s.kind, "name": s.name, "start_ms": s.start_ms, "duration_ms": s.duration_ms, "status": s.status,
                       "input_tokens": s.input_tokens, "output_tokens": s.output_tokens, "detail": s.detail} for s in spans]}


@router.get("/prometheus", response_class=PlainTextResponse, summary="Métricas en formato Prometheus")
def prometheus(_admin: Admin, db: DbSession, hours: Annotated[float, Query(gt=0, le=24 * 90)] = 24) -> str:
    runs = load_runs(db, hours=hours)
    ids = [r.run_id for r in runs]
    spans = list(db.scalars(select(AgentSpan).where(AgentSpan.run_id.in_(ids)))) if ids else []
    return prometheus_text(summarize(runs, spans))
