from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import PriceHistory, StoreOffer


class StoreOfferRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_product(self, product_id: int) -> list[StoreOffer]:
        return list(self.db.scalars(select(StoreOffer).where(StoreOffer.product_id == product_id).options(selectinload(StoreOffer.store)).order_by(StoreOffer.price)))

    def get_price_history(self, product_id: int) -> list[PriceHistory]:
        statement = select(PriceHistory).join(StoreOffer).where(StoreOffer.product_id == product_id).order_by(PriceHistory.observed_at.asc())
        return list(self.db.scalars(statement))

    def record_price(self, offer: StoreOffer, *, price: int, original_price: int | None, observed_at: datetime | None = None) -> PriceHistory:
        history = PriceHistory(store_offer=offer, price=price, original_price=original_price, currency=offer.currency, observed_at=observed_at or datetime.now().astimezone())
        self.db.add(history)
        return history
