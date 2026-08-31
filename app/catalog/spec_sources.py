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