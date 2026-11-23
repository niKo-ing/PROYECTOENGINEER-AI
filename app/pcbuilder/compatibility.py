"""Motor de compatibilidad determinista.

Cada regla mira solo datos de las fichas técnicas y devuelve hallazgos con nivel:

* ``error``: no funciona o no cabe (socket distinto, memoria DDR4 en placa DDR5, tarjeta más larga que el gabinete…);
* ``warning``: funciona, pero con riesgo o mal aprovechada (fuente justa, disipador corto, cuello de botella…);
* ``info``: dato útil que no cambia la decisión (la RAM correrá a menor velocidad, el procesador trae disipador…).

El LLM nunca decide si dos piezas son compatibles: explica este reporte. Así la respuesta es reproducible y se puede
medir (precisión del agente = coincide con este motor).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.pcbuilder.parts import SLOT_BY_KEY, Build

# Consumo de lo que no es CPU ni GPU (placa, RAM, discos, ventiladores, USB) y margen recomendado para la fuente.
BASE_SYSTEM_W = 60
PSU_HEADROOM = 1.3
PSU_MIN_MARGIN = 1.1


@dataclass(frozen=True)
class Issue:
    level: str  # error | warning | info
    code: str
    message: str
    slots: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["slots"] = list(self.slots)
        return data


@dataclass
class CompatibilityReport:
    compatible: bool
    complete: bool
    issues: list[Issue] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    estimated_watts: int = 0
    recommended_psu_w: int = 0
    total_clp: int = 0
    checks_run: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "compatible": self.compatible,
            "complete": self.complete,
            "issues": [i.as_dict() for i in self.issues],
            "missing": self.missing,
            "missing_labels": [SLOT_BY_KEY[m].label for m in self.missing],
            "estimated_watts": self.estimated_watts,
            "recommended_psu_w": self.recommended_psu_w,
            "total_clp": self.total_clp,
            "checks_run": self.checks_run,
            "summary": summary_text(self),
        }


def estimate_power(build: Build) -> tuple[int, int]:
    """(consumo estimado en W, fuente recomendada en W redondeada a 50)."""
    cpu, gpu = build.one("cpu"), build.one("gpu")
    load = BASE_SYSTEM_W + (int(cpu.get("max_power_w") or cpu.get("tdp_w") or 65) if cpu else 0) + (int(gpu.get("board_power_w") or 0) if gpu else 0)
    recommended = max(load * PSU_HEADROOM, int(gpu.get("recommended_psu_w") or 0) if gpu else 0)
    recommended = int(-(-recommended // 50) * 50)
    return int(load), recommended


def _check_socket(build: Build, out: list[Issue]) -> None:
    cpu, board = build.one("cpu"), build.one("motherboard")
    if cpu and board and cpu.get("socket") and board.get("socket") and cpu.get("socket") != board.get("socket"):
        out.append(Issue("error", "socket", f"El procesador {cpu.name} usa socket {cpu.get('socket')} y la placa {board.name} es {board.get('socket')}: no calzan.", ("cpu", "motherboard")))


ENTRY_CHIPSET_MAX_CPU_W = 150


def board_tier(board) -> str:
    """entrada (A520/A620/H610…), media (B550/B650/B760/B860) o alta (X670/Z790…), según la letra del chipset."""
    chipset = str(board.get("chipset") or "").upper()
    return {"A": "entrada", "H": "entrada", "B": "media", "Z": "alta", "X": "alta"}.get(chipset[:1], "media")


def _check_board_power(build: Build, out: list[Issue]) -> None:
    cpu, board = build.one("cpu"), build.one("motherboard")
    if cpu and board and board_tier(board) == "entrada" and int(cpu.get("max_power_w") or 0) > ENTRY_CHIPSET_MAX_CPU_W:
        out.append(Issue("warning", "vrm", f"La placa {board.name} es de entrada ({board.get('chipset')}) y el {cpu.name} puede consumir {cpu.get('max_power_w')} W: sus reguladores (VRM) se calentarán y el procesador bajará su rendimiento. Conviene una placa B o Z.", ("cpu", "motherboard")))


def _check_memory(build: Build, out: list[Issue]) -> None:
    board, cpu, kits = build.one("motherboard"), build.one("cpu"), build.all("ram")
    if not kits:
        return
    types = {k.get("memory_type") for k in kits if k.get("memory_type")}
    if len(types) > 1:
        out.append(Issue("error", "ram_mixed", "Mezclaste módulos DDR4 y DDR5: una placa usa solo un tipo de memoria.", ("ram",)))
    if board and board.get("memory_type"):
        for kit in kits:
            if kit.get("memory_type") and kit.get("memory_type") != board.get("memory_type"):
                out.append(Issue("error", "ram_type", f"La memoria {kit.name} es {kit.get('memory_type')} y la placa {board.name} usa {board.get('memory_type')}: no entra físicamente.", ("ram", "motherboard")))
    if cpu and cpu.get("memory_types"):
        for kit in kits:
            if kit.get("memory_type") and kit.get("memory_type") not in cpu.get("memory_types"):
                out.append(Issue("error", "ram_cpu", f"El procesador {cpu.name} solo admite {', '.join(cpu.get('memory_types'))}.", ("ram", "cpu")))
    modules = sum(int(k.get("modules") or 1) for k in kits)
    capacity = sum(int(k.get("capacity_gb") or 0) for k in kits)
    if board and board.get("ram_slots") and modules > int(board.get("ram_slots")):
        out.append(Issue("error", "ram_slots", f"Son {modules} módulos de RAM y la placa tiene {board.get('ram_slots')} ranuras.", ("ram", "motherboard")))
    if board and board.get("max_ram_gb") and capacity > int(board.get("max_ram_gb")):
        out.append(Issue("error", "ram_capacity", f"Son {capacity} GB de RAM y la placa admite hasta {board.get('max_ram_gb')} GB.", ("ram", "motherboard")))
    if len(kits) > 1:
        out.append(Issue("warning", "ram_kits", "Juntar dos kits distintos de RAM puede obligar a bajar la velocidad o fallar en el arranque: mejor un solo kit de la capacidad total.", ("ram",)))
    speed = max(int(k.get("speed_mts") or 0) for k in kits)
    limits = [int(x) for x in ((board.get("max_mem_mts") if board else None), (cpu.get("max_mem_mts") if cpu else None)) if x]
    if speed and limits and speed > min(limits):
        out.append(Issue("info", "ram_speed", f"La RAM es de {speed} MT/s; funcionará, pero el procesador o la placa la dejarán en {min(limits)} MT/s salvo que se active el perfil XMP/EXPO.", ("ram",)))
    if capacity and capacity < 16:
        out.append(Issue("warning", "ram_low", f"{capacity} GB de RAM se quedan cortos hoy; 16 GB es lo mínimo razonable para jugar o trabajar con varias aplicaciones.", ("ram",)))
    if modules == 1 and board:
        out.append(Issue("info", "ram_single_channel", "Un solo módulo trabaja en canal simple: con dos módulos (doble canal) el procesador rinde más, sobre todo con gráficos integrados.", ("ram",)))


def _check_case(build: Build, out: list[Issue]) -> None:
    case, board, gpu, psu = build.one("case"), build.one("motherboard"), build.one("gpu"), build.one("psu")
    if not case:
        return
    if board and board.get("form_factor") and case.get("form_factors") and board.get("form_factor") not in case.get("form_factors"):
        out.append(Issue("error", "form_factor", f"La placa {board.name} es {board.get('form_factor')} y el gabinete {case.name} acepta {', '.join(case.get('form_factors'))}.", ("motherboard", "case")))
    if gpu and gpu.get("length_mm") and case.get("max_gpu_mm"):
        length, room = int(gpu.get("length_mm")), int(case.get("max_gpu_mm"))
        if length > room:
            out.append(Issue("error", "gpu_length", f"La tarjeta {gpu.name} mide {length} mm y en el gabinete {case.name} caben hasta {room} mm.", ("gpu", "case")))
        elif room - length < 15:
            out.append(Issue("warning", "gpu_length_tight", f"La tarjeta ({length} mm) entra muy justa en el gabinete ({room} mm): revise los cables de alimentación.", ("gpu", "case")))
    if psu and psu.get("form_factor") and case.get("psu_form_factors") and psu.get("form_factor") not in case.get("psu_form_factors"):
        out.append(Issue("error", "psu_form", f"La fuente {psu.name} es {psu.get('form_factor')} y el gabinete {case.name} necesita una fuente {', '.join(case.get('psu_form_factors'))}.", ("psu", "case")))


def _check_cooling(build: Build, out: list[Issue]) -> None:
    cpu, cooler, case = build.one("cpu"), build.one("cooler"), build.one("case")
    if not cpu:
        return
    if not cooler:
        if cpu.get("includes_cooler") is False:
            out.append(Issue("error", "no_cooler", f"El procesador {cpu.name} no trae disipador en la caja: hay que agregar uno.", ("cpu", "cooler")))
        elif cpu.get("includes_cooler"):
            out.append(Issue("info", "stock_cooler", f"El {cpu.name} trae disipador de fábrica: alcanza para uso normal.", ("cpu",)))
        return
    if cooler.get("sockets") and cpu.get("socket") and cpu.get("socket") not in cooler.get("sockets"):
        out.append(Issue("error", "cooler_socket", f"El disipador {cooler.name} no trae anclaje para socket {cpu.get('socket')}.", ("cooler", "cpu")))
    if cooler.get("tdp_rating_w") and cpu.get("tdp_w") and int(cooler.get("tdp_rating_w")) < int(cpu.get("tdp_w")):
        out.append(Issue("warning", "cooler_weak", f"El disipador ({cooler.get('tdp_rating_w')} W) disipa menos que el TDP del procesador ({cpu.get('tdp_w')} W): bajará su frecuencia por temperatura.", ("cooler", "cpu")))
    if case and cooler.get("type") == "aire" and cooler.get("height_mm") and case.get("max_cooler_mm") and int(cooler.get("height_mm")) > int(case.get("max_cooler_mm")):
        out.append(Issue("error", "cooler_height", f"El disipador mide {cooler.get('height_mm')} mm de alto y en el gabinete caben {case.get('max_cooler_mm')} mm.", ("cooler", "case")))
    if case and cooler.get("type") == "liquida" and cooler.get("radiator_mm") and int(cooler.get("radiator_mm")) not in [int(x) for x in case.get("radiators_mm", [])]:
        out.append(Issue("error", "radiator", f"El radiador de {cooler.get('radiator_mm')} mm no tiene dónde montarse en el gabinete {case.name}.", ("cooler", "case")))


def _check_graphics(build: Build, out: list[Issue]) -> None:
    cpu, gpu = build.one("cpu"), build.one("gpu")
    if cpu and not gpu and cpu.get("igpu") is False:
        out.append(Issue("error", "no_video", f"El {cpu.name} no tiene gráficos integrados: sin tarjeta gráfica el equipo no da imagen.", ("cpu", "gpu")))
    if cpu and gpu and cpu.get("gaming_score") and gpu.get("perf"):
        ratio = float(gpu.get("perf")) / float(cpu.get("gaming_score"))
        if ratio > 1.15:
            out.append(Issue("warning", "cpu_bottleneck", f"La tarjeta {gpu.name} es bastante más potente que el procesador: en juegos el procesador limitará los FPS (cuello de botella).", ("cpu", "gpu")))


def _check_power(build: Build, out: list[Issue]) -> tuple[int, int]:
    load, recommended = estimate_power(build)
    psu = build.one("psu")
    if psu and psu.get("watts"):
        watts = int(psu.get("watts"))
        if watts < load * PSU_MIN_MARGIN:
            out.append(Issue("error", "psu_insufficient", f"El equipo consume cerca de {load} W y la fuente es de {watts} W: se apagará bajo carga. Use al menos {recommended} W.", ("psu",)))
        elif watts < recommended:
            out.append(Issue("warning", "psu_tight", f"La fuente de {watts} W queda justa para un consumo estimado de {load} W; lo recomendable son {recommended} W.", ("psu",)))
    return load, recommended


def _check_storage(build: Build, out: list[Issue]) -> None:
    board, drives = build.one("motherboard"), build.all("storage")
    if not board or not drives:
        return
    nvme = sum(1 for d in drives if d.get("interface") == "NVMe")
    sata = sum(1 for d in drives if d.get("interface") == "SATA")
    if board.get("m2_slots") is not None and nvme > int(board.get("m2_slots")):
        out.append(Issue("error", "m2_slots", f"Son {nvme} unidades M.2 y la placa tiene {board.get('m2_slots')} ranura(s) M.2.", ("storage", "motherboard")))
    if board.get("sata_ports") is not None and sata > int(board.get("sata_ports")):
        out.append(Issue("error", "sata_ports", f"Son {sata} discos SATA y la placa tiene {board.get('sata_ports')} puertos.", ("storage", "motherboard")))
    if drives and all(d.get("interface") == "SATA" and d.get("form") == "3.5" for d in drives):
        out.append(Issue("warning", "hdd_only", "Solo hay disco duro mecánico: el sistema operativo arrancará lento. Agregue un SSD para Windows y los programas.", ("storage",)))


CHECKS = (
    ("socket", _check_socket),
    ("alimentacion_placa", _check_board_power),
    ("memoria", _check_memory),
    ("gabinete", _check_case),
    ("refrigeracion", _check_cooling),
    ("video", _check_graphics),
    ("almacenamiento", _check_storage),
)


def check_build(build: Build) -> CompatibilityReport:
    issues: list[Issue] = []
    for _, check in CHECKS:
        check(build, issues)
    load, recommended = _check_power(build, issues)
    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: order.get(i.level, 3))
    missing = build.missing_required()
    return CompatibilityReport(
        compatible=not any(i.level == "error" for i in issues),
        complete=not missing,
        issues=issues,
        missing=missing,
        estimated_watts=load,
        recommended_psu_w=recommended,
        total_clp=build.total_clp,
        checks_run=[name for name, _ in CHECKS] + ["energia"],
    )


def summary_text(report: CompatibilityReport) -> str:
    errors, warnings = len(report.errors), len(report.warnings)
    if errors:
        head = f"Hay {errors} incompatibilidad(es) que impiden armar el equipo"
    elif warnings:
        head = f"Las piezas son compatibles, con {warnings} advertencia(s)"
    else:
        head = "Las piezas son compatibles"
    if report.missing:
        head += f"; faltan: {', '.join(SLOT_BY_KEY[m].label.lower() for m in report.missing)}"
    return head + "."
