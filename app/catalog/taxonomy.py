"""Canonical taxonomy for SoloTodo AI.

The taxonomy defines the product categories that SoloTodo tracks.
Each node has a priority (P0/P1/P2) and is_group flag.

Idempotent seed: use slug as primary identity, so existing categories can be moved.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SpecificationDefinition:
    key: str
    label: str
    group: str = "General"
    data_type: str = "text"
    unit: str | None = None
    filter_type: str = "text"
    required: bool = False
    comparable: bool = True
    facetable: bool = True
    sort_order: int = 0
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaxonomyNode:
    name: str
    slug: str
    priority: str  # "P0", "P1", "P2"
    is_group: bool = False
    children: tuple["TaxonomyNode", ...] = field(default_factory=tuple)
    specs: tuple[SpecificationDefinition, ...] = field(default_factory=tuple)


def _spec(
    key: str,
    label: str,
    group: str,
    data_type: str = "text",
    unit: str | None = None,
    filter_type: str = "text",
    required: bool = False,
    sort_order: int = 0,
    options: tuple[str, ...] = (),
) -> SpecificationDefinition:
    return SpecificationDefinition(key=key, label=label, group=group, data_type=data_type, unit=unit, filter_type=filter_type, required=required, sort_order=sort_order, options=options)


def _leaf(name: str, slug: str, priority: str, specs: tuple[SpecificationDefinition, ...] = ()) -> TaxonomyNode:
    return TaxonomyNode(name=name, slug=slug, priority=priority, is_group=False, specs=specs)


def _group(name: str, slug: str, *children: TaxonomyNode) -> TaxonomyNode:
    return TaxonomyNode(name=name, slug=slug, priority="P0", is_group=True, children=children)


CPU_SPECS = (
    _spec("socket", "Socket", "Compatibilidad", filter_type="exact", required=True, sort_order=10),
    _spec("cores", "Núcleos", "Procesador", "integer", filter_type="range", sort_order=20),
    _spec("threads", "Hilos", "Procesador", "integer", filter_type="range", sort_order=30),
    _spec("base_frequency", "Frecuencia base", "Procesador", "decimal", "GHz", "range", sort_order=40),
    _spec("boost_frequency", "Frecuencia turbo", "Procesador", "decimal", "GHz", "range", sort_order=50),
    _spec("cache", "Cache", "Procesador", "integer", "MB", "range", sort_order=60),
    _spec("tdp", "TDP", "Energía", "integer", "W", "range", sort_order=70),
    _spec("integrated_graphics", "Gráficos integrados", "Gráficos", "text", filter_type="exact", sort_order=80),
)

GPU_SPECS = (
    _spec("chipset", "Chip gráfico", "GPU", filter_type="exact", required=True, sort_order=10),
    _spec("vram", "VRAM", "Memoria", "integer", "GB", "range", sort_order=20),
    _spec("memory_type", "Tipo de memoria", "Memoria", filter_type="exact", sort_order=30),
    _spec("memory_bus", "Bus de memoria", "Memoria", "integer", "bit", "range", sort_order=40),
    _spec("tdp", "Consumo/TDP", "Energía", "integer", "W", "range", sort_order=50),
    _spec("length", "Largo", "Dimensiones", "integer", "mm", "range", sort_order=60),
    _spec("power_connector", "Conector de poder", "Energía", filter_type="exact", sort_order=70),
)

MOTHERBOARD_SPECS = (
    _spec("socket", "Socket", "Compatibilidad", filter_type="exact", required=True, sort_order=10),
    _spec("chipset", "Chipset", "Compatibilidad", filter_type="exact", sort_order=20),
    _spec("form_factor", "Formato", "Formato", filter_type="exact", sort_order=30),
    _spec("memory_type", "Tipo de RAM", "Memoria", filter_type="exact", sort_order=40),
    _spec("ram_slots", "Slots RAM", "Memoria", "integer", filter_type="range", sort_order=50),
    _spec("m2_slots", "Slots M.2", "Almacenamiento", "integer", filter_type="range", sort_order=60),
    _spec("pcie_slots", "Slots PCIe", "Expansión", "integer", filter_type="range", sort_order=70),
)

RAM_SPECS = (
    _spec("capacity", "Capacidad", "Memoria", "integer", "GB", "range", required=True, sort_order=10),
    _spec("type", "Tipo", "Memoria", filter_type="exact", sort_order=20),
    _spec("speed", "Velocidad", "Memoria", "integer", "MHz", "range", sort_order=30),
    _spec("modules", "Módulos", "Kit", "integer", filter_type="range", sort_order=40),
    _spec("latency", "Latencia", "Memoria", filter_type="exact", sort_order=50),
)

SSD_SPECS = (
    _spec("capacity", "Capacidad", "Almacenamiento", "integer", "GB", "range", required=True, sort_order=10),
    _spec("form_factor", "Formato", "Formato", filter_type="exact", sort_order=20),
    _spec("interface", "Interfaz", "Conectividad", filter_type="exact", sort_order=30),
    _spec("read_speed", "Lectura secuencial", "Rendimiento", "integer", "MB/s", "range", sort_order=40),
    _spec("write_speed", "Escritura secuencial", "Rendimiento", "integer", "MB/s", "range", sort_order=50),
)

HDD_SPECS = (
    _spec("capacity", "Capacidad", "Almacenamiento", "integer", "GB", "range", required=True, sort_order=10),
    _spec("form_factor", "Formato", "Formato", filter_type="exact", sort_order=20),
    _spec("interface", "Interfaz", "Conectividad", filter_type="exact", sort_order=30),
    _spec("rpm", "RPM", "Rendimiento", "integer", filter_type="range", sort_order=40),
    _spec("cache", "Cache", "Rendimiento", "integer", "MB", "range", sort_order=50),
)

PSU_SPECS = (
    _spec("wattage", "Potencia", "Energía", "integer", "W", "range", required=True, sort_order=10),
    _spec("efficiency", "Certificación", "Energía", filter_type="exact", sort_order=20),
    _spec("modularity", "Modularidad", "Cableado", filter_type="exact", sort_order=30),
    _spec("form_factor", "Formato", "Formato", filter_type="exact", sort_order=40),
)

CASE_SPECS = (
    _spec("motherboard_support", "Soporte placa madre", "Compatibilidad", filter_type="multi", sort_order=10),
    _spec("gpu_clearance", "Largo máximo GPU", "Dimensiones", "integer", "mm", "range", sort_order=20),
    _spec("cooler_clearance", "Alto máximo cooler", "Dimensiones", "integer", "mm", "range", sort_order=30),
    _spec("fans_included", "Ventiladores incluidos", "Refrigeración", "integer", filter_type="range", sort_order=40),
)

COOLING_SPECS = (
    _spec("type", "Tipo", "Refrigeración", filter_type="exact", required=True, sort_order=10),
    _spec("socket_support", "Sockets compatibles", "Compatibilidad", filter_type="multi", sort_order=20),
    _spec("radiator_size", "Tamaño radiador", "Refrigeración", "integer", "mm", "range", sort_order=30),
    _spec("fan_size", "Tamaño ventilador", "Refrigeración", "integer", "mm", "range", sort_order=40),
    _spec("tdp_support", "TDP soportado", "Energía", "integer", "W", "range", sort_order=50),
)

MONITOR_SPECS = (
    _spec("size", "Tamaño", "Pantalla", "decimal", '"', "range", required=True, sort_order=10),
    _spec("resolution", "Resolución", "Pantalla", filter_type="exact", sort_order=20),
    _spec("refresh_rate", "Frecuencia", "Pantalla", "integer", "Hz", "range", sort_order=30),
    _spec("panel_type", "Tipo de panel", "Pantalla", filter_type="exact", sort_order=40),
    _spec("response_time", "Tiempo de respuesta", "Pantalla", "decimal", "ms", "range", sort_order=50),
    _spec("brightness", "Brillo", "Pantalla", "integer", "cd/m2", "range", sort_order=60),
    _spec("hdr", "HDR", "Imagen", "boolean", filter_type="boolean", sort_order=70),
    _spec("adaptive_sync", "Sincronización adaptativa", "Gaming", filter_type="exact", sort_order=80),
    _spec("ports", "Puertos", "Conectividad", filter_type="multi", sort_order=90),
    _spec("vesa_mount", "Montaje VESA", "Ergonomía", "boolean", filter_type="boolean", sort_order=100),
)

NOTEBOOK_SPECS = (
    _spec("processor", "Procesador", "Procesador", filter_type="exact", required=True, sort_order=10),
    _spec("processor_cores", "Núcleos CPU", "Procesador", "integer", filter_type="range", sort_order=20),
    _spec("processor_threads", "Hilos CPU", "Procesador", "integer", filter_type="range", sort_order=30),
    _spec("ram", "RAM", "Memoria", filter_type="range", sort_order=40),
    _spec("ram_capacity", "Capacidad RAM", "Memoria", "integer", "GB", "range", sort_order=50),
    _spec("ram_type", "Tipo de RAM", "Memoria", filter_type="exact", sort_order=60),
    _spec("ram_speed", "Velocidad RAM", "Memoria", "integer", "MHz", "range", sort_order=70),
    _spec("storage", "Almacenamiento", "Almacenamiento", filter_type="range", sort_order=80),
    _spec("storage_capacity", "Capacidad almacenamiento", "Almacenamiento", "integer", "GB", "range", sort_order=90),
    _spec("storage_type", "Tipo almacenamiento", "Almacenamiento", filter_type="exact", sort_order=100),
    _spec("gpu", "Tarjeta de video", "Gráficos", filter_type="exact", sort_order=110),
    _spec("gpu_vram", "VRAM GPU", "Gráficos", "integer", "GB", "range", sort_order=120),
    _spec("screen", "Pantalla", "Pantalla", filter_type="exact", sort_order=130),
    _spec("screen_size", "Tamaño pantalla", "Pantalla", "decimal", '"', "range", sort_order=140),
    _spec("screen_resolution", "Resolución pantalla", "Pantalla", filter_type="exact", sort_order=150),
    _spec("screen_refresh_rate", "Frecuencia pantalla", "Pantalla", "integer", "Hz", "range", sort_order=160),
    _spec("panel_type", "Tipo de panel", "Pantalla", filter_type="exact", sort_order=170),
    _spec("battery", "Batería", "Energía", filter_type="range", sort_order=180),
    _spec("battery_capacity", "Capacidad batería", "Energía", "integer", "Wh", "range", sort_order=190),
    _spec("weight", "Peso", "Dimensiones", "integer", "g", "range", sort_order=200),
    _spec("ports", "Puertos", "Conectividad", filter_type="multi", sort_order=210),
    _spec("wireless", "Conectividad inalámbrica", "Conectividad", filter_type="multi", sort_order=220),
)

DESKTOP_SPECS = (
    _spec("processor", "Procesador", "Procesador", filter_type="exact", sort_order=10),
    _spec("processor_cores", "Núcleos CPU", "Procesador", "integer", filter_type="range", sort_order=20),
    _spec("ram_capacity", "Capacidad RAM", "Memoria", "integer", "GB", "range", sort_order=30),
    _spec("ram_type", "Tipo de RAM", "Memoria", filter_type="exact", sort_order=40),
    _spec("storage_capacity", "Capacidad almacenamiento", "Almacenamiento", "integer", "GB", "range", sort_order=50),
    _spec("storage_type", "Tipo almacenamiento", "Almacenamiento", filter_type="exact", sort_order=60),
    _spec("gpu", "Tarjeta de video", "Gráficos", filter_type="exact", sort_order=70),
    _spec("gpu_vram", "VRAM GPU", "Gráficos", "integer", "GB", "range", sort_order=80),
    _spec("psu_wattage", "Potencia fuente", "Energía", "integer", "W", "range", sort_order=90),
    _spec("form_factor", "Formato", "Formato", filter_type="exact", sort_order=100),
    _spec("os", "Sistema operativo", "Software", filter_type="exact", sort_order=110),
)

MOBILE_SPECS = (
    _spec("screen", "Pantalla", "Pantalla", filter_type="exact", sort_order=10),
    _spec("processor", "Procesador", "Procesador", filter_type="exact", sort_order=20),
    _spec("ram", "RAM", "Memoria", filter_type="range", sort_order=30),
    _spec("storage", "Almacenamiento", "Almacenamiento", filter_type="range", sort_order=40),
    _spec("rear_camera", "Cámara trasera", "Cámara", filter_type="exact", sort_order=50),
    _spec("battery", "Batería", "Energía", filter_type="range", sort_order=60),
    _spec("connectivity", "Conectividad", "Conectividad", filter_type="multi", sort_order=70),
)

CONSOLE_SPECS = (
    _spec("storage", "Almacenamiento", "Almacenamiento", filter_type="range", sort_order=10),
    _spec("resolution", "Resolución máxima", "Video", filter_type="exact", sort_order=20),
    _spec("fps", "FPS máximo", "Video", "integer", "FPS", "range", sort_order=30),
    _spec("optical_drive", "Lector óptico", "Formato", "boolean", filter_type="boolean", sort_order=40),
)

PERIPHERAL_SPECS = (
    _spec("connection", "Conexión", "Conectividad", filter_type="exact", sort_order=10),
    _spec("interface", "Interfaz", "Conectividad", filter_type="exact", sort_order=20),
    _spec("compatibility", "Compatibilidad", "Compatibilidad", filter_type="multi", sort_order=30),
)


INITIAL_TAXONOMY: TaxonomyNode = _group(
    "Tecnología", "tecnologia",

    _group(
        "PC y Componentes", "pc-y-componentes",
        _leaf("Procesadores", "procesadores", "P0", CPU_SPECS),
        _leaf("Tarjetas gráficas", "tarjetas-graficas", "P0", GPU_SPECS),
        _leaf("Placas madre", "placas-madre", "P0", MOTHERBOARD_SPECS),
        _leaf("Memoria RAM", "memoria-ram", "P0", RAM_SPECS),
        _leaf("Almacenamiento SSD", "almacenamiento-ssd", "P0", SSD_SPECS),
        _leaf("Discos duros", "discos-duros", "P0", HDD_SPECS),
        _leaf("Fuentes de poder", "fuentes-de-poder", "P0", PSU_SPECS),
        _leaf("Gabinetes", "gabinetes", "P0", CASE_SPECS),
        _leaf("Refrigeración PC", "refrigeracion-pc", "P0", COOLING_SPECS),
    ),

    _group(
        "Computadores", "computadores",
        _leaf("Notebooks", "notebooks", "P0", NOTEBOOK_SPECS),
        _leaf("PCs de escritorio", "pcs-de-escritorio", "P0", DESKTOP_SPECS),
        _leaf("Mini PCs", "mini-pcs", "P1", DESKTOP_SPECS),
    ),

    _group(
        "Monitores y Pantallas", "monitores-y-pantallas",
        _leaf("Monitores", "monitores", "P0", MONITOR_SPECS),
        _leaf("Smart TVs", "smart-tvs", "P1", MONITOR_SPECS),
    ),

    _group(
        "Periféricos", "perifericos",
        _leaf("Teclados", "teclados", "P1", PERIPHERAL_SPECS),
        _leaf("Mouse", "mouse", "P1", PERIPHERAL_SPECS),
        _leaf("Audífonos", "audifonos", "P1", PERIPHERAL_SPECS),
        _leaf("Micrófonos", "microfonos", "P2", PERIPHERAL_SPECS),
        _leaf("Webcams", "webcams", "P2", PERIPHERAL_SPECS),
        _leaf("Mousepads", "mousepads", "P2", PERIPHERAL_SPECS),
        _leaf("Controles / Gamepads", "controles-gamepads", "P1", PERIPHERAL_SPECS),
    ),

    _group(
        "Gaming", "gaming",
        _leaf("Consolas", "consolas", "P0", CONSOLE_SPECS),
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
        "Móviles", "moviles",
        _leaf("Celulares", "celulares", "P0", MOBILE_SPECS),
        _leaf("Tablets", "tablets", "P0", MOBILE_SPECS),
        _leaf("Smartwatches", "smartwatches", "P2"),
        _leaf("Accesorios celular", "accesorios-celular", "P2"),
        _leaf("Cámaras", "camaras", "P2"),
        _leaf("Accesorios electrónicos", "accesorios-electronicos", "P2"),
    ),
)
