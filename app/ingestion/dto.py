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
    condition: str = "unknown"
    # True when this source declares numeric IDs as reliable manufacturer identity.
    # Allows numeric manufacturer_sku to be used for exact matching instead of
    # being discarded as a store-internal ID. Defaults to False (store-internal).
    sku_is_identity: bool = False
    # Ordered gallery of product image URLs (beyond image_url).
    images: list[str] | None = None
    # Description provided by the store (never AI-generated).
    description: str | None = None
    # Structured technical sheet {highlights, sections} extracted upstream.
    specs: dict | None = None
    specs_source_type: str | None = None
    specs_source_name: str | None = None
    specs_extraction_method: str | None = None
