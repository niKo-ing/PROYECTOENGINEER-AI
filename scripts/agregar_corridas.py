"""Junta varias corridas independientes de ``scripts/evaluar_ia.py`` y calcula media y desviación estándar.

Cada corrida debe ser «limpia»: base nueva y ``--repeticiones 1``. Así la variación entre corridas mide lo que cambia
Gemini de una vez a otra, y no el estado que dejó una corrida anterior. Las métricas se calculan desde las filas crudas
de cada corrida (``crudo``), filtradas por conjunto, con la misma definición de acierto que ``evaluar_ia.py``.

    python -m scripts.agregar_corridas --conjunto prueba-3 --salida evals/resultados/eval-2026-11-23-prueba3 \\
        corrida1.json corrida2.json corrida3.json

Escribe ``<salida>.json`` y ``<salida>.md``. La desviación estándar es la muestral (n − 1).
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

# Mismo percentil que el panel y evaluar_ia.py (interpolación lineal, igual a numpy).
from app.observability.metrics import percentile


def _hit(row: dict[str, Any]) -> bool:
    return bool(row["estado_ok"]) and row["extraccion_ok"] is not False and row["falta_ok"] is not False


def _mean(values: list[Any]) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def _ratio(values: list[Any]) -> float | None:
    values = [bool(v) for v in values if v is not None]
    return sum(values) / len(values) if values else None


# (clave, etiqueta, tipo): «pct» se muestra en %, «ms» en milisegundos, «num» tal cual.
METRICS: list[tuple[str, str, str]] = [
    ("acierto", "Acierto total", "pct"),
    ("estado", "Exactitud del estado", "pct"),
    ("extraccion", "Exactitud de la extracción", "pct"),
    ("falta", "Pregunta lo que falta", "pct"),
    ("compatibles", "Armados compatibles", "pct"),
    ("en_presupuesto", "Armados dentro del presupuesto", "pct"),
    ("precios", "Precios citados con respaldo", "pct"),
    ("respaldo", "Tasa de respaldo (reglas)", "pct"),
    ("p50", "Latencia p50", "ms"),
    ("p95", "Latencia p95", "ms"),
    ("llamadas", "Llamadas al modelo por ejecución", "num"),
    ("tokens", "Tokens por ejecución", "num"),
]


def run_metrics(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None and r["estado"] != "blocked"]
    return {
        "acierto": _ratio([_hit(r) for r in rows]),
        "estado": _ratio([r["estado_ok"] for r in rows]),
        "extraccion": _ratio([r["extraccion_ok"] for r in rows]),
        "falta": _ratio([r["falta_ok"] for r in rows]),
        "compatibles": _ratio([r["compatible"] for r in rows]),
        "en_presupuesto": _ratio([r["en_presupuesto"] for r in rows]),
        "precios": _ratio([r.get("precios_ok") for r in rows]),
        "respaldo": _ratio([r.get("status") == "fallback" for r in rows]),
        "p50": percentile(latencies, 0.5) if latencies else None,
        "p95": percentile(latencies, 0.95) if latencies else None,
        "llamadas": _mean([r.get("llm_calls") or 0 for r in rows]),
        "tokens": _mean([r.get("tokens") or 0 for r in rows]),
    }


def describe(values: list[float | None]) -> dict[str, float | None]:
    values = [v for v in values if v is not None]
    if not values:
        return {"media": None, "de": None, "min": None, "max": None, "n": 0}
    return {"media": statistics.mean(values), "de": statistics.stdev(values) if len(values) > 1 else 0.0,
            "min": min(values), "max": max(values), "n": len(values)}


def aggregate(reports: list[dict[str, Any]], conjunto: str) -> dict[str, Any]:
    modes = [m for m in reports[0]["modos"] if all(m in r["crudo"] for r in reports)]
    out: dict[str, Any] = {"conjunto": conjunto, "corridas": len(reports), "etiquetas": [r["etiqueta"] for r in reports],
                           "fechas": [r["fecha"] for r in reports], "modelo": reports[0]["modelo"], "modos": modes, "por_modo": {}}
    for mode in modes:
        runs = [[row for row in r["crudo"][mode] if row.get("conjunto") == conjunto] for r in reports]
        per_run = [run_metrics(rows) for rows in runs]
        ids = sorted({row["id"] for rows in runs for row in rows})
        cases = {}
        for case_id in ids:
            rows = [next((row for row in rr if row["id"] == case_id), None) for rr in runs]
            rows = [row for row in rows if row is not None]
            parts = [tuple(row["piezas"]) for row in rows]
            cases[case_id] = {
                "categoria": rows[0]["categoria"],
                "aciertos": [_hit(row) for row in rows],
                "estados": [row["estado"] for row in rows],
                "needs": [row["needs"] for row in rows],
                "campos": [row["campos"] for row in rows],
                "mismo_estado": len({row["estado"] for row in rows}) == 1,
                "mismas_necesidades": len({json.dumps(row["needs"], sort_keys=True) for row in rows}) == 1,
                "mismas_piezas": (len(set(parts)) == 1) if all(parts) else None,
            }
        out["por_modo"][mode] = {
            "por_corrida": per_run,
            "resumen": {key: describe([m[key] for m in per_run]) for key, _, _ in METRICS},
            "consistencia_entre_corridas": {
                "estado": _ratio([c["mismo_estado"] for c in cases.values()]),
                "necesidades": _ratio([c["mismas_necesidades"] for c in cases.values()]),
                "piezas": _ratio([c["mismas_piezas"] for c in cases.values()]),
            },
            "casos": cases,
        }
    return out


def _fmt(value: float | None, kind: str) -> str:
    if value is None:
        return "—"
    if kind == "pct":
        return f"{value * 100:.1f} %"
    if kind == "ms":
        return f"{value:,.0f} ms".replace(",", ".")
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if value < 100 else f"{value:,.0f}".replace(",", ".")


def _pm(desc: dict[str, float | None], kind: str) -> str:
    if desc["media"] is None:
        return "—"
    return f"{_fmt(desc['media'], kind)} ± {_fmt(desc['de'], kind)}"


def to_markdown(agg: dict[str, Any], preregistro: str | None) -> str:
    modes = agg["modos"]
    lines = [f"# Evaluación ciega «{agg['conjunto']}»: {agg['corridas']} corridas limpias", "",
             f"Modelo: `{agg['modelo']}` · Corridas: {', '.join(agg['etiquetas'])} · Fechas: {agg['fechas'][0]} a {agg['fechas'][-1]}"]
    if preregistro:
        lines.append(f"Pre-registro (casos y lo esperado, antes de correr): commit `{preregistro}`.")
    lines += ["", "Media ± desviación estándar muestral entre corridas (cada corrida: base nueva, 1 repetición por caso).", "",
              "| Métrica | " + " | ".join(modes) + " |", "|---|" + "---|" * len(modes)]
    for key, label, kind in METRICS:
        lines.append(f"| {label} | " + " | ".join(_pm(agg["por_modo"][m]["resumen"][key], kind) for m in modes) + " |")
    lines += ["", "**Por corrida (acierto total):** " + " · ".join(
        f"{m}: " + ", ".join(_fmt(r["acierto"], "pct") for r in agg["por_modo"][m]["por_corrida"]) for m in modes), ""]
    lines += ["### Consistencia entre corridas", "", "| | " + " | ".join(modes) + " |", "|---|" + "---|" * len(modes)]
    for key, label in (("estado", "Mismo estado en las 3"), ("necesidades", "Mismas necesidades (uso, presupuesto…)"), ("piezas", "Mismas piezas")):
        lines.append(f"| {label} | " + " | ".join(_fmt(agg["por_modo"][m]["consistencia_entre_corridas"][key], "pct") for m in modes) + " |")
    lines += ["", "### Caso por caso", "", "✓ = acierto en esa corrida.", "", "| Caso | Categoría | " + " | ".join(modes) + " |", "|---|---|" + "---|" * len(modes)]
    first = agg["por_modo"][modes[0]]["casos"]
    for case_id in first:
        cells = []
        for m in modes:
            case = agg["por_modo"][m]["casos"].get(case_id)
            cells.append("".join("✓" if h else "✗" for h in case["aciertos"]) if case else "—")
        lines.append(f"| {case_id} | {first[case_id]['categoria']} | " + " | ".join(cells) + " |")
    lines += ["", "### Fallos", ""]
    any_failure = False
    for m in modes:
        for case_id, case in agg["por_modo"][m]["casos"].items():
            for i, hit in enumerate(case["aciertos"]):
                if not hit:
                    any_failure = True
                    wrong = [k for k, ok in case["campos"][i].items() if not ok]
                    lines.append(f"* **{m} · {case_id} · corrida {i + 1}:** estado `{case['estados'][i]}`; necesidades "
                                 f"`{json.dumps(case['needs'][i], ensure_ascii=False)}`" + (f"; campos errados: {', '.join(wrong)}" if wrong else ""))
    if not any_failure:
        lines.append("Ninguno.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corridas", nargs="+", help="JSON de cada corrida de evaluar_ia.py")
    parser.add_argument("--conjunto", required=True)
    parser.add_argument("--salida", required=True, help="ruta sin extensión")
    parser.add_argument("--preregistro", default=None, help="commit con los casos fijados antes de correr")
    args = parser.parse_args()
    reports = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.corridas]
    agg = aggregate(reports, args.conjunto)
    agg["preregistro"] = args.preregistro
    Path(args.salida + ".json").write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.salida + ".md").write_text(to_markdown(agg, args.preregistro), encoding="utf-8")
    for mode in agg["modos"]:
        acierto = agg["por_modo"][mode]["resumen"]["acierto"]
        print(f"{mode}: acierto {_pm(acierto, 'pct')} (corridas: {[round(r['acierto'] * 100, 1) for r in agg['por_modo'][mode]['por_corrida']]})")
    print(f"Guardado en {args.salida}.json y .md")


if __name__ == "__main__":
    main()
