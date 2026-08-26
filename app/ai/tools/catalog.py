from sqlalchemy.orm import Session

from app.ai.schemas.tools import GetPriceHistoryInput, GetProductInput, GetProductOffersInput, ProductToolResult, SearchProductsInput
from app.services.product_service import ProductService


class SearchProductsTool:
    def __init__(self, db: Session):
        self.service = ProductService(db)

    def execute(self, params: SearchProductsInput) -> dict:
        products, total = self.service.search(
            query=params.query,
            category=params.category,
            min_price_clp=params.min_price_clp,
            max_price_clp=params.max_price_clp,
            limit=params.limit,
            offset=0,
        )
        items = [ProductToolResult(id=item.id, name=item.name, category=item.category, price_clp=item.price_clp, rating=float(item.rating) if item.rating is not None else None).model_dump() for item in products]
        return {"items": items, "total": total}


class GetProductTool:
    def __init__(self, db: Session):
        self.service = ProductService(db)

    def execute(self, params: GetProductInput) -> dict:
        product = self.service.get(params.product_id)
        return ProductToolResult(id=product.id, name=product.name, category=product.category, price_clp=product.price_clp, rating=float(product.rating) if product.rating is not None else None).model_dump()


class GetProductOffersTool:
    def __init__(self, db: Session):
        self.service = ProductService(db)

    def execute(self, params: GetProductOffersInput) -> dict:
        offers = self.service.offers(params.product_id)
        return {"items": [{"store": offer.store.name, "price": offer.price, "currency": offer.currency, "availability": offer.availability, "stock_status": offer.stock_status, "url": offer.url, "seller_name": offer.seller_name} for offer in offers[: params.limit]], "total": len(offers)}


class GetPriceHistoryTool:
    def __init__(self, db: Session):
        self.service = ProductService(db)

    def execute(self, params: GetPriceHistoryInput) -> dict:
        history = self.service.price_history(params.product_id)
        return {"items": [{"price": item.price, "original_price": item.original_price, "currency": item.currency, "observed_at": item.observed_at.isoformat()} for item in history[-params.limit :]], "total": len(history)}
