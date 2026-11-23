"""Recomendador del armador: elige piezas compatibles según el uso y el presupuesto, y propone mejoras.

Es una búsqueda exhaustiva pequeña (procesador × tarjeta gráfica; el resto de las piezas se completa con la opción más
barata que cumple), con un puntaje de rendimiento por uso:

* en juegos, media armónica ponderada de procesador y tarjeta (castiga el desbalance = cuello de botella);
* en trabajo, media aritmética ponderada;
* multiplicadores si falta RAM, almacenamiento o memoria de video para ese uso.

Todo es determinista y se prueba sin red. Gemini interpreta lo que pide la persona (→ ``Needs``) y explica el resultado.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.pcbuilder.compatibility import ENTRY_CHIPSET_MAX_CPU_W, CompatibilityReport, board_tier, check_build, estimate_power
from app.pcbuilder.parts import Build, Part


@dataclass(frozen=True)
class UseCase:
    key: str
    label: str
    w_cpu: float
    w_gpu: float
    gaming: bool
    needs_gpu: bool
    ram_gb: int
    storage_gb: int
    min_vram_gb: int = 0
    description: str = ""


USE_CASES: dict[str, UseCase] = {
    uc.key: uc
    for uc in (
        UseCase("gaming_1080", "Juegos en 1080p", 0.35, 0.65, True, True, 16, 500, 8, "Juegos actuales en Full HD con calidad alta."),
        UseCase("gaming_1440", "Juegos en 1440p", 0.30, 0.70, True, True, 32, 1000, 12, "Juegos en 2K con calidad alta o muchos FPS."),
        UseCase("esports", "Juegos competitivos (eSports)", 0.55, 0.45, True, True, 16, 500, 6, "Valorant, CS2, LoL o Fortnite a muchos FPS."),
        UseCase("oficina", "Oficina y estudio", 1.0, 0.0, False, False, 16, 500, 0, "Navegador, Office, clases en línea y videollamadas."),
        UseCase("programacion", "Programación", 0.85, 0.15, False, False, 32, 1000, 0, "IDE, Docker, máquinas virtuales y compilar."),
        UseCase("edicion", "Edición de video y foto", 0.55, 0.45, False, True, 32, 2000, 8, "Premiere, DaVinci Resolve, Photoshop o Lightroom."),
        UseCase("modelado_ia", "3D e IA local", 0.40, 0.60, False, True, 32, 1000, 12, "Blender, renders y modelos de IA en el propio equipo."),
        UseCase("streaming", "Jugar y transmitir", 0.50, 0.50, True, True, 32, 1000, 8, "Juegos mientras transmite en Twitch o YouTube."),
    )
}


@dataclass
class Needs:
    use_case: str = "gaming_1080"
    budget_clp: int = 800_000
    cpu_brand: str | None = None  # "AMD" | "Intel"
    gpu_brand: str | None = None  # "NVIDIA" | "AMD"
    wifi: bool = False
    small: bool = False  # equipo compacto (Mini-ITX)
    min_ram_gb: int | None = None
    min_storage_gb: int | None = None

    def normalized(self) -> "Needs":
        use_case = self.use_case if self.use_case in USE_CASES else "gaming_1080"
        cpu_brand = {"amd": "AMD", "intel": "Intel"}.get((self.cpu_brand or "").strip().lower())
        gpu_brand = {"nvidia": "NVIDIA", "amd": "AMD", "radeon": "AMD", "geforce": "NVIDIA"}.get((self.gpu_brand or "").strip().lower())
        return Needs(use_case, max(int(self.budget_clp or 0), 0), cpu_brand, gpu_brand, bool(self.wifi), bool(self.small), self.min_ram_gb, self.min_storage_gb)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Recommendation:
    needs: Needs
    build: Build
    report: CompatibilityReport
    score: float
    within_budget: bool
    reasons: dict[str, str] = field(default_factory=dict)
    alternatives: dict[str, dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "needs": self.needs.as_dict(),
            "use_case_label": USE_CASES[self.needs.use_case].label,
            "items": self.build.as_items(),
            "report": self.report.as_dict(),
            "score": round(self.score, 1),
            "within_budget": self.within_budget,
            "total_clp": self.build.total_clp,
            "leftover_clp": self.needs.budget_clp - self.build.total_clp,
            "reasons": self.reasons,
            "alternatives": self.alternatives,
        }


# ── Puntaje ─────────────────────────────────────────────────────────────────────────────────────

UNKNOWN_CPU_SCORE, UNKNOWN_GPU_PERF = 30.0, 15.0


def performance_score(build: Build, use_case: str) -> float:
    uc = USE_CASES.get(use_case, USE_CASES["gaming_1080"])
    cpu, gpu = build.one("cpu"), build.one("gpu")
    if cpu is None:
        return 0.0
    c = float(cpu.get("gaming_score" if uc.gaming else "cpu_score") or UNKNOWN_CPU_SCORE)
    g = float(gpu.get("perf") or UNKNOWN_GPU_PERF) if gpu else float(cpu.get("igpu_score") or 0.5)
    if uc.w_gpu == 0:
        score = c
    elif uc.gaming:
        score = 1.0 / (uc.w_cpu / max(c, 0.5) + uc.w_gpu / max(g, 0.5))
    else:
        score = uc.w_cpu * c + uc.w_gpu * g
    ram = sum(int(k.get("capacity_gb") or 0) for k in build.all("ram"))
    need_ram = uc.ram_gb
    if ram and ram < need_ram:
        score *= 0.85 if ram >= need_ram / 2 else 0.7
    storage = sum(int(d.get("capacity_gb") or 0) for d in build.all("storage"))
    if storage and storage < uc.storage_gb:
        score *= 0.95
    if gpu and uc.min_vram_gb and int(gpu.get("vram_gb") or 0) < uc.min_vram_gb:
        score *= 0.9
    return score


# ── Selección de piezas ─────────────────────────────────────────────────────────────────────────

def _priced(parts: list[Part], slot: str) -> list[Part]:
    return sorted((p for p in parts if p.slot == slot and p.price_clp and not p.legacy), key=lambda p: p.price_clp or 0)


def _boards_for(cpu: Part, boards: list[Part], needs: Needs) -> list[Part]:
    return [b for b in boards if b.get("socket") == cpu.get("socket") and b.get("memory_type") in (cpu.get("memory_types") or [b.get("memory_type")])
            and (not needs.wifi or b.get("wifi")) and (not needs.small or b.get("form_factor") == "ITX")
            and not (board_tier(b) == "entrada" and int(cpu.get("max_power_w") or 0) > ENTRY_CHIPSET_MAX_CPU_W)]


def _ram_for(board: Part, kits: list[Part], ram_gb: int) -> Part | None:
    fits = [k for k in kits if k.get("memory_type") == board.get("memory_type") and int(k.get("modules") or 1) <= int(board.get("ram_slots") or 2)
            and int(k.get("capacity_gb") or 0) <= int(board.get("max_ram_gb") or 9999)]
    enough = [k for k in fits if int(k.get("capacity_gb") or 0) >= ram_gb]
    dual = [k for k in enough if int(k.get("modules") or 1) >= 2]
    pool = dual or enough or sorted(fits, key=lambda k: -int(k.get("capacity_gb") or 0))
    return pool[0] if pool else None


def _storage_for(drives: list[Part], storage_gb: int) -> Part | None:
    nvme = [d for d in drives if d.get("interface") == "NVMe"]
    enough = [d for d in nvme if int(d.get("capacity_gb") or 0) >= storage_gb]
    pool = enough or sorted(nvme, key=lambda d: -int(d.get("capacity_gb") or 0))
    return pool[0] if pool else None


def _cooler_for(cpu: Part, case: Part, coolers: list[Part]) -> tuple[bool, Part | None]:
    """(¿se resolvió?, disipador). Sin disipador si el procesador trae uno y no pasa de 105 W."""
    if cpu.get("includes_cooler") and int(cpu.get("tdp_w") or 65) <= 105:
        return True, None
    for cooler in coolers:
        if cpu.get("socket") not in (cooler.get("sockets") or []):
            continue
        if int(cooler.get("tdp_rating_w") or 0) < int(cpu.get("tdp_w") or 65):
            continue
        if cooler.get("type") == "aire" and int(cooler.get("height_mm") or 0) > int(case.get("max_cooler_mm") or 999):
            continue
        if cooler.get("type") == "liquida" and int(cooler.get("radiator_mm") or 0) not in [int(x) for x in case.get("radiators_mm", [])]:
            continue
        return True, cooler
    return False, None


def _psu_for(build: Build, case: Part, psus: list[Part]) -> Part | None:
    _, recommended = estimate_power(build)
    for psu in psus:
        if int(psu.get("watts") or 0) >= recommended and psu.get("form_factor") in (case.get("psu_form_factors") or ["ATX"]):
            return psu
    return None


def _complete(cpu: Part, gpu: Part | None, catalog: list[Part], needs: Needs, uc: UseCase) -> Build | None:
    """Arma el equipo más barato posible alrededor de un procesador y una tarjeta."""
    boards, kits = _priced(catalog, "motherboard"), _priced(catalog, "ram")
    drives, cases, coolers, psus = _priced(catalog, "storage"), _priced(catalog, "case"), _priced(catalog, "cooler"), _priced(catalog, "psu")
    ram_gb = max(uc.ram_gb, needs.min_ram_gb or 0)
    storage = _storage_for(drives, max(uc.storage_gb, needs.min_storage_gb or 0))
    best: Build | None = None
    for board in _boards_for(cpu, boards, needs):
        ram = _ram_for(board, kits, ram_gb)
        if ram is None or storage is None:
            continue
        for case in cases:
            if board.get("form_factor") not in (case.get("form_factors") or []):
                continue
            if needs.small and case.get("form_factors") != ["ITX"]:
                continue
            if gpu and int(gpu.get("length_mm") or 0) > int(case.get("max_gpu_mm") or 999):
                continue
            ok, cooler = _cooler_for(cpu, case, coolers)
            if not ok:
                continue
            parts = [cpu, board, ram, storage, case] + ([gpu] if gpu else []) + ([cooler] if cooler else [])
            psu = _psu_for(Build(parts), case, psus)
            if psu is None:
                continue
            candidate = Build(parts + [psu])
            if best is None or candidate.total_clp < best.total_clp:
                best = candidate
            break  # los gabinetes van de menor a mayor precio: el primero que sirve es el más barato con esta placa
    return best


def _search(catalog: list[Part], needs: Needs, budget: int) -> tuple[Build | None, float, Build | None]:
    """(mejor equipo dentro del presupuesto, su puntaje, equipo más barato posible)."""
    uc = USE_CASES[needs.use_case]
    cpus = [c for c in _priced(catalog, "cpu") if not needs.cpu_brand or c.brand == needs.cpu_brand]
    gpus: list[Part | None] = [g for g in _priced(catalog, "gpu") if not needs.gpu_brand or g.get("chip") == needs.gpu_brand]
    if not uc.needs_gpu:
        gpus = [None] + gpus
    best, best_score, cheapest = None, -1.0, None
    for cpu in cpus:
        for gpu in gpus:
            if gpu is None and cpu.get("igpu") is False:
                continue
            build = _complete(cpu, gpu, catalog, needs, uc)
            if build is None or not check_build(build).compatible:
                continue
            if cheapest is None or build.total_clp < cheapest.total_clp:
                cheapest = build
            if build.total_clp > budget:
                continue
            score = performance_score(build, needs.use_case)
            if score > best_score + 1e-9 or (abs(score - best_score) <= 1e-9 and best is not None and build.total_clp < best.total_clp):
                best, best_score = build, score
    return best, best_score, cheapest


def _polish(build: Build, catalog: list[Part], needs: Needs) -> Build:
    """Con el saldo que queda, sube RAM y almacenamiento si el uso lo aprovecha."""
    leftover = needs.budget_clp - build.total_clp
    board = build.one("motherboard")
    for slot, key in (("ram", "capacity_gb"), ("storage", "capacity_gb")):
        current = build.one(slot)
        if current is None or board is None:
            continue
        options = [p for p in _priced(catalog, slot) if int(p.get(key) or 0) > int(current.get(key) or 0)]
        if slot == "ram":
            options = [k for k in options if k.get("memory_type") == board.get("memory_type") and int(k.get("modules") or 1) <= int(board.get("ram_slots") or 2) and int(k.get("capacity_gb") or 0) <= min(64, int(board.get("max_ram_gb") or 64))]
        else:
            options = [d for d in options if d.get("interface") == "NVMe"]
        for option in options:
            extra = (option.price_clp or 0) - (current.price_clp or 0)
            if extra <= leftover * 0.6:
                candidate = build.replace(slot, [option])
                if check_build(candidate).compatible:
                    build, leftover = candidate, leftover - extra
                break
    return build


def reasons_for(build: Build, needs: Needs) -> dict[str, str]:
    uc = USE_CASES[needs.use_case]
    out: dict[str, str] = {}
    cpu, gpu, ram, board, psu = build.one("cpu"), build.one("gpu"), build.one("ram"), build.one("motherboard"), build.one("psu")
    if cpu:
        extra = f", con gráficos {cpu.get('igpu_name')}" if cpu.get("igpu") and not gpu else ""
        out["cpu"] = f"{cpu.get('cores')} núcleos / {cpu.get('threads')} hilos hasta {cpu.get('boost_ghz')} GHz{extra}; buen equilibrio para {uc.label.lower()}."
    if gpu:
        out["gpu"] = f"{gpu.get('vram_gb')} GB de memoria de video; es la tarjeta que más rinde para {uc.label.lower()} dentro del presupuesto."
    if board:
        out["motherboard"] = f"Socket {board.get('socket')} ({board.get('chipset')}), {board.get('memory_type')}, formato {board.get('form_factor')}{', con Wi-Fi' if board.get('wifi') else ''}."
    if ram:
        out["ram"] = f"{ram.get('capacity_gb')} GB {ram.get('memory_type')} en {ram.get('modules')} módulo(s) a {ram.get('speed_mts')} MT/s (doble canal si son 2)."
    if psu:
        load, recommended = estimate_power(build)
        out["psu"] = f"{psu.get('watts')} W {psu.get('efficiency')} para un consumo estimado de {load} W (recomendado {recommended} W)."
    if build.one("cooler"):
        out["cooler"] = "El procesador no trae disipador o necesita uno mejor para su consumo."
    return out


def recommend(catalog: list[Part], needs: Needs) -> Recommendation:
    needs = needs.normalized()
    best, score, cheapest = _search(catalog, needs, needs.budget_clp)
    within = best is not None
    build = _polish(best, catalog, needs) if best is not None else (cheapest or Build())
    score = performance_score(build, needs.use_case) if build.parts else 0.0
    rec = Recommendation(needs, build, check_build(build), score, within, reasons_for(build, needs))
    for key, factor in (("mas_barato", 0.8), ("mejor", 1.25)):
        alt, alt_score, _ = _search(catalog, needs, int(needs.budget_clp * factor))
        if alt is not None and alt.total_clp != build.total_clp:
            rec.alternatives[key] = {
                "budget_clp": int(needs.budget_clp * factor),
                "total_clp": alt.total_clp,
                "score": round(alt_score, 1),
                "cpu": alt.one("cpu").name if alt.one("cpu") else None,
                "gpu": alt.one("gpu").name if alt.one("gpu") else None,
            }
    if not within and cheapest is not None:
        rec.alternatives["minimo"] = {"total_clp": cheapest.total_clp, "nota": "Es el equipo compatible más barato que cumple este uso."}
    return rec


# ── Mejoras para un equipo existente ────────────────────────────────────────────────────────────

@dataclass
class UpgradeOption:
    title: str
    buy: list[Part]
    remove_slots: list[str]
    cost_clp: int
    score_before: float
    score_after: float
    report: CompatibilityReport

    def as_dict(self) -> dict[str, Any]:
        gain = (self.score_after / self.score_before - 1) * 100 if self.score_before else 0.0
        return {"title": self.title, "buy": [p.as_dict() for p in self.buy], "replaces": self.remove_slots, "cost_clp": self.cost_clp,
                "score_before": round(self.score_before, 1), "score_after": round(self.score_after, 1), "gain_pct": round(gain, 1), "report": self.report.as_dict()}


def _with_psu_if_needed(build: Build, catalog: list[Part]) -> tuple[Build, list[Part]]:
    report = check_build(build)
    if not any(i.code in ("psu_insufficient", "psu_tight") for i in report.issues):
        return build, []
    case = build.one("case")
    psu = _psu_for(build, case, _priced(catalog, "psu")) if case else next((p for p in _priced(catalog, "psu") if int(p.get("watts") or 0) >= estimate_power(build)[1]), None)
    if psu is None:
        return build, []
    return build.replace("psu", [psu]), [psu]


def suggest_upgrades(current: Build, catalog: list[Part], use_case: str, budget_clp: int, limit: int = 3) -> list[UpgradeOption]:
    use_case = use_case if use_case in USE_CASES else "gaming_1080"
    base = performance_score(current, use_case)
    options: list[UpgradeOption] = []

    def consider(title: str, new: Build, buy: list[Part], slots: list[str]) -> None:
        new, extra = _with_psu_if_needed(new, catalog)
        buy = buy + extra
        cost = sum(p.price_clp or 0 for p in buy)
        report = check_build(new)
        if cost <= budget_clp and report.compatible:
            after = performance_score(new, use_case)
            if after > base * 1.02:
                options.append(UpgradeOption(title, buy, slots + (["psu"] if extra else []), cost, base, after, report))

    gpu = current.one("gpu")
    for candidate in _priced(catalog, "gpu"):
        if not gpu or float(candidate.get("perf") or 0) > float(gpu.get("perf") or 0):
            consider(f"Cambiar la tarjeta gráfica por {candidate.name}", current.replace("gpu", [candidate]), [candidate], ["gpu"])

    cpu, board = current.one("cpu"), current.one("motherboard")
    if cpu and board:
        for candidate in _priced(catalog, "cpu"):
            if candidate.get("socket") == board.get("socket") and float(candidate.get("cpu_score") or 0) > float(cpu.get("cpu_score") or 0):
                new, buy = current.replace("cpu", [candidate]), [candidate]
                if not candidate.get("includes_cooler") and not current.one("cooler"):
                    case = current.one("case")
                    ok, cooler = _cooler_for(candidate, case, _priced(catalog, "cooler")) if case else (False, None)
                    if not ok or cooler is None:
                        continue
                    new, buy = new.replace("cooler", [cooler]), buy + [cooler]
                consider(f"Cambiar el procesador por {candidate.name} (misma placa)", new, buy, ["cpu"])
        # Plataforma nueva: procesador + placa + RAM.
        kits = _priced(catalog, "ram")
        ram_gb = max(USE_CASES[use_case].ram_gb, sum(int(k.get("capacity_gb") or 0) for k in current.all("ram")))
        for candidate in _priced(catalog, "cpu"):
            if candidate.get("socket") == board.get("socket"):
                continue
            needs = Needs(use_case=use_case)
            for new_board in _boards_for(candidate, _priced(catalog, "motherboard"), needs)[:2]:
                ram = _ram_for(new_board, kits, ram_gb)
                if ram is None:
                    continue
                new = current.replace("cpu", [candidate]).replace("motherboard", [new_board]).replace("ram", [ram])
                buy = [candidate, new_board, ram]
                if not candidate.get("includes_cooler") and not (current.one("cooler") and candidate.get("socket") in (current.one("cooler").get("sockets") or [])):
                    case = current.one("case")
                    ok, cooler = _cooler_for(candidate, case, _priced(catalog, "cooler")) if case else (False, None)
                    if not ok or cooler is None:
                        continue
                    new, buy = new.replace("cooler", [cooler]), buy + [cooler]
                consider(f"Plataforma nueva: {candidate.name} + {new_board.name} + {ram.name}", new, buy, ["cpu", "motherboard", "ram"])
                break

    if board:
        total_ram = sum(int(k.get("capacity_gb") or 0) for k in current.all("ram"))
        for kit in _priced(catalog, "ram"):
            if kit.get("memory_type") == board.get("memory_type") and int(kit.get("capacity_gb") or 0) > total_ram and int(kit.get("modules") or 1) <= int(board.get("ram_slots") or 2):
                consider(f"Pasar a {kit.get('capacity_gb')} GB de RAM ({kit.name})", current.replace("ram", [kit]), [kit], ["ram"])

    options.sort(key=lambda o: (-(o.score_after - o.score_before), o.cost_clp))
    unique: list[UpgradeOption] = []
    seen: set[str] = set()
    for option in options:
        kind = option.title.split(" ")[0] + "".join(sorted(option.remove_slots))
        if kind in seen:
            continue
        seen.add(kind)
        unique.append(option)
    return unique[:limit]
