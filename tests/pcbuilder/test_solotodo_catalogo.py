"""Catálogo del armador para producción, hecho solo con productos de SoloTodo (instantánea revisable, sin red)."""

import collections
import json

import httpx
import pytest
from sqlalchemy import select

from app.models.catalog import StoreOffer
from app.pcbuilder.catalog import REFERENCE_STORE, ensure_seeded, load_parts
from app.pcbuilder.compatibility import check_build
from app.pcbuilder.parts import SLOT_BY_KEY, Part
from app.pcbuilder.recommender import Needs, recommend
from app.pcbuilder.solotodo import sincronizar_si_toca, sincronizado_hace_poco
from app.pcbuilder.solotodo_catalogo import INSTANTANEA, cpu, disipador, gabinete, gpu

CATALOGO = json.loads(INSTANTANEA.read_text(encoding="utf-8"))


def _partes() -> list[Part]:
    """La instantánea con el precio que tenía al generarla (en producción el precio lo pone la sincronización)."""
    return [Part(slot=e["slot"], name=e["name"], specs=e["pc"], product_id=i + 1, price_clp=e["precio_al_generar"],
                 brand=e["brand"], store="Tienda", legacy=False) for i, e in enumerate(CATALOGO)]


def test_conversion_de_fichas_con_reglas_fijas():
    ryzen = cpu({"socket_socket_name": "AM5", "core_count_value": 6, "thread_count_value": 12, "frequency": 3800,
                 "max_turbo_frequency": 5100, "tdp": 65, "graphics_name": "Radeon Graphics", "cooler_name": "Wraith Stealth",
                 "passmark_score": 27618, "cinebench_r20_single_score": 722}, "AMD Ryzen 5 7600")
    assert ryzen["socket"] == "AM5" and ryzen["memory_types"] == ["DDR5"] and ryzen["max_power_w"] == 88
    assert ryzen["cpu_score"] == 62 and ryzen["igpu"] and ryzen["includes_cooler"]
    assert cpu({"socket_socket_name": "AM5", "core_count_value": 6, "thread_count_value": 12, "frequency": 3800, "tdp": 65},
               "sin benchmark") is None  # sin dato para comparar: se descarta, no se inventa
    tarjeta = {"gpu_line_family_name": "GeForce RTX 50", "length": 240, "gpu_tdp": 145, "memory_quantity_value": 8192,
               "gpu_tdmark_time_spy_score": 13646}
    assert gpu(tarjeta, "MSI GeForce RTX 5060 8G") == {"chip": "NVIDIA", "vram_gb": 8, "length_mm": 240, "board_power_w": 145,
                                                       "recommended_psu_w": 550, "pcie_gen": 4, "perf": 63}
    assert gpu({**tarjeta, "gpu_line_family_name": "Radeon Pro W6000"}, "AMD Radeon Pro W6600") is None  # workstation
    caja = {"largest_motherboard_format_format_name": "Micro ATX", "max_video_card_length": 330, "max_cpu_cooler_height": 160,
            "frontal_fan_slots": [{"fan_mm": 120, "quantity": 3}]}
    assert gabinete(caja, "x") == {"form_factors": ["mATX", "ITX"], "max_gpu_mm": 330, "max_cooler_mm": 160,
                                   "psu_form_factors": ["ATX"], "radiators_mm": [120, 240, 360]}
    assert gabinete({**caja, "power_supply_power": 500}, "con fuente") is None
    liquida = disipador({"type_name": "Refrigeración líquida", "grouped_sockets": [{"sockets": [{"socket_name": "AM5"}, {"socket_name": "LGA 1700"}]}]},
                        "Arctic Liquid Freezer III 240")
    assert liquida == {"type": "liquida", "sockets": ["AM5", "LGA1700"], "radiator_mm": 240, "tdp_rating_w": 280}


def test_la_instantanea_cubre_todos_los_tipos_y_plataformas():
    por_slot = collections.Counter(e["slot"] for e in CATALOGO)
    assert set(por_slot) == set(SLOT_BY_KEY) and min(por_slot.values()) >= 10
    assert {e["pc"]["socket"] for e in CATALOGO if e["slot"] == "cpu"} == {"AM4", "AM5", "LGA1700", "LGA1851"}
    assert {e["pc"]["memory_type"] for e in CATALOGO if e["slot"] == "ram"} == {"DDR4", "DDR5"}
    assert {e["pc"]["form_factor"] for e in CATALOGO if e["slot"] == "psu"} == {"ATX", "SFX"}
    assert len({e["name"] for e in CATALOGO}) == len(CATALOGO)
    for e in CATALOGO:
        assert isinstance(e["solotodo_id"], int) and e["ofertas_al_generar"] >= 1, e["name"]
        assert "[" not in e["name"] and ".local" not in json.dumps(e)
        assert (e["imagen"] or "").startswith("https://"), e["name"]


@pytest.mark.parametrize("necesidad", [
    Needs(use_case="oficina", budget_clp=600_000),
    Needs(use_case="gaming_1080", budget_clp=1_000_000),
    Needs(use_case="gaming_1440", budget_clp=1_600_000, cpu_brand="Intel", gpu_brand="AMD", wifi=True),
    Needs(use_case="edicion", budget_clp=1_500_000),
    Needs(use_case="gaming_1080", budget_clp=1_300_000, small=True),
], ids=lambda n: f"{n.use_case}-{n.budget_clp}{'-itx' if n.small else ''}")
def test_el_armador_arma_pcs_compatibles_con_el_catalogo_de_solotodo(necesidad):
    rec = recommend(_partes(), necesidad)
    assert rec.build.parts and not check_build(rec.build).errors
    assert {"cpu", "motherboard", "ram", "storage", "psu", "case"} <= {p.slot for p in rec.build.parts}


def test_produccion_siembra_solo_solotodo_y_apaga_los_precios_de_referencia(env, monkeypatch):
    _, Session = env  # la base ya trae la semilla del equipo con sus precios de referencia
    monkeypatch.setenv("PC_CATALOGO", "solotodo")
    with Session() as db:
        ensure_seeded(db)
        partes = load_parts(db)
        assert {p.name for p in partes} == {e["name"] for e in CATALOGO}
        assert all(p.price_clp is None and p.store != REFERENCE_STORE for p in partes)  # sin precio hasta sincronizar
        assert not db.scalars(select(StoreOffer).where(StoreOffer.source == "semilla-armador", StoreOffer.availability.is_(True))).all()
        ensure_seeded(db)  # idempotente
        assert len(load_parts(db)) == len(CATALOGO)

        pieza = CATALOGO[0]

        def responder(pedido: httpx.Request) -> httpx.Response:
            if pedido.url.path == "/stores/":
                return httpx.Response(200, json=[{"id": 12, "name": "PC Factory", "country_id": 1}])
            return httpx.Response(200, json=[{"product": {"id": pieza["solotodo_id"], "picture_url": pieza["imagen"]}, "entities": [
                {"id": 1, "store_id": 12, "is_visible": True, "external_url": "https://www.pcfactory.cl/producto/1",
                 "active_registry": {"is_available": True, "offer_price": "99990.00", "normal_price": "99990.00"}}]}])

        cliente = httpx.Client(transport=httpx.MockTransport(responder), base_url="https://publicapi.solotodo.com")
        opciones = {"cliente": cliente, "mapa": {pieza["name"]: {"solotodo_id": pieza["solotodo_id"]}}, "pausa": 0}
        assert sincronizar_si_toca(db, 6, **opciones)["con_tiendas"] == 1
        parte = next(p for p in load_parts(db) if p.name == pieza["name"])
        assert (parte.price_clp, parte.store) == (99990, "PC Factory")
        assert sincronizado_hace_poco(db, 6)
        assert sincronizar_si_toca(db, 6, **opciones) is None  # otro proceso ya lo hizo en este ciclo
