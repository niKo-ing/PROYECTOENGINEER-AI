"""Ingesta de un muestreo curado de hardware PC (CPUs, GPUs, placas madre) desde SP Digital.

Replica el mecanismo de repopulate_spdigital.py pero para las categorías de
hardware de la taxonomía (procesadores, tarjetas-graficas, placas-madre),
usando una lista curada de URLs descubiertas desde el sitemap de SP Digital.

La categoría se asigna por slug interno (kebab-case), que el servicio resuelve
por slug en _resolve_category.
"""

from app.db import SessionLocal
from app.ingestion.connectors.spdigital.connector import SPDigitalConnector
from app.ingestion.runner import IngestionRunner
from app.models.catalog import Store
from sqlalchemy import select

CURATED_URLS: dict[str, list[str]] = {
    "procesadores": [
        "https://www.spdigital.cl/procesador-intel-core-i5-10600kf-41ghz-six-core-12mb-socket-lga1200/",
        "https://www.spdigital.cl/procesador-intel-core-i5-11600kf-lga1200-39ghz-6-núcleos-12-hilos-sin-gráficos-sin-ventilador/",
        "https://www.spdigital.cl/procesador-intel-core-i7-11700k-lga1200-36ghz-8-núcleos-16-hilos-16mb-caché-sin-ventilador/",
        "https://www.spdigital.cl/procesador-intel-core-i7-12700k-12o-gen-36ghz-hasta-50ghz-socket-lga1700-con-gráficas/",
        "https://www.spdigital.cl/procesador-intel-core-i9-12900k-12o-gen-32ghz-hasta-52ghz-socket-lga1700-con-gráficas/",
        "https://www.spdigital.cl/procesador-intel-core-i7-11700f-lga-1200-8-núcleos-16-hilos-25ghz-16mb-caché-sin-gráficos/",
        "https://www.spdigital.cl/procesador-intel-core-i9-11900k-350ghz-16m-cache-up-to-530-ghz-lga1200-95w-sin-ventilador/",
    ],
    "tarjetas-graficas": [
        "https://www.spdigital.cl/asus-dual-rtx4070s-o12g-evo-pci-express-40-nvidia-nvidia-geforce-rtx-4070-super/",
        "https://www.spdigital.cl/asus-tuf-rtx3080-12g-gaming-pci-express-40-x8-nvidia-nvidiaâ-geforce-rtxâ-3080-12-gb/",
        "https://www.spdigital.cl/dual-rtx4060-o8g/",
        "https://www.spdigital.cl/dual-rx7600-o8g/",
        "https://www.spdigital.cl/dual-rtx3060-o12g-v2/",
        "https://www.spdigital.cl/gigabyte-radeon-rx-6600-pci-express-40-amd-amd-radeon-rx6600-gddr6-sdram-displayport/",
        "https://www.spdigital.cl/dual-gtx1650-4gd6-p-evo/",
        "https://www.spdigital.cl/dual-rtx3050-o8g/",
    ],
    "placas-madre": [
        "https://www.spdigital.cl/asus-prime-b650m-a-ii-csm-placa-base-micro-atx-socket-am5-amd-b650-chipset-usb-32-gen-1/",
        "https://www.spdigital.cl/asus-prime-b760m-a-ax-placa-base-micro-atx-socket-lga1700-b760-chipset-usb-32-gen-1-usb/",
        "https://www.spdigital.cl/asus-tuf-gaming-b550m-plus-wifi-ii-placa-base-micro-atx-socket-am4-amd-b550-chipset-usb-c/",
        "https://www.spdigital.cl/asus-rog-strix-z790-e-gaming-wifi-placa-base-atx-socket-lga1700-z790-chipset-usb-32-gen-1/",
        "https://www.spdigital.cl/asus-prime-z690-p-d4-placa-base-atx-socket-lga1700-z690-chipset-usb-c-gen1-usb-32-gen-1/",
        "https://www.spdigital.cl/asus-prime-h610m-e-d4-placa-base-micro-atx-socket-lga1700-h610-chipset-usb-32-gen-1-gig/",
    ],
}


def main() -> None:
    db = SessionLocal()
    try:
        domain = "www.spdigital.cl"
        store = db.scalar(select(Store).where(Store.domain == domain))
        if store is None:
            raise SystemExit(f"Store '{domain}' not found")

        urls: list[str] = []
        url_category_map: dict[str, str] = {}
        for slug, cat_urls in CURATED_URLS.items():
            urls.extend(cat_urls)
            for u in cat_urls:
                url_category_map[u] = slug

        connector = SPDigitalConnector(urls=urls, url_category_map=url_category_map)
        runner = IngestionRunner()
        run = runner.run(db=db, connector=connector, urls=urls)
        print("Run id:", run.id)
        print("status:", run.status)
        print("urls_total:", run.urls_total, "urls_processed:", run.urls_processed)
        print("products_created:", run.products_created)
        print("products_updated:", run.products_updated)
        print("price_changes:", run.price_changes)
        print("errors_count:", run.errors_count)
        if run.error_messages:
            print("errors:", run.error_messages)
        print("duration_ms:", run.duration_ms)
    finally:
        db.close()


if __name__ == "__main__":
    main()
