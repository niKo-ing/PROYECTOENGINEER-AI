"""Análisis de logs de la IA: patrones de error, ejecuciones lentas, herramientas que fallan y fuga de datos.

Lee las trazas desde el archivo JSONL (``TRACE_LOG_FILE``, por defecto ``logs/trazas.jsonl``) o desde la base
(``--db``) y escribe un informe en Markdown:

* volumen y estados por flujo; latencia p50/p95/p99;
* errores agrupados por tipo y mensaje, y respaldos (modelo caído o explicación descartada);
* ejecuciones anómalas: más lentas que 2× el p95 de su flujo (umbral robusto, no una media);
* herramientas con más errores y etapas más lentas;
* intentos de inyección por hora;
* **auditoría de privacidad**: busca correos, RUT, teléfonos, tarjetas o llaves en lo registrado (debe dar 0).

Uso::

    .venv/bin/python -m scripts.analizar_trazas                      # desde logs/trazas.jsonl
    DATABASE_URL=sqlite:///./todobarato.db .venv/bin/python -m scripts.analizar_trazas --db --horas 48
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.observability.metrics import percentile  # noqa: E402
from app.observability.redaction import redact  # noqa: E402


def from_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for file in sorted(path.parent.glob(path.name + "*")):  # incluye los archivos rotados (.1, .2…)
        for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if data.get("evento") == "ejecucion_ia":
                rows.append(data)
    return rows


def from_db(hours: float, include_eval: bool) -> list[dict[str, Any]]:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from app.db import SessionLocal
    from app.observability.metrics import load_runs, run_view

    with SessionLocal() as db:
        runs = load_runs(db, hours=hours, include_eval=include_eval)
        return [run_view(r) | {"error_message": r.error_message, "extra": r.extra, "ts": r.started_at.isoformat() if r.started_at else ""} for r in runs]


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    flows = defaultdict(list)
    for row in rows:
        flows[row.get("flow", "?")].append(row)
    per_flow = {}
    anomalies = []
    for flow, items in flows.items():
        lat = [r.get("latency_ms") or 0 for r in items if r.get("status") != "blocked"]
        p95 = percentile(lat, 0.95)
        per_flow[flow] = {"runs": len(items), "status": dict(Counter(r.get("status") for r in items)), "p50": percentile(lat, 0.5), "p95": p95, "p99": percentile(lat, 0.99)}
        if p95 and len(lat) >= 10:
            anomalies += [{"run_id": r.get("run_id"), "flow": flow, "latency_ms": r.get("latency_ms"), "umbral_ms": round(2 * p95, 1), "tools": r.get("tools")}
                          for r in items if (r.get("latency_ms") or 0) > 2 * p95]
    errors = Counter((r.get("error_type") or "desconocido") for r in rows if r.get("status") == "error")
    fallbacks = Counter(((r.get("extra") or {}).get("llm_error") or ("explicacion_descartada" if (r.get("quality") or {}).get("explicacion_descartada") else "otro"))
                        for r in rows if r.get("status") == "fallback")
    tools = Counter(t for r in rows for t in (r.get("tools") or []))
    injections = Counter((r.get("ts") or "")[:13] for r in rows if (r.get("guardrails") or {}).get("injection"))
    unsupported = [(r.get("run_id"), (r.get("quality") or {}).get("precios", {}).get("unsupported")) for r in rows
                   if (r.get("quality") or {}).get("precios", {}).get("unsupported")]

    leaks = Counter()
    for r in rows:
        blob = json.dumps({k: v for k, v in r.items() if k not in ("user_hash", "run_id")}, ensure_ascii=False)
        for kind in redact(blob)[1]:
            leaks[kind] += 1
    return {"total": len(rows), "per_flow": per_flow, "errors": errors.most_common(10), "fallbacks": fallbacks.most_common(10), "anomalies": anomalies[:20],
            "tools": tools.most_common(15), "tool_error_runs": sum(1 for r in rows if r.get("tool_errors")), "injections": sorted(injections.items()),
            "unsupported_prices": unsupported[:20], "leaks": dict(leaks), "replans": sum(r.get("replans") or 0 for r in rows)}


def to_markdown(a: dict[str, Any], source: str) -> str:
    out = [f"# Análisis de trazas de la IA", "", f"Fuente: `{source}` · Ejecuciones: **{a['total']}**", "", "## Volumen y latencia por flujo", "",
           "| Flujo | Ejecuciones | Estados | p50 ms | p95 ms | p99 ms |", "|---|---|---|---|---|---|"]
    for flow, d in sorted(a["per_flow"].items()):
        out.append(f"| {flow} | {d['runs']} | {', '.join(f'{k}: {v}' for k, v in d['status'].items())} | {d['p50']} | {d['p95']} | {d['p99']} |")
    out += ["", "## Errores", ""] + ([f"- `{k}`: {v}" for k, v in a["errors"]] or ["- Sin errores."])
    out += ["", "## Respuestas con respaldo (reglas)", ""] + ([f"- `{k}`: {v}" for k, v in a["fallbacks"]] or ["- Ninguna."])
    out += ["", "## Ejecuciones anómalas (> 2 × p95 del flujo)", ""] + ([f"- {x['run_id']} ({x['flow']}): {x['latency_ms']} ms, umbral {x['umbral_ms']} ms, herramientas {x['tools']}" for x in a["anomalies"]] or ["- Ninguna."])
    out += ["", "## Herramientas más usadas", ""] + [f"- {t}: {n}" for t, n in a["tools"]]
    out += [f"", f"Ejecuciones con algún error de herramienta: {a['tool_error_runs']} · Replanificaciones: {a['replans']}"]
    out += ["", "## Precios sin respaldo detectados", ""] + ([f"- {rid}: {vals}" for rid, vals in a["unsupported_prices"]] or ["- Ninguno."])
    out += ["", "## Intentos de inyección por hora", ""] + ([f"- {h}: {n}" for h, n in a["injections"]] or ["- Ninguno."])
    out += ["", "## Auditoría de privacidad", ""]
    out.append("- Sin datos personales en los registros (correos, RUT, teléfonos, tarjetas ni llaves)." if not a["leaks"] else f"- ⚠ Posibles datos personales: {a['leaks']}")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archivo", default=str(ROOT / "logs" / "trazas.jsonl"))
    parser.add_argument("--db", action="store_true", help="leer desde agent_runs en vez del archivo")
    parser.add_argument("--horas", type=float, default=24 * 7)
    parser.add_argument("--incluir-eval", action="store_true")
    parser.add_argument("--salida", default="")
    args = parser.parse_args()
    rows = from_db(args.horas, args.incluir_eval) if args.db else from_jsonl(Path(args.archivo))
    report = to_markdown(analyze(rows), "agent_runs" if args.db else args.archivo)
    if args.salida:
        Path(args.salida).write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
