"""Catálogo del armador hecho solo con productos de SoloTodo que tienen stock en tiendas chilenas.

En producción (``PC_CATALOGO=solotodo``) el armador no usa la semilla escrita por el equipo: usa la instantánea
``catalogo_solotodo.json`` (la genera ``scripts/solotodo_catalogo.py``) y ``solotodo.sincronizar`` le pone precios,
tiendas e imágenes reales. Las pruebas y las evaluaciones siguen con la semilla fija, sin red, para poder repetirse.

Cada ficha sale de la ficha técnica de SoloTodo. Lo que SoloTodo no publica se deduce con reglas fijas y
conservadoras, y una ficha a la que le falta un dato que la compatibilidad necesita se descarta (no se rellena):

* puntajes relativos del recomendador, calibrados con los benchmarks que publica SoloTodo contra la semilla:
  ``cpu_score = PassMark / 444`` (o Cinebench R20 multi / 90), ``gaming_score = 18,3 + 0,086 × Cinebench R20 de un
  núcleo`` (+15 en los X3D, tope 100) y ``perf`` de la GPU ``= 3DMark Time Spy / 216`` (o Fire Strike / 440);
* consumo máximo de la CPU: AMD = TDP × 1,35 (PPT); Intel = 89 W (TDP ≤ 60), 148 W, o 181/253 W si es «K»;
* fuente recomendada para la GPU = su consumo + 400 W, redondeado a 50;
* placa: PCIe según el chipset y RAM máxima = ranuras × 32 GB (DDR4) o × 48 GB (DDR5);
* disipador: capacidad según tipo y tamaño (aire: < 80 mm 65 W, < 120 mm 120 W, < 150 mm 150 W, si no 200 W;
  líquida: 120 mm 200 W, 240 mm 280 W, 280 mm 300 W, 360 mm o más 350 W);
* gabinete: Mini-ITX = fuente SFX; los demás, ATX. Radiadores según las ranuras de ventilador frontales y superiores.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Category, Product, StoreOffer
from app.pcbuilder.parts import SLOT_BY_KEY

log = logging.getLogger(__name__)

INSTANTANEA = Path(__file__).with_name("catalogo_solotodo.json")
FUENTE = "SoloTodo"
SOCKETS = {"AM4": "AM4", "AM5": "AM5", "LGA 1700": "LGA1700", "LGA 1851": "LGA1851"}
MEMORIA_POR_SOCKET = {"AM4": ["DDR4"], "AM5": ["DDR5"], "LGA1700": ["DDR4", "DDR5"], "LGA1851": ["DDR5"]}
PCIE_POR_CHIPSET = {"A520": 3, "B450": 3, "X470": 3, "B550": 4, "X570": 4, "A620": 4, "B650": 4, "B650E": 5, "X670": 4,
                    "X670E": 5, "B840": 3, "B850": 4, "X870": 5, "X870E": 5, "H610": 4, "B660": 4, "H670": 4, "Z690": 5,
                    "B760": 4, "H770": 4, "Z790": 5, "H810": 4, "B860": 4, "Z890": 5}
IGPU = {"Radeon Vega 7": 12, "Radeon Vega 8": 13, "Radeon 760M": 20, "Radeon 780M": 26, "UHD 710": 4, "UHD 730": 6, "UHD 770": 7}
FORMATOS_PLACA = {"ATX": "ATX", "Micro ATX": "mATX", "Mini ITX": "ITX", "E-ATX": "E-ATX", "Extended ATX": "E-ATX"}
PLACAS_QUE_CABEN = {"E-ATX": ["E-ATX", "ATX", "mATX", "ITX"], "ATX": ["ATX", "mATX", "ITX"], "mATX": ["mATX", "ITX"], "ITX": ["ITX"]}
RADIADORES = {120, 140, 240, 280, 360, 420}


def catalogo_activo() -> str:
    """«semilla» (pruebas, evaluaciones, desarrollo) o «solotodo» (producción)."""
    return os.getenv("PC_CATALOGO", "semilla").strip().lower()


def _sin_vacios(valor: Any) -> bool:
    return valor not in (None, "", "No posee", 0)


def _redondear(valor: float, paso: int) -> int:
    return int(math.ceil(valor / paso) * paso)


def cpu(s: dict, nombre: str) -> dict | None:
    socket = SOCKETS.get(s.get("socket_socket_name") or "")
    nucleos, hilos, tdp = s.get("core_count_value") or s.get("total_core_count"), s.get("thread_count_value"), s.get("tdp")
    base, turbo = (s.get("frequency") or 0) / 1000, (s.get("max_turbo_frequency") or s.get("frequency") or 0) / 1000
    if not (socket and nucleos and hilos and tdp and base):
        return None
    passmark, multi, simple = s.get("passmark_score") or 0, s.get("cinebench_r20_multi_score") or 0, s.get("cinebench_r20_single_score") or 0
    if passmark >= 5000:
        cpu_score = round(passmark / 444)
    elif multi:
        cpu_score = round(multi / 90)
    else:
        return None  # sin benchmark no se puede comparar con las demás
    gaming = 18.3 + 0.086 * simple if simple else 0.45 * cpu_score + 48
    if "X3D" in nombre.upper():
        gaming += 15
    amd = socket.startswith("AM")
    if amd:
        maximo = round(tdp * 1.35)
    elif s.get("has_unlocked_multiplier"):
        maximo = 181 if nucleos <= 14 else 253
    else:
        maximo = 89 if tdp <= 60 else 148
    if socket == "AM4":
        mts = 2933 if (s.get("core_architecture_name") or "") in ("Zen", "Zen+") else 3200  # Ryzen 1000/2000 y APU 3000G
    elif socket == "AM5":
        mts = 5600 if "Zen 5" in (s.get("core_architecture_name") or "") else 5200
    elif socket == "LGA1851":
        mts = 6400
    else:
        mts = 4800 if re.search(r"-12\d{3}", nombre) else 5600
    grafica = s.get("graphics_name")
    pc = {"socket": socket, "cores": int(nucleos), "threads": int(hilos), "base_ghz": round(base, 1), "boost_ghz": round(turbo, 1),
          "tdp_w": int(tdp), "max_power_w": maximo, "igpu": _sin_vacios(grafica), "memory_types": MEMORIA_POR_SOCKET[socket],
          "max_mem_mts": mts, "includes_cooler": _sin_vacios(s.get("cooler_name")), "cpu_score": cpu_score,
          "gaming_score": min(100, round(gaming))}
    if pc["igpu"]:
        pc["igpu_name"] = grafica
        pc["igpu_score"] = next((v for k, v in IGPU.items() if k in grafica), 14 if "Arc" in grafica else 5)
    return pc


def placa(s: dict, nombre: str) -> dict | None:
    socket = SOCKETS.get(s.get("chipset_northbridge_family_socket_socket_name") or "")
    chipset = s.get("chipset_name") or s.get("chipset_northbridge_name")
    formato = FORMATOS_PLACA.get(s.get("format_format_name") or "")
    memoria, ranuras = s.get("memory_slots_mtype_itype_type_name"), s.get("memory_slots_quantity")
    if not (socket and chipset and formato and memoria in ("DDR4", "DDR5") and ranuras) or s.get("memory_slots_mtype_itype_format_name") != "DIMM":
        return None
    puertos = s.get("storage_ports") or []
    m2 = sum(int(p.get("quantity") or 1) for p in puertos if "M.2" in (p.get("unicode") or ""))
    sata = sum(int(p.get("quantity") or 1) for p in puertos if "SATA" in (p.get("unicode") or "") and "M.2" not in (p.get("unicode") or ""))
    return {"socket": socket, "chipset": chipset, "form_factor": formato, "memory_type": memoria, "ram_slots": int(ranuras),
            "max_ram_gb": int(ranuras) * (32 if memoria == "DDR4" else 48), "max_mem_mts": 4400 if memoria == "DDR4" else 6400,
            "m2_slots": m2, "sata_ports": sata, "wifi": bool(re.search(r"wi-?fi|\bax\b", nombre, re.I)),
            "pcie_gen": PCIE_POR_CHIPSET.get(chipset, 4)}


def ram(s: dict, nombre: str) -> dict | None:
    tipo, total, modulos, velocidad = s.get("bus_bus_bus_type_name"), s.get("capacity_total_capacity_value"), s.get("capacity_dimm_quantity_value"), s.get("bus_frequency_value")
    if s.get("bus_bus_bus_format_name") != "DIMM" or s.get("is_ecc") or tipo not in ("DDR4", "DDR5") or not (total and modulos and velocidad):
        return None
    return {"memory_type": tipo, "capacity_gb": int(total) // 1024, "modules": int(modulos), "speed_mts": int(velocidad),
            "cas": int(s.get("latency_cl_value") or (16 if tipo == "DDR4" else 36))}


def gpu(s: dict, nombre: str) -> dict | None:
    familia = s.get("gpu_line_family_name") or ""
    chip = "NVIDIA" if "GeForce" in familia else "AMD" if "Radeon" in familia else "Intel" if "Arc" in familia else None
    largo, consumo, vram = s.get("length"), s.get("gpu_tdp"), s.get("memory_quantity_value")
    time_spy, fire_strike = s.get("gpu_tdmark_time_spy_score") or 0, s.get("gpu_tdmark_fire_strike_score") or 0
    perf = round(time_spy / 216) if time_spy else round(fire_strike / 440) if fire_strike else None
    if not (chip and largo and consumo and vram and perf):
        return None
    if perf < 10 or re.search(r"\bpro w\d|quadro|\brtx a\d|radeon pro", f"{familia} {nombre}", re.I):
        return None  # adaptadores de video y tarjetas de workstation: no son para un PC de uso general o juegos
    return {"chip": chip, "vram_gb": int(vram) // 1024, "length_mm": int(largo), "board_power_w": int(consumo),
            "recommended_psu_w": _redondear(int(consumo) + 400, 50), "pcie_gen": int(float(s.get("bus_bus_version") or 4)), "perf": perf}


def ssd(s: dict, nombre: str) -> dict | None:
    familia, bus, capacidad = s.get("ssd_type_format_family_name") or "", s.get("ssd_type_bus_bus_with_version_bus_name"), s.get("capacity_value")
    if not capacidad or bus not in ("PCIe", "SATA") or not (familia.startswith("M.2") or "2.5" in familia):
        return None
    pc = {"interface": "NVMe" if bus == "PCIe" else "SATA", "form": "M.2" if familia.startswith("M.2") else "2.5", "capacity_gb": int(capacidad)}
    if lectura := s.get("sequential_read_speed"):
        pc["read_mbps"] = int(lectura)
    if bus == "PCIe":
        pc["pcie_gen"] = int(float(s.get("ssd_type_bus_bus_with_version_version") or 3))
    return pc


def hdd(s: dict, nombre: str) -> dict | None:
    if s.get("size_value") != 3.5 or s.get("bus_bus_bus_with_version_bus_name") != "SATA" or not s.get("capacity_value"):
        return None
    return {"interface": "SATA", "form": "3.5", "capacity_gb": int(s["capacity_value"])}


def fuente(s: dict, nombre: str) -> dict | None:
    watts, formato = s.get("power_value"), s.get("size_name") or ""
    if not watts:
        return None
    certificacion = (s.get("certification_name") or "Sin certificación").replace("80PLUS", "80 Plus").replace("80 PLUS", "80 Plus")
    return {"watts": int(watts), "efficiency": certificacion, "modular": bool(s.get("is_modular")), "form_factor": "SFX" if "SFX" in formato.upper() else "ATX"}


def _radiadores(s: dict) -> list[int]:
    tamanos: set[int] = set()
    for ranura in (s.get("frontal_fan_slots") or []) + (s.get("top_fan_slots") or []):
        mm, cantidad = int(ranura.get("fan_mm") or 0), int(ranura.get("quantity") or 0)
        tamanos |= {mm * k for k in range(1, cantidad + 1)} & RADIADORES
    return sorted(tamanos)


def gabinete(s: dict, nombre: str) -> dict | None:
    mayor = FORMATOS_PLACA.get(s.get("largest_motherboard_format_format_name") or "")
    gpu_mm, disipador_mm = s.get("max_video_card_length"), s.get("max_cpu_cooler_height")
    if not (mayor and gpu_mm and disipador_mm) or (s.get("power_supply_power") or 0) > 0:  # los que traen fuente se excluyen
        return None
    if not (200 <= gpu_mm <= 500 and 40 <= disipador_mm <= 200):
        return None  # medidas fuera de rango: ficha dudosa (p. ej. GPU y disipador invertidos)
    return {"form_factors": PLACAS_QUE_CABEN[mayor], "max_gpu_mm": int(gpu_mm), "max_cooler_mm": int(disipador_mm),
            "psu_form_factors": ["SFX"] if mayor == "ITX" else ["ATX"], "radiators_mm": _radiadores(s)}


def disipador(s: dict, nombre: str) -> dict | None:
    sockets = sorted({SOCKETS[k["socket_name"]] for g in s.get("grouped_sockets") or [] for k in g.get("sockets") or []
                      if k.get("socket_name") in SOCKETS})
    if not sockets:
        return None
    if "quida" in (s.get("type_name") or ""):  # «Refrigeración líquida»
        medida = re.search(r"\b(120|240|280|360|420)\b", nombre)
        if not medida:
            return None
        radiador = int(medida.group(1))
        capacidad = {120: 200, 240: 280, 280: 300}.get(radiador, 350)
        return {"type": "liquida", "sockets": sockets, "radiator_mm": radiador, "tdp_rating_w": capacidad}
    alto = s.get("height")
    if not alto:
        return None
    capacidad = 65 if alto < 80 else 120 if alto < 120 else 150 if alto < 150 else 200
    return {"type": "aire", "sockets": sockets, "height_mm": int(alto), "tdp_rating_w": capacidad}


CONVERSORES = {"cpu": ("cpu", cpu), "motherboard": ("motherboard", placa), "ram": ("ram", ram), "gpu": ("gpu", gpu),
               "ssd": ("storage", ssd), "hdd": ("storage", hdd), "psu": ("psu", fuente), "case": ("case", gabinete),
               "cooler": ("cooler", disipador)}


def nombre_limpio(nombre: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\[.*?\]", "", nombre)).strip()


def seed_solotodo_parts(db: Session, instantanea: list[dict] | None = None) -> dict[str, int]:
    """Crea las piezas de la instantánea de SoloTodo (sin precios: los pone ``solotodo.sincronizar``). Idempotente."""
    from app.pcbuilder.catalog import _highlights, _sections

    piezas = instantanea if instantanea is not None else json.loads(INSTANTANEA.read_text(encoding="utf-8"))
    categorias = {c.slug: c for c in db.scalars(select(Category))}
    creadas = actualizadas = 0
    for pieza in piezas:
        slot, pc = pieza["slot"], pieza["pc"]
        slug = "discos-duros" if slot == "storage" and pc.get("form") == "3.5" else SLOT_BY_KEY[slot].category_slug
        categoria = categorias.get(slug)
        if categoria is None:
            categoria = Category(name=SLOT_BY_KEY[slot].label, slug=slug)
            db.add(categoria)
            db.flush()
            categorias[slug] = categoria
        specs = {"highlights": _highlights(slot, pc), "sections": _sections(slot, pc), "pc": pc, "pc_slot": slot, "legacy": False,
                 "fuente": FUENTE, "solotodo_id": pieza["solotodo_id"]}
        producto = db.scalar(select(Product).where(Product.name == pieza["name"]))
        if producto is None:
            producto = Product(name=pieza["name"], brand=pieza["brand"], model=pieza["model"], category_id=categoria.id, specs=specs,
                               description=f"{SLOT_BY_KEY[slot].label} {pieza['name']}. Ficha técnica: SoloTodo.",
                               image_url=pieza.get("imagen"), images=[pieza["imagen"]] if pieza.get("imagen") else [])
            db.add(producto)
            creadas += 1
        else:
            producto.specs, producto.category_id = specs, categoria.id
            actualizadas += 1
    # Si la base trae precios de referencia de la semilla (no vienen de ninguna página), dejan de contar.
    for oferta in db.scalars(select(StoreOffer).where(StoreOffer.source == "semilla-armador", StoreOffer.availability.is_(True))):
        oferta.availability = False
    db.commit()
    log.info("Catálogo SoloTodo: %d creadas, %d actualizadas", creadas, actualizadas)
    return {"creadas": creadas, "actualizadas": actualizadas, "total": len(piezas)}


def mapa_instantanea() -> dict[str, dict]:
    """Nombre de la pieza → id de SoloTodo, para ``solotodo.sincronizar``."""
    if not INSTANTANEA.exists():
        return {}
    return {p["name"]: {"solotodo_id": p["solotodo_id"]} for p in json.loads(INSTANTANEA.read_text(encoding="utf-8"))}
