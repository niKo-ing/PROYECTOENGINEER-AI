"""API del armador de PC: piezas, compatibilidad, recomendación y «Mis computadores»."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.ratelimit import rate_limit
from app.core.security import AuthenticatedUser, get_current_user
from app.db import get_db
from app.pcbuilder.catalog import load_parts
from app.pcbuilder.compatibility import check_build
from app.pcbuilder.parts import SLOT_KEYS, SLOTS, Build
from app.pcbuilder.recommender import USE_CASES
from app.pcbuilder.service import BuildIn, ItemIn, NeedsIn, PcIn, PcPatch, PcService, recommend_for, resolve_build

router = APIRouter(tags=["armador de PC"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
limited = Depends(rate_limit("pc", "PC_RATE_LIMIT_PER_MINUTE", 60))


class OptionsIn(BuildIn):
    slot: str = Field(pattern="^(" + "|".join(SLOT_KEYS) + ")$")
    include_legacy: bool = False


class UpgradeIn(BaseModel):
    use_case: str | None = Field(default=None, max_length=32)
    budget_clp: int = Field(default=300_000, ge=10_000, le=10_000_000)


@router.get("/pc/slots", summary="Espacios del armador y usos disponibles")
def slots() -> dict[str, Any]:
    return {
        "slots": [{"key": s.key, "label": s.label, "required": s.required, "multiple": s.multiple} for s in SLOTS],
        "use_cases": [{"key": u.key, "label": u.label, "description": u.description} for u in USE_CASES.values()],
    }


@router.get("/pc/components", summary="Piezas de un espacio", dependencies=[limited])
def components(db: DbSession, slot: Annotated[str, Query(pattern="^(" + "|".join(SLOT_KEYS) + ")$")], include_legacy: bool = False) -> dict[str, Any]:
    parts = [p for p in load_parts(db) if p.slot == slot and (include_legacy or not p.legacy)]
    parts.sort(key=lambda p: (p.price_clp is None, p.price_clp or 0, p.name))
    return {"slot": slot, "items": [p.as_dict() for p in parts]}


@router.post("/pc/options", summary="Piezas de un espacio marcadas según la selección actual", dependencies=[limited])
def options(payload: OptionsIn, db: DbSession) -> dict[str, Any]:
    """Para cada pieza candidata del espacio: ¿calza con lo ya elegido? y, si no, por qué. Alimenta el armador."""
    current = resolve_build(db, payload.items)
    out = []
    for part in load_parts(db):
        if part.slot != payload.slot or (part.legacy and not payload.include_legacy):
            continue
        # Un disco se suma a los que ya hay; en los demás espacios la pieza reemplaza a la elegida.
        trial = Build(current.parts + [part]) if payload.slot == "storage" else current.replace(payload.slot, [part])
        report = check_build(trial)
        relevant = [i.as_dict() for i in report.issues if payload.slot in i.slots and i.level in ("error", "warning")]
        out.append({**part.as_dict(), "compatible": not any(i["level"] == "error" for i in relevant), "issues": relevant})
    out.sort(key=lambda p: (not p["compatible"], p["price_clp"] is None, p["price_clp"] or 0))
    return {"slot": payload.slot, "items": out}


@router.post("/pc/compatibility", summary="Revisa la compatibilidad de un conjunto de piezas", dependencies=[limited])
def compatibility(payload: BuildIn, db: DbSession) -> dict[str, Any]:
    build = resolve_build(db, payload.items)
    return {"items": build.as_items(), "report": check_build(build).as_dict()}


@router.post("/pc/recommend", summary="Arma un PC compatible según uso y presupuesto", dependencies=[limited])
def recommend(payload: NeedsIn, db: DbSession) -> dict[str, Any]:
    return recommend_for(db, payload.to_needs())


# ── Mis computadores ────────────────────────────────────────────────────────────────────────────

@router.get("/me/pcs", summary="Mis computadores")
def list_pcs(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return {"items": PcService(db, user.id).list()}


@router.post("/me/pcs", status_code=status.HTTP_201_CREATED, summary="Guardar un computador (propio o proyecto)")
def create_pc(payload: PcIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return PcService(db, user.id).create(payload)


@router.get("/me/pcs/{pc_id}", summary="Un computador con su reporte de compatibilidad")
def get_pc(pc_id: int, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return PcService(db, user.id).get(pc_id)


@router.patch("/me/pcs/{pc_id}", summary="Editar un computador")
def update_pc(pc_id: int, payload: PcPatch, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return PcService(db, user.id).update(pc_id, payload)


@router.delete("/me/pcs/{pc_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Borrar un computador")
def delete_pc(pc_id: int, user: CurrentUser, db: DbSession) -> Response:
    PcService(db, user.id).delete(pc_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/me/pcs/{pc_id}/upgrades", summary="Mejoras posibles para un computador según uso y presupuesto")
def upgrades(pc_id: int, payload: UpgradeIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return PcService(db, user.id).upgrades(pc_id, payload.use_case, payload.budget_clp)


__all__ = ["router", "ItemIn"]
