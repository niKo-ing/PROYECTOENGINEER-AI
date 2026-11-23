"""Puente entre el catálogo (``Product`` con ``specs["pc"]``) y el armador, y semilla de piezas."""

from __future__ import annotations

import logging
from urllib.parse import quote_plus

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import Category, Product, Store, StoreOffer
from app.pcbuilder.catalog_data import PARTS
from app.pcbuilder.parts import CATEGORY_TO_SLOT, SLOT_BY_KEY, Part

log = logging.getLogger(__name__)

REFERENCE_STORE = "Precio de referencia"
REFERENCE_DOMAIN = "referencia.todobarato.local"


def part_from_product(product: Product) -> Part | None:
    specs = product.specs if isinstance(product.specs, dict) else {}
    pc = specs.get("pc")
    if not isinstance(pc, dict):
        return None
    slot = specs.get("pc_slot") or CATEGORY_TO_SLOT.get(product.category_entity.slug if product.category_entity else "")
    if slot not in SLOT_BY_KEY:
        return None
    offer = product.lowest_offer
    return Part(
        slot=slot,
        name=product.name,
        specs=pc,
        product_id=product.id,
        price_clp=int(offer.price) if offer else None,
        brand=product.brand,
        store=offer.store.name if offer and offer.store else None,
        legacy=bool(specs.get("legacy")),
    )


def load_parts(db: Session) -> list[Part]:
    slugs = list(CATEGORY_TO_SLOT)
    stmt = (
        select(Product)
        .join(Category, Product.category_id == Category.id)
        .where(Category.slug.in_(slugs))
        .options(selectinload(Product.offers).selectinload(StoreOffer.store), selectinload(Product.category_entity))
    )
    parts = [part_from_product(product) for product in db.scalars(stmt)]
    return [p for p in parts if p is not None]


def parts_by_id(db: Session, product_ids: list[int]) -> dict[int, Part]:
    if not product_ids:
        return {}
    stmt = select(Product).where(Product.id.in_(product_ids)).options(selectinload(Product.offers).selectinload(StoreOffer.store), selectinload(Product.category_entity))
    out: dict[int, Part] = {}
    for product in db.scalars(stmt):
        part = part_from_product(product)
        if part is not None:
            out[product.id] = part
    return out


# ── Semilla ─────────────────────────────────────────────────────────────────────────────────────

def _highlights(slot: str, pc: dict) -> list[str]:
    if slot == "cpu":
        return [f"{pc['cores']} núcleos / {pc['threads']} hilos", f"Socket {pc['socket']}", f"Hasta {pc['boost_ghz']} GHz"]
    if slot == "motherboard":
        return [f"Socket {pc['socket']} · {pc['chipset']}", f"{pc['memory_type']} · {pc['form_factor']}", "Wi-Fi" if pc.get("wifi") else "Sin Wi-Fi"]
    if slot == "ram":
        return [f"{pc['capacity_gb']} GB {pc['memory_type']}", f"{pc['speed_mts']} MT/s"]
    if slot == "gpu":
        return [f"{pc['vram_gb']} GB de video", f"{pc['length_mm']} mm de largo", f"Fuente recomendada {pc['recommended_psu_w']} W"]
    if slot == "storage":
        return [f"{pc['capacity_gb']} GB", f"{pc['interface']} {pc['form']}", f"Lectura {pc['read_mbps']} MB/s"]
    if slot == "psu":
        return [f"{pc['watts']} W", pc["efficiency"], pc["form_factor"]]
    if slot == "case":
        return [", ".join(pc["form_factors"]), f"GPU hasta {pc['max_gpu_mm']} mm", f"Disipador hasta {pc['max_cooler_mm']} mm"]
    if slot == "cooler":
        size = f"Radiador {pc['radiator_mm']} mm" if pc.get("type") == "liquida" else f"Altura {pc['height_mm']} mm"
        return [pc["type"].capitalize(), size, f"Hasta {pc['tdp_rating_w']} W"]
    return []


LABELS = {
    "socket": "Socket", "cores": "Núcleos", "threads": "Hilos", "base_ghz": "Frecuencia base (GHz)", "boost_ghz": "Frecuencia turbo (GHz)",
    "tdp_w": "TDP (W)", "max_power_w": "Consumo máximo (W)", "igpu": "Gráficos integrados", "igpu_name": "GPU integrada", "memory_types": "Memoria compatible",
    "max_mem_mts": "Velocidad de memoria máx. (MT/s)", "includes_cooler": "Incluye disipador", "chipset": "Chipset", "form_factor": "Formato",
    "memory_type": "Tipo de memoria", "ram_slots": "Ranuras de RAM", "max_ram_gb": "RAM máxima (GB)", "m2_slots": "Ranuras M.2", "sata_ports": "Puertos SATA",
    "wifi": "Wi-Fi", "pcie_gen": "PCIe", "capacity_gb": "Capacidad (GB)", "modules": "Módulos", "speed_mts": "Velocidad (MT/s)", "cas": "Latencia CAS",
    "chip": "Fabricante del chip", "vram_gb": "Memoria de video (GB)", "length_mm": "Largo (mm)", "board_power_w": "Consumo (W)",
    "recommended_psu_w": "Fuente recomendada (W)", "interface": "Interfaz", "form": "Formato", "read_mbps": "Lectura (MB/s)", "watts": "Potencia (W)",
    "efficiency": "Eficiencia", "modular": "Modular", "form_factors": "Placas compatibles", "max_gpu_mm": "Largo máx. de GPU (mm)",
    "max_cooler_mm": "Altura máx. de disipador (mm)", "psu_form_factors": "Formato de fuente", "radiators_mm": "Radiadores (mm)", "type": "Tipo",
    "sockets": "Sockets compatibles", "height_mm": "Altura (mm)", "radiator_mm": "Radiador (mm)", "tdp_rating_w": "Capacidad de disipación (W)",
}
HIDDEN = {"cpu_score", "gaming_score", "perf", "igpu_score"}


def _fmt(value) -> str:
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "—"
    return str(value)


def _sections(slot: str, pc: dict) -> list[dict]:
    items = [{"label": LABELS.get(k, k), "value": _fmt(v)} for k, v in pc.items() if k not in HIDDEN]
    return [{"title": f"Ficha técnica · {SLOT_BY_KEY[slot].label}", "items": items}]


def seed_pc_parts(db: Session) -> dict[str, int]:
    """Crea (o actualiza) las piezas de la semilla y su oferta de referencia. Idempotente."""
    categories = {c.slug: c for c in db.scalars(select(Category))}
    store = db.scalar(select(Store).where(Store.domain == REFERENCE_DOMAIN))
    if store is None:
        store = Store(name=REFERENCE_STORE, domain=REFERENCE_DOMAIN, country="CL", trust_level=0, store_type="retailer")
        db.add(store)
        db.flush()
    created = updated = offers = 0
    for data in PARTS:
        slot = data["slot"]
        slug = "discos-duros" if slot == "storage" and data["pc"].get("form") == "3.5" else SLOT_BY_KEY[slot].category_slug
        category = categories.get(slug)
        if category is None:
            category = Category(name=SLOT_BY_KEY[slot].label, slug=slug)
            db.add(category)
            db.flush()
            categories[slug] = category
        name = f"{data['brand']} {data['model']}"
        specs = {"highlights": _highlights(slot, data["pc"]), "sections": _sections(slot, data["pc"]), "pc": data["pc"], "pc_slot": slot, "legacy": bool(data.get("legacy"))}
        product = db.scalar(select(Product).where(Product.name == name))
        if product is None:
            product = Product(name=name, brand=data["brand"], model=data["model"], category_id=category.id, specs=specs,
                              description=f"{SLOT_BY_KEY[slot].label} {name}." + (" Modelo descontinuado: sirve para registrar equipos existentes." if data.get("legacy") else ""))
            db.add(product)
            db.flush()
            created += 1
        else:
            product.specs, product.category_id = specs, category.id
            updated += 1
        price = data.get("price")
        offer = db.scalar(select(StoreOffer).where(StoreOffer.product_id == product.id, StoreOffer.store_id == store.id))
        if price and offer is None:
            db.add(StoreOffer(product_id=product.id, store_id=store.id, url=f"https://www.google.com/search?q={quote_plus(name + ' precio Chile')}",
                              price=int(price), currency="CLP", stock_status="unknown", condition="new", availability=True, source="semilla-armador"))
            offers += 1
        elif price and offer is not None:
            offer.price = int(price)
        elif not price and offer is not None:
            db.delete(offer)
    db.commit()
    log.info("Semilla del armador: %d creadas, %d actualizadas, %d ofertas nuevas", created, updated, offers)
    return {"created": created, "updated": updated, "offers": offers, "total": len(PARTS)}


def ensure_seeded(db: Session) -> None:
    """Siembra solo si el catálogo no tiene ninguna pieza del armador (primer arranque en Docker/AWS)."""
    if not load_parts(db):
        seed_pc_parts(db)
