"""Métricas de la IA calculadas desde las trazas (``agent_runs`` / ``agent_spans``).

Métricas clave (las que mira el panel /observabilidad y el informe):

* **Latencia** de punta a punta por flujo: p50, p95, p99 (objetivo: p95 bajo ``SLO_P95_MS``).
* **Tasa de error** (fallo sin respuesta) y **tasa de respaldo** (respondió con reglas porque el modelo falló o alucinó).
* **Precisión factual de precios**: % de respuestas cuyos precios citados están respaldados por los datos.
* **Uso de recursos**: llamadas al modelo, tokens de entrada/salida por ejecución y tiempo de CPU del proceso.
* **Herramientas**: uso, duración y errores por herramienta; latencia por etapa.
* **Seguridad**: intentos de inyección detectados y bloqueados.
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.observability import AgentRun, AgentSpan

SLO_P95_MS = float(os.getenv("SLO_P95_MS", "8000"))
SLO_ERROR_RATE = float(os.getenv("SLO_ERROR_RATE", "0.05"))
SLO_GROUNDED = float(os.getenv("SLO_GROUNDED", "0.95"))
SLO_FALLBACK_RATE = float(os.getenv("SLO_FALLBACK_RATE", "0.20"))


def percentile(values: list[float], q: float) -> float | None:
    """Percentil con interpolación lineal (igual que numpy por defecto)."""
    if not values:
        return None
    data = sorted(values)
    pos = (len(data) - 1) * q
    low = int(pos)
    high = min(low + 1, len(data) - 1)
    return round(data[low] + (data[high] - data[low]) * (pos - low), 1)


def _latency(values: list[float]) -> dict[str, Any]:
    return {"n": len(values), "p50": percentile(values, 0.5), "p95": percentile(values, 0.95), "p99": percentile(values, 0.99),
            "mean": round(sum(values) / len(values), 1) if values else None, "max": round(max(values), 1) if values else None}


def _rate(part: int, total: int) -> float | None:
    return round(part / total, 4) if total else None


def load_runs(db: Session, *, hours: float | None = 24 * 7, flow: str | None = None, eval_tag: str | None = None, include_eval: bool = False) -> list[AgentRun]:
    stmt = select(AgentRun).order_by(AgentRun.started_at)
    if hours:
        stmt = stmt.where(AgentRun.started_at >= datetime.now(timezone.utc) - timedelta(hours=hours))
    if flow:
        stmt = stmt.where(AgentRun.flow == flow)
    if eval_tag:
        stmt = stmt.where(AgentRun.eval_tag == eval_tag)
    elif not include_eval:
        stmt = stmt.where(AgentRun.eval_tag.is_(None))
    return list(db.scalars(stmt))


def summarize(runs: list[AgentRun], spans: list[AgentSpan]) -> dict[str, Any]:
    total = len(runs)
    status = Counter(r.status for r in runs)
    answered = [r for r in runs if r.status in ("ok", "fallback")]
    cited = [r for r in runs if ((r.quality or {}).get("precios") or {}).get("cited")]
    grounded = [r for r in cited if (r.quality or {}).get("precios", {}).get("ok")]
    llm_runs = [r for r in runs if r.llm_calls]

    by_flow: dict[str, Any] = {}
    for flow in sorted({r.flow for r in runs}):
        subset = [r for r in runs if r.flow == flow]
        by_flow[flow] = {"runs": len(subset), "latency_ms": _latency([r.latency_ms for r in subset if r.status != "blocked"]),
                         "error_rate": _rate(sum(r.status == "error" for r in subset), len(subset)),
                         "fallback_rate": _rate(sum(r.status == "fallback" for r in subset), len(subset))}

    tools: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "errors": 0, "durations": []})
    stages: dict[str, list[float]] = defaultdict(list)
    llm_durations: list[float] = []
    for span in spans:
        if span.kind == "tool":
            tools[span.name]["calls"] += 1
            tools[span.name]["errors"] += span.status == "error"
            tools[span.name]["durations"].append(span.duration_ms)
        elif span.kind == "stage":
            stages[span.name].append(span.duration_ms)
        elif span.kind == "llm":
            llm_durations.append(span.duration_ms)

    return {
        "runs": total,
        "status": dict(status),
        "error_rate": _rate(status.get("error", 0), total),
        "fallback_rate": _rate(status.get("fallback", 0), total),
        "latency_ms": _latency([r.latency_ms for r in answered]),
        "by_flow": by_flow,
        "llm": {
            "calls": sum(r.llm_calls for r in runs), "calls_per_run": round(sum(r.llm_calls for r in llm_runs) / len(llm_runs), 2) if llm_runs else None,
            "latency_ms": _latency(llm_durations),
            "input_tokens": sum(r.input_tokens for r in runs), "output_tokens": sum(r.output_tokens for r in runs),
            "tokens_per_run": round(sum(r.input_tokens + r.output_tokens for r in llm_runs) / len(llm_runs), 1) if llm_runs else None,
            "errors": sum(1 for s in spans if s.kind == "llm" and s.status == "error"),
        },
        "cpu_ms": _latency([r.cpu_ms for r in runs if r.cpu_ms is not None]),
        "tools": {name: {"calls": t["calls"], "errors": t["errors"], "error_rate": _rate(t["errors"], t["calls"]), "p50_ms": percentile(t["durations"], 0.5),
                         "p95_ms": percentile(t["durations"], 0.95)} for name, t in sorted(tools.items(), key=lambda kv: -kv[1]["calls"])},
        "stages": {name: {"n": len(v), "p50_ms": percentile(v, 0.5), "p95_ms": percentile(v, 0.95)} for name, v in stages.items()},
        "quality": {
            "answers_with_prices": len(cited), "grounded_rate": _rate(len(grounded), len(cited)),
            "unsupported_prices": sum(len((r.quality or {}).get("precios", {}).get("unsupported") or []) for r in cited),
            "explanations_discarded": sum(1 for r in runs if (r.quality or {}).get("explicacion_descartada")),
            "invented_budget_discarded": sum(1 for r in runs if (r.quality or {}).get("presupuesto_inventado_descartado")),
            "replans": sum(r.replans for r in runs), "tool_errors": sum(r.tool_errors for r in runs),
        },
        "security": {
            "injection_detected": sum(1 for r in runs if (r.guardrails or {}).get("injection")),
            "blocked": status.get("blocked", 0),
        },
    }


def slo_status(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Objetivos de servicio con su estado: ok, alerta o sin_datos. Son las alertas del panel."""
    p95 = summary["latency_ms"]["p95"]
    checks = [
        ("latencia_p95", "Latencia p95 de punta a punta", p95, SLO_P95_MS, "<=", "ms"),
        ("tasa_error", "Tasa de error", summary["error_rate"], SLO_ERROR_RATE, "<=", "ratio"),
        ("tasa_respaldo", "Respuestas con respaldo (modelo caído o descartado)", summary["fallback_rate"], SLO_FALLBACK_RATE, "<=", "ratio"),
        ("precios_respaldados", "Precios citados con respaldo en datos", summary["quality"]["grounded_rate"], SLO_GROUNDED, ">=", "ratio"),
    ]
    out = []
    for key, label, value, target, op, unit in checks:
        if value is None:
            state = "sin_datos"
        else:
            state = "ok" if (value <= target if op == "<=" else value >= target) else "alerta"
        out.append({"key": key, "label": label, "value": value, "target": target, "op": op, "unit": unit, "state": state})
    return out


def timeseries(runs: list[AgentRun], bucket_minutes: int = 60) -> list[dict[str, Any]]:
    buckets: dict[datetime, list[AgentRun]] = defaultdict(list)
    for run in runs:
        started = run.started_at if run.started_at.tzinfo else run.started_at.replace(tzinfo=timezone.utc)
        minute = (started.minute // bucket_minutes) * bucket_minutes if bucket_minutes < 60 else 0
        buckets[started.replace(minute=minute, second=0, microsecond=0)].append(run)
    out = []
    for when in sorted(buckets):
        group = buckets[when]
        out.append({"t": when.isoformat(), "runs": len(group), "p50_ms": percentile([r.latency_ms for r in group], 0.5), "p95_ms": percentile([r.latency_ms for r in group], 0.95),
                    "errors": sum(r.status == "error" for r in group), "fallbacks": sum(r.status == "fallback" for r in group),
                    "tokens": sum(r.input_tokens + r.output_tokens for r in group)})
    return out


def run_view(run: AgentRun) -> dict[str, Any]:
    return {"run_id": run.run_id, "flow": run.flow, "started_at": run.started_at.isoformat() if run.started_at else None, "latency_ms": run.latency_ms,
            "status": run.status, "error_type": run.error_type, "model": run.model, "llm_calls": run.llm_calls, "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens, "tool_calls": run.tool_calls, "tool_errors": run.tool_errors, "tools": run.tools, "replans": run.replans,
            "input_preview": run.input_preview, "guardrails": run.guardrails, "quality": run.quality, "eval_tag": run.eval_tag, "user_hash": run.user_hash}


def dashboard(db: Session, *, hours: float | None = 24 * 7, flow: str | None = None, include_eval: bool = False, eval_tag: str | None = None) -> dict[str, Any]:
    runs = load_runs(db, hours=hours, flow=flow, include_eval=include_eval, eval_tag=eval_tag)
    ids = [r.run_id for r in runs]
    spans: list[AgentSpan] = []
    for i in range(0, len(ids), 500):
        spans += list(db.scalars(select(AgentSpan).where(AgentSpan.run_id.in_(ids[i : i + 500]))))
    summary = summarize(runs, spans)
    bucket = 60 if not hours or hours > 48 else 15
    return {"window_hours": hours, "flow": flow, "generated_at": datetime.now(timezone.utc).isoformat(), "summary": summary, "slo": slo_status(summary),
            "timeseries": timeseries(runs, bucket), "recent": [run_view(r) for r in reversed(runs[-25:])]}


def prometheus_text(summary: dict[str, Any]) -> str:
    """Exposición en formato de texto de Prometheus (sin dependencias) para conectar Grafana u otra herramienta."""
    lines = ["# HELP todobarato_ai_runs_total Ejecuciones de IA por estado", "# TYPE todobarato_ai_runs_total gauge"]
    for status, count in summary["status"].items():
        lines.append(f'todobarato_ai_runs_total{{status="{status}"}} {count}')
    lines += ["# HELP todobarato_ai_latency_ms Latencia de punta a punta por flujo", "# TYPE todobarato_ai_latency_ms summary"]
    for flow, data in summary["by_flow"].items():
        for q in ("p50", "p95", "p99"):
            value = data["latency_ms"][q]
            if value is not None:
                lines.append(f'todobarato_ai_latency_ms{{flow="{flow}",quantile="0.{q[1:]}"}} {value}')
    lines += ["# TYPE todobarato_ai_tokens_total gauge", f'todobarato_ai_tokens_total{{kind="input"}} {summary["llm"]["input_tokens"]}',
              f'todobarato_ai_tokens_total{{kind="output"}} {summary["llm"]["output_tokens"]}', "# TYPE todobarato_ai_tool_calls_total gauge"]
    for name, data in summary["tools"].items():
        lines.append(f'todobarato_ai_tool_calls_total{{tool="{name}"}} {data["calls"]}')
        lines.append(f'todobarato_ai_tool_errors_total{{tool="{name}"}} {data["errors"]}')
    if summary["quality"]["grounded_rate"] is not None:
        lines += ["# TYPE todobarato_ai_grounded_ratio gauge", f'todobarato_ai_grounded_ratio {summary["quality"]["grounded_rate"]}']
    lines += ["# TYPE todobarato_ai_injection_detected_total gauge", f'todobarato_ai_injection_detected_total {summary["security"]["injection_detected"]}']
    return "\n".join(lines) + "\n"
