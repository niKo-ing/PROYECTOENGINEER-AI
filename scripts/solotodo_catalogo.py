"""Genera app/pcbuilder/catalogo_solotodo.json: el catálogo del armador para producción, solo con productos de
SoloTodo que hoy tienen stock en alguna tienda chilena.

    python scripts/solotodo_catalogo.py                    # descarga los listados (1 consulta/s) y escribe la instantánea
    python scripts/solotodo_catalogo.py --cache DIR        # reutiliza listados ya descargados en DIR/<tipo>.json

Elige, en el orden de popularidad de SoloTodo, unos pocos productos por grupo (socket, tipo de memoria, formato, chip,
capacidad, potencia, tamaño) para que el armador tenga variedad en todos los presupuestos, y descarta los que no tienen
ninguna oferta chilena vigente. Las reglas de conversión están en app/pcbuilder/solotodo_catalogo.py.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pcbuilder.solotodo import API, HEADERS, ofertas_chilenas, tiendas_chilenas  # noqa: E402
from app.pcbuilder.solotodo_catalogo import CONVERSORES, INSTANTANEA, nombre_limpio  # noqa: E402

USADAS = ("UsedCondition", "RefurbishedCondition", "DamagedCondition")


def nuevas(entidades: list[dict]) -> list[dict]:
    """Ofertas nuevas: una pieza que hoy solo se vende usada no entra al catálogo."""
    return [e for e in entidades if not str(e.get("condition", "")).endswith(USADAS)]


def modelo_base(nombre: str) -> str:
    """«AMD Ryzen 7 7800X3D Tray» y «AMD Ryzen 7 7800X3D [BOX]» son el mismo procesador para el armador."""
    return re.sub(r"\s+", " ", re.sub(r"\b(tray|box|mpk|wof)\b", " ", nombre_limpio(nombre).lower())).strip()


CATEGORIAS = {"cpu": 3, "motherboard": 5, "ram": 7, "gpu": 2, "ssd": 39, "hdd": 8, "psu": 9, "case": 10, "cooler": 12}


def grupo(tipo: str, pc: dict, specs: dict) -> tuple | None:
    """Grupo de variedad y cuántos productos se aceptan por grupo; None = fuera del catálogo."""
    if tipo == "cpu":
        return (pc["socket"], pc["igpu"]), 4  # con y sin gráficos integrados (oficina sin tarjeta de video)
    if tipo == "motherboard":
        return (pc["socket"], pc["memory_type"], pc["form_factor"]), 2
    if tipo == "ram":
        return ((pc["memory_type"], pc["capacity_gb"], pc["modules"]), 2) if pc["capacity_gb"] in (8, 16, 32, 64) else None
    if tipo == "gpu":
        return (specs.get("gpu_name"),), 1
    if tipo == "ssd":
        return ((pc["interface"], pc["form"], pc["capacity_gb"]), 1) if 240 <= pc["capacity_gb"] <= 4000 else None
    if tipo == "hdd":
        return ((pc["capacity_gb"],), 1) if pc["capacity_gb"] in (1000, 2000, 4000) else None
    if tipo == "psu":
        return ((pc["form_factor"], round(pc["watts"] / 100) * 100), 2) if 450 <= pc["watts"] <= 1200 else None
    if tipo == "case":
        return (pc["form_factors"][0],), 5
    if tipo == "cooler":
        if pc["type"] == "liquida":
            return ("liquida", pc["radiator_mm"]), 2
        return ("aire", 0 if pc["height_mm"] < 80 else 1 if pc["height_mm"] < 150 else 2), 3
    return None


def descargar(cliente: httpx.Client, categoria: int) -> list[dict]:
    items, pagina = [], 1
    while True:
        time.sleep(1)
        r = cliente.get(f"{API}/categories/{categoria}/browse/", params={"page_size": 50, "page": pagina})
        r.raise_for_status()
        datos = r.json()
        items.extend(datos["results"])
        if len(items) >= datos["count"] or not datos["results"]:
            return items
        pagina += 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    cliente = httpx.Client(headers=HEADERS, timeout=60)
    tiendas = tiendas_chilenas(cliente)
    final: list[dict] = []
    descartes = collections.Counter()
    for tipo, categoria in CATEGORIAS.items():
        archivo = args.cache / f"{tipo}.json" if args.cache else None
        listado = json.loads(archivo.read_text(encoding="utf-8")) if archivo and archivo.exists() else descargar(cliente, categoria)
        slot, convertir = CONVERSORES[tipo]
        candidatos: list[tuple[tuple, int, dict]] = []
        modelos: set[str] = set()
        for item in listado:  # en el orden de popularidad de SoloTodo
            producto = item["product_entries"][0]["product"]
            pc = convertir(producto["specs"], producto["name"])
            if pc is None:
                descartes[f"{tipo}: ficha incompleta"] += 1
                continue
            clave = grupo(tipo, pc, producto["specs"])
            if clave is None:
                descartes[f"{tipo}: fuera de rango"] += 1
                continue
            if modelo_base(producto["name"]) in modelos:
                continue
            modelos.add(modelo_base(producto["name"]))
            marca = (producto.get("brand") or {}).get("name") or producto["name"].split()[0]
            nombre = nombre_limpio(producto["name"])
            modelo = nombre[len(marca):].strip() if nombre.lower().startswith(marca.lower()) else nombre
            candidatos.append((*clave, {"slot": slot, "tipo": tipo, "solotodo_id": producto["id"], "name": nombre, "brand": marca,
                                        "model": modelo, "imagen": producto.get("picture_url"), "pc": pc}))
        # Llena los cupos de cada grupo verificando el stock por lotes: uno sin oferta nueva en Chile cede su lugar.
        cupos: collections.Counter = collections.Counter()
        pendientes = candidatos
        while pendientes:
            lote = [c for c in pendientes if cupos[c[0]] < c[1]][:20]
            if not lote:
                break
            revisados = {id(c) for c in lote}
            pendientes = [c for c in pendientes if id(c) not in revisados]
            ofertas = {i: nuevas(o) for i, o in ofertas_chilenas(cliente, [c[2]["solotodo_id"] for c in lote], tiendas).items()}
            for g, maximo, e in lote:
                vigentes = ofertas.get(e["solotodo_id"]) or []
                if not vigentes:
                    descartes[f"{tipo}: sin stock nuevo en Chile"] += 1
                    continue
                if cupos[g] >= maximo:
                    continue
                cupos[g] += 1
                e["ofertas_al_generar"] = len(vigentes)
                # Solo para las pruebas sin red: en producción el precio siempre lo pone solotodo.sincronizar.
                e["precio_al_generar"] = min(int(float(o["active_registry"]["offer_price"])) for o in vigentes)
                final.append(e)
        print(f"{tipo}: {sum(cupos.values())} piezas en {len(cupos)} grupos", flush=True)
    final.sort(key=lambda e: (e["slot"], e["tipo"], e["name"]))
    INSTANTANEA.write_text(json.dumps(final, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    por_tipo = collections.Counter(e["tipo"] for e in final)
    print("Por tipo (con stock en Chile):", dict(por_tipo))
    print("Descartes:", dict(descartes))
    print(f"{len(final)} piezas → {INSTANTANEA}")


if __name__ == "__main__":
    main()
