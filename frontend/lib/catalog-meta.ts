import {
  Boxes,
  CircuitBoard,
  Cpu,
  Gamepad2,
  Gauge,
  HardDrive,
  Headphones,
  Keyboard,
  Laptop,
  MemoryStick,
  Monitor,
  Mouse,
  MousePointer2,
  Network,
  Package,
  PcCase,
  Radio,
  Router,
  Smartphone,
  Tablet,
  Tv,
  Usb,
  Watch,
  Wifi,
  type LucideIcon,
} from "lucide-react";

import type { CategoryRead } from "@/types/category";

const GROUP_ICONS: Record<string, LucideIcon> = {
  "pc-y-componentes": Cpu,
  computadores: Laptop,
  "monitores-y-pantallas": Monitor,
  perifericos: Keyboard,
  gaming: Gamepad2,
  redes: Network,
  moviles: Smartphone,
};

const LEAF_ICONS: Record<string, LucideIcon> = {
  procesadores: Cpu,
  "tarjetas-graficas": CircuitBoard,
  "placas-madre": CircuitBoard,
  "memoria-ram": MemoryStick,
  "almacenamiento-ssd": HardDrive,
  "discos-duros": HardDrive,
  "fuentes-de-poder": Gauge,
  gabinetes: PcCase,
  "refrigeracion-pc": MousePointer2,
  notebooks: Laptop,
  "pcs-de-escritorio": PcCase,
  "mini-pcs": PcCase,
  monitores: Monitor,
  "smart-tvs": Tv,
  teclados: Keyboard,
  mouse: Mouse,
  audifonos: Headphones,
  microfonos: Radio,
  webcams: Usb,
  mousepads: MousePointer2,
  "controles-gamepads": Gamepad2,
  consolas: Gamepad2,
  juegos: Boxes,
  "controles-gaming": Gamepad2,
  "accesorios-gaming": Package,
  "sillas-gaming": PcCase,
  routers: Router,
  "sistemas-wifi-mesh": Wifi,
  switches: Network,
  "adaptadores-de-red": Usb,
  celulares: Smartphone,
  tablets: Tablet,
  smartwatches: Watch,
  "accesorios-celular": Package,
  camaras: Tv,
  "accesorios-electronicos": Package,
};

const GROUP_DESCRIPTIONS: Record<string, string> = {
  "pc-y-componentes":
    "Procesadores, tarjetas gráficas, memorias, placas madre y todo lo necesario para armar tu PC.",
  computadores:
    "Notebooks, PCs de escritorio y mini PCs listos para usar o para potenciar tu setup.",
  "monitores-y-pantallas":
    "Monitores y Smart TV para trabajo, gaming y entretenimiento, con la mejor resolución y tasa de refresco.",
  perifericos:
    "Teclados, mouse, audífonos y más accesorios para tu día a día y para gaming.",
  gaming:
    "Consolas, juegos y accesorios para llevar tu experiencia gamer al siguiente nivel.",
  redes:
    "Routers, malla Wi-Fi y switches para una conexión estable en todo tu hogar o negocio.",
  moviles:
    "Celulares, tablets y smartwatches de las mejores marcas, con el mejor precio del mercado.",
};

export function categoryIcon(category: CategoryRead | { slug: string }): LucideIcon {
  return LEAF_ICONS[category.slug] ?? (GROUP_ICONS[category.slug] ?? Package);
}

export function categoryDescription(category: CategoryRead | { slug: string; name: string }): string {
  return (
    GROUP_DESCRIPTIONS[category.slug] ??
    `Encuentra y compara ${category.name.toLowerCase()} de distintas tiendas en un solo lugar.`
  );
}

export function isGroupSlug(slug: string): boolean {
  return slug in GROUP_ICONS || Object.keys(GROUP_DESCRIPTIONS).includes(slug);
}