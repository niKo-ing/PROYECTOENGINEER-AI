from decimal import Decimal
from urllib.parse import urlparse

from app.ingestion.dto import NormalizedOffer
from app.models.catalog import OfferCondition


class OfferValidationError(ValueError):
    pass


class OfferValidator:
    def validate(self, offer: NormalizedOffer) -> None:
        if not offer.source.strip() or not offer.name.strip():
            raise OfferValidationError("source y name son obligatorios")
        if urlparse(offer.product_url).scheme not in {"http", "https"}:
            raise OfferValidationError("product_url debe ser HTTP(S)")
        if offer.price <= Decimal("0"):
            raise OfferValidationError("price debe ser mayor a 0")
        if len(offer.currency) != 3 or not offer.currency.isalpha():
            raise OfferValidationError("currency debe ser un código ISO de tres letras")
        if offer.condition not in {condition.value for condition in OfferCondition}:
            raise OfferValidationError("condition no es válida")
        if offer.scraped_at.tzinfo is None:
            raise OfferValidationError("scraped_at debe incluir zona horaria")
