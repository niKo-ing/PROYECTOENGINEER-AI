"""Precios de tiendas chilenas e imágenes para las piezas del armador, desde la API pública de SoloTodo.

SoloTodo reúne los precios de las tiendas chilenas (PC Factory, Winpy, MyShop, Infor-Ingen…) con fichas normalizadas.
Se usa su API JSON pública, no se raspa HTML: consultas por lote (hasta 20 productos), con pausa entre ellas y un
User-Agent que identifica el proyecto. Qué producto de SoloTodo corresponde a cada pieza está fijado: en producción, en
``catalogo_solotodo.json`` (``scripts/solotodo_catalogo.py``); para la semilla del equipo, en ``solotodo_productos.json``
(``scripts/solotodo_mapear.py``). Aquí no se adivina.

    python -m app.pcbuilder.solotodo        # sincroniza la base configurada

Cada oferta queda con la tienda real, su enlace y ``source = "solotodo"``. Si una pieza tiene al menos una tienda con
stock, su «Precio de referencia» deja de estar disponible (no se borra) y el armador usa el precio real más bajo; si
la pieza no tiene tiendas, sigue con la referencia. Las evaluaciones no llaman a esta función: usan solo la semilla.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import func, select, text
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
    if mapa is None:
        from app.pcbuilder.solotodo_catalogo import mapa_instantanea

        mapa = {**json.loads(MAPA.read_text(encoding="utf-8")), **mapa_instantanea()}
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
    omitidas = 0
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
            url = entidad.get("external_url") or ""
            tienda = _tienda(db, tiendas[entidad["store_id"]], url, cache)
            oferta = next((o for o in producto.offers if o.store_id == tienda.id), None)
            if tienda.id in vistas and oferta is not None and oferta.price <= precio:
                continue  # la tienda publica el producto más de una vez: queda el precio más bajo
            ajena = db.scalar(select(StoreOffer).where(StoreOffer.store_id == tienda.id, StoreOffer.url == url, StoreOffer.product_id != producto.id))
            if ajena is not None:
                # La tienda vende varias variantes en la misma página (p. ej. dos capacidades): no se sabe a cuál
                # corresponde el precio, así que esta oferta no se publica.
                omitidas += 1
                continue
            normal = _precio(registro.get("normal_price"))
            cambio = oferta is None or oferta.price != precio
            if oferta is None:
                oferta = StoreOffer(product=producto, store=tienda, currency="CLP", source=FUENTE, price=precio, url=url)
                db.add(oferta)
                db.flush()  # fija store_id: una segunda oferta de la misma tienda actualiza esta, no la duplica
            oferta.url = url or oferta.url
            oferta.external_id = str(entidad.get("id"))
            oferta.price, oferta.original_price = precio, None
            oferta.payment_condition = f"Precio oferta; precio normal ${normal:,}".replace(",", ".") if normal and normal > precio else None
            oferta.stock_status, oferta.availability = "in_stock", True
            oferta.condition = CONDICIONES.get(str(entidad.get("condition", "")).rsplit("/", 1)[-1], "new")
            oferta.source, oferta.last_seen_at, oferta.last_checked_at = FUENTE, ahora, ahora
            if cambio:
                db.flush()
                db.add(PriceHistory(store_offer_id=oferta.id, price=precio, currency="CLP", observed_at=ahora))
            if tienda.id not in vistas:
                resumen["ofertas"] += 1
            vistas.add(tienda.id)
        # Ofertas de SoloTodo que ya no aparecen: sin stock (quedan en el historial). Referencia: solo si no hay tiendas.
        for oferta in producto.offers:
            if oferta.source == FUENTE and oferta.store_id not in vistas and oferta.availability:
                oferta.availability, oferta.stock_status = False, "out_of_stock"
        for oferta in producto.offers:
            if oferta.source == "semilla-armador":
                oferta.availability = not vistas
        resumen["con_tiendas"] += int(bool(vistas))
    resumen["tiendas"] = len(cache)
    if omitidas:
        resumen["omitidas_url_compartida"] = omitidas
    db.commit()
    log.info("SoloTodo: %s", resumen)
    return resumen


CANDADO_PG = 731_031  # clave del candado de Postgres: una sola sincronización a la vez entre réplicas


@contextmanager
def _turno(sesion: Session) -> Iterator[bool]:
    """True si este proceso puede sincronizar ahora. En Postgres, candado de transacción (se suelta con el commit de
    ``sincronizar``); en SQLite (una sola máquina), un archivo con ``flock`` que comparten los procesos de uvicorn."""
    if sesion.get_bind().dialect.name == "postgresql":
        yield bool(sesion.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": CANDADO_PG}).scalar())
        return
    import fcntl

    with open(os.path.join(tempfile.gettempdir(), "solotodo-sync.lock"), "w") as archivo:
        try:
            fcntl.flock(archivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True


def sincronizado_hace_poco(sesion: Session, horas: float) -> bool:
    """Otra réplica ya sincronizó en este ciclo: no se repite la consulta a SoloTodo."""
    ultima = sesion.scalar(select(func.max(StoreOffer.last_checked_at)).where(StoreOffer.source == FUENTE))
    if ultima is None:
        return False
    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ultima < timedelta(hours=horas * 0.8)


def sincronizar_si_toca(sesion: Session, horas: float, **opciones: Any) -> dict[str, int] | None:
    with _turno(sesion) as puedo:
        if not puedo or sincronizado_hace_poco(sesion, horas):
            sesion.rollback()
            return None
        return sincronizar(sesion, **opciones)


def sincronizar_periodicamente(horas: float | None = None) -> None:
    """Hilo de fondo de la API en producción: sincroniza al arrancar (con una espera al azar) y luego cada
    ``SOLOTODO_SYNC_HORAS`` horas (6 por defecto). Entre réplicas y procesos sincroniza uno solo por ciclo. Un fallo
    solo se registra: la app sigue con los últimos precios."""
    import random

    from app.db import SessionLocal

    horas = horas or float(os.getenv("SOLOTODO_SYNC_HORAS", "6"))
    time.sleep(random.uniform(5, 60))
    while True:
        try:
            with SessionLocal() as sesion:
                sincronizar_si_toca(sesion, horas)
        except Exception:  # noqa: BLE001 — sin SoloTodo la app sigue; se reintenta en el próximo ciclo
            log.warning("No se pudo sincronizar con SoloTodo", exc_info=True)
        time.sleep(horas * 3600)


if __name__ == "__main__":
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as sesion:
        print("SoloTodo:", sincronizar(sesion))
