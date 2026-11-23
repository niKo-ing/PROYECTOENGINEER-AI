"""Evaluación del asistente de armado y del agente con escenarios variables.

Mide, por modo (``gemini`` y ``reglas``):

* **exactitud del estado** (armó / preguntó / bloqueó cuando correspondía),
* **exactitud de la extracción** (uso, presupuesto, marcas y preferencias),
* **compatibilidad** y **respeto del presupuesto** de los armados,
* **precisión factual de precios** (precios citados con respaldo en los datos),
* **latencia** p50/p95, llamadas al modelo y tokens,
* **consistencia** entre repeticiones (mismo estado, mismas necesidades, mismas piezas),
* **tasa de respaldo** (el modelo falló o fue descartado y respondieron las reglas).

Uso::

    DATABASE_URL=sqlite:///./todobarato.db .venv/bin/python -m scripts.evaluar_ia --modos gemini,reglas --repeticiones 3 --agente

Cada ejecución queda en ``agent_runs`` con la etiqueta ``eval_tag`` (no se mezcla con el tráfico real del panel).
Resultados: ``evals/resultados/<etiqueta>.json`` (crudo) y ``.md`` (resumen).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models.observability import AgentRun  # noqa: E402
from app.observability.metrics import percentile  # noqa: E402
from app.pcbuilder.assistant import AssistantIn, PcAssistant  # noqa: E402
from app.pcbuilder.catalog import ensure_seeded  # noqa: E402
from app.pcbuilder.guides import seed_guides  # noqa: E402

EVAL_USER = "evaluador-ia"
SYNTHETIC_REPLY = "Entendido. ¿Algo más que deba saber?"


def build_payload(messages: list[str]) -> AssistantIn:
    turns = []
    for i, text in enumerate(messages):
        if i:
            turns.append({"role": "assistant", "content": SYNTHETIC_REPLY})
        turns.append({"role": "user", "content": text})
    return AssistantIn(messages=turns)


def score_assistant(case: dict[str, Any], result: dict[str, Any], run: AgentRun | None) -> dict[str, Any]:
    expected = case["esperado"]
    needs = result.get("needs") or {}
    fields = [k for k in ("use_case", "budget_clp", "cpu_brand", "gpu_brand", "small", "wifi") if k in expected]
    field_hits = {k: needs.get(k) == expected[k] for k in fields}
    if "use_case_any" in expected:
        field_hits["use_case"] = needs.get("use_case") in expected["use_case_any"]
        fields.append("use_case")
    rec = result.get("recommendation")
    out: dict[str, Any] = {
        "estado": result["state"], "estado_ok": result["state"] == expected["estado"],
        "campos": field_hits, "extraccion_ok": all(field_hits.values()) if fields else None,
        "falta_ok": (sorted(result.get("missing") or []) == sorted(expected["falta"])) if "falta" in expected else None,
        "compatible": rec["report"]["compatible"] if rec else None, "en_presupuesto": rec["within_budget"] if rec else None,
        "piezas": sorted(i["product_id"] for i in rec["items"]) if rec else [], "needs": needs,
        "explicado_por": result.get("explained_by"), "fuente": result.get("source"), "respuesta": result.get("answer", "")[:600],
    }
    if "sin_precio" in expected:
        out["no_repite_precio_falso"] = f"${expected['sin_precio']} " not in (result.get("answer") or "") + " "
    if run is not None:
        precios = (run.quality or {}).get("precios") or {}
        out.update(latency_ms=run.latency_ms, llm_calls=run.llm_calls, tokens=run.input_tokens + run.output_tokens, status=run.status,
                   precios_citados=precios.get("cited", 0), precios_ok=precios.get("ok") if precios.get("cited") else None,
                   llm_error=(run.extra or {}).get("llm_error"), descartada=bool((run.quality or {}).get("explicacion_descartada")))
    return out


def run_assistant_case(db, case, mode, tag, llm, pause) -> dict[str, Any]:
    attempts = 0
    while True:
        attempts += 1
        result = PcAssistant(db, EVAL_USER, llm if mode == "gemini" else None).run(build_payload(case["mensajes"]), eval_tag=tag)
        db.expire_all()
        run = db.scalar(select(AgentRun).where(AgentRun.run_id == result["run_id"]))
        rate_limited = mode == "gemini" and run is not None and (run.extra or {}).get("llm_error") and attempts < 3
        if not rate_limited:
            break
        print(f"    el modelo falló ({run.extra['llm_error']}); reintento en 30 s", flush=True)
        time.sleep(30)
    scored = score_assistant(case, result, run) | {"intentos": attempts}
    if mode == "gemini":
        time.sleep(pause)
    return scored


def run_agent_case(db, case, tag, llm, pause) -> dict[str, Any]:
    from langgraph.checkpoint.memory import MemorySaver

    from app.agent.service import AgentService
    from app.ai.rag.factory import get_embedding_provider

    expected = case["esperado"]
    started = time.perf_counter()
    try:
        result = AgentService(db, EVAL_USER, llm=llm, embedder=get_embedding_provider(), checkpointer=MemorySaver()).run(case["mensaje"], eval_tag=tag)
    except Exception as error:  # noqa: BLE001
        time.sleep(pause)
        return {"error": f"{type(error).__name__}: {str(error)[:200]}", "latency_ms": (time.perf_counter() - started) * 1000, "ok": False}
    db.expire_all()
    run = db.scalar(select(AgentRun).where(AgentRun.run_id == result.run_id))
    used = result.tools_used
    out = {
        "herramientas": used, "herramientas_ok": all(t in used for t in expected.get("herramientas", [])),
        "escritura_ok": (not result.wrote) if expected.get("no_escribe") else all(t in result.wrote for t in expected.get("escribe", [])),
        "menciona_ok": all(m.lower() in result.answer.lower() for m in expected.get("menciona", [])),
        "precios_ok": result.grounding.get("ok") if result.grounding.get("cited") else None, "precios_citados": result.grounding.get("cited", 0),
        "replans": result.replans, "pasos": result.steps, "respuesta": result.answer[:600],
        "latency_ms": run.latency_ms if run else None, "llm_calls": run.llm_calls if run else None, "tokens": (run.input_tokens + run.output_tokens) if run else None,
        "status": run.status if run else None,
    }
    out["ok"] = out["herramientas_ok"] and out["escritura_ok"] and out["menciona_ok"] and out["precios_ok"] is not False
    if expected.get("escribe"):  # limpiar lo que guardó el agente de prueba
        from app.models.pc import PcBuild

        for pc in db.scalars(select(PcBuild).where(PcBuild.user_id == EVAL_USER)):
            db.delete(pc)
        db.commit()
    time.sleep(pause)
    return out


def ratio(values: list[Any]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(bool(v) for v in vals) / len(vals), 4) if vals else None


def summarize_mode(rows: list[dict[str, Any]], reps: int) -> dict[str, Any]:
    by_case: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_case[row["id"]].append(row)
    consistency_state, consistency_needs, consistency_parts = [], [], []
    for runs in by_case.values():
        if len(runs) < 2:
            continue
        consistency_state.append(len({r["estado"] for r in runs}) == 1)
        consistency_needs.append(len({json.dumps(r["needs"], sort_keys=True) for r in runs}) == 1)
        if all(r["piezas"] for r in runs):
            consistency_parts.append(len({tuple(r["piezas"]) for r in runs}) == 1)
    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None and r["estado"] != "blocked"]
    by_category: dict[str, list[bool]] = defaultdict(list)
    by_set: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        hit = r["estado_ok"] and r["extraccion_ok"] is not False and r["falta_ok"] is not False
        by_category[r["categoria"]].append(hit)
        by_set[r.get("conjunto", "desarrollo")].append(hit)
    return {
        "ejecuciones": len(rows), "repeticiones": reps,
        "exactitud_estado": ratio([r["estado_ok"] for r in rows]),
        "exactitud_extraccion": ratio([r["extraccion_ok"] for r in rows]),
        "exactitud_falta": ratio([r["falta_ok"] for r in rows]),
        "exactitud_por_campo": {k: ratio([r["campos"].get(k) for r in rows if k in r["campos"]]) for k in ("use_case", "budget_clp", "cpu_brand", "gpu_brand", "small", "wifi")},
        "armados_compatibles": ratio([r["compatible"] for r in rows]),
        "armados_en_presupuesto": ratio([r["en_presupuesto"] for r in rows]),
        "precios_respaldados": ratio([r.get("precios_ok") for r in rows]),
        "explicaciones_descartadas": sum(1 for r in rows if r.get("descartada")),
        "tasa_respaldo": ratio([r.get("status") == "fallback" for r in rows]),
        "no_repite_precio_falso": ratio([r.get("no_repite_precio_falso") for r in rows]),
        "latencia_ms": {"p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95), "media": round(statistics.mean(latencies), 1) if latencies else None},
        "llamadas_modelo_por_ejecucion": round(statistics.mean([r.get("llm_calls") or 0 for r in rows]), 2) if rows else None,
        "tokens_por_ejecucion": round(statistics.mean([r.get("tokens") or 0 for r in rows]), 1) if rows else None,
        "consistencia_estado": ratio(consistency_state), "consistencia_necesidades": ratio(consistency_needs), "consistencia_piezas": ratio(consistency_parts),
        "exactitud_por_categoria": {k: ratio(v) for k, v in sorted(by_category.items())},
        "exactitud_por_conjunto": {k: ratio(v) for k, v in sorted(by_set.items())},
        "fallos": [{"id": r["id"], "rep": r["rep"], "estado": r["estado"], "needs": r["needs"], "campos": r["campos"]} for r in rows
                   if not (r["estado_ok"] and r["extraccion_ok"] is not False and r["falta_ok"] is not False)],
    }


def summarize_agent(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms")]
    return {"ejecuciones": len(rows), "exito": ratio([r.get("ok") for r in rows]), "herramientas_correctas": ratio([r.get("herramientas_ok") for r in rows]),
            "escritura_correcta": ratio([r.get("escritura_ok") for r in rows]), "precios_respaldados": ratio([r.get("precios_ok") for r in rows]),
            "errores": sum(1 for r in rows if r.get("error")), "replanificaciones": sum(r.get("replans") or 0 for r in rows),
            "latencia_ms": {"p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95)},
            "llamadas_modelo_por_ejecucion": round(statistics.mean([r.get("llm_calls") or 0 for r in rows]), 2) if rows else None,
            "tokens_por_ejecucion": round(statistics.mean([r.get("tokens") or 0 for r in rows]), 1) if rows else None}


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f} %"


def markdown(report: dict[str, Any]) -> str:
    lines = [f"# Evaluación de la IA — {report['etiqueta']}", "", f"Fecha: {report['fecha']} · Modelo: `{report['modelo']}` · Escenarios del asistente: {report['escenarios']} · "
             f"Repeticiones: {report['repeticiones']}", "", "## Asistente de armado", "",
             "| Métrica | " + " | ".join(report["modos"]) + " |", "|---|" + "---|" * len(report["modos"])]
    lines.append("| **Acierto total, conjunto de desarrollo** | " + " | ".join(pct(report["asistente"][m]["exactitud_por_conjunto"].get("desarrollo")) for m in report["modos"]) + " |")
    lines.append("| **Acierto total, conjunto de prueba (no visto)** | " + " | ".join(pct(report["asistente"][m]["exactitud_por_conjunto"].get("prueba")) for m in report["modos"]) + " |")
    rows = [("Exactitud del estado", "exactitud_estado", pct), ("Exactitud de la extracción", "exactitud_extraccion", pct), ("Pregunta lo que falta", "exactitud_falta", pct),
            ("Armados compatibles", "armados_compatibles", pct), ("Armados dentro del presupuesto", "armados_en_presupuesto", pct),
            ("Precios citados con respaldo", "precios_respaldados", pct), ("Tasa de respaldo (reglas)", "tasa_respaldo", pct),
            ("Consistencia del estado", "consistencia_estado", pct), ("Consistencia de las necesidades", "consistencia_necesidades", pct),
            ("Consistencia de las piezas", "consistencia_piezas", pct)]
    for label, key, fmt in rows:
        lines.append(f"| {label} | " + " | ".join(fmt(report["asistente"][m][key]) for m in report["modos"]) + " |")
    for label, key in (("Latencia p50 (ms)", "p50"), ("Latencia p95 (ms)", "p95")):
        lines.append(f"| {label} | " + " | ".join(str(report["asistente"][m]["latencia_ms"][key]) for m in report["modos"]) + " |")
    lines.append("| Llamadas al modelo por ejecución | " + " | ".join(str(report["asistente"][m]["llamadas_modelo_por_ejecucion"]) for m in report["modos"]) + " |")
    lines.append("| Tokens por ejecución | " + " | ".join(str(report["asistente"][m]["tokens_por_ejecucion"]) for m in report["modos"]) + " |")
    lines += ["", "### Exactitud por categoría", "", "| Categoría | " + " | ".join(report["modos"]) + " |", "|---|" + "---|" * len(report["modos"])]
    categories = sorted({c for m in report["modos"] for c in report["asistente"][m]["exactitud_por_categoria"]})
    for cat in categories:
        lines.append(f"| {cat} | " + " | ".join(pct(report["asistente"][m]["exactitud_por_categoria"].get(cat)) for m in report["modos"]) + " |")
    for m in report["modos"]:
        fallos = report["asistente"][m]["fallos"]
        if fallos:
            lines += ["", f"### Casos fallidos ({m})", ""] + [f"- {f['id']} (rep {f['rep']}): estado `{f['estado']}`, necesidades `{json.dumps(f['needs'], ensure_ascii=False)}`" for f in fallos]
    if report.get("agente"):
        a = report["agente"]
        lines += ["", "## Agente (Gemini + herramientas)", "", "| Métrica | Valor |", "|---|---|", f"| Éxito | {pct(a['exito'])} |",
                  f"| Herramientas correctas | {pct(a['herramientas_correctas'])} |", f"| Escritura correcta (solo si se pidió) | {pct(a['escritura_correcta'])} |",
                  f"| Precios con respaldo | {pct(a['precios_respaldados'])} |", f"| Errores | {a['errores']} |", f"| Replanificaciones | {a['replanificaciones']} |",
                  f"| Latencia p50 / p95 (ms) | {a['latencia_ms']['p50']} / {a['latencia_ms']['p95']} |",
                  f"| Llamadas al modelo por ejecución | {a['llamadas_modelo_por_ejecucion']} |", f"| Tokens por ejecución | {a['tokens_por_ejecucion']} |"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--modos", default="gemini,reglas")
    parser.add_argument("--repeticiones", type=int, default=3)
    parser.add_argument("--agente", action="store_true", help="evaluar también el agente (gasta ~5 llamadas por escenario)")
    parser.add_argument("--repeticiones-agente", type=int, default=2)
    parser.add_argument("--pausa", type=float, default=2.0, help="segundos entre llamadas a Gemini (cuota)")
    parser.add_argument("--solo", default="", help="ids separados por coma")
    parser.add_argument("--etiqueta", default="")
    parser.add_argument("--salida", default=str(ROOT / "evals" / "resultados"))
    args = parser.parse_args()

    spec = json.loads((ROOT / "evals" / "escenarios.json").read_text(encoding="utf-8"))
    cases = [c for c in spec["asistente"] if not args.solo or c["id"] in args.solo.split(",")]
    modes = [m.strip() for m in args.modos.split(",") if m.strip()]
    tag = args.etiqueta or f"eval-{datetime.now():%Y%m%d-%H%M}"
    os.environ.setdefault("TRACE_LOG_FILE", str(ROOT / "logs" / "trazas.jsonl"))

    llm = None
    if "gemini" in modes or args.agente:
        from app.agent.llm import get_chat_model

        llm = get_chat_model(temperature=0.2)

    db = SessionLocal()
    ensure_seeded(db)
    seed_guides(db)
    report: dict[str, Any] = {"etiqueta": tag, "fecha": datetime.now().isoformat(timespec="seconds"), "modelo": os.getenv("GEMINI_MODEL", ""), "escenarios": len(cases),
                              "repeticiones": args.repeticiones, "modos": modes, "asistente": {}, "crudo": {}}
    for mode in modes:
        rows = []
        reps = args.repeticiones if mode == "gemini" else 1  # las reglas son deterministas
        for rep in range(1, reps + 1):
            for case in cases:
                row = run_assistant_case(db, case, mode, f"{tag}:{mode}", llm, args.pausa) | {"id": case["id"], "categoria": case["categoria"], "conjunto": case.get("conjunto", "desarrollo"), "rep": rep}
                rows.append(row)
                mark = "✓" if row["estado_ok"] and row["extraccion_ok"] is not False and row["falta_ok"] is not False else "✗"
                print(f"[{mode} r{rep}] {case['id']} {mark} estado={row['estado']} needs={row['needs']} {row.get('latency_ms', 0):.0f} ms", flush=True)
        report["asistente"][mode] = summarize_mode(rows, reps)
        report["crudo"][mode] = rows

    if args.agente:
        rows = []
        for rep in range(1, args.repeticiones_agente + 1):
            for case in spec["agente"]:
                row = run_agent_case(db, case, f"{tag}:agente", llm, args.pausa) | {"id": case["id"], "categoria": case["categoria"], "rep": rep}
                rows.append(row)
                print(f"[agente r{rep}] {case['id']} {'✓' if row.get('ok') else '✗'} {row.get('herramientas') or row.get('error')} {row.get('latency_ms') or 0:.0f} ms", flush=True)
        report["agente"] = summarize_agent(rows)
        report["crudo"]["agente"] = rows

    out_dir = Path(args.salida)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{tag}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / f"{tag}.md").write_text(markdown(report), encoding="utf-8")
    print("\n" + markdown(report))
    print(f"Guardado en {out_dir / (tag + '.json')} y .md")
    print("Resumen de estados:", {m: dict(Counter(r["estado"] for r in report["crudo"][m])) for m in modes})


if __name__ == "__main__":
    main()
