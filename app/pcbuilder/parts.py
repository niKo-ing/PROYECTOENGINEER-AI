"""Pieza de PC y espacios del armador."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SlotInfo:
    key: str
    label: str
    required: bool
    multiple: bool = False
    category_slug: str = ""


SLOTS: tuple[SlotInfo, ...] = (
    SlotInfo("cpu", "Procesador", True, category_slug="procesadores"),
    SlotInfo("motherboard", "Placa madre", True, category_slug="placas-madre"),
    SlotInfo("ram", "Memoria RAM", True, multiple=True, category_slug="memoria-ram"),
    SlotInfo("gpu", "Tarjeta gráfica", False, category_slug="tarjetas-graficas"),
    SlotInfo("storage", "Almacenamiento", True, multiple=True, category_slug="almacenamiento-ssd"),
    SlotInfo("psu", "Fuente de poder", True, category_slug="fuentes-de-poder"),
    SlotInfo("case", "Gabinete", True, category_slug="gabinetes"),
    SlotInfo("cooler", "Refrigeración", False, category_slug="refrigeracion-pc"),
)
SLOT_BY_KEY = {slot.key: slot for slot in SLOTS}
SLOT_KEYS = tuple(slot.key for slot in SLOTS)
CATEGORY_TO_SLOT = {slot.category_slug: slot.key for slot in SLOTS} | {"discos-duros": "storage"}


@dataclass(frozen=True)
class Part:
    slot: str
    name: str
    specs: dict[str, Any] = field(default_factory=dict)
    product_id: int | None = None
    price_clp: int | None = None
    brand: str | None = None
    store: str | None = None
    legacy: bool = False
    image_url: str | None = None

    @property
    def label(self) -> str:
        return SLOT_BY_KEY[self.slot].label if self.slot in SLOT_BY_KEY else self.slot

    def get(self, key: str, default: Any = None) -> Any:
        return self.specs.get(key, default)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Build:
    """Conjunto de piezas. Los espacios múltiples (RAM y almacenamiento) admiten varias piezas."""

    def __init__(self, parts: list[Part] | None = None):
        self.parts: list[Part] = []
        for part in parts or []:
            self.add(part)

    def add(self, part: Part) -> None:
        if part.slot not in SLOT_BY_KEY:
            raise ValueError(f"Espacio desconocido: {part.slot}")
        if not SLOT_BY_KEY[part.slot].multiple:
            self.parts = [p for p in self.parts if p.slot != part.slot]
        self.parts.append(part)

    def one(self, slot: str) -> Part | None:
        return next((p for p in self.parts if p.slot == slot), None)

    def all(self, slot: str) -> list[Part]:
        return [p for p in self.parts if p.slot == slot]

    def replace(self, slot: str, parts: list[Part]) -> "Build":
        return Build([p for p in self.parts if p.slot != slot] + parts)

    def without(self, slot: str) -> "Build":
        return Build([p for p in self.parts if p.slot != slot])

    @property
    def total_clp(self) -> int:
        return sum(p.price_clp or 0 for p in self.parts)

    def missing_required(self) -> list[str]:
        present = {p.slot for p in self.parts}
        return [slot.key for slot in SLOTS if slot.required and slot.key not in present]

    def as_items(self) -> list[dict[str, Any]]:
        order = {key: i for i, key in enumerate(SLOT_KEYS)}
        return [part.as_dict() for part in sorted(self.parts, key=lambda p: order.get(p.slot, 99))]
