from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentSpec:
    aliases: tuple[str, ...]
    section: str
    items: tuple[tuple[str, str], ...]
    highlights: tuple[str, ...] = ()


CPU_SPECS: tuple[ComponentSpec, ...] = (
    ComponentSpec(
        aliases=("intel core i3-n305", "core i3-n305", "i3-n305"),
        section="Procesador",
        highlights=("8 núcleos / 8 hilos", "Turbo hasta 3.80 GHz"),
        items=(
            ("Núcleos", "8 E-cores"),
            ("Hilos", "8"),
            ("Frecuencia turbo", "hasta 3.80 GHz"),
            ("Cache", "6 MB Intel Smart Cache"),
            ("TDP", "15 W Processor Base Power"),
            ("Arquitectura", "Alder Lake-N"),
            ("Tecnología", "Intel 7"),
            ("Gráficos integrados", "Intel UHD Graphics"),
        ),
    ),
    ComponentSpec(
        aliases=("intel core i5-13420h", "core i5-13420h", "i5-13420h"),
        section="Procesador",
        highlights=("8 núcleos / 12 hilos", "Turbo hasta 4.60 GHz"),
        items=(
            ("Núcleos", "4 P-cores + 4 E-cores"),
            ("Hilos", "12"),
            ("Frecuencia turbo", "hasta 4.60 GHz"),
            ("Cache", "12 MB Intel Smart Cache"),
            ("TDP", "45 W Processor Base Power"),
            ("Arquitectura", "Raptor Lake-H"),
            ("Tecnología", "Intel 7"),
            ("Gráficos integrados", "Intel UHD Graphics"),
        ),
    ),
    ComponentSpec(
        aliases=("intel core i5-12450h", "core i5-12450h", "i5-12450h"),
        section="Procesador",
        highlights=("8 núcleos / 12 hilos", "Turbo hasta 4.40 GHz"),
        items=(
            ("Núcleos", "4 P-cores + 4 E-cores"),
            ("Hilos", "12"),
            ("Frecuencia turbo", "hasta 4.40 GHz"),
            ("Cache", "12 MB Intel Smart Cache"),
            ("TDP", "45 W Processor Base Power"),
            ("Arquitectura", "Alder Lake-H"),
            ("Tecnología", "Intel 7"),
            ("Gráficos integrados", "Intel UHD Graphics"),
        ),
    ),
    ComponentSpec(
        aliases=("amd ryzen 5 7520u", "ryzen 5 7520u"),
        section="Procesador",
        highlights=("4 núcleos / 8 hilos", "Turbo hasta 4.30 GHz"),
        items=(
            ("Núcleos", "4"),
            ("Hilos", "8"),
            ("Frecuencia base", "2.80 GHz"),
            ("Frecuencia turbo", "hasta 4.30 GHz"),
            ("Cache", "4 MB L3"),
            ("TDP", "15 W"),
            ("Arquitectura", "Zen 2"),
            ("Tecnología", "TSMC 6 nm"),
            ("Gráficos integrados", "AMD Radeon 610M"),
        ),
    ),
    ComponentSpec(
        aliases=("amd ryzen 7 7730u", "ryzen 7 7730u"),
        section="Procesador",
        highlights=("8 núcleos / 16 hilos", "Turbo hasta 4.50 GHz"),
        items=(
            ("Núcleos", "8"),
            ("Hilos", "16"),
            ("Frecuencia base", "2.00 GHz"),
            ("Frecuencia turbo", "hasta 4.50 GHz"),
            ("Cache", "16 MB L3"),
            ("TDP", "15 W"),
            ("Arquitectura", "Zen 3"),
            ("Tecnología", "TSMC 7 nm"),
            ("Gráficos integrados", "AMD Radeon Graphics"),
        ),
    ),
    ComponentSpec(
        aliases=("amd ryzen 7 7735hs", "ryzen 7 7735hs"),
        section="Procesador",
        highlights=("8 núcleos / 16 hilos", "Turbo hasta 4.75 GHz"),
        items=(
            ("Núcleos", "8"),
            ("Hilos", "16"),
            ("Frecuencia base", "3.20 GHz"),
            ("Frecuencia turbo", "hasta 4.75 GHz"),
            ("Cache", "16 MB L3"),
            ("TDP", "35 W"),
            ("Arquitectura", "Zen 3+"),
            ("Tecnología", "TSMC 6 nm"),
            ("Gráficos integrados", "AMD Radeon 680M"),
        ),
    ),
)


GPU_SPECS: tuple[ComponentSpec, ...] = (
    ComponentSpec(
        aliases=("rtx 5090", "geforce rtx 5090"),
        section="Tarjeta de video",
        highlights=("GPU dedicada NVIDIA RTX 5090",),
        items=(
            ("Tipo", "Dedicada"),
            ("Fabricante", "NVIDIA"),
            ("Familia", "GeForce RTX 50"),
            ("Arquitectura", "Blackwell"),
        ),
    ),
    ComponentSpec(
        aliases=("rtx4060", "rtx 4060", "geforce rtx 4060"),
        section="Tarjeta de video",
        highlights=("GPU dedicada NVIDIA RTX 4060", "8 GB GDDR6"),
        items=(
            ("Tipo", "Dedicada"),
            ("Fabricante", "NVIDIA"),
            ("Modelo", "GeForce RTX 4060"),
            ("VRAM", "8 GB GDDR6"),
            ("Bus", "128-bit"),
            ("Arquitectura", "Ada Lovelace"),
        ),
    ),
    ComponentSpec(
        aliases=("rtx 2050", "geforce rtx 2050"),
        section="Tarjeta de video",
        highlights=("GPU dedicada NVIDIA RTX 2050", "4 GB GDDR6"),
        items=(
            ("Tipo", "Dedicada"),
            ("Fabricante", "NVIDIA"),
            ("Modelo", "GeForce RTX 2050"),
            ("VRAM", "4 GB GDDR6"),
            ("Bus", "64-bit"),
            ("Arquitectura", "Ampere"),
        ),
    ),
)


def known_components() -> tuple[ComponentSpec, ...]:
    return CPU_SPECS + GPU_SPECS
