"""Empareja cada pieza del armador con su producto en SoloTodo y guarda el resultado para revisarlo a mano.

    python scripts/solotodo_mapear.py            # escribe app/pcbuilder/solotodo_productos.json y muestra la tabla

Se corre una vez (y cuando cambian las piezas): el despliegue solo lee el archivo, no adivina en cada arranque. Usa la
API pública de SoloTodo (publicapi.solotodo.com) con una consulta por segundo.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pcbuilder.catalog_data import PARTS  # noqa: E402
from app.pcbuilder.solotodo import API, HEADERS, categoria, ofertas_chilenas, tiendas_chilenas  # noqa: E402

SALIDA = Path(__file__).resolve().parents[1] / "app" / "pcbuilder" / "solotodo_productos.json"
# Si el candidato trae una de estas palabras y la pieza no, es otra variante (RTX 4060 Ti ≠ RTX 4060, 5600G ≠ 5600).
DIFERENCIADORES = {"ti", "super", "xt", "xtx", "gre", "x3d", "ddr4", "ddr5", "wifi", "ax", "v2", "v3", "white", "blanco",
                   "blanca", "argb", "rgb", "16g", "12g", "6g", "4g", "lp", "low", "plus", "pro", "max", "elite", "se",
                   "evo", "3dhp", "fuente", "air", "m", "tray", "extrem"}
MINIMO = 0.85
ALIAS = {"WD": "Western Digital"}  # marca de la semilla → como la escribe SoloTodo
CAPACIDAD = re.compile(r"\d+g")
# Descripciones de la semilla que SoloTodo no pone en el nombre.
RELLENO = re.compile(r"m\.2|nvme|pcie\s*[45]\.0|sata\s*2\.5\"?|hdd\s*3\.5\"?|7200\s*rpm|80\s*plus\s*\w+|atx\s*3\.0|\bsfx\b|"
                     r"\bgeforce\b|\bradeon\b", re.I)


def tokens(texto: str) -> set[str]:
    t = texto.lower()
    t = re.sub(r"\[.*?\]", " ", t)                       # número de parte de SoloTodo
    t = re.sub(r"\(\s*(\d+)\s*x\s*(\d+)\s*(?:gb?)?", r" \1x\2 ", t)  # RAM: (2 x 8GB) → 2x8 (no «VENTUS 2X 8G»)
    t = re.sub(r"(\d+)\s*gb?\b", r"\1g", t)               # 8GB / 8 GB / 8G → 8g
    t = re.sub(r"(\d+)\s*tb\b", r"\1tb", t)
    t = re.sub(r"(\d+)\s*w\b", r"\1w", t)                # (750 W) → 750w
    t = re.sub(r"ddr([45])-?(\d{4})", r"ddr\1 \2", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return set(t.split())


def clave(t: str) -> bool:
    """Código de modelo: letras con números (b550m, rm750e, nv3) o un número de 3+ cifras (5600, 4060, 3200)."""
    if re.fullmatch(r"\d+w", t):  # los watts de una fuente no siempre están en el nombre
        return False
    return (any(c.isdigit() for c in t) and any(c.isalpha() for c in t)) or (t.isdigit() and len(t) >= 3)


def marca(pieza: dict) -> str:
    return ALIAS.get(pieza["brand"], pieza["brand"])


def puntaje(pieza: dict, candidato: str) -> float:
    propios = tokens(RELLENO.sub(" ", f'{marca(pieza)} {pieza["model"]}'))
    ajenos = tokens(candidato)
    if marca(pieza).lower().split()[0] not in ajenos:
        return 0.0
    requeridas = {t for t in propios if clave(t)}
    if not any(CAPACIDAD.fullmatch(t) for t in ajenos):  # SoloTodo no siempre pone la capacidad (RX 7700 XT, kits de RAM)
        requeridas = {t for t in requeridas if not CAPACIDAD.fullmatch(t)}
        propios = {t for t in propios if not CAPACIDAD.fullmatch(t)}
    if not requeridas <= ajenos or (ajenos - propios) & DIFERENCIADORES:
        return 0.0
    valor = round(len(propios & ajenos) / len(propios), 3)
    return valor if valor >= MINIMO else 0.0


def extras(pieza: dict, candidato: str) -> int:
    return len(tokens(candidato) - tokens(f'{marca(pieza)} {pieza["model"]}'))


def consultas(pieza: dict) -> list[str]:
    """De la más precisa a la más amplia; se detiene en la primera que da un candidato válido."""
    modelo = re.sub(r"\s+", " ", RELLENO.sub(" ", pieza["model"])).strip()
    espaciado = re.sub(r"(\d+)(GB|TB)\b", r"\1 \2", modelo, flags=re.I)
    sin_capacidad = re.sub(r"\s+", " ", re.sub(r"\(\d+x\d+\)|\b\d+\s*(GB|G|TB)\b", " ", modelo, flags=re.I)).strip()
    corto = " ".join(t for t in sin_capacidad.split() if clave(t.lower()) or len(t) > 2)
    return list(dict.fromkeys(f"{marca(pieza)} {q}".strip() for q in (espaciado, modelo, sin_capacidad, corto) if q))


def main() -> None:
    cliente = httpx.Client(headers=HEADERS, timeout=30)
    tiendas = tiendas_chilenas(cliente)
    resultado, filas = {}, []
    for pieza in PARTS:
        nombre = f'{pieza["brand"]} {pieza["model"]}'
        candidatos: dict[int, dict] = {}
        for q in consultas(pieza):
            time.sleep(1)
            r = cliente.get(f"{API}/products/", params={"categories": categoria(pieza), "search": q, "page_size": 40})
            r.raise_for_status()
            for p in r.json()["results"]:
                if (s := puntaje(pieza, p["name"])) > 0:
                    candidatos[p["id"]] = {"id": p["id"], "nombre": p["name"], "puntaje": s, "imagen": p.get("picture_url")}
            if candidatos:
                break
        if candidatos:
            time.sleep(1)
            ofertas = ofertas_chilenas(cliente, list(candidatos), tiendas)
            for c in candidatos.values():
                c["ofertas"] = len(ofertas.get(c["id"], []))
            mejor = max(candidatos.values(), key=lambda c: (c["puntaje"], c["ofertas"], -extras(pieza, c["nombre"])))
            resultado[nombre] = {"solotodo_id": mejor["id"], "nombre_solotodo": mejor["nombre"], "puntaje": mejor["puntaje"]}
            filas.append((nombre, mejor["nombre"], mejor["puntaje"], mejor["ofertas"], len(candidatos)))
        else:
            filas.append((nombre, "—", 0, 0, 0))
    SALIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for nombre, st, s, n, c in filas:
        print(f"{s:5.2f} {n:3d} ofertas ({c} cand.) | {nombre:<48} → {st}")
    print(f"\n{len(resultado)} de {len(PARTS)} piezas emparejadas → {SALIDA}")


if __name__ == "__main__":
    main()
