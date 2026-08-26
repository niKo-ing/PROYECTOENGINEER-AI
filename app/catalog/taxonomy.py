"""Canonical taxonomy for SoloTodo AI.

The taxonomy defines the product categories that SoloTodo tracks.
Each node has a priority (P0/P1/P2) and is_group flag.

Idempotent seed: use (name, parent_id) as identity.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TaxonomyNode:
    name: str
    slug: str
    priority: str  # "P0", "P1", "P2"
    is_group: bool = False
    children: tuple["TaxonomyNode", ...] = field(default_factory=tuple)


def _leaf(name: str, slug: str, priority: str) -> TaxonomyNode:
    return TaxonomyNode(name=name, slug=slug, priority=priority, is_group=False)


def _group(name: str, slug: str, *children: TaxonomyNode) -> TaxonomyNode:
    return TaxonomyNode(name=name, slug=slug, priority="P0", is_group=True, children=children)


INITIAL_TAXONOMY: TaxonomyNode = _group(
    "Tecnología", "tecnologia",

    _group(
        "Computación", "computacion",
        _leaf("Notebooks", "notebooks", "P0"),
        _leaf("PCs de escritorio", "pcs-de-escritorio", "P0"),
        _leaf("Mini PCs", "mini-pcs", "P1"),
        _leaf("Monitores", "monitores", "P0"),
        _leaf("Procesadores", "procesadores", "P0"),
        _leaf("Tarjetas gráficas", "tarjetas-graficas", "P0"),
        _leaf("Placas madre", "placas-madre", "P0"),
        _leaf("Memoria RAM", "memoria-ram", "P0"),
        _leaf("Almacenamiento SSD", "almacenamiento-ssd", "P0"),
        _leaf("Discos duros", "discos-duros", "P1"),
        _leaf("Fuentes de poder", "fuentes-de-poder", "P1"),
        _leaf("Gabinetes", "gabinetes", "P1"),
        _leaf("Refrigeración PC", "refrigeracion-pc", "P1"),
    ),

    _group(
        "Periféricos", "perifericos",
        _leaf("Teclados", "teclados", "P1"),
        _leaf("Mouse", "mouse", "P1"),
        _leaf("Audífonos", "audifonos", "P1"),
        _leaf("Micrófonos", "microfonos", "P2"),
        _leaf("Webcams", "webcams", "P2"),
        _leaf("Mousepads", "mousepads", "P2"),
        _leaf("Controles / Gamepads", "controles-gamepads", "P1"),
    ),

    _group(
        "Gaming", "gaming",
        _leaf("Consolas", "consolas", "P0"),
        _leaf("Juegos", "juegos", "P1"),
        _leaf("Controles gaming", "controles-gaming", "P1"),
        _leaf("Accesorios gaming", "accesorios-gaming", "P2"),
        _leaf("Sillas gaming", "sillas-gaming", "P2"),
    ),

    _group(
        "Redes", "redes",
        _leaf("Routers", "routers", "P1"),
        _leaf("Sistemas Wi-Fi Mesh", "sistemas-wifi-mesh", "P1"),
        _leaf("Switches", "switches", "P2"),
        _leaf("Adaptadores de red", "adaptadores-de-red", "P2"),
    ),

    _group(
        "Electrónica", "electronica",
        _leaf("Smart TVs", "smart-tvs", "P1"),
        _leaf("Cámaras", "camaras", "P2"),
        _leaf("Accesorios electrónicos", "accesorios-electronicos", "P2"),
    ),

    _group(
        "Smartphones", "smartphones",
        _leaf("Celulares", "celulares", "P0"),
        _leaf("Tablets", "tablets", "P1"),
        _leaf("Smartwatches", "smartwatches", "P2"),
        _leaf("Accesorios celular", "accesorios-celular", "P2"),
    ),
)
