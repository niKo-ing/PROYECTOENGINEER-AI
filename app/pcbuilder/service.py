"""Casos de uso del armador sobre la base: resolver piezas, revisar compatibilidad, recomendar y guardar equipos."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pc import PcBuild
from app.pcbuilder.catalog import load_parts, parts_by_id
from app.pcbuilder.compatibility import check_build
from app.pcbuilder.parts import SLOT_BY_KEY, SLOT_KEYS, Build, Part
from app.pcbuilder.recommender import USE_CASES, Needs, performance_score, recommend, suggest_upgrades

MAX_PCS_PER_USER = 30


class ItemIn(BaseModel):
    slot: str = Field(pattern="^(" + "|".join(SLOT_KEYS) + ")$")
    product_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, max_length=160)
    specs: dict[str, Any] | None = None


class BuildIn(BaseModel):
    items: list[ItemIn] = Field(default_factory=list, max_length=16)


class NeedsIn(BaseModel):
    use_case: str = Field(default="gaming_1080")
    budget_clp: int = Field(default=800_000, ge=100_000, le=20_000_000)
    cpu_brand: str | None = Field(default=None, max_length=16)
    gpu_brand: str | None = Field(default=None, max_length=16)
    wifi: bool = False
    small: bool = False
    min_ram_gb: int | None = Field(default=None, ge=4, le=256)
    min_storage_gb: int | None = Field(default=None, ge=120, le=20_000)

    def to_needs(self) -> Needs:
        return Needs(**self.model_dump())


class PcIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: str = Field(default="proyecto", pattern="^(propio|proyecto)$")
    use_case: str | None = Field(default=None, max_length=32)
    budget_clp: int | None = Field(default=None, ge=0, le=20_000_000)
    items: list[ItemIn] = Field(default_factory=list, max_length=16)
    notes: str | None = Field(default=None, max_length=1000)
    source: str = Field(default="manual", pattern="^(manual|asistente|agente)$")


class PcPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    kind: str | None = Field(default=None, pattern="^(propio|proyecto)$")
    use_case: str | None = Field(default=None, max_length=32)
    budget_clp: int | None = Field(default=None, ge=0, le=20_000_000)
    items: list[ItemIn] | None = Field(default=None, max_length=16)
    notes: str | None = Field(default=None, max_length=1000)


def resolve_build(db: Session, items: list[ItemIn] | list[dict]) -> Build:
    """Piezas del catálogo por ``product_id`` (con precio actual) o piezas escritas a mano con sus datos."""
    parsed = [i if isinstance(i, ItemIn) else ItemIn.model_validate(i) for i in items]
    catalog = parts_by_id(db, [i.product_id for i in parsed if i.product_id])
    build = Build()
    for item in parsed:
        if item.product_id:
            part = catalog.get(item.product_id)
            if part is None:
                raise HTTPException(422, f"El producto {item.product_id} no es una pieza del armador")
            if part.slot != item.slot:
                raise HTTPException(422, f"{part.name} es {part.label.lower()}, no {SLOT_BY_KEY[item.slot].label.lower()}")
            build.add(part)
        elif item.name:
            build.add(Part(slot=item.slot, name=item.name.strip(), specs=dict(item.specs or {})))
    return build


def items_for_storage(build: Build) -> list[dict[str, Any]]:
    out = []
    for part in build.parts:
        entry: dict[str, Any] = {"slot": part.slot, "name": part.name}
        if part.product_id:
            entry["product_id"] = part.product_id
        else:
            entry["specs"] = part.specs
        out.append(entry)
    return out


def pc_view(db: Session, pc: PcBuild, *, with_report: bool = True) -> dict[str, Any]:
    build = resolve_build(db, pc.items or []) if pc.items else Build()
    data: dict[str, Any] = {
        "id": pc.id, "name": pc.name, "kind": pc.kind, "use_case": pc.use_case,
        "use_case_label": USE_CASES[pc.use_case].label if pc.use_case in USE_CASES else None,
        "budget_clp": pc.budget_clp, "notes": pc.notes, "source": pc.source,
        "items": build.as_items(), "total_clp": build.total_clp,
        "created_at": pc.created_at.isoformat() if pc.created_at else None,
        "updated_at": pc.updated_at.isoformat() if pc.updated_at else None,
    }
    if with_report:
        report = check_build(build)
        data["report"] = report.as_dict()
        data["score"] = round(performance_score(build, pc.use_case or "gaming_1080"), 1) if build.one("cpu") else None
    return data


class PcService:
    def __init__(self, db: Session, user_id: str):
        self.db, self.user_id = db, user_id

    def _get(self, pc_id: int) -> PcBuild:
        pc = self.db.get(PcBuild, pc_id)
        if pc is None or pc.user_id != self.user_id:  # nunca revela si existe un equipo de otra persona
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipo no encontrado")
        return pc

    def list(self) -> list[dict[str, Any]]:
        pcs = self.db.scalars(select(PcBuild).where(PcBuild.user_id == self.user_id).order_by(PcBuild.updated_at.desc(), PcBuild.id.desc()))
        return [pc_view(self.db, pc) for pc in pcs]

    def get(self, pc_id: int) -> dict[str, Any]:
        return pc_view(self.db, self._get(pc_id))

    def create(self, payload: PcIn) -> dict[str, Any]:
        count = len(self.db.scalars(select(PcBuild.id).where(PcBuild.user_id == self.user_id)).all())
        if count >= MAX_PCS_PER_USER:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Puedes guardar hasta {MAX_PCS_PER_USER} equipos")
        build = resolve_build(self.db, payload.items)
        pc = PcBuild(user_id=self.user_id, name=payload.name.strip(), kind=payload.kind, use_case=payload.use_case, budget_clp=payload.budget_clp,
                     items=items_for_storage(build), notes=payload.notes, source=payload.source, last_report=check_build(build).as_dict())
        self.db.add(pc)
        self.db.commit()
        self.db.refresh(pc)
        return pc_view(self.db, pc)

    def update(self, pc_id: int, payload: PcPatch) -> dict[str, Any]:
        pc = self._get(pc_id)
        data = payload.model_dump(exclude_unset=True)
        if "items" in data and payload.items is not None:
            build = resolve_build(self.db, payload.items)
            pc.items, pc.last_report = items_for_storage(build), check_build(build).as_dict()
        for key in ("name", "kind", "use_case", "budget_clp", "notes"):
            if key in data:
                setattr(pc, key, data[key])
        self.db.commit()
        self.db.refresh(pc)
        return pc_view(self.db, pc)

    def delete(self, pc_id: int) -> None:
        self.db.delete(self._get(pc_id))
        self.db.commit()

    def upgrades(self, pc_id: int, use_case: str | None, budget_clp: int) -> dict[str, Any]:
        pc = self._get(pc_id)
        build = resolve_build(self.db, pc.items or [])
        if build.one("cpu") is None:
            raise HTTPException(422, "Para sugerir mejoras el equipo necesita al menos el procesador")
        uc = use_case or pc.use_case or "gaming_1080"
        options = suggest_upgrades(build, load_parts(self.db), uc, budget_clp)
        return {"pc_id": pc.id, "use_case": uc, "budget_clp": budget_clp, "score_now": round(performance_score(build, uc), 1), "options": [o.as_dict() for o in options]}


def recommend_for(db: Session, needs: Needs) -> dict[str, Any]:
    return recommend(load_parts(db), needs).as_dict()
