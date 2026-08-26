from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class NormalizedOffer:
    """Portable connector output. It deliberately has no database identity."""

    source: str
    external_id: str | None
    product_url: str
    name: str
    brand: str | None
    model: str | None
    mpn: str | None
    gtin: str | None
    sku: str | None
    price: Decimal
    previous_price: Decimal | None
    currency: str
    availability: bool
    stock: str | None
    image_url: str | None
    category: str | None
    scraped_at: datetime
