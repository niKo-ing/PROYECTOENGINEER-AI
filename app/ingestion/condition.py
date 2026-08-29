from app.models.catalog import OfferCondition


def normalize_offer_condition(value: str | None) -> str:
    """Map store condition labels/schema.org URLs into the catalog vocabulary."""
    if not value:
        return OfferCondition.UNKNOWN.value
    normalized = value.casefold().replace("_", " ").replace("-", " ")
    if "open box" in normalized or "openbox" in normalized:
        return OfferCondition.OPEN_BOX.value
    if "refurb" in normalized or "reacond" in normalized:
        return OfferCondition.REFURBISHED.value
    if "semi" in normalized and "nuevo" in normalized:
        return OfferCondition.SEMI_NEW.value
    if "used" in normalized or "usado" in normalized:
        return OfferCondition.USED.value
    if "newcondition" in normalized or "new condition" in normalized or "new" in normalized or "nuevo" in normalized:
        return OfferCondition.NEW.value
    return OfferCondition.UNKNOWN.value
