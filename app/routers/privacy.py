"""Derechos sobre los datos personales (Ley 19.628 y Ley 21.719): acceso (descargar) y supresión (borrar).

Las trazas de la IA no guardan el id del usuario sino un seudónimo; al borrar se eliminan también las trazas con ese
seudónimo y el historial de conversación del agente.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser, get_current_user
from app.db import get_db
from app.models.account import UserAccount
from app.models.agent import AgentMemory, PriceAlert, ShoppingList
from app.models.observability import AgentRun, AgentSpan
from app.models.pc import PcBuild
from app.models.user_profile import UserProfile
from app.observability.redaction import pseudonym
from app.pcbuilder.service import pc_view

router = APIRouter(prefix="/me/data", tags=["privacidad"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
log = logging.getLogger(__name__)

USER_TABLES = (PcBuild, ShoppingList, PriceAlert, AgentMemory, UserProfile)


class DeleteIn(BaseModel):
    confirm: Literal["BORRAR"]
    delete_account: bool = True


def _rows(db: Session, model, user_id: str) -> list[dict[str, Any]]:
    out = []
    for row in db.scalars(select(model).where(model.user_id == user_id)):
        values = {c.name: getattr(row, c.name) for c in model.__table__.columns}
        out.append({k: v.isoformat() if isinstance(v, datetime) else v for k, v in values.items()})
    return out


def _agent_threads(user_id: str) -> int:
    """Borra el historial de conversación del agente (checkpoints con hilo «usuario:…»)."""
    try:
        from app.agent.service import default_checkpointer

        saver = default_checkpointer()
        threads = {c.config["configurable"]["thread_id"] for c in saver.list(None) if str(c.config["configurable"].get("thread_id", "")).startswith(f"{user_id}:")}
        for thread in threads:
            saver.delete_thread(thread)
        return len(threads)
    except Exception:  # noqa: BLE001 — el resto del borrado no debe depender del historial
        log.warning("No se pudo borrar el historial del agente", exc_info=True)
        return 0


@router.get("", summary="Descargar todos mis datos (derecho de acceso)")
def export_data(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    account = db.get(UserAccount, user.id)
    user_hash = pseudonym(user.id)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account": {"id": user.id, "email": user.email, "display_name": account.display_name if account else None,
                    "created_at": account.created_at.isoformat() if account and account.created_at else None},
        "computers": [pc_view(db, pc) for pc in db.scalars(select(PcBuild).where(PcBuild.user_id == user.id))],
        "shopping_lists": _rows(db, ShoppingList, user.id),
        "price_alerts": _rows(db, PriceAlert, user.id),
        "agent_memories": _rows(db, AgentMemory, user.id),
        "profile": (_rows(db, UserProfile, user.id) or [None])[0],
        "ai_usage": {"runs": db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.user_hash == user_hash)) or 0,
                     "note": "Las trazas de la IA guardan un seudónimo y una vista previa con datos personales enmascarados, no el texto completo."},
    }


@router.delete("", summary="Borrar todos mis datos (derecho de supresión)")
def delete_data(payload: DeleteIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    deleted: dict[str, int] = {}
    for model in USER_TABLES:
        deleted[model.__tablename__] = db.execute(delete(model).where(model.user_id == user.id)).rowcount or 0
    user_hash = pseudonym(user.id)
    run_ids = list(db.scalars(select(AgentRun.run_id).where(AgentRun.user_hash == user_hash)))
    if run_ids:
        db.execute(delete(AgentSpan).where(AgentSpan.run_id.in_(run_ids)))
    deleted["agent_runs"] = db.execute(delete(AgentRun).where(AgentRun.user_hash == user_hash)).rowcount or 0
    if payload.delete_account:
        deleted["user_accounts"] = db.execute(delete(UserAccount).where(UserAccount.id == user.id)).rowcount or 0
    db.commit()
    deleted["agent_threads"] = _agent_threads(user.id)
    log.info("Datos de usuario borrados a pedido: %s", {k: v for k, v in deleted.items() if v})
    return {"deleted": deleted, "account_deleted": bool(payload.delete_account)}

