"""CLI entry point for the Store Discovery Tool.

Usage:
    python -m app.ingestion.discovery <url>
"""

from __future__ import annotations

import json
import sys

from app.ingestion.discovery.discovery import StoreDiscovery


def _format_result(result) -> str:
    lines = [
        "=" * 60,
        "  Store Discovery Result",
        "=" * 60,
        f"  URL:            {result.url}",
    ]
    if result.final_url and result.final_url != result.url:
        lines.append(f"  Final URL:      {result.final_url}")
    lines.append(f"  HTTP Status:    {result.http_status or 'N/A'}")

    if result.detected_platform:
        p = result.detected_platform
        lines.append(f"  Platform:       {p.name} (confidence: {p.confidence})")
        for sig in p.signals:
            lines.append(f"    - {sig}")
    else:
        lines.append("  Platform:       Not detected")

    lines.append("")
    lines.append("  --- Structured Data ---")
    lines.append(f"  JSON-LD:        {'Yes' if result.json_ld_found else 'No'}")
    lines.append(f"    Product:      {'Yes' if result.json_ld_product_found else 'No'}")
    lines.append(f"    Offer:        {'Yes' if result.json_ld_offer_found else 'No'}")
    lines.append(f"  Embedded JSON:  {'Yes' if result.embedded_json_found else 'No'}")
    lines.append(f"  Meta Tags:      {'Yes' if result.meta_data_found else 'No'}")

    lines.append("")
    lines.append("  --- Product Data ---")
    lines.append(f"  Name:           {'Yes' if result.product_name_found else 'No'}")
    lines.append(f"  Price:          {'Yes' if result.price_found else 'No'}")
    lines.append(f"  Currency:       {'Yes' if result.currency_found else 'No'}")
    lines.append(f"  Availability:   {'Yes' if result.availability_found else 'No'}")
    lines.append(f"  SKU:            {'Yes' if result.sku_found else 'No'}")
    lines.append(f"  GTIN:           {'Yes' if result.gtin_found else 'No'}")
    lines.append(f"  MPN:            {'Yes' if result.mpn_found else 'No'}")
    lines.append(f"  Brand:          {'Yes' if result.brand_found else 'No'}")
    lines.append(f"  Image:          {'Yes' if result.image_found else 'No'}")
    lines.append(f"  Product URL:    {'Yes' if result.product_url_found else 'No'}")

    if result.structured_sources:
        lines.append("")
        lines.append(f"  Sources:        {', '.join(result.structured_sources)}")

    if result.warnings:
        lines.append("")
        lines.append("  --- Warnings ---")
        for w in result.warnings:
            lines.append(f"  ⚠  {w}")

    if result.errors:
        lines.append("")
        lines.append("  --- Errors ---")
        for e in result.errors:
            lines.append(f"  ✗  {e}")

    lines.append("=" * 60)
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m app.ingestion.discovery <url>", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    discovery = StoreDiscovery()
    result = discovery.discover(url)

    if "--json" in sys.argv:
        print(json.dumps(
            {
                "url": result.url,
                "final_url": result.final_url,
                "http_status": result.http_status,
                "content_type": result.content_type,
                "title": result.title,
                "detected_platform": {
                    "name": result.detected_platform.name,
                    "confidence": result.detected_platform.confidence,
                    "signals": result.detected_platform.signals,
                } if result.detected_platform else None,
                "json_ld_found": result.json_ld_found,
                "json_ld_product_found": result.json_ld_product_found,
                "json_ld_offer_found": result.json_ld_offer_found,
                "embedded_json_found": result.embedded_json_found,
                "meta_data_found": result.meta_data_found,
                "price_found": result.price_found,
                "currency_found": result.currency_found,
                "availability_found": result.availability_found,
                "sku_found": result.sku_found,
                "gtin_found": result.gtin_found,
                "mpn_found": result.mpn_found,
                "brand_found": result.brand_found,
                "product_name_found": result.product_name_found,
                "image_found": result.image_found,
                "product_url_found": result.product_url_found,
                "structured_sources": result.structured_sources,
                "warnings": result.warnings,
                "errors": result.errors,
            },
            indent=2,
            ensure_ascii=False,
        ))
    else:
        print(_format_result(result))


if __name__ == "__main__":
    main()
