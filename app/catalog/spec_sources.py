"""Canonical research sources for catalog components.

Each entry maps the product component aliases (as they appear in real catalog
names, models or descriptions) to a stable URL that documents the component's
specifications. The research pipeline fetches only these URLs and never
searches the free web, keeping every extracted value traceable.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.models.catalog import Product


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


CPU_ALLOWED_KEYS = (
    "processor",
    "processor_cores",
    "processor_threads",
    "processor_base_frequency",
    "processor_boost_frequency",
    "processor_cache",
    "processor_tdp",
    "integrated_graphics",
)

GPU_ALLOWED_KEYS = (
    "gpu",
    "gpu_type",
    "gpu_vram",
)

CPU_PART_ALLOWED_KEYS = (
    "socket",
    "cores",
    "threads",
    "base_frequency",
    "boost_frequency",
    "cache",
    "tdp",
    "integrated_graphics",
    "memory_type",
    "max_memory",
    "pcie_version",
    "manufacturing_process",
    "cooler_included",
)

GPU_PART_ALLOWED_KEYS = (
    "chipset",
    "vram",
    "memory_type",
    "memory_bus",
    "base_clock",
    "boost_clock",
    "cuda_cores",
    "tdp",
    "recommended_psu",
    "power_connector",
    "length",
    "display_ports",
    "cooling",
    "pcie_interface",
)

MOTHERBOARD_ALLOWED_KEYS = (
    "socket",
    "chipset",
    "platform",
    "form_factor",
    "dimensions",
    "weight",
    "memory_type",
    "ram_slots",
    "memory_channels",
    "max_memory",
    "ecc_support",
    "xmp_support",
    "expo_support",
    "pcie_slots",
    "pcie_slot_list",
    "pcie_generation",
    "multi_gpu_support",
    "m2_slots",
    "m2_slot_list",
    "nvme_support",
    "sata_ports",
    "raid_support",
    "usb_2_count",
    "usb_3_2_gen1_count",
    "usb_3_2_gen2_count",
    "usb_3_2_gen2x2_count",
    "usb4_count",
    "usb_c_count",
    "rear_ports",
    "hdmi",
    "displayport",
    "ethernet",
    "wifi",
    "wifi_standard",
    "bluetooth",
    "bluetooth_version",
    "audio_codec",
    "audio_channels",
    "motherboard_power_connector",
    "cpu_power_connector_types",
    "pcie_power_connectors",
    "fan_headers_total",
    "cpu_fan_headers",
    "fan_header_list",
    "rgb_headers",
    "bios_flashback",
    "debug_led",
    "rear_usb_ports",
)


@dataclass(frozen=True)
class SpecSource:
    target: str
    kind: str
    aliases: tuple[str, ...]
    url: str
    source_name: str
    source_type: str = "external"
    allow_keys: tuple[str, ...] | None = None
    prefer_text: bool = False
    priority: int = 100

    @property
    def needles(self) -> tuple[str, ...]:
        return (self.target, *self.aliases)

    def matches(self, text: str) -> bool:
        normalized = _normalize(text)
        return any(_normalize(alias) in normalized for alias in self.aliases)


_g = "https://www.gsmarena.com/"

SOURCES: tuple[SpecSource, ...] = (
    SpecSource(
        target="Intel Core i3-N305",
        kind="cpu",
        aliases=("intel core i3-n305", "core i3-n305", "i3-n305"),
        url="https://cputronic.com/en/cpu/intel-core-i3-n305",
        source_name="CpuTronic",
        priority=30,
        allow_keys=CPU_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="Intel Core i5-13420H",
        kind="cpu",
        aliases=("intel core i5-13420h", "core i5-13420h", "i5-13420h"),
        url="https://cputronic.com/en/cpu/intel-core-i5-13420h",
        source_name="CpuTronic",
        priority=30,
        allow_keys=CPU_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="Intel Core i5-12450H",
        kind="cpu",
        aliases=("intel core i5-12450h", "core i5-12450h", "i5-12450h"),
        url="https://cputronic.com/en/cpu/intel-core-i5-12450h",
        source_name="CpuTronic",
        priority=30,
        allow_keys=CPU_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="Intel Core Ultra 7 155H",
        kind="cpu",
        aliases=("intel core ultra 7", "core ultra 7", "ultra 7", "155h"),
        url="https://en.wikipedia.org/wiki/Meteor_Lake",
        source_name="Wikipedia (Meteor Lake)",
        priority=20,
        allow_keys=CPU_ALLOWED_KEYS,
    ),
    SpecSource(
        target="Intel Core Ultra 9 185H",
        kind="cpu",
        aliases=("intel core ultra 9", "core ultra 9", "ultra 9", "185h"),
        url="https://en.wikipedia.org/wiki/Meteor_Lake",
        source_name="Wikipedia (Meteor Lake)",
        priority=20,
        allow_keys=CPU_ALLOWED_KEYS,
    ),
    SpecSource(
        target="AMD Ryzen 5 7520U",
        kind="cpu",
        aliases=("amd ryzen 5 7520u", "ryzen 5 7520u", "7520u"),
        url="https://en.wikipedia.org/wiki/List_of_AMD_Ryzen_processors",
        source_name="Wikipedia (List of AMD Ryzen processors)",
        priority=20,
        allow_keys=CPU_ALLOWED_KEYS,
    ),
    SpecSource(
        target="AMD Ryzen 7 7730U",
        kind="cpu",
        aliases=("amd ryzen 7 7730u", "ryzen 7 7730u", "7730u"),
        url="https://en.wikipedia.org/wiki/List_of_AMD_Ryzen_processors",
        source_name="Wikipedia (List of AMD Ryzen processors)",
        priority=20,
        allow_keys=CPU_ALLOWED_KEYS,
    ),
    SpecSource(
        target="AMD Ryzen 7 7735HS",
        kind="cpu",
        aliases=("amd ryzen 7 7735hs", "ryzen 7 7735hs", "7735hs"),
        url="https://en.wikipedia.org/wiki/List_of_AMD_Ryzen_processors",
        source_name="Wikipedia (List of AMD Ryzen processors)",
        priority=20,
        allow_keys=CPU_ALLOWED_KEYS,
    ),
    SpecSource(
        target="Intel Core i5-10600KF",
        kind="cpu",
        aliases=("intel core i5-10600kf", "core i5-10600kf", "i5-10600kf", "i5 10600kf", "10600kf"),
        url="https://cputronic.com/en/cpu/intel-core-i5-10600kf",
        source_name="CpuTronic",
        priority=30,
        allow_keys=CPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="Intel Core i5-11600KF",
        kind="cpu",
        aliases=("intel core i5-11600kf", "core i5-11600kf", "i5-11600kf", "i5 11600kf", "11600kf"),
        url="https://cputronic.com/en/cpu/intel-core-i5-11600kf",
        source_name="CpuTronic",
        priority=30,
        allow_keys=CPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="Intel Core i7-11700K",
        kind="cpu",
        aliases=("intel core i7-11700k", "core i7-11700k", "i7-11700k", "i7 11700k", "11700k"),
        url="https://cputronic.com/en/cpu/intel-core-i7-11700k",
        source_name="CpuTronic",
        priority=30,
        allow_keys=CPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="Intel Core i7-11700F",
        kind="cpu",
        aliases=("intel core i7-11700f", "core i7-11700f", "i7-11700f", "i7 11700f", "11700f"),
        url="https://cputronic.com/en/cpu/intel-core-i7-11700f",
        source_name="CpuTronic",
        priority=30,
        allow_keys=CPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="Intel Core i9-11900K",
        kind="cpu",
        aliases=("intel core i9-11900k", "core i9-11900k", "i9-11900k", "i9 11900k", "11900k"),
        url="https://cputronic.com/en/cpu/intel-core-i9-11900k",
        source_name="CpuTronic",
        priority=30,
        allow_keys=CPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="Intel Core i7-12700K",
        kind="cpu",
        aliases=("intel core i7-12700k", "core i7-12700k", "i7-12700k", "i7 12700k", "12700k"),
        url="https://cputronic.com/en/cpu/intel-core-i7-12700k",
        source_name="CpuTronic",
        priority=30,
        allow_keys=CPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="Intel Core i9-12900K",
        kind="cpu",
        aliases=("intel core i9-12900k", "core i9-12900k", "i9-12900k", "i9 12900k", "12900k"),
        url="https://cputronic.com/en/cpu/intel-core-i9-12900k",
        source_name="CpuTronic",
        priority=30,
        allow_keys=CPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="NVIDIA GeForce RTX 4070 Super",
        kind="gpu",
        aliases=("geforce rtx 4070 super", "rtx 4070 super", "rtx4070 super", "4070 super", "4070s"),
        url="https://www.notebookcheck.net/NVIDIA-GeForce-RTX-4070-SUPER-Desktop-GPU-Benchmarks-and-Specs.793708.0.html",
        source_name="Notebookcheck",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="NVIDIA GeForce RTX 3080 12GB",
        kind="gpu",
        aliases=("geforce rtx 3080", "rtx 3080", "rtx3080", "3080"),
        url="https://www.notebookcheck.net/NVIDIA-GeForce-RTX-3080-12-GB-GPU-Benchmarks-and-Specs.635433.0.html",
        source_name="Notebookcheck",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="NVIDIA GeForce RTX 4060",
        kind="gpu",
        aliases=("geforce rtx 4060 oc", "rtx 4060 oc", "rtx4060", "rtx 4060 oc", "4060 oc", "4060"),
        url="https://www.notebookcheck.net/NVIDIA-GeForce-RTX-4060-GPU-Benchmarks-and-Specs.741899.0.html",
        source_name="Notebookcheck",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="AMD Radeon RX 7600",
        kind="gpu",
        aliases=("radeon rx 7600", "rx 7600", "rx7600", "7600"),
        url="https://www.notebookcheck.net/AMD-Radeon-RX-7600-Benchmarks-and-Specs.806213.0.html",
        source_name="Notebookcheck",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="NVIDIA GeForce RTX 3060",
        kind="gpu",
        aliases=("geforce rtx 3060", "rtx 3060", "rtx3060", "3060"),
        url="https://www.notebookcheck.net/NVIDIA-GeForce-RTX-3060-Desktop-GPU-Benchmarks-and-Specs.579000.0.html",
        source_name="Notebookcheck",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="AMD Radeon RX 6600",
        kind="gpu",
        aliases=("radeon rx 6600", "rx 6600", "rx6600", "6600"),
        url="https://www.notebookcheck.net/AMD-Radeon-RX-6600-GPU-Benchmarks-and-Specs.582209.0.html",
        source_name="Notebookcheck",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="NVIDIA GeForce GTX 1650",
        kind="gpu",
        aliases=("geforce gtx 1650", "gtx 1650", "gtx1650", "1650"),
        url="https://www.notebookcheck.net/NVIDIA-GeForce-GTX-1650-Desktop-GPU-Benchmarks-and-Specs.421420.0.html",
        source_name="Notebookcheck",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="NVIDIA GeForce RTX 3050",
        kind="gpu",
        aliases=("geforce rtx 3050 oc", "rtx 3050 oc", "rtx3050", "3050 oc", "3050"),
        url="https://www.notebookcheck.net/NVIDIA-GeForce-RTX-3050-GPU-Benchmarks-and-Specs.659500.0.html",
        source_name="Notebookcheck",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="ASUS Dual GeForce RTX 4070 SUPER EVO OC",
        kind="gpu",
        aliases=("dual rtx 4070 super evo oc", "dual rtx 4070 super evo", "rtx 4070 super evo oc", "rtx 4070 super evo", "4070 super evo"),
        url="https://www.asus.com/motherboards-components/graphics-cards/dual/dual-rtx4070s-o12g-evo/techspec/",
        source_name="ASUS",
        source_type="manufacturer",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="ASUS TUF Gaming GeForce RTX 3080 12GB",
        kind="gpu",
        aliases=("tuf gaming rtx 3080 12gb", "tuf gaming geforce rtx 3080", "tuf rtx 3080", "asus tuf rtx 3080"),
        url="https://www.asus.com/motherboards-components/graphics-cards/tuf-gaming/tuf-rtx3080-12g-gaming/techspec/",
        source_name="ASUS",
        source_type="manufacturer",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="ASUS Dual GeForce RTX 4060 OC",
        kind="gpu",
        aliases=("dual rtx 4060 oc", "rtx 4060 oc edition", "dual 4060 oc", "rtx 4060 oc"),
        url="https://www.asus.com/motherboards-components/graphics-cards/dual/dual-rtx4060-o8g/techspec/",
        source_name="ASUS",
        source_type="manufacturer",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="ASUS Dual Radeon RX 7600 OC",
        kind="gpu",
        aliases=("dual radeon rx 7600 oc", "dual rx 7600 oc", "radeon rx 7600 oc edition", "rx 7600 oc"),
        url="https://www.asus.com/motherboards-components/graphics-cards/dual/dual-rx7600-o8g/techspec/",
        source_name="ASUS",
        source_type="manufacturer",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="ASUS Dual GeForce RTX 3060 V2 OC",
        kind="gpu",
        aliases=("dual rtx 3060 v2 oc", "rtx 3060 v2 oc edition", "rtx 3060 v2 oc", "dual rtx 3060 v2"),
        url="https://www.asus.com/motherboards-components/graphics-cards/dual/dual-rtx3060-o12g-v2/techspec/",
        source_name="ASUS",
        source_type="manufacturer",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="ASUS Dual GeForce GTX 1650 EVO OC",
        kind="gpu",
        aliases=("dual gtx 1650 evo oc", "dual gtx 1650 evo", "gtx 1650 evo oc", "gtx 1650 evo"),
        url="https://www.asus.com/motherboards-components/graphics-cards/dual/dual-gtx1650-o4gd6-p-evo/techspec/",
        source_name="ASUS",
        source_type="manufacturer",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="ASUS Dual GeForce RTX 3050 OC",
        kind="gpu",
        aliases=("dual rtx 3050 oc", "rtx 3050 oc edition", "dual rtx 3050", "rtx 3050 oc"),
        url="https://www.asus.com/motherboards-components/graphics-cards/dual/dual-rtx3050-o8g/techspec/",
        source_name="ASUS",
        source_type="manufacturer",
        priority=30,
        allow_keys=GPU_PART_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="NVIDIA GeForce RTX 4060 Mobile",
        kind="gpu",
        aliases=("geforce rtx 4060 laptop gpu", "rtx 4060 laptop", "rtx4060", "rtx 4060"),
        url="https://www.notebookcheck.net/NVIDIA-GeForce-RTX-4060-Laptop-GPU-Benchmarks-and-Specs.675692.0.html",
        source_name="Notebookcheck",
        priority=30,
        allow_keys=GPU_ALLOWED_KEYS,
    ),
    SpecSource(
        target="NVIDIA GeForce RTX 2050 Mobile",
        kind="gpu",
        aliases=("geforce rtx 2050 mobile", "rtx 2050 mobile", "rtx2050", "rtx 2050"),
        url="https://www.notebookcheck.net/NVIDIA-GeForce-RTX-2050-Mobile-GPU-Benchmarks-and-Specs.586930.0.html",
        source_name="Notebookcheck",
        priority=30,
        allow_keys=GPU_ALLOWED_KEYS,
    ),
    SpecSource(
        target="ASUS Prime B650M-A II-CSM",
        kind="motherboard",
        aliases=("prime b650m-a ii-csm", "prime b650m-a", "b650m-a ii", "b650m-a-ii"),
        url="https://www.asus.com/us/motherboards-components/motherboards/prime/prime-b650m-a-ii-csm/techspec/",
        source_name="ASUS",
        source_type="manufacturer",
        priority=30,
        allow_keys=MOTHERBOARD_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="ASUS Prime B760M-A AX",
        kind="motherboard",
        aliases=("prime b760m-a ax", "prime b760m-a", "b760m-a ax", "b760m-a-ax"),
        url="https://www.asus.com/us/motherboards-components/motherboards/prime/prime-b760m-a-ax/techspec/",
        source_name="ASUS",
        source_type="manufacturer",
        priority=30,
        allow_keys=MOTHERBOARD_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="ASUS TUF Gaming B550M-PLUS WIFI II",
        kind="motherboard",
        aliases=("tuf gaming b550m-plus wifi ii", "tuf gaming b550m-plus", "b550m-plus wifi", "b550m-plus"),
        url="https://www.asus.com/us/motherboards-components/motherboards/tuf-gaming/tuf-gaming-b550m-plus-wifi-ii/techspec/",
        source_name="ASUS",
        source_type="manufacturer",
        priority=30,
        allow_keys=MOTHERBOARD_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="ASUS ROG Strix Z790-E Gaming WiFi",
        kind="motherboard",
        aliases=("rog strix z790-e gaming wifi", "rog strix z790-e", "strix z790-e", "z790-e gaming wifi"),
        url="https://rog.asus.com/us/motherboards/rog-strix/rog-strix-z790-e-gaming-wifi-model/",
        source_name="ASUS ROG",
        source_type="manufacturer",
        priority=30,
        allow_keys=MOTHERBOARD_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="ASUS Prime Z690-P D4",
        kind="motherboard",
        aliases=("prime z690-p d4", "prime z690-p", "z690-p d4", "z690-p"),
        url="https://www.asus.com/us/motherboards-components/motherboards/prime/prime-z690-p-d4/techspec/",
        source_name="ASUS",
        source_type="manufacturer",
        priority=30,
        allow_keys=MOTHERBOARD_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="ASUS Prime H610M-E D4",
        kind="motherboard",
        aliases=("prime h610m-e d4", "prime h610m-e", "h610m-e d4", "h610m-e"),
        url="https://www.asus.com/us/motherboards-components/motherboards/prime/prime-h610m-e-d4/techspec/",
        source_name="ASUS",
        source_type="manufacturer",
        priority=30,
        allow_keys=MOTHERBOARD_ALLOWED_KEYS,
        prefer_text=True,
    ),
    SpecSource(
        target="Samsung Galaxy A57",
        kind="phone",
        aliases=("galaxy a57 5g", "galaxy a57"),
        url=_g + "samsung_galaxy_a57_5g-14379.php",
        source_name="GSMArena",
        priority=20,
    ),
    SpecSource(
        target="Samsung Galaxy S24 Ultra",
        kind="phone",
        aliases=("galaxy s24 ultra", "s24 ultra"),
        url=_g + "samsung_galaxy_s24_ultra-12771.php",
        source_name="GSMArena",
        priority=20,
    ),
    SpecSource(
        target="Samsung Galaxy S25",
        kind="phone",
        aliases=("galaxy s25",),
        url=_g + "samsung_galaxy_s25-13610.php",
        source_name="GSMArena",
        priority=20,
    ),
    SpecSource(
        target="Samsung Galaxy S26",
        kind="phone",
        aliases=("galaxy s26 5g", "galaxy s26"),
        url=_g + "samsung_galaxy_s26_5g-14456.php",
        source_name="GSMArena",
        priority=20,
    ),
    SpecSource(
        target="Apple iPhone 15",
        kind="phone",
        aliases=("iphone 15",),
        url=_g + "apple_iphone_15-12559.php",
        source_name="GSMArena",
        priority=20,
    ),
    SpecSource(
        target="Apple iPhone 16",
        kind="phone",
        aliases=("iphone 16",),
        url=_g + "apple_iphone_16-13317.php",
        source_name="GSMArena",
        priority=20,
    ),
    SpecSource(
        target="Xiaomi POCO X6",
        kind="phone",
        aliases=("poco x6",),
        url=_g + "xiaomi_poco_x6-12723.php",
        source_name="GSMArena",
        priority=20,
    ),
    SpecSource(
        target="Xiaomi POCO M8",
        kind="phone",
        aliases=("poco m8 5g", "poco m8"),
        url=_g + "xiaomi_poco_m8_5g-14391.php",
        source_name="GSMArena",
        priority=20,
    ),
    SpecSource(
        target="Xiaomi Redmi Note 15 Pro",
        kind="phone",
        aliases=("redmi note 15 pro 5g", "redmi note 15 pro"),
        url=_g + "xiaomi_redmi_note_15_pro_5g_(global)-14327.php",
        source_name="GSMArena",
        priority=20,
    ),
)


def product_text(product: Product) -> str:
    parts = [product.name or "", product.brand or "", product.model or "", product.mpn or "", product.description or ""]
    return "\n".join(parts)


def sources_for_product(product: Product) -> list[SpecSource]:
    text = product_text(product)
    if not text.strip():
        return []
    return [source for source in SOURCES if source.matches(text)]


def source_url_available(url: str) -> bool:
    return any(source.url == url for source in SOURCES)


def all_urls() -> list[str]:
    return sorted({source.url for source in SOURCES})