"""Banco de evaluación (evals/escenarios.json) y agregador de corridas (scripts/agregar_corridas.py)."""

import json
import statistics
from pathlib import Path

from app.pcbuilder.assistant import MAX_BUDGET
from app.pcbuilder.recommender import USE_CASES
from scripts.agregar_corridas import aggregate, to_markdown

BANCO = json.loads((Path(__file__).resolve().parents[1] / "evals" / "escenarios.json").read_text(encoding="utf-8"))
CONJUNTOS = {"desarrollo", "prueba", "prueba-2", "prueba-3"}


def test_escenarios_bien_formados():
    casos = BANCO["asistente"]
    assert len({c["id"] for c in casos}) == len(casos)
    textos = [" / ".join(c["mensajes"]).strip().lower() for c in casos]
    assert len(set(textos)) == len(textos), "hay un pedido repetido entre conjuntos"
    for c in casos:
        esperado = c["esperado"]
        assert c["conjunto"] in CONJUNTOS and c["categoria"] and c["mensajes"]
        assert esperado["estado"] in {"build", "question", "blocked"}
        assert esperado.get("use_case") in (None, *USE_CASES)
        assert all(u in USE_CASES for u in esperado.get("use_case_any", []))
        assert esperado.get("budget_clp") is None or 0 < esperado["budget_clp"] <= MAX_BUDGET
        assert set(esperado.get("falta", [])) <= {"use_case", "budget_clp"}


def test_prueba_3_tiene_15_casos_nuevos():
    prueba3 = [c for c in BANCO["asistente"] if c["conjunto"] == "prueba-3"]
    assert len(prueba3) == 15 and [c["id"] for c in prueba3] == [f"R{i:02d}" for i in range(1, 16)]


def _fila(case_id, ok, latencia, tokens, estado="build", needs=None, piezas=(1, 2)):
    return {"id": case_id, "categoria": "claro", "conjunto": "prueba-3", "estado": estado, "estado_ok": ok, "extraccion_ok": ok, "falta_ok": None,
            "campos": {"use_case": ok}, "compatible": True, "en_presupuesto": True, "precios_ok": True, "status": "ok", "latency_ms": latencia,
            "llm_calls": 2, "tokens": tokens, "needs": needs or {"use_case": "esports"}, "piezas": list(piezas)}


def _corrida(etiqueta, filas):
    return {"etiqueta": etiqueta, "fecha": "2026-11-23", "modelo": "m", "modos": ["gemini"], "crudo": {"gemini": filas}}


def test_agregador_media_y_desviacion_entre_corridas():
    corridas = [
        _corrida("c1", [_fila("R01", True, 1000, 2000), _fila("R02", True, 3000, 2000)]),
        _corrida("c2", [_fila("R01", True, 1000, 2100), _fila("R02", False, 3000, 2100, needs={"use_case": "oficina"})]),
        _corrida("c3", [_fila("R01", True, 1000, 2200), _fila("R02", True, 3000, 2200)]),
    ]
    agg = aggregate(corridas, "prueba-3")
    resumen = agg["por_modo"]["gemini"]["resumen"]
    assert resumen["acierto"]["media"] == statistics.mean([1.0, 0.5, 1.0])
    assert resumen["acierto"]["de"] == statistics.stdev([1.0, 0.5, 1.0])
    assert resumen["tokens"]["media"] == 2100 and resumen["tokens"]["de"] == 100
    casos = agg["por_modo"]["gemini"]["casos"]
    assert casos["R02"]["aciertos"] == [True, False, True] and casos["R02"]["mismas_necesidades"] is False
    assert agg["por_modo"]["gemini"]["consistencia_entre_corridas"]["necesidades"] == 0.5
    texto = to_markdown(agg, "abc1234")
    assert "| R02 | claro | ✓✗✓ |" in texto and "commit `abc1234`" in texto and "gemini · R02 · corrida 2" in texto
