"""Herramientas del agente (LangChain ``StructuredTool``).

Reutilizan los servicios del catálogo que ya existen y agregan tres familias:

* **consulta**: ``search_products``, ``get_product_offers``, ``get_price_history``,
  ``compare_products``, ``get_user_profile``, ``recall_memory``, ``check_price_alerts``;
* **razonamiento**: ``analyze_price_trend`` (convierte el historial en un veredicto
  comprar/esperar con números, para que el modelo no tenga que adivinar);
* **escritura**: ``create_price_alert``, ``save_shopping_list``, ``remember_preference``.

Cada herramienta devuelve JSON (texto) y levanta ``ToolException`` ante un error de
negocio, así el agente lo ve como observación y puede replanificar.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from fastapi import HTTPException
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.memory import MEMORY_KINDS, LongTermMemory
from app.ai.schemas.tools import CompareProductsInput, GetPriceHistoryInput, GetProductOffersInput, GetUserProfileInput, SearchProductsInput
from app.ai.tools.catalog import CompareProductsTool, GetPriceHistoryTool, GetProductOffersTool, SearchProductsTool
from app.ai.tools.user_profile import GetUserProfileTool
from app.models.agent import PriceAlert, ShoppingList
from app.models.catalog import Product
from app.services.product_service import ProductService

READ_TOOLS = ("search_products", "get_product_offers", "get_price_history", "compare_products", "get_user_profile", "recall_memory", "check_price_alerts", "analyze_price_trend")
WRITE_TOOLS = ("create_price_alert", "save_shopping_list", "remember_preference")


# El pedido tiene que mencionar una lista o pedir guardar/armar/anotar para que se guarde una lista. Es una regla
# en código y no solo en el prompt: Gemini guardaba listas que el usuario no había pedido.
LIST_INTENT = re.compile(r"\blist[ao]s?\b|\bguard(a|á|ar|e|alo|álo|ame)\w*|\barm(a|ar|ame|alo)\w*|\bañad(e|ir)\w*|\bagreg(a|ar)\w*|\banot(a|ar|á)\w*", re.IGNORECASE)


class RunContext:
    """Estado de la ejecución en curso que las herramientas necesitan: el pedido del usuario."""

    def __init__(self) -> None:
        self.goal = ""


class ProductIdInput(BaseModel):
    product_id: int = Field(ge=1, description="Identificador del producto en el catálogo")


class RecallMemoryInput(BaseModel):
    query: str = Field(min_length=2, max_length=200, description="Qué se quiere recordar del usuario")
    limit: int = Field(default=4, ge=1, le=10)


class RememberPreferenceInput(BaseModel):
    content: str = Field(min_length=3, max_length=400, description="Preferencia o dato estable del usuario, en una frase autocontenida")
    kind: str = Field(default="preference", description="preference | fact")
    importance: int = Field(default=3, ge=1, le=5)


class CreatePriceAlertInput(BaseModel):
    product_id: int = Field(ge=1)
    target_price_clp: int = Field(ge=1, description="Precio (CLP) bajo el cual el usuario quiere que se le avise")


class SaveShoppingListInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    product_ids: list[int] = Field(min_length=1, max_length=15)
    budget_clp: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=500)


class NoInput(BaseModel):
    pass


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _lowest(product: Product) -> tuple[int, str, str] | None:
    offer = product.lowest_offer
    if offer is None:
        return None
    return int(offer.price), offer.store.name if offer.store else "", offer.url


def trend_verdict(history_prices: list[int], current: int | None) -> dict[str, Any]:
    """Veredicto numérico a partir del historial. Puro: se prueba sin base de datos."""
    if current is None:
        return {"verdict": "sin_precio_actual", "reason": "El producto no tiene ofertas disponibles."}
    prices = [p for p in history_prices if p]
    if len(prices) < 3:
        return {"verdict": "sin_historial_suficiente", "current_clp": current, "points": len(prices), "reason": "Hay menos de 3 observaciones de precio: no se puede juzgar la tendencia."}
    low, high, avg = min(prices), max(prices), round(mean(prices))
    vs_avg = round((current - avg) / avg * 100, 1)
    if current <= low * 1.03:
        verdict, reason = "buen_momento", f"El precio actual está a menos de 3% del mínimo histórico (${low:,}).".replace(",", ".")
    elif current >= avg * 1.05:
        verdict, reason = "esperar", f"El precio actual está {vs_avg}% sobre el promedio histórico (${avg:,}).".replace(",", ".")
    else:
        verdict, reason = "precio_normal", f"El precio actual está cerca del promedio histórico (${avg:,}).".replace(",", ".")
    return {"verdict": verdict, "current_clp": current, "min_clp": low, "max_clp": high, "avg_clp": avg, "vs_avg_pct": vs_avg, "points": len(prices), "reason": reason}


def build_tools(db: Session, user_id: str, memory: LongTermMemory, context: RunContext | None = None) -> list[StructuredTool]:
    """Construye las herramientas ligadas a una sesión de base de datos y a un usuario."""
    products = ProductService(db)

    # Todas las herramientas comparten UNA sesión de base de datos, que no admite uso simultáneo. Gemini suele
    # pedir varias herramientas en un mismo paso y LangGraph las ejecuta en paralelo (hilos): sin este candado,
    # dos búsquedas a la vez fallaban con «concurrent operations are not permitted». Se ejecutan de a una.
    db_lock = threading.RLock()

    def guarded(fn):
        def run(**kwargs):
            try:
                with db_lock:
                    return _dump(fn(**kwargs))
            except HTTPException as error:
                raise ToolException(str(error.detail)) from error
            except ValueError as error:
                raise ToolException(str(error)) from error

        run.__name__ = fn.__name__
        return run

    # -- consulta ----------------------------------------------------------------------
    def search_products(**kwargs):
        return SearchProductsTool(db).execute(SearchProductsInput(**kwargs))

    def get_product_offers(product_id: int, limit: int = 10):
        return GetProductOffersTool(db).execute(GetProductOffersInput(product_id=product_id, limit=limit))

    def get_price_history(product_id: int, limit: int = 20):
        return GetPriceHistoryTool(db).execute(GetPriceHistoryInput(product_id=product_id, limit=limit))

    def compare_products(product_ids: list[int], limit_specs: int = 60):
        return CompareProductsTool(db).execute(CompareProductsInput(product_ids=product_ids, limit_specs=limit_specs))

    def get_user_profile():
        return GetUserProfileTool(db, user_id).execute(GetUserProfileInput())

    def recall_memory(query: str, limit: int = 4):
        hits = memory.search(query, k=limit)
        return {"memories": [{"kind": h.kind, "content": h.content, "relevance": h.score} for h in hits], "total": len(hits)}

    def check_price_alerts():
        alerts = list(db.scalars(select(PriceAlert).where(PriceAlert.user_id == user_id, PriceAlert.active.is_(True)).order_by(PriceAlert.id)))
        now = datetime.now(timezone.utc)
        report, newly = [], 0
        for alert in alerts:
            product = db.get(Product, alert.product_id)
            low = _lowest(product) if product else None
            current = low[0] if low else None
            hit = current is not None and current <= alert.target_price_clp
            if hit:
                alert.active, alert.triggered_at, alert.triggered_price_clp = False, now, current
                newly += 1
            report.append({"alert_id": alert.id, "product_id": alert.product_id, "product": product.name if product else None, "target_price_clp": alert.target_price_clp, "current_price_clp": current, "store": low[1] if low else None, "triggered": hit})
        db.commit()
        return {"alerts": report, "active_checked": len(alerts), "newly_triggered": newly}

    # -- razonamiento ------------------------------------------------------------------
    def analyze_price_trend(product_id: int):
        product = products.get(product_id)
        low = _lowest(product)
        history = products.price_history(product_id)
        result = trend_verdict([int(item.price) for item in history], low[0] if low else None)
        return {"product_id": product_id, "product": product.name, **result}

    # -- escritura ---------------------------------------------------------------------
    def create_price_alert(product_id: int, target_price_clp: int):
        product = products.get(product_id)
        low = _lowest(product)
        current = low[0] if low else None
        alert = db.scalar(select(PriceAlert).where(PriceAlert.user_id == user_id, PriceAlert.product_id == product_id, PriceAlert.active.is_(True)))
        updated = alert is not None
        if alert is None:
            alert = PriceAlert(user_id=user_id, product_id=product_id, target_price_clp=target_price_clp, price_at_creation_clp=current)
            db.add(alert)
        else:
            alert.target_price_clp = target_price_clp
        db.commit()
        db.refresh(alert)
        return {"alert_id": alert.id, "product": product.name, "target_price_clp": alert.target_price_clp, "current_price_clp": current, "already_met": current is not None and current <= target_price_clp, "updated_existing": updated}

    def save_shopping_list(name: str, product_ids: list[int], budget_clp: int | None = None, notes: str | None = None):
        if context is not None and context.goal and not LIST_INTENT.search(context.goal):
            return {"saved": False, "reason": "El usuario no pidió guardar una lista. No se guardó nada: da la recomendación y ofrécele guardarla si quiere."}
        items, skipped = [], []
        for pid in dict.fromkeys(product_ids):
            product = db.get(Product, pid)
            low = _lowest(product) if product else None
            if product is None or low is None:
                skipped.append({"product_id": pid, "reason": "no existe o no tiene oferta disponible"})
                continue
            items.append({"product_id": pid, "name": product.name, "price_clp": low[0], "store": low[1], "url": low[2]})
        if not items:
            raise ValueError("Ninguno de los productos tiene una oferta disponible; no se guardó la lista.")
        total = sum(item["price_clp"] for item in items)
        shopping = ShoppingList(user_id=user_id, name=name, items=items, total_clp=total, budget_clp=budget_clp, notes=notes)
        db.add(shopping)
        db.commit()
        db.refresh(shopping)
        return {"list_id": shopping.id, "name": name, "items": items, "total_clp": total, "budget_clp": budget_clp, "within_budget": None if budget_clp is None else total <= budget_clp, "skipped": skipped}

    def remember_preference(content: str, kind: str = "preference", importance: int = 3):
        if kind not in MEMORY_KINDS[:2]:
            raise ValueError("kind debe ser 'preference' o 'fact'")
        memory_row, created = memory.add(content, kind=kind, importance=importance)
        return {"memory_id": memory_row.id, "created": created, "content": memory_row.content}

    def tool(name: str, description: str, fn, schema: type[BaseModel]) -> StructuredTool:
        return StructuredTool.from_function(func=guarded(fn), name=name, description=description, args_schema=schema, handle_tool_error=True)

    return [
        tool("search_products", "Busca productos del catálogo por texto, categoría, marca y rango de precio (CLP). Devuelve id, nombre y el menor precio vigente.", search_products, SearchProductsInput),
        tool("get_product_offers", "Lista las ofertas (tienda, precio, stock) de un producto, de la más barata a la más cara.", get_product_offers, GetProductOffersInput),
        tool("get_price_history", "Historial crudo de precios de un producto.", get_price_history, GetPriceHistoryInput),
        tool("analyze_price_trend", "Dice si es buen momento para comprar un producto (buen_momento / precio_normal / esperar) comparando su precio actual con el mínimo y el promedio históricos.", analyze_price_trend, ProductIdInput),
        tool("compare_products", "Compara de 2 a 5 productos lado a lado (especificaciones y precio).", compare_products, CompareProductsInput),
        tool("get_user_profile", "Preferencias guardadas del usuario: presupuesto típico, categorías y marcas favoritas o rechazadas.", get_user_profile, GetUserProfileInput),
        tool("recall_memory", "Busca en la memoria de largo plazo del usuario (preferencias, hechos y tareas anteriores) por significado.", recall_memory, RecallMemoryInput),
        tool("check_price_alerts", "Revisa las alertas de precio activas del usuario contra los precios de hoy y marca las que ya se cumplieron.", check_price_alerts, NoInput),
        tool("create_price_alert", "ESCRIBE una alerta: avisar al usuario cuando un producto baje de un precio objetivo.", create_price_alert, CreatePriceAlertInput),
        tool("save_shopping_list", "ESCRIBE una lista de compra con los productos elegidos, su mejor oferta y el total frente al presupuesto.", save_shopping_list, SaveShoppingListInput),
        tool("remember_preference", "ESCRIBE en la memoria de largo plazo una preferencia o dato estable del usuario (marca que evita, uso, presupuesto) para sesiones futuras.", remember_preference, RememberPreferenceInput),
    ]
