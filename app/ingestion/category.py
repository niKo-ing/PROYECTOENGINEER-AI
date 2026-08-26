"""Ingestion category components.

Provides deterministic mapping from store source categories
to SoloTodo internal taxonomy, filtering by priority/whitelist/blacklist,
and offer eligibility checks.
"""

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from app.catalog.taxonomy import INITIAL_TAXONOMY, TaxonomyNode


# ── Category mapper ────────────────────────────────────────────────

@dataclass(frozen=True)
class CategoryMapping:
    source_category: str
    target_slug: str


class CategoryMapper:
    """Deterministic per-store mapping from source category → internal taxonomy slug."""

    def __init__(self, store_domain: str, mappings: list[CategoryMapping] | None = None):
        self.store_domain = store_domain
        self._mappings: dict[str, str] = {}
        if mappings:
            for m in mappings:
                self._mappings[m.source_category.strip().lower()] = m.target_slug

    def register(self, source: str, target_slug: str) -> None:
        self._mappings[source.strip().lower()] = target_slug

    def map(self, source_category: str) -> str | None:
        """Return target slug or None if unmapped."""
        return self._mappings.get(source_category.strip().lower())

    def mapped_slugs(self) -> list[str]:
        return list(set(self._mappings.values()))

    @classmethod
    def build(cls, store_domain: str, mappings: dict[str, str]) -> "CategoryMapper":
        """Convenience: pass {source: target_slug} dict."""
        mapper = cls(store_domain)
        for src, slug in mappings.items():
            mapper.register(src, slug)
        return mapper


# ── Taxonomy lookup ────────────────────────────────────────────────

def _flatten_taxonomy(
    node: TaxonomyNode,
    parent_path: str = "",
) -> dict[str, TaxonomyNode]:
    """Flatten tree to slug → node dict, preserving full paths as info."""
    result: dict[str, TaxonomyNode] = {}
    result[node.slug] = node
    for child in node.children:
        result.update(_flatten_taxonomy(child, f"{parent_path}/{node.slug}"))
    return result


_TAXONOMY_BY_SLUG: dict[str, TaxonomyNode] = _flatten_taxonomy(INITIAL_TAXONOMY)


def get_taxonomy_node(slug: str) -> TaxonomyNode | None:
    return _TAXONOMY_BY_SLUG.get(slug)


def get_leaf_slugs() -> list[str]:
    return [s for s, n in _TAXONOMY_BY_SLUG.items() if not n.is_group]


def get_group_slugs() -> list[str]:
    return [s for s, n in _TAXONOMY_BY_SLUG.items() if n.is_group]


# ── Category filter ────────────────────────────────────────────────

class RejectReason(StrEnum):
    UNKNOWN_CATEGORY = "unknown_category"
    NOT_IN_WHITELIST = "not_in_whitelist"
    BLACKLISTED = "blacklisted"
    IS_GROUP_NODE = "is_group_node"


@dataclass(frozen=True)
class FilterResult:
    allowed: bool
    slug: str
    reason: RejectReason | None = None


class CategoryFilter:
    """Filter offers by taxonomy priority and whitelist/blacklist."""

    def __init__(
        self,
        allowed_priorities: frozenset[str] | None = None,
        blacklist_slugs: frozenset[str] | None = None,
        whitelist_slugs: frozenset[str] | None = None,
    ):
        self.allowed_priorities = allowed_priorities or frozenset({"P0", "P1", "P2"})
        self.blacklist_slugs = blacklist_slugs or frozenset()
        self.whitelist_slugs = whitelist_slugs

    def check(self, slug: str) -> FilterResult:
        node = get_taxonomy_node(slug)
        if node is None:
            return FilterResult(allowed=False, slug=slug, reason=RejectReason.UNKNOWN_CATEGORY)

        if node.is_group:
            return FilterResult(allowed=False, slug=slug, reason=RejectReason.IS_GROUP_NODE)

        if slug in self.blacklist_slugs:
            return FilterResult(allowed=False, slug=slug, reason=RejectReason.BLACKLISTED)

        if self.whitelist_slugs is not None and slug not in self.whitelist_slugs:
            return FilterResult(allowed=False, slug=slug, reason=RejectReason.NOT_IN_WHITELIST)

        if node.priority not in self.allowed_priorities:
            return FilterResult(allowed=False, slug=slug, reason=RejectReason.NOT_IN_WHITELIST)

        return FilterResult(allowed=True, slug=slug)


# ── Eligibility check ──────────────────────────────────────────────

class EligibilityRejectReason(StrEnum):
    MISSING_CATEGORY = "missing_category"
    MISSING_PRODUCT_IDENTITY = "missing_product_identity"
    MISSING_NAME = "missing_name"
    MISSING_URL = "missing_url"
    INVALID_PRICE = "invalid_price"
    IS_BUNDLE = "is_bundle"
    IS_SERVICE = "is_service"
    CATEGORY_NOT_ALLOWED = "category_not_allowed"


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reason: EligibilityRejectReason | None = None


_BUNDLE_KEYWORDS = frozenset({
    "bundle", "bulto", "pack", "combo", "kit", "set", "lote",
    "2 en 1", "3 en 1", "4 en 1", "5 en 1",
    "regalo", "obsequio",
})

_SERVICE_KEYWORDS = frozenset({
    "servicio", "service", "suscripción", "subscription",
    "garantía", "warranty", "garant estendida", "seguro",
    "plan", "mantención",
})

_GIFT_CARD_KEYWORDS = frozenset({
    "gift card", "tarjeta de regalo", "tarjeta de regalo",
    "vale", "voucher", "crédito", "saldo",
})


def _contains_any(text: str, keywords: frozenset[str]) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def check_eligibility(
    *,
    category_slug: str | None,
    name: str | None,
    url: str | None,
    price: int | None,
    gtin: str | None = None,
    mpn: str | None = None,
    brand: str | None = None,
    sku: str | None = None,
    product_id: str | None = None,
    category_filter: CategoryFilter | None = None,
) -> EligibilityResult:
    """Check if an offer is eligible for ingestion.

    Returns EligibilityResult with eligible=True/False and explicit reason.
    """
    # Category required
    if not category_slug:
        return EligibilityResult(eligible=False, reason=EligibilityRejectReason.MISSING_CATEGORY)

    # Category must be allowed
    if category_filter is not None:
        filter_result = category_filter.check(category_slug)
        if not filter_result.allowed:
            return EligibilityResult(eligible=False, reason=EligibilityRejectReason.CATEGORY_NOT_ALLOWED)

    # Name required
    if not name or not name.strip():
        return EligibilityResult(eligible=False, reason=EligibilityRejectReason.MISSING_NAME)

    # URL required
    if not url or not url.strip():
        return EligibilityResult(eligible=False, reason=EligibilityRejectReason.MISSING_URL)

    # Price must be > 0
    if price is None or price <= 0:
        return EligibilityResult(eligible=False, reason=EligibilityRejectReason.INVALID_PRICE)

    # Product identity: at least one of GTIN, MPN+brand, SKU, product_id
    has_gtin = bool(gtin and gtin.strip())
    has_mpn_brand = bool(mpn and mpn.strip() and brand and brand.strip())
    has_sku = bool(sku and sku.strip())
    has_product_id = bool(product_id and product_id.strip())

    if not (has_gtin or has_mpn_brand or has_sku or has_product_id):
        return EligibilityResult(eligible=False, reason=EligibilityRejectReason.MISSING_PRODUCT_IDENTITY)

    # Bundle / service / gift-card heuristics (structured signals first)
    if _contains_any(name, _BUNDLE_KEYWORDS):
        return EligibilityResult(eligible=False, reason=EligibilityRejectReason.IS_BUNDLE)

    if _contains_any(name, _SERVICE_KEYWORDS):
        return EligibilityResult(eligible=False, reason=EligibilityRejectReason.IS_SERVICE)

    if _contains_any(name, _GIFT_CARD_KEYWORDS):
        return EligibilityResult(eligible=False, reason=EligibilityRejectReason.IS_SERVICE)

    return EligibilityResult(eligible=True)


# ── URL-level eligibility check ────────────────────────────────────

_URL_BUNDLE_KEYWORDS = frozenset({
    "bundle", "bulto", "pack", "combo", "kit", "set", "lote",
    "regalo", "obsequio", "gift",
})

_URL_SERVICE_KEYWORDS = frozenset({
    "servicio", "service", "suscripcion", "subscription",
    "garantia", "warranty", "seguro", "plan", "mantencion",
    "soporte", "instalacion", "configuracion",
})

_URL_GIFT_CARD_KEYWORDS = frozenset({
    "gift-card", "tarjeta-de-regalo", "vale", "voucher", "credito", "saldo",
})


def check_url_eligibility(
    url: str,
    category_filter: CategoryFilter | None = None,
    category_slug: str | None = None,
) -> EligibilityResult:
    """Check if a URL is eligible for fetching.

    This is a lightweight check that runs BEFORE making HTTP requests.
    It filters out obviously ineligible URLs to reduce unnecessary fetches.

    Checks:
    1. URL is not empty
    2. URL has valid scheme (http/https)
    3. URL is not obviously a bundle/service/gift card based on path
    4. Category is allowed (if provided)
    """
    if not url or not url.strip():
        return EligibilityResult(eligible=False, reason=EligibilityRejectReason.MISSING_URL)

    url = url.strip()

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return EligibilityResult(eligible=False, reason=EligibilityRejectReason.MISSING_URL)

    path_lower = parsed.path.lower()

    if _contains_any(path_lower, _URL_BUNDLE_KEYWORDS):
        return EligibilityResult(eligible=False, reason=EligibilityRejectReason.IS_BUNDLE)

    if _contains_any(path_lower, _URL_SERVICE_KEYWORDS):
        return EligibilityResult(eligible=False, reason=EligibilityRejectReason.IS_SERVICE)

    if _contains_any(path_lower, _URL_GIFT_CARD_KEYWORDS):
        return EligibilityResult(eligible=False, reason=EligibilityRejectReason.IS_SERVICE)

    if category_filter is not None and category_slug:
        filter_result = category_filter.check(category_slug)
        if not filter_result.allowed:
            return EligibilityResult(eligible=False, reason=EligibilityRejectReason.CATEGORY_NOT_ALLOWED)

    return EligibilityResult(eligible=True)
