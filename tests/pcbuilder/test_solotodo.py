"""Sincronización con SoloTodo: tiendas chilenas reales, imagen y precio de referencia solo como respaldo (sin red)."""

import httpx
from sqlalchemy import select

from app.models.catalog import PriceHistory, Product, StoreOffer
from app.pcbuilder.catalog import load_parts
from app.pcbuilder.solotodo import sincronizar

PIEZA = "AMD Ryzen 5 5600"
MAPA = {PIEZA: {"solotodo_id": 135981}}
TIENDAS = [{"id": 12, "name": "PC Factory", "country_id": 1}, {"id": 99, "name": "Tienda de Perú", "country_id": 2}]


def _entidad(tienda: int, precio: str, url: str) -> dict:
    return {"id": tienda * 10, "store_id": tienda, "is_visible": True, "external_url": url,
            "condition": "https://schema.org/NewCondition",
            "active_registry": {"is_available": True, "offer_price": precio, "normal_price": "185590.00"}}


def _cliente(entidades: list[dict]) -> httpx.Client:
    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path == "/stores/":
            return httpx.Response(200, json=TIENDAS)
        assert pedido.url.params.get_list("ids") == ["135981"]
        return httpx.Response(200, json={"results": [{"product": {"id": 135981, "picture_url": "https://media.solotodo.com/r5.webp"},
                                                      "entities": entidades}]})
    return httpx.Client(transport=httpx.MockTransport(responder), base_url="https://publicapi.solotodo.com")


def _ofertas(db) -> list[StoreOffer]:
    producto = db.scalar(select(Product).where(Product.name == PIEZA))
    db.refresh(producto)
    return producto.offers


def test_trae_tiendas_chilenas_imagen_y_el_armador_usa_el_precio_real(env):
    _, Session = env
    pcfactory = _entidad(12, "179990.00", "https://www.pcfactory.cl/producto/49205")
    peru = _entidad(99, "1000.00", "https://tienda.pe/r5")
    with Session() as db:
        resumen = sincronizar(db, cliente=_cliente([pcfactory, peru]), mapa=MAPA, pausa=0)
        assert resumen == {"piezas": 1, "con_tiendas": 1, "ofertas": 1, "imagenes": 1, "tiendas": 1}
        ofertas = {o.source: o for o in _ofertas(db)}
        real = ofertas["solotodo"]
        assert (real.store.name, real.store.domain, real.price) == ("PC Factory", "www.pcfactory.cl", 179990)
        assert real.url.startswith("https://www.pcfactory.cl/") and real.condition == "new" and real.availability
        assert "185.590" in real.payment_condition
        assert ofertas["semilla-armador"].availability is False  # la referencia queda de respaldo
        producto = db.scalar(select(Product).where(Product.name == PIEZA))
        assert producto.image_url == "https://media.solotodo.com/r5.webp" and producto.images == [producto.image_url]
        parte = next(p for p in load_parts(db) if p.name == PIEZA)
        assert (parte.price_clp, parte.store) == (179990, "PC Factory")


def test_es_idempotente_y_la_referencia_vuelve_si_no_quedan_tiendas(env):
    _, Session = env
    pcfactory = _entidad(12, "179990.00", "https://www.pcfactory.cl/producto/49205")
    with Session() as db:
        sincronizar(db, cliente=_cliente([pcfactory]), mapa=MAPA, pausa=0)
        sincronizar(db, cliente=_cliente([pcfactory]), mapa=MAPA, pausa=0)
        assert len([o for o in _ofertas(db) if o.source == "solotodo"]) == 1
        assert len(db.scalars(select(PriceHistory)).all()) == 1  # mismo precio: sin historial nuevo

        sincronizar(db, cliente=_cliente([]), mapa=MAPA, pausa=0)
        ofertas = {o.source: o for o in _ofertas(db)}
        assert ofertas["solotodo"].availability is False and ofertas["solotodo"].stock_status == "out_of_stock"
        assert ofertas["semilla-armador"].availability is True
        assert next(p for p in load_parts(db) if p.name == PIEZA).store == "Precio de referencia"


def test_una_pagina_con_varias_variantes_no_rompe_ni_se_asigna_a_dos_productos(env):
    """Una tienda vende dos productos en la misma URL (p. ej. dos capacidades): el segundo no recibe esa oferta."""
    _, Session = env
    otra = "Intel Core i5-12400F"
    url = "https://www.pcfactory.cl/procesadores-varios"

    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path == "/stores/":
            return httpx.Response(200, json=TIENDAS)
        return httpx.Response(200, json=[
            {"product": {"id": 135981}, "entities": [_entidad(12, "179990.00", url + "?a"), _entidad(12, "150000.00", url)]},
            {"product": {"id": 777}, "entities": [_entidad(12, "120000.00", url)]},  # misma página que la oferta del Ryzen
        ])

    with Session() as db:
        assert db.scalar(select(Product).where(Product.name == otra)) is not None
        cliente = httpx.Client(transport=httpx.MockTransport(responder), base_url="https://publicapi.solotodo.com")
        resumen = sincronizar(db, cliente=cliente, mapa={**MAPA, otra: {"solotodo_id": 777}}, pausa=0)
        assert resumen["ofertas"] == 1 and resumen["omitidas_url_compartida"] == 1
        real = next(o for o in _ofertas(db) if o.source == "solotodo")
        assert (real.url, real.price) == (url, 150000)  # dos publicaciones en la tienda: queda la más barata
        intel = db.scalar(select(Product).where(Product.name == otra))
        assert not [o for o in intel.offers if o.source == "solotodo"]


def test_el_armador_cotiza_la_oferta_nueva_aunque_haya_una_usada_mas_barata(env):
    _, Session = env
    nueva = _entidad(12, "179990.00", "https://www.pcfactory.cl/producto/49205")
    usada = {**_entidad(13, "90000.00", "https://www.otra.cl/r5-usado"), "condition": "https://schema.org/UsedCondition"}

    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path == "/stores/":
            return httpx.Response(200, json=[*TIENDAS, {"id": 13, "name": "Tienda de usados", "country_id": 1}])
        return httpx.Response(200, json=[{"product": {"id": 135981}, "entities": [nueva, usada]}])

    with Session() as db:
        sincronizar(db, cliente=httpx.Client(transport=httpx.MockTransport(responder), base_url="https://publicapi.solotodo.com"), mapa=MAPA, pausa=0)
        assert {o.condition for o in _ofertas(db) if o.source == "solotodo"} == {"new", "used"}  # la ficha muestra las dos
        parte = next(p for p in load_parts(db) if p.name == PIEZA)
        assert (parte.price_clp, parte.store) == (179990, "PC Factory")
