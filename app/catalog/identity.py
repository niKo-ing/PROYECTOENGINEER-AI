"""Product identity normalization.

Conservative normalization for product identity fields.
Normalization is for COMPARISON — stored values retain original form.

Design principles:
- GTIN: aggressive (digits only, standardized identifier)
- Brand: conservative (strip + lowercase)
- MPN: moderate (strip + uppercase + collapse whitespace, keep separators)
- Model: moderate (strip + lowercase + collapse whitespace)
- Manufacturer SKU: conservative (strip + uppercase)

NEVER delete information that differentiates:
capacity, variant, generation, model, edition, color, memory, storage, size.
"""

from __future__ import annotations

import re
import unicodedata


def normalize_gtin(value: str | None) -> str | None:
    """Normalize GTIN/EAN/UPC to digits-only string.

    GTIN is a standardized identifier — safe to aggressive normalization.
    Returns None if input is None, empty, or not valid digits.
    """
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    if not digits:
        return None
    # GTIN-8, GTIN-12, GTIN-13, GTIN-14
    if len(digits) not in (8, 12, 13, 14):
        return None
    return digits


def normalize_brand(value: str | None) -> str | None:
    """Normalize brand for comparison. Conservative.

    - Strip whitespace
    - Lowercase
    - Normalize unicode accents
    - Do NOT merge distinct brands
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    # Normalize unicode: decompose then strip combining marks
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = unicodedata.normalize("NFC", text)
    text = text.lower().strip()
    return text or None


def normalize_mpn(value: str | None) -> str | None:
    """Normalize MPN for comparison. Moderate.

    - Strip whitespace
    - Uppercase
    - Collapse multiple whitespace to single space
    - Keep hyphens, dots, slashes (they differentiate variants)
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    text = text.upper()
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalize_model(value: str | None) -> str | None:
    """Normalize model for comparison. Moderate.

    - Strip whitespace
    - Lowercase
    - Collapse multiple whitespace to single space
    - Keep hyphens, dots, slashes (they differentiate variants)
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalize_manufacturer_sku(value: str | None) -> str | None:
    """Normalize manufacturer SKU for comparison. Conservative.

    - Strip whitespace
    - Uppercase
    - Do NOT strip hyphens or other separators
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    text = text.upper()
    return text or None


def normalize_identity_pair(
    brand: str | None,
    model: str | None,
) -> tuple[str, str] | None:
    """Create a normalized (brand, model) pair for identity comparison.

    Returns None if either field is missing after normalization.
    """
    b = normalize_brand(brand)
    m = normalize_model(model)
    if b and m:
        return (b, m)
    return None


# ── MPN comparison variants ────────────────────────────────────────

_MPNASEP_RE = re.compile(r"[\s\-_. /\\]+")


def mpn_variants(value: str | None) -> set[str]:
    """Generate comparison variants for an MPN.

    Different stores may format the same MPN differently:
    "RTX-5070" vs "RTX 5070" vs "RTX5070"

    Returns a set of normalized variants for matching.
    """
    if not value:
        return set()
    normalized = normalize_mpn(value)
    if not normalized:
        return set()

    variants = {normalized}

    # Version with all separators removed
    stripped = _MPNASEP_RE.sub("", normalized)
    if stripped:
        variants.add(stripped)

    # Version with spaces replacing separators
    collapsed = _MPNASEP_RE.sub(" ", normalized).strip()
    if collapsed:
        variants.add(collapsed)

    return variants


def mpn_matches(incoming_mpn: str | None, stored_mpn: str | None) -> bool:
    """Check if two MPNs match using variant comparison.

    Conservative: both MPNs must have at least one common variant.
    """
    if not incoming_mpn or not stored_mpn:
        return False
    incoming_variants = mpn_variants(incoming_mpn)
    stored_variants = mpn_variants(stored_mpn)
    return bool(incoming_variants & stored_variants)
