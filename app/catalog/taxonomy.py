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
    item_schema: dict | None = None
    applicability: str = "optional"  # "required" | "optional" | "conditional"


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
    item_schema: dict | None = None,
    comparable: bool = True,
    facetable: bool = True,
    applicability: str | None = None,
) -> SpecificationDefinition:
    if applicability is None:
        applicability = "required" if required else "optional"
    return SpecificationDefinition(key=key, label=label, group=group, data_type=data_type, unit=unit, filter_type=filter_type, required=required, sort_order=sort_order, options=options, item_schema=item_schema, comparable=comparable, facetable=facetable, applicability=applicability)


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
    _spec("memory_type", "Tipos de memoria", "Memoria", filter_type="multi", sort_order=90, options=("DDR3", "DDR4", "DDR5", "LPDDR4", "LPDDR5")),
    _spec("max_memory", "Memoria máxima", "Memoria", "integer", "GB", "range", sort_order=100),
    _spec("pcie_version", "Versión PCIe", "Conectividad", filter_type="exact", sort_order=110),
    _spec("manufacturing_process", "Proceso de fabricación", "Procesador", filter_type="exact", sort_order=120),
    _spec("cooler_included", "Cooler incluido", "Refrigeración", "boolean", filter_type="boolean", sort_order=130),
)

GPU_SPECS = (
    _spec("chipset", "Chip gráfico", "GPU", filter_type="exact", required=True, sort_order=10),
    _spec("vram", "VRAM", "Memoria", "integer", "GB", "range", sort_order=20),
    _spec("memory_type", "Tipo de memoria", "Memoria", filter_type="exact", sort_order=30),
    _spec("memory_bus", "Bus de memoria", "Memoria", "integer", "bit", "range", sort_order=40),
    _spec("base_clock", "Frecuencia base", "GPU", "integer", "MHz", "range", sort_order=50),
    _spec("boost_clock", "Frecuencia boost", "GPU", "integer", "MHz", "range", sort_order=60),
    _spec("cuda_cores", "Núcleos CUDA", "GPU", "integer", filter_type="range", sort_order=70),
    _spec("tdp", "Consumo/TDP", "Energía", "integer", "W", "range", sort_order=80),
    _spec("recommended_psu", "Fuente recomendada", "Energía", "integer", "W", "range", sort_order=90),
    _spec("power_connector", "Conector de poder", "Energía", filter_type="exact", sort_order=100),
    _spec("length", "Largo", "Dimensiones", "integer", "mm", "range", sort_order=110),
    _spec("display_ports", "Salidas de video", "Conectividad", filter_type="multi", sort_order=120),
    _spec("pcie_interface", "Interfaz PCIe", "Conectividad", filter_type="exact", sort_order=125, options=("PCIe 3.0 x16", "PCIe 4.0 x16", "PCIe 5.0 x16")),
    _spec("cooling", "Refrigeración", "Refrigeración", filter_type="exact", sort_order=130),
)

MOTHERBOARD_SPECS = (
    # --- Identidad ---
    _spec("revision", "Revisión", "Identidad", sort_order=7, facetable=False),
    _spec("chipset", "Chipset", "Identidad", filter_type="exact", required=True, sort_order=10),
    _spec("platform", "Plataforma", "Identidad", filter_type="exact", sort_order=12),
    # --- Compatibilidad / CPU ---
    _spec("socket", "Socket", "Compatibilidad", filter_type="exact", required=True, sort_order=20),
    _spec("supported_cpu_generations", "Generaciones CPU soportadas", "Compatibilidad", "json", filter_type="multi", sort_order=22, item_schema={"generation": "string"}, facetable=False),
    _spec("cpu_compatibility", "Compatibilidad CPU", "Compatibilidad", filter_type="exact", sort_order=24, facetable=False),
    _spec("bios_requirement", "Requisito BIOS", "Compatibilidad", sort_order=26, facetable=False),
    _spec("form_factor", "Formato", "Formato", filter_type="exact", required=True, sort_order=30, options=("Mini-ITX", "Micro-ATX", "ATX", "E-ATX", "XL-ATX")),
    # --- Memoria ---
    _spec("memory_type", "Tipo de RAM", "Memoria", filter_type="exact", required=True, sort_order=40, options=("DDR3", "DDR4", "DDR5")),
    _spec("ram_slots", "Slots RAM", "Memoria", "integer", filter_type="range", required=True, sort_order=42),
    _spec("memory_channels", "Canales de memoria", "Memoria", "integer", filter_type="range", sort_order=44),
    _spec("max_memory", "Memoria máxima", "Memoria", "integer", "GB", "range", required=True, sort_order=46),
    _spec("max_memory_per_slot", "Máx. por slot", "Memoria", "integer", "GB", "range", sort_order=48),
    _spec("supported_memory_speeds", "Velocidades soportadas", "Memoria", "json", sort_order=50, item_schema={"speed": "number", "unit": "MHz"}, facetable=False),
    _spec("overclock_memory_speeds", "Velocidades OC", "Memoria", "json", sort_order=52, item_schema={"speed": "number", "unit": "MHz"}, facetable=False),
    _spec("ecc_support", "Soporte ECC", "Memoria", "boolean", filter_type="boolean", sort_order=54),
    _spec("registered_memory_support", "Memoria registrada", "Memoria", "boolean", filter_type="boolean", sort_order=56),
    _spec("unbuffered_memory_support", "Memoria unbuffered", "Memoria", "boolean", filter_type="boolean", sort_order=58),
    _spec("xmp_support", "XMP", "Memoria", "boolean", filter_type="boolean", sort_order=60, applicability="conditional"),
    _spec("expo_support", "EXPO", "Memoria", "boolean", filter_type="boolean", sort_order=62, applicability="conditional"),
    # --- Expansión PCIe ---
    _spec("pcie_slots", "Slots PCIe", "Expansión", "integer", filter_type="range", required=True, sort_order=70),
    _spec("pcie_slot_list", "Detalle slots PCIe", "Expansión", "json", sort_order=72, item_schema={"type": "string", "generation": "string", "lanes": "number", "count": "number"}, facetable=False),
    _spec("pcie_generation", "Generación PCIe", "Expansión", filter_type="exact", sort_order=74),
    _spec("pcie_lane_configuration", "Configuración de líneas PCIe", "Expansión", sort_order=76, facetable=False),
    _spec("multi_gpu_support", "Multi-GPU", "Expansión", "boolean", filter_type="boolean", sort_order=78),
    _spec("sli_support", "Soporte SLI", "Expansión", "boolean", filter_type="boolean", sort_order=80, applicability="conditional"),
    _spec("crossfire_support", "Soporte CrossFire", "Expansión", "boolean", filter_type="boolean", sort_order=82, applicability="conditional"),
    # --- Almacenamiento ---
    _spec("m2_slots", "Slots M.2", "Almacenamiento", "integer", filter_type="range", required=True, sort_order=90),
    _spec("m2_slot_list", "Detalle slots M.2", "Almacenamiento", "json", sort_order=92, item_schema={"interface": "string", "generation": "string", "lanes": "number", "form_factors": ["string"]}, facetable=False),
    _spec("nvme_support", "Soporte NVMe", "Almacenamiento", "boolean", filter_type="boolean", sort_order=94),
    _spec("sata_ports", "Puertos SATA", "Almacenamiento", "integer", filter_type="range", required=True, sort_order=96),
    _spec("sata_speed", "Velocidad SATA", "Almacenamiento", filter_type="exact", sort_order=98, options=("SATA 3.0 6 Gb/s", "SATA 2.0 3 Gb/s")),
    _spec("raid_support", "Soporte RAID", "Almacenamiento", "boolean", filter_type="boolean", sort_order=100),
    # --- USB ---
    _spec("usb_2_count", "USB 2.0", "USB", "integer", filter_type="range", sort_order=110),
    _spec("usb_3_2_gen1_count", "USB 3.2 Gen 1", "USB", "integer", filter_type="range", sort_order=112),
    _spec("usb_3_2_gen2_count", "USB 3.2 Gen 2", "USB", "integer", filter_type="range", sort_order=114),
    _spec("usb_3_2_gen2x2_count", "USB 3.2 Gen 2x2", "USB", "integer", filter_type="range", sort_order=116),
    _spec("usb4_count", "USB4", "USB", "integer", filter_type="range", sort_order=118, applicability="conditional"),
    _spec("usb_c_count", "USB-C total", "USB", "integer", filter_type="range", sort_order=120),
    _spec("rear_usb_ports", "USB traseros", "USB", "integer", filter_type="range", sort_order=122),
    _spec("front_usb_headers", "Headers USB frontales", "USB", "integer", filter_type="range", sort_order=124),
    _spec("usb_c_headers", "Headers USB-C", "USB", "integer", filter_type="range", sort_order=126),
    # --- Video ---
    _spec("hdmi", "HDMI", "Video", "json", sort_order=130, item_schema={"version": "string", "count": "number"}, facetable=False),
    _spec("displayport", "DisplayPort", "Video", "json", sort_order=132, item_schema={"version": "string", "count": "number"}, facetable=False),
    _spec("dvi", "DVI", "Video", "boolean", filter_type="boolean", sort_order=134),
    _spec("vga", "VGA", "Video", "boolean", filter_type="boolean", sort_order=136),
    _spec("usb_c_display", "USB-C con video", "Video", "boolean", filter_type="boolean", sort_order=138),
    _spec("max_displays", "Máx. pantallas", "Video", "integer", filter_type="range", sort_order=140),
    _spec("max_resolution", "Resolución máxima", "Video", filter_type="exact", sort_order=142, facetable=False),
    # --- Red ---
    _spec("ethernet", "Ethernet", "Red", filter_type="exact", required=True, sort_order=150, options=("1 GbE", "2.5 GbE", "5 GbE", "10 GbE")),
    _spec("ethernet_controller", "Controlador Ethernet", "Red", sort_order=152, facetable=False),
    _spec("wifi", "Wi-Fi", "Red", "boolean", filter_type="boolean", sort_order=154),
    _spec("wifi_standard", "Estándar Wi-Fi", "Red", filter_type="exact", sort_order=156, options=("Wi-Fi 5", "Wi-Fi 6", "Wi-Fi 6E", "Wi-Fi 7"), applicability="conditional"),
    _spec("wifi_controller", "Controlador Wi-Fi", "Red", sort_order=158, facetable=False),
    _spec("bluetooth", "Bluetooth", "Red", "boolean", filter_type="boolean", sort_order=160),
    _spec("bluetooth_version", "Versión Bluetooth", "Red", filter_type="exact", sort_order=162, applicability="conditional"),
    _spec("antenna_connectors", "Conectores antena", "Red", "integer", filter_type="range", sort_order=164),
    # --- Audio ---
    _spec("audio_codec", "Códec de audio", "Audio", sort_order=170, facetable=False),
    _spec("audio_channels", "Canales de audio", "Audio", filter_type="exact", sort_order=172, options=("2.0", "5.1", "7.1")),
    _spec("analog_audio_outputs", "Salidas analógicas", "Audio", "integer", filter_type="range", sort_order=174),
    _spec("optical_spdif", "S/PDIF óptico", "Audio", "boolean", filter_type="boolean", sort_order=176),
    _spec("audio_features", "Características de audio", "Audio", "json", filter_type="multi", sort_order=178, item_schema={"feat": "string"}, facetable=False),
    # --- Alimentación ---
    _spec("motherboard_power_connector", "Conector principal", "Alimentación", "json", sort_order=180, item_schema={"type": "string", "pins": "number", "count": "number"}, facetable=False),
    _spec("cpu_power_connector_types", "Tipos conector CPU", "Alimentación", "json", filter_type="multi", sort_order=182, item_schema={"type": "string", "pins": "number", "count": "number"}, facetable=False),
    _spec("auxiliary_power_connectors", "Conectores auxiliares", "Alimentación", "json", sort_order=184, item_schema={"type": "string", "pins": "number", "count": "number"}, facetable=False),
    _spec("pcie_power_connectors", "Conectores PCIe alimentación", "Alimentación", "json", sort_order=186, item_schema={"type": "string", "pins": "number", "count": "number"}, facetable=False),
    _spec("sata_power_headers", "Headers SATA de poder", "Alimentación", "integer", filter_type="range", sort_order=188),
    # --- Refrigeración ---
    _spec("fan_headers_total", "Headers ventilador totales", "Refrigeración", "integer", filter_type="range", sort_order=190),
    _spec("cpu_fan_headers", "Headers CPU fan", "Refrigeración", "integer", filter_type="range", sort_order=192),
    _spec("cpu_opt_headers", "Headers CPU_OPT", "Refrigeración", "integer", filter_type="range", sort_order=194),
    _spec("pump_headers", "Headers pump", "Refrigeración", "integer", filter_type="range", sort_order=196),
    _spec("system_fan_headers", "Headers fan sistema", "Refrigeración", "integer", filter_type="range", sort_order=198),
    _spec("fan_header_list", "Detalle headers ventilador", "Refrigeración", "json", sort_order=199, item_schema={"name": "string", "count": "number"}, facetable=False),
    _spec("temperature_sensors", "Sensores de temperatura", "Refrigeración", "integer", filter_type="range", sort_order=200),
    _spec("fan_control", "Control de ventiladores", "Refrigeración", "boolean", filter_type="boolean", sort_order=202),
    # --- RGB ---
    _spec("rgb_headers", "Headers RGB", "RGB", "integer", filter_type="range", sort_order=210),
    _spec("argb_headers", "Headers ARGB", "RGB", "integer", filter_type="range", sort_order=212),
    _spec("onboard_rgb", "RGB integrado", "RGB", "boolean", filter_type="boolean", sort_order=214),
    _spec("rgb_software", "Software RGB", "RGB", sort_order=216, facetable=False),
    _spec("rgb_features", "Características RGB", "RGB", "json", filter_type="multi", sort_order=218, item_schema={"feat": "string"}, facetable=False),
    # --- BIOS / diagnóstico ---
    _spec("bios_flashback", "BIOS FlashBack", "BIOS", "boolean", filter_type="boolean", sort_order=220),
    _spec("dual_bios", "Dual BIOS", "BIOS", "boolean", filter_type="boolean", sort_order=222),
    _spec("clear_cmos", "Clear CMOS", "BIOS", "boolean", filter_type="boolean", sort_order=224),
    _spec("debug_led", "LED de debug", "BIOS", "boolean", filter_type="boolean", sort_order=226),
    _spec("post_code", "Código POST", "BIOS", "boolean", filter_type="boolean", sort_order=228, applicability="conditional"),
    _spec("onboard_buttons", "Botones integrados", "BIOS", "json", filter_type="multi", sort_order=230, item_schema={"btn": "string"}, facetable=False),
    _spec("tpm_header", "Header TPM", "BIOS", "boolean", filter_type="boolean", sort_order=232),
    # --- Conectores internos ---
    _spec("sata_headers", "Headers SATA", "Conectores", "json", sort_order=240, item_schema={"count": "number", "type": "string"}, facetable=False),
    _spec("usb_headers", "Headers USB", "Conectores", "json", sort_order=242, item_schema={"generation": "string", "count": "number"}, facetable=False),
    _spec("audio_headers", "Headers audio", "Conectores", "json", sort_order=244, item_schema={"type": "string", "count": "number"}, facetable=False),
    _spec("front_panel_headers", "Headers panel frontal", "Conectores", "json", filter_type="multi", sort_order=246, item_schema={"header": "string"}, facetable=False),
    _spec("thunderbolt_header", "Header Thunderbolt", "Conectores", "boolean", filter_type="boolean", sort_order=248, applicability="conditional"),
    _spec("com_header", "Header COM", "Conectores", "boolean", filter_type="boolean", sort_order=250),
    # --- Panel trasero ---
    _spec("rear_ports", "Puertos traseros", "Panel trasero", "json", sort_order=260, item_schema={"kind": "string", "count": "number", "version": "string"}, facetable=False),
    _spec("wifi_antennas", "Antenas Wi-Fi", "Panel trasero", "integer", filter_type="range", sort_order=262),
    # --- Dimensiones ---
    _spec("dimensions", "Dimensiones", "Dimensiones", "json", sort_order=270, item_schema={"w": "number", "h": "number", "unit": "mm"}, facetable=False),
    _spec("weight", "Peso", "Dimensiones", "integer", "g", "range", sort_order=272),
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
    _spec("aspect_ratio", "Relación de aspecto", "Pantalla", filter_type="exact", sort_order=50),
    _spec("response_time", "Tiempo de respuesta", "Pantalla", "decimal", "ms", "range", sort_order=60),
    _spec("brightness", "Brillo", "Pantalla", "integer", "cd/m2", "range", sort_order=70),
    _spec("curved", "Pantalla curva", "Pantalla", "boolean", filter_type="boolean", sort_order=75),
    _spec("color_gamut", "Gama de colores", "Imagen", filter_type="exact", sort_order=80),
    _spec("contrast_ratio", "Contraste", "Imagen", filter_type="exact", sort_order=90),
    _spec("viewing_angle", "Ángulo de visión", "Imagen", filter_type="exact", sort_order=100),
    _spec("hdr", "HDR", "Imagen", "boolean", filter_type="boolean", sort_order=110),
    _spec("adaptive_sync", "Sincronización adaptativa", "Gaming", filter_type="exact", sort_order=120),
    _spec("ports", "Puertos", "Conectividad", filter_type="multi", sort_order=130),
    _spec("vesa_mount", "Montaje VESA", "Ergonomía", "boolean", filter_type="boolean", sort_order=140),
    _spec("speakers", "Altavoces integrados", "Audio", "boolean", filter_type="boolean", sort_order=150),
)

NOTEBOOK_SPECS = (
    _spec("processor", "Procesador", "Procesador", filter_type="exact", required=True, sort_order=10),
    _spec("processor_cores", "Núcleos CPU", "Procesador", "integer", filter_type="range", sort_order=20),
    _spec("processor_threads", "Hilos CPU", "Procesador", "integer", filter_type="range", sort_order=30),
    _spec("processor_base_frequency", "Frecuencia base CPU", "Procesador", "decimal", "GHz", "range", sort_order=40),
    _spec("processor_boost_frequency", "Frecuencia turbo CPU", "Procesador", "decimal", "GHz", "range", sort_order=50),
    _spec("processor_cache", "Cache CPU", "Procesador", "integer", "MB", "range", sort_order=60),
    _spec("processor_tdp", "TDP CPU", "Procesador", "integer", "W", "range", sort_order=70),
    _spec("ram", "RAM", "Memoria", filter_type="range", sort_order=80),
    _spec("ram_capacity", "Capacidad RAM", "Memoria", "integer", "GB", "range", sort_order=90),
    _spec("ram_type", "Tipo de RAM", "Memoria", filter_type="exact", sort_order=100),
    _spec("ram_speed", "Velocidad RAM", "Memoria", "integer", "MHz", "range", sort_order=110),
    _spec("storage", "Almacenamiento", "Almacenamiento", filter_type="range", sort_order=120),
    _spec("storage_capacity", "Capacidad almacenamiento", "Almacenamiento", "integer", "GB", "range", sort_order=130),
    _spec("storage_type", "Tipo almacenamiento", "Almacenamiento", filter_type="exact", sort_order=140),
    _spec("gpu", "Tarjeta de video", "Gráficos", filter_type="exact", sort_order=150),
    _spec("gpu_type", "Tipo de GPU", "Gráficos", filter_type="exact", sort_order=155),
    _spec("gpu_vram", "VRAM GPU", "Gráficos", "integer", "GB", "range", sort_order=160),
    _spec("screen", "Pantalla", "Pantalla", filter_type="exact", sort_order=170),
    _spec("screen_size", "Tamaño pantalla", "Pantalla", "decimal", '"', "range", sort_order=180),
    _spec("screen_resolution", "Resolución pantalla", "Pantalla", filter_type="exact", sort_order=190),
    _spec("screen_refresh_rate", "Frecuencia pantalla", "Pantalla", "integer", "Hz", "range", sort_order=200),
    _spec("panel_type", "Tipo de panel", "Pantalla", filter_type="exact", sort_order=210),
    _spec("touchscreen", "Pantalla táctil", "Pantalla", "boolean", filter_type="boolean", sort_order=220),
    _spec("battery", "Batería", "Energía", filter_type="range", sort_order=230),
    _spec("battery_capacity", "Capacidad batería", "Energía", "integer", "Wh", "range", sort_order=240),
    _spec("weight", "Peso", "Dimensiones", "integer", "g", "range", sort_order=250),
    _spec("ports", "Puertos", "Conectividad", filter_type="multi", sort_order=260),
    _spec("wireless", "Conectividad inalámbrica", "Conectividad", filter_type="multi", sort_order=270),
    _spec("webcam", "Cámara web", "Cámara", filter_type="exact", sort_order=280),
    _spec("os", "Sistema operativo", "Software", filter_type="exact", sort_order=290),
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
    _spec("screen_size", "Tamaño pantalla", "Pantalla", "decimal", '"', "range", sort_order=20),
    _spec("screen_resolution", "Resolución pantalla", "Pantalla", filter_type="exact", sort_order=30),
    _spec("screen_refresh_rate", "Frecuencia pantalla", "Pantalla", "integer", "Hz", "range", sort_order=40),
    _spec("panel_type", "Tipo de panel", "Pantalla", filter_type="exact", sort_order=50),
    _spec("processor", "Procesador", "Procesador", filter_type="exact", sort_order=60),
    _spec("ram", "RAM", "Memoria", filter_type="range", sort_order=70),
    _spec("ram_capacity", "Capacidad RAM", "Memoria", "integer", "GB", "range", sort_order=80),
    _spec("ram_type", "Tipo de RAM", "Memoria", filter_type="exact", sort_order=90),
    _spec("storage", "Almacenamiento", "Almacenamiento", filter_type="range", sort_order=100),
    _spec("storage_capacity", "Capacidad almacenamiento", "Almacenamiento", "integer", "GB", "range", sort_order=110),
    _spec("storage_type", "Tipo almacenamiento", "Almacenamiento", filter_type="exact", sort_order=120),
    _spec("rear_camera", "Cámara trasera", "Cámara", filter_type="exact", sort_order=130),
    _spec("rear_camera_megapixels", "Megapíxeles cámara trasera", "Cámara", "decimal", "MP", "range", sort_order=140),
    _spec("front_camera", "Cámara frontal", "Cámara", filter_type="exact", sort_order=150),
    _spec("battery", "Batería", "Energía", filter_type="range", sort_order=160),
    _spec("battery_capacity", "Capacidad batería", "Energía", "integer", "mAh", "range", sort_order=170),
    _spec("charging_wattage", "Carga rápida", "Energía", "integer", "W", "range", sort_order=180),
    _spec("connectivity", "Conectividad", "Conectividad", filter_type="multi", sort_order=190),
    _spec("os", "Sistema operativo", "Software", filter_type="exact", sort_order=200),
    _spec("weight", "Peso", "Dimensiones", "integer", "g", "range", sort_order=210),
    _spec("ip_rating", "Resistencia al agua", "Cuerpo", filter_type="exact", sort_order=220),
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
