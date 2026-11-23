"""Precios de tiendas chilenas e imágenes para las piezas del armador, desde la API pública de SoloTodo.

SoloTodo reúne los precios de las tiendas chilenas (PC Factory, Winpy, MyShop, Infor-Ingen…) con fichas normalizadas.
Se usa su API JSON pública, no se raspa HTML: consultas por lote (hasta 20 productos), con pausa entre ellas y un
User-Agent que identifica el proyecto. Qué producto de SoloTodo corresponde a cada pieza está fijado y revisado en
``solotodo_productos.json`` (lo genera ``scripts/solotodo_mapear.py``); aquí no se adivina.

    python -m app.pcbuilder.solotodo        # sincroniza la base configurada

Cada oferta queda con la tienda real, su enlace y ``source = "solotodo"``. Si una pieza tiene al menos una tienda con
stock, su «Precio de referencia» deja de estar disponible (no se borra) y el armador usa el precio real más bajo; si
la pieza no tiene tiendas, sigue con la referencia. Las evaluaciones no llaman a esta función: usan solo la semilla.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import PriceHistory, Product, Store, StoreOffer

log = logging.getLogger(__name__)

API = "https://publicapi.solotodo.com"
HEADERS = {"User-Agent": "TodoBaratoAI/1.0 (proyecto academico Duoc UC; precios del armador de PC)"}
CHILE = 1
FUENTE = "solotodo"
MAPA = Path(__file__).with_name("solotodo_productos.json")
CATEGORIAS = {"cpu": 3, "motherboard": 5, "gpu": 2, "ram": 7, "storage": 39, "case": 10, "cooler": 12, "psu": 9}
DISCOS_DUROS = 8
PAUSA_S = 1.0
LOTE = 20
CONDICIONES = {"NewCondition": "new", "UsedCondition": "used", "RefurbishedCondition": "refurbished", "DamagedCondition": "used"}


def categoria(pieza: dict[str, Any]) -> int:
    if pieza["slot"] == "storage" and pieza.get("pc", {}).get("form") == "3.5":
        return DISCOS_DUROS
    return CATEGORIAS[pieza["slot"]]


def _lista(datos: Any) -> list[dict[str, Any]]:
    return datos.get("results", []) if isinstance(datos, dict) else list(datos)


def tiendas_chilenas(cliente: httpx.Client) -> dict[int, str]:
    respuesta = cliente.get(f"{API}/stores/", params={"countries": CHILE})
    respuesta.raise_for_status()
    return {t["id"]: t["name"] for t in _lista(respuesta.json()) if t.get("country_id") == CHILE}


def _lotes(ids: list[int]) -> Iterable[list[int]]:
    for inicio in range(0, len(ids), LOTE):
        yield ids[inicio:inicio + LOTE]


def disponibles(cliente: httpx.Client, ids: list[int], pausa: float = PAUSA_S) -> list[dict[str, Any]]:
    """Productos de SoloTodo con sus ofertas vigentes (``entities``), por lotes."""
    resultados: list[dict[str, Any]] = []
    for numero, lote in enumerate(_lotes(ids)):
        if numero:
            time.sleep(pausa)
        respuesta = cliente.get(f"{API}/products/available_entities/", params=[("ids", i) for i in lote])
        respuesta.raise_for_status()
        resultados.extend(_lista(respuesta.json()))
    return resultados


def ofertas_chilenas(cliente: httpx.Client, ids: list[int], tiendas: dict[int, str], pausa: float = PAUSA_S) -> dict[int, list[dict]]:
    """Por producto de SoloTodo: ofertas visibles, disponibles y de tiendas chilenas."""
    salida: dict[int, list[dict]] = {}
    for item in disponibles(cliente, ids, pausa):
        producto = item.get("product") or {}
        salida[producto.get("id")] = [
            e for e in item.get("entities", [])
            if e.get("store_id") in tiendas and e.get("is_visible", True) and (e.get("active_registry") or {}).get("is_available")
        ]
    return salida


def _tienda(db: Session, nombre: str, url: str, cache: dict[str, Store]) -> Store:
    dominio = (urlparse(url).hostname or nombre).lower()
    if dominio in cache:
        return cache[dominio]
    tienda = db.scalar(select(Store).where(Store.domain == dominio)) or db.scalar(select(Store).where(Store.name == nombre))
    if tienda is None:
        tienda = Store(name=nombre, domain=dominio, country="CL", trust_level=1, store_type="retailer")
        db.add(tienda)
        db.flush()
    cache[dominio] = tienda
    return tienda


def _precio(valor: Any) -> int | None:
    try:
        return int(Decimal(str(valor)))
    except Exception:  # noqa: BLE001 — precio ausente o mal formado: no se publica
        return None


def sincronizar(db: Session, cliente: httpx.Client | None = None, mapa: dict[str, dict] | None = None, pausa: float = PAUSA_S) -> dict[str, int]:
    """Trae precios e imágenes de SoloTodo para las piezas emparejadas. Idempotente."""
    mapa = mapa if mapa is not None else json.loads(MAPA.read_text(encoding="utf-8"))
    propio = cliente is None
    cliente = cliente or httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True)
    try:
        tiendas = tiendas_chilenas(cliente)
        nombres = list(mapa)
        productos = {
            p.name: p
            for p in db.scalars(select(Product).where(Product.name.in_(nombres)).options(selectinload(Product.offers).selectinload(StoreOffer.store)))
        }
        por_solotodo = {datos["solotodo_id"]: productos[n] for n, datos in mapa.items() if n in productos}
        items = disponibles(cliente, list(por_solotodo), pausa) if por_solotodo else []
    finally:
        if propio:
            cliente.close()

    ahora = datetime.now(timezone.utc)
    cache: dict[str, Store] = {}
    resumen = {"piezas": len(por_solotodo), "con_tiendas": 0, "ofertas": 0, "imagenes": 0, "tiendas": 0}
    for item in items:
        info = item.get("product") or {}
        producto = por_solotodo.get(info.get("id"))
        if producto is None:
            continue
        if imagen := info.get("picture_url"):
            if producto.image_url != imagen:
                producto.image_url, producto.images = imagen, [imagen]
            resumen["imagenes"] += 1
        vistas: set[int] = set()
        for entidad in item.get("entities", []):
            registro = entidad.get("active_registry") or {}
            precio = _precio(registro.get("offer_price"))
            if entidad.get("store_id") not in tiendas or not registro.get("is_available") or not entidad.get("is_visible", True) or not precio:
                continue
            tienda = _tienda(db, tiendas[entidad["store_id"]], entidad.get("external_url") or "", cache)
            oferta = next((o for o in producto.offers if o.store_id == tienda.id), None)
            normal = _precio(registro.get("normal_price"))
            cambio = oferta is None or oferta.price != precio
            if oferta is None:
                oferta = StoreOffer(product=producto, store=tienda, currency="CLP", source=FUENTE, price=precio,
                                    url=entidad.get("external_url") or "")
                db.add(oferta)
                db.flush()  # fija store_id: una segunda oferta de la misma tienda actualiza esta, no la duplica
            oferta.url = entidad.get("external_url") or oferta.url
            oferta.external_id = str(entidad.get("id"))
            oferta.price, oferta.original_price = precio, None
            oferta.payment_condition = f"Precio oferta; precio normal ${normal:,}".replace(",", ".") if normal and normal > precio else None
            oferta.stock_status, oferta.availability = "in_stock", True
            oferta.condition = CONDICIONES.get(str(entidad.get("condition", "")).rsplit("/", 1)[-1], "new")
            oferta.source, oferta.last_seen_at, oferta.last_checked_at = FUENTE, ahora, ahora
            if cambio:
                db.flush()
                db.add(PriceHistory(store_offer_id=oferta.id, price=precio, currency="CLP", observed_at=ahora))
            vistas.add(tienda.id)
            resumen["ofertas"] += 1
        # Ofertas de SoloTodo que ya no aparecen: sin stock (quedan en el historial). Referencia: solo si no hay tiendas.
        for oferta in producto.offers:
            if oferta.source == FUENTE and oferta.store_id not in vistas and oferta.availability:
                oferta.availability, oferta.stock_status = False, "out_of_stock"
        for oferta in producto.offers:
            if oferta.source == "semilla-armador":
                oferta.availability = not vistas
        resumen["con_tiendas"] += int(bool(vistas))
    resumen["tiendas"] = len(cache)
    db.commit()
    log.info("SoloTodo: %s", resumen)
    return resumen


if __name__ == "__main__":
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as sesion:
        print("SoloTodo:", sincronizar(sesion))
