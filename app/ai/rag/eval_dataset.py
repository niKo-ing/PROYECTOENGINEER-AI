"""Curated retrieval-evaluation dataset (AI V4).

30+ realistic user queries across motherboards, GPUs, CPUs and SSDs used by
:func:`app.ai.rag.evaluation.evaluate`. Each case pins the expected SKU via
``relevant_keywords`` (variant-safe: never mixes RTX 5070 / 5070 Ti / 5070
Laptop / 5070 Ti Laptop). The companion corpus lets tests build a hermetic
store without touching the network.
"""

from __future__ import annotations

from app.ai.rag.evaluation import EvalCase

# (model, brand, category, document_type, content)
RAG_EVAL_CORPUS: list[tuple[str, str, str, str, str]] = [
    ("ROG STRIX B650E-F GAMING WIFI", "ASUS", "motherboard", "specifications",
     "La ASUS ROG STRIX B650E-F GAMING WIFI soporta AM5, DDR5 hasta 8000 MT/s con EXPO, PCIe 5.0 y Wi-Fi 6E."),
    ("B650E", "Gigabyte", "motherboard", "specifications",
     "Placa B650E de Gigabyte con socket AM5, DDR5 y chipset B650E para Ryzen 7000."),
    ("B650M", "MSI", "motherboard", "specifications",
     "MSI B650M: motherboard micro-ATX AM5 con DDR5, sale del estándar B650."),
    ("Z790 AORUS", "Gigabyte", "motherboard", "specifications",
     "Gigabyte Z790 AORUS para LGA1700 con DDR5, PCIe 5.0 y VRM reforzado."),
    ("X670E", "ASRock", "motherboard", "specifications",
     "ASRock X670E Taichi: socket AM5, DDR5, PCIe 5.0, segmento premium."),
    ("RTX 5070 Ti", "NVIDIA", "gpu", "review",
     "La RTX 5070 Ti rinde fuerte en raster a 1440p/4K. Consumo pico algo elevado bajo carga."),
    ("RTX 5070 Laptop", "NVIDIA", "gpu", "benchmark",
     "Geekbench 6 y 3DMark de la RTX 5070 Laptop 115W: buena eficiencia en notebooks."),
    ("RTX 5070", "NVIDIA", "gpu", "benchmark",
     "La RTX 5070 alcanza buena puntuación en Geekbench 6 y DLSS 4 con frame generation."),
    ("RTX 5070 Ti Laptop", "NVIDIA", "gpu", "review",
     "RTX 5070 Ti Laptop 150W: más VRAM y frecuencia de boost que la 5070 Laptop en portátiles."),
    ("RX 9070 XT", "AMD", "gpu", "benchmark",
     "La RX 9070 XT compite con 5070 Ti en raster, pierde en trazado de rayos."),
    ("i9-14900K", "Intel", "cpu", "benchmark",
     "Core i9-14900K: Geekbench 6 Single 3151, Multi 21420. Consumo alto sin refrigeración top."),
    ("i5-14600K", "Intel", "cpu", "specifications",
     "Core i5-14600K: 14 núcleos (6P+8E), DDR5-5600, LGA1700. Sustituto del 13600K."),
    ("Ryzen 7 7800X3D", "AMD", "cpu", "benchmark",
     "Ryzen 7 7800X3D: 96MB de L3, excelente en gaming a 1440p, consumo bajo en juegos."),
    ("Ryzen 5 7600", "AMD", "cpu", "specifications",
     "Ryzen 5 7600 AM5: 6 núcleos/12 hilos, DDR5-5200, base gaming para presupuesto."),
    ("990 PRO 2TB", "Samsung", "ssd", "review",
     "Samsung 990 PRO 2TB: PCIe 4.0 NVMe, 7450 MB/s lectura, óptimo para PS5 y edición."),
    ("980 PRO 1TB", "Samsung", "ssd", "specifications",
     "Samsung 980 PRO 1TB: NVMe PCIe 4.0, 7000 MB/s lectura, para consolas y PC."),
    ("P5 Plus 1TB", "Crucial", "ssd", "review",
     "Crucial P5 Plus 1TB: NVMe PCIe 4.0 rápido y económico, buen valor."),
    ("B760M", "ASUS", "motherboard", "specifications",
     "ASUS B760M: micro-ATX LGA1700 con DDR5 para Core 12/13/14."),
    ("H610M", "MSI", "motherboard", "specifications",
     "MSI H610M: LGA1700 económico con slot M.2 y HDMI."),
    ("A620M", "Gigabyte", "motherboard", "specifications",
     "Gigabyte A620M: la puerta de entrada a AM5 con DDR5."),
    ("RTX 5060 Ti", "NVIDIA", "gpu", "benchmark",
     "La RTX 5060 Ti 16GB rinde fluido a 1440p con DLSS 4."),
    ("RTX 5060", "NVIDIA", "gpu", "review",
     "La RTX 5060 8GB es eficiente a 1080p para presupuestos."),
    ("RTX 5080", "NVIDIA", "gpu", "benchmark",
     "La RTX 5080 supera con holgura a la 5070 Ti en 4K con Ray Tracing."),
    ("RX 7600", "AMD", "gpu", "review",
     "La RX 7600 8GB es la opción sensata a 1080p en el segmento de entrada."),
    ("Ryzen 9 7950X3D", "AMD", "cpu", "benchmark",
     "Ryzen 9 7950X3D: 16 núcleos con 3D V-Cache, bestial en gaming y creación."),
    ("Ryzen 7 9700X", "AMD", "cpu", "specifications",
     "Ryzen 7 9700X: 8 núcleos Zen 5, DDR5-5600, AM5."),
    ("i7-14700K", "Intel", "cpu", "benchmark",
     "Core i7-14700K con 20 núcleos: multihilo muy bueno para edición."),
    ("i3-12100F", "Intel", "cpu", "specifications",
     "Core i3-12100F de 4 núcleos: gaming económico sin punto muerto."),
    ("SN850X 2TB", "Western Digital", "ssd", "benchmark",
     "WD Black SN850X 2TB: NVMe Gen4 hasta 7300 MB/s de lectura."),
    ("T500 2TB", "Crucial", "ssd", "review",
     "Crucial T500 2TB: NVMe Gen4 rapidísimo con DRAM y bajo consumo."),
    ("970 EVO Plus 1TB", "Samsung", "ssd", "specifications",
     "Samsung 970 EVO Plus 1TB: NVMe Gen3 sólido para laptop y PC."),
    ("P3 Plus 1TB", "Crucial", "ssd", "review",
     "Crucial P3 Plus 1TB: QLC barato y suficiente para juegos."),
]

# Each query expects ONLY its own SKU: keyword arrays must be disjoint per family
# so a greedy retrieval surfacing a sibling model scores as a miss.
RAG_EVAL_CASES: list[EvalCase] = [
    EvalCase("¿la ASUS B650E-F soporta DDR5 8000 con EXPO?", "motherboard", relevant_keywords=["b650e-f"]),
    EvalCase("cuánta RAM soporta la Gigabyte B650E?", "motherboard", relevant_keywords=["gigabyte b650e"]),
    EvalCase("que memora usa la MSI B650M", "motherboard", relevant_keywords=["b650m"]),
    EvalCase("es congruente la Z790 AORUS para LGA1700", "motherboard", relevant_keywords=["z790"]),
    EvalCase("diferencia entre X670E y B650E", "motherboard", relevant_keywords=["x670e", "b650e"]),
    EvalCase("rendimiento 1440p de la RTX 5070 Ti", "gpu", relevant_keywords=["ti rinde fuerte"]),
    EvalCase("cuánta VRAM tiene la RTX 5070 Ti Laptop 150W", "gpu", relevant_keywords=["frecuencia de boost"]),
    EvalCase("benchmark de la RTX 5070 Laptop 115W", "gpu", relevant_keywords=["115w"]),
    EvalCase("fps de la RTX 5070 en 4K con DLSS", "gpu", relevant_keywords=["frame generation"]),
    EvalCase("RTX 5070 Ti o RX 9070 XT para ray tracing", "gpu", relevant_keywords=["trazado de rayos", "9070 xt"]),
    EvalCase("es eficiente la RTX 5070 Laptop 115W en notebooks", "gpu", relevant_keywords=["eficiencia en notebooks"]),
    EvalCase("Geekbench del Core i9-14900K", "cpu", relevant_keywords=["14900k"]),
    EvalCase("núcleos y hilos del i5-14600K", "cpu", relevant_keywords=["14600k"]),
    EvalCase("es bueno el Ryzen 7 7800X3D para gaming", "cpu", relevant_keywords=["7800x3d"]),
    EvalCase("¿qué CPU AMD barato para AM5?", "cpu", relevant_keywords=["ryzen 5 7600"]),
    EvalCase("velocidades del Samsung 990 PRO 2TB", "ssd", relevant_keywords=["990 pro"]),
    EvalCase("es compatible el 980 PRO 1TB con PS5", "ssd", relevant_keywords=["980 pro"]),
    EvalCase("mejor SSD NVMe precio rendimiento P5 Plus", "ssd", relevant_keywords=["p5 plus"]),
    EvalCase("¿que placa AM5 economica sugiere Gigabyte?", "motherboard", relevant_keywords=["a620m"]),
    EvalCase("la ASUS B760M sirve para Core 13?", "motherboard", relevant_keywords=["b760m"]),
    EvalCase("MSI H610M economica para i5", "motherboard", relevant_keywords=["h610m"]),
    EvalCase("¿es buena la RTX 5060 Ti a 1440p?", "gpu", relevant_keywords=["5060 ti"]),
    EvalCase("la RTX 5060 rinde bien a 1080p", "gpu", relevant_keywords=["rtx 5060"]),
    EvalCase("cuánto supera la RTX 5080 a la 5070 Ti en 4K", "gpu", relevant_keywords=["5080"]),
    EvalCase("RX 7600 para 1080p presupuesto", "gpu", relevant_keywords=["rx 7600"]),
    EvalCase("¿la RX 9070 XT le gana a la 5070 Ti en raster?", "gpu", relevant_keywords=["9070 xt"]),
    EvalCase("Ryzen 9 7950X3D para creación y gaming", "cpu", relevant_keywords=["7950x3d"]),
    EvalCase("specs del Ryzen 7 9700X", "cpu", relevant_keywords=["9700x"]),
    EvalCase("i7-14700K buen multihilo para edición", "cpu", relevant_keywords=["14700k"]),
    EvalCase("i3-12100F gaming económico", "cpu", relevant_keywords=["12100f"]),
    EvalCase("¿qué tan rápido es el WD SN850X 2TB?", "ssd", relevant_keywords=["sn850x"]),
    EvalCase("Crucial T500 2TB con DRAM", "ssd", relevant_keywords=["t500"]),
    EvalCase("970 EVO Plus 1TB para laptop", "ssd", relevant_keywords=["970 evo plus"]),
    EvalCase("P3 Plus 1TB QLC para juegos", "ssd", relevant_keywords=["p3 plus"]),
]


def eval_cases(category: str | None = None) -> list[EvalCase]:
    cases = [case for case in RAG_EVAL_CASES if category is None or case.category == category]
    return [EvalCase(**asdict(case)) for case in cases]


def asdict(case: EvalCase) -> dict:
    return {
        "query": case.query,
        "category": case.category,
        "relevant_ids": list(case.relevant_ids),
        "relevant_keywords": list(case.relevant_keywords),
    }