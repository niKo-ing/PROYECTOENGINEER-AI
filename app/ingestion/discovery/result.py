from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlatformDetection:
    name: str
    confidence: float
    signals: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DiscoveryResult:
    url: str
    final_url: str | None = None
    http_status: int | None = None
    content_type: str | None = None
    title: str | None = None
    detected_platform: PlatformDetection | None = None

    json_ld_found: bool = False
    json_ld_product_found: bool = False
    json_ld_offer_found: bool = False
    embedded_json_found: bool = False
    meta_data_found: bool = False

    price_found: bool = False
    currency_found: bool = False
    availability_found: bool = False
    sku_found: bool = False
    gtin_found: bool = False
    mpn_found: bool = False
    brand_found: bool = False
    product_name_found: bool = False
    image_found: bool = False
    product_url_found: bool = False

    structured_sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    json_ld_data: list[dict[str, Any]] = field(default_factory=list)
    embedded_json_data: list[dict[str, Any]] = field(default_factory=list)
    meta_tags: dict[str, str] = field(default_factory=dict)
