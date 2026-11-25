"""Herramientas del agente para el armador de PC.

* **consulta**: ``search_pc_parts``, ``list_my_pcs``, ``search_compatibility_guide`` (RAG sobre las guías, fuente
  interna) y ``research_part_web`` (ficha del fabricante o reseñas en la web, fuente externa, con presupuesto de
  consultas y validación de URL);
* **razonamiento**: ``check_pc_compatibility`` (motor determinista), ``recommend_pc_build`` y ``suggest_pc_upgrade``
  (recomendador): el modelo no decide compatibilidades ni inventa armados, los explica;
* **escritura**: ``save_pc_build`` (solo si el usuario pidió guardar o registrar el equipo; regla en código).
"""

from __future__ import annotations

import re
from typing import Any, Callable

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pc import PcBuild
from app.pcbuilder.catalog import load_parts, parts_by_id
from app.pcbuilder.compatibility import check_build
from app.pcbuilder.guides import search_guides
from app.pcbuilder.parts import SLOT_BY_KEY, SLOT_KEYS, Build
from app.pcbuilder.recommender import USE_CASES, Needs, recommend, suggest_upgrades
from app.pcbuilder.service import ItemIn, PcIn, PcService, resolve_build

PC_READ_TOOLS = ("search_pc_parts", "check_pc_compatibility", "recommend_pc_build", "list_my_pcs", "suggest_pc_upgrade", "search_compatibility_guide", "research_part_web")
PC_WRITE_TOOLS = ("save_pc_build",)

# Guardar un equipo es escritura: solo si el pedido lo pide («guarda», «registra», «agrega a mis computadores»…).
SAVE_PC_INTENT = re.compile(r"\bguard\w*|\bregistr\w*|\banot\w*|\bagreg\w*|\bañad\w*|mis computadores|mi perfil|\bsalva\w*", re.IGNORECASE)

KEY_SPECS = {
    "cpu": ("socket", "cores", "threads", "boost_ghz", "tdp_w", "igpu", "includes_cooler", "memory_types"),
    "motherboard": ("socket", "chipset", "form_factor", "memory_type", "ram_slots", "m2_slots", "wifi"),
    "ram": ("memory_type", "capacity_gb", "modules", "speed_mts"),
    "gpu": ("vram_gb", "length_mm", "board_power_w", "recommended_psu_w"),
    "storage": ("interface", "form", "capacity_gb", "read_mbps"),
    "psu": ("watts", "efficiency", "form_factor"),
    "case": ("form_factors", "max_gpu_mm", "max_cooler_mm", "psu_form_factors"),
    "cooler": ("type", "sockets", "height_mm", "radiator_mm", "tdp_rating_w"),
}
USE_CASE_HELP = ", ".join(f"{k} ({v.label})" for k, v in USE_CASES.items())


class SearchPcPartsInput(BaseModel):
    slot: str | None = Field(default=None, description=f"Espacio: {', '.join(SLOT_KEYS)}")
    query: str | None = Field(default=None, max_length=80, description="Texto del modelo o marca, p. ej. 'ryzen 5' o 'rtx 4060'")
    max_price_clp: int | None = Field(default=None, ge=1)
    include_discontinued: bool = Field(default=False, description="Incluir modelos descontinuados (para identificar el PC que el usuario ya tiene)")
    limit: int = Field(default=8, ge=1, le=15)


class CheckCompatibilityInput(BaseModel):
    product_ids: list[int] = Field(default_factory=list, max_length=12, description="Piezas a revisar (ids de search_pc_parts)")
    pc_id: int | None = Field(default=None, ge=1, description="Equipo guardado del usuario: las piezas nuevas reemplazan a las del mismo espacio")


class RecommendPcInput(BaseModel):
    use_case: str = Field(description=f"Uso principal: {USE_CASE_HELP}")
    budget_clp: int = Field(ge=100_000, le=20_000_000)
    cpu_brand: str | None = Field(default=None, description="AMD o Intel, solo si el usuario lo pidió")
    gpu_brand: str | None = Field(default=None, description="NVIDIA o AMD, solo si el usuario lo pidió")
    wifi: bool = False
    small: bool = Field(default=False, description="Equipo compacto (Mini-ITX)")


class UpgradeInput(BaseModel):
    pc_id: int = Field(ge=1)
    budget_clp: int = Field(ge=10_000, le=10_000_000)
    use_case: str | None = Field(default=None, description=f"Uso para el que quiere mejorar: {USE_CASE_HELP}")


class GuideInput(BaseModel):
    query: str = Field(min_length=3, max_length=200, description="Pregunta o concepto (socket, DDR5, watts de la fuente, doble canal…)")


class SavePcInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    product_ids: list[int] = Field(min_length=1, max_length=12)
    kind: str = Field(default="proyecto", pattern="^(propio|proyecto)$", description="propio = el PC que ya tiene; proyecto = uno que planea armar")
    use_case: str | None = None
    budget_clp: int | None = Field(default=None, ge=0)


class NoArgs(BaseModel):
    pass


def _short(part) -> dict[str, Any]:
    keys = KEY_SPECS.get(part.slot, ())
    return {"product_id": part.product_id, "slot": part.slot, "name": part.name, "price_clp": part.price_clp, "discontinued": part.legacy,
            "specs": {k: part.specs[k] for k in keys if k in part.specs}}


def _report_view(build: Build) -> dict[str, Any]:
    report = check_build(build).as_dict()
    return {
        "parts": [{"slot": p.slot, "name": p.name, "price_clp": p.price_clp} for p in build.parts],
        "compatible": report["compatible"], "complete": report["complete"], "summary": report["summary"],
        "issues": [{"level": i["level"], "code": i["code"], "message": i["message"]} for i in report["issues"] if i["level"] != "info"][:8],
        "notes": [i["message"] for i in report["issues"] if i["level"] == "info"][:4],
        "missing": report["missing_labels"], "estimated_watts": report["estimated_watts"], "recommended_psu_w": report["recommended_psu_w"],
        "total_clp": report["total_clp"],
    }


class ResearchPartInput(BaseModel):
    product_id: int = Field(ge=1, description="Pieza del armador (id de search_pc_parts)")
    question: str = Field(min_length=3, max_length=160, description="Qué dato falta, p. ej. 'largo de la tarjeta en mm' o 'soporta Ryzen 9000 con BIOS'")


def _web_research(db: Session):
    """Fábrica del servicio de investigación web (DuckDuckGo + descarga validada); las pruebas la reemplazan."""
    from app.ai.research.web_research_service import WebResearchService

    return WebResearchService.from_settings(db=db)


def build_pc_tools(db: Session, user_id: str, context: Any, tool: Callable) -> list:
    def search_pc_parts(slot: str | None = None, query: str | None = None, max_price_clp: int | None = None, include_discontinued: bool = False, limit: int = 8):
        if slot and slot not in SLOT_BY_KEY:
            raise ValueError(f"slot debe ser uno de: {', '.join(SLOT_KEYS)}")
        terms = [t for t in re.split(r"\s+", (query or "").lower()) if t]
        found = []
        for part in load_parts(db):
            if slot and part.slot != slot:
                continue
            if part.legacy and not include_discontinued:
                continue
            if max_price_clp and (part.price_clp is None or part.price_clp > max_price_clp):
                continue
            haystack = part.name.lower().replace("-", " ") + " " + part.name.lower()
            if terms and not all(t.replace("-", " ") in haystack or t in haystack for t in terms):
                continue
            found.append(part)
        found.sort(key=lambda p: (p.price_clp is None, p.price_clp or 0))
        return {"items": [_short(p) for p in found[:limit]], "total": len(found)}

    def check_pc_compatibility(product_ids: list[int] | None = None, pc_id: int | None = None):
        product_ids = list(dict.fromkeys(product_ids or []))
        if not product_ids and not pc_id:
            raise ValueError("Indique product_ids o pc_id")
        build = Build()
        if pc_id:
            pc = db.get(PcBuild, pc_id)
            if pc is None or pc.user_id != user_id:
                raise ValueError("Ese equipo no existe en el perfil del usuario")
            build = resolve_build(db, pc.items or [])
        found = parts_by_id(db, product_ids)
        missing = [pid for pid in product_ids if pid not in found]
        if missing:
            raise ValueError(f"Estos ids no son piezas del armador: {missing}. Búsquelas con search_pc_parts.")
        for pid in product_ids:
            build.add(found[pid])
        return _report_view(build)

    def recommend_pc_build(use_case: str, budget_clp: int, cpu_brand: str | None = None, gpu_brand: str | None = None, wifi: bool = False, small: bool = False):
        if use_case not in USE_CASES:
            raise ValueError(f"use_case debe ser uno de: {', '.join(USE_CASES)}")
        rec = recommend(load_parts(db), Needs(use_case, budget_clp, cpu_brand, gpu_brand, wifi, small))
        data = rec.as_dict()
        return {
            "use_case": data["use_case_label"], "budget_clp": budget_clp, "within_budget": data["within_budget"], "total_clp": data["total_clp"],
            "leftover_clp": data["leftover_clp"], "parts": [{"product_id": i["product_id"], "slot": i["slot"], "name": i["name"], "price_clp": i["price_clp"]} for i in data["items"]],
            "why": data["reasons"], "compatibility": data["report"]["summary"],
            "warnings": [i["message"] for i in data["report"]["issues"] if i["level"] == "warning"], "alternatives": data["alternatives"],
        }

    def list_my_pcs():
        pcs = db.scalars(select(PcBuild).where(PcBuild.user_id == user_id).order_by(PcBuild.updated_at.desc()))
        out = []
        for pc in pcs:
            build = resolve_build(db, pc.items or [])
            report = check_build(build)
            out.append({"pc_id": pc.id, "name": pc.name, "kind": pc.kind, "use_case": pc.use_case, "parts": [f"{SLOT_BY_KEY[p.slot].label}: {p.name}" for p in build.parts],
                        "compatible": report.compatible, "total_clp": build.total_clp})
        return {"pcs": out, "total": len(out)}

    def suggest_pc_upgrade(pc_id: int, budget_clp: int, use_case: str | None = None):
        return PcService(db, user_id).upgrades(pc_id, use_case, budget_clp) | {"note": "score = índice relativo de rendimiento para ese uso; gain_pct = mejora estimada"}

    def search_compatibility_guide(query: str):
        hits = search_guides(db, query, k=3)
        return {"chunks": [{"guide": h["title"], "url": h["url"], "content": h["content"]} for h in hits], "source": "Guías TodoBarato (base de conocimiento interna)"}

    def research_part_web(product_id: int, question: str):
        from app.ai.research.schemas import ResearchTarget
        from app.core.config import settings

        part = parts_by_id(db, [product_id]).get(product_id)
        if part is None:
            raise ValueError("Ese id no corresponde a una pieza del armador")
        if not settings.research_enabled:
            return {"used": False, "reason": "La búsqueda en la web está desactivada; responda solo con el catálogo y las guías."}
        target = ResearchTarget(id=product_id, name=part.name, brand=part.brand, model=part.name, category=part.slot, specs={k: str(v) for k, v in part.specs.items() if v is not None})
        report = _web_research(db).research([target], question)
        if report is None or not report.used:
            return {"used": False, "reason": (report.note if report else None) or "No se encontraron fuentes externas."}
        sources = [
            {"title": e["title"], "url": e["source_url"], "source": e["source_name"], "type": e["source_type"], "confidence": e["confidence"], "excerpt": (e["content"] or "")[:500]}
            for e in report.sources[:4]
        ]
        return {
            "used": True,
            "part": part.name,
            "sources": sources,
            "queries_run": report.queries_run,
            "note": "Fuente externa: cite la URL y diga que es información de la web. La compatibilidad la sigue decidiendo check_pc_compatibility; los precios, el catálogo.",
        }

    def save_pc_build(name: str, product_ids: list[int], kind: str = "proyecto", use_case: str | None = None, budget_clp: int | None = None):
        if context is not None and context.goal and not SAVE_PC_INTENT.search(context.goal):
            return {"saved": False, "reason": "El usuario no pidió guardar el equipo. No se guardó: muestre el armado y ofrézcale guardarlo en «Mis computadores»."}
        found = parts_by_id(db, list(dict.fromkeys(product_ids)))
        items = [ItemIn(slot=part.slot, product_id=part.product_id) for part in found.values()]
        if not items:
            raise ValueError("Ningún id corresponde a una pieza del armador")
        pc = PcService(db, user_id).create(PcIn(name=name, kind=kind, use_case=use_case if use_case in USE_CASES else None, budget_clp=budget_clp, items=items, source="agente"))
        return {"saved": True, "pc_id": pc["id"], "name": pc["name"], "kind": pc["kind"], "compatible": pc["report"]["compatible"], "total_clp": pc["total_clp"], "url": f"/mis-pc/{pc['id']}"}

    return [
        tool("search_pc_parts", "Busca piezas de PC del armador (procesador, placa, RAM, tarjeta gráfica, almacenamiento, fuente, gabinete, refrigeración) con sus datos técnicos clave y precio. Devuelve product_id.", search_pc_parts, SearchPcPartsInput),
        tool("check_pc_compatibility", "Revisa si un conjunto de piezas es compatible (socket, tipo de RAM, formato, largo de la tarjeta, altura del disipador, watts de la fuente, ranuras M.2). Única fuente válida para afirmar compatibilidad.", check_pc_compatibility, CheckCompatibilityInput),
        tool("recommend_pc_build", "Arma un PC completo y compatible según el uso y el presupuesto (CLP), con el motivo de cada pieza y alternativas.", recommend_pc_build, RecommendPcInput),
        tool("list_my_pcs", "Lista los computadores guardados del usuario (propios y proyectos) con sus piezas y si son compatibles.", list_my_pcs, NoArgs),
        tool("suggest_pc_upgrade", "Propone las mejores mejoras para un PC guardado del usuario dentro de un presupuesto (incluye la fuente si la nueva pieza la necesita).", suggest_pc_upgrade, UpgradeInput),
        tool("search_compatibility_guide", "Busca en las guías de compatibilidad de TodoBarato (RAG) para explicar conceptos: socket, chipset, DDR4/DDR5, doble canal, watts de la fuente, formatos, refrigeración, VRAM.", search_compatibility_guide, GuideInput),
        tool("research_part_web", "Busca en la web (fabricante, reseñas) un dato técnico de una pieza que el catálogo no tiene, p. ej. largo de una tarjeta o soporte de BIOS. Úsela solo si falta el dato; devuelve las fuentes con su URL.", research_part_web, ResearchPartInput),
        tool("save_pc_build", "ESCRIBE en «Mis computadores» del usuario un equipo con las piezas indicadas (propio o proyecto).", save_pc_build, SavePcInput),
    ]
