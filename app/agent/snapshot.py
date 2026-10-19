"""Resumen de lo que el agente dejó guardado para un usuario (alertas, listas y memoria)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import AgentMemory, PriceAlert, ShoppingList
from app.models.catalog import Product


def snapshot(db: Session, user_id: str) -> dict[str, Any]:
    alerts = []
    for alert in db.scalars(select(PriceAlert).where(PriceAlert.user_id == user_id).order_by(PriceAlert.id.desc())):
        product = db.get(Product, alert.product_id)
        alerts.append(
            {
                "id": alert.id,
                "product": product.name if product else f"#{alert.product_id}",
                "target_price_clp": alert.target_price_clp,
                "current_price_clp": product.lowest_price if product else None,
                "active": alert.active,
                "triggered_price_clp": alert.triggered_price_clp,
            }
        )
    lists = [
        {"id": s.id, "name": s.name, "total_clp": s.total_clp, "budget_clp": s.budget_clp, "items": [{"name": i["name"], "price_clp": i["price_clp"], "store": i["store"]} for i in s.items]}
        for s in db.scalars(select(ShoppingList).where(ShoppingList.user_id == user_id).order_by(ShoppingList.id.desc()))
    ]
    memories = [
        {"id": m.id, "kind": m.kind, "content": m.content, "importance": m.importance}
        for m in db.scalars(select(AgentMemory).where(AgentMemory.user_id == user_id).order_by(AgentMemory.id.desc()))
    ]
    return {"alerts": alerts, "lists": lists, "memories": memories}
