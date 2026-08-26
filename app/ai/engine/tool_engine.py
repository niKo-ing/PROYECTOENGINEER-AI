from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.ai.schemas.tools import GetPriceHistoryInput, GetProductInput, GetProductOffersInput, GetUserProfileInput, SearchProductsInput, ToolExecutionRequest, ToolExecutionResult
from app.ai.tools.catalog import GetPriceHistoryTool, GetProductOffersTool, GetProductTool, SearchProductsTool
from app.ai.tools.user_profile import GetUserProfileTool
from app.core.security import AuthenticatedUser

ToolHandler = Callable[[BaseModel], dict[str, Any]]


class AIEngine:
    """Closed tool registry; an LLM can later call this interface safely."""

    def __init__(self, db: Session, user: AuthenticatedUser):
        self.registry: dict[str, tuple[type[BaseModel], ToolHandler]] = {
            "search_products": (SearchProductsInput, SearchProductsTool(db).execute),
            "get_product": (GetProductInput, GetProductTool(db).execute),
            "get_product_offers": (GetProductOffersInput, GetProductOffersTool(db).execute),
            "get_price_history": (GetPriceHistoryInput, GetPriceHistoryTool(db).execute),
            "get_user_profile": (GetUserProfileInput, GetUserProfileTool(db, user.id).execute),
        }

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        tool = self.registry.get(request.tool)
        if tool is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Herramienta no registrada")
        input_model, handler = tool
        try:
            parameters = input_model.model_validate(request.parameters)
        except ValidationError as error:
            detail = [{"loc": item["loc"], "msg": item["msg"], "type": item["type"]} for item in error.errors()]
            raise HTTPException(status_code=422, detail=detail) from error
        return ToolExecutionResult(tool=request.tool, data=handler(parameters))

    def tool_definitions(self) -> list[dict[str, Any]]:
        descriptions = {
            "search_products": "Busca productos aplicando texto, categoría y rango de precio.",
            "get_product": "Obtiene un resumen de un producto específico usando su identificador.",
            "get_product_offers": "Obtiene ofertas compactas de un producto, ordenadas por precio.",
            "get_price_history": "Obtiene el historial disponible de precios de un producto.",
            "get_user_profile": "Obtiene las preferencias básicas del usuario autenticado actual.",
        }
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": descriptions[name],
                    "parameters": input_model.model_json_schema(),
                    "strict": False,
                },
            }
            for name, (input_model, _) in self.registry.items()
        ]
