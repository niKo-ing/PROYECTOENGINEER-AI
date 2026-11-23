"use client";

import Link from "next/link";
import { useState } from "react";
import {
  CircleCheck,
  CircleX,
  CircuitBoard,
  Cpu,
  Fan,
  Gpu,
  HardDrive,
  Info,
  LoaderCircle,
  MemoryStick,
  PcCase,
  PlugZap,
  TriangleAlert,
  UserRound,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createPc, updatePc, type BuildItem, type CompatibilityReport, type Issue, type Part, type SavedPc, type SlotKey } from "@/lib/api/pc";
import { cn, formatCLP } from "@/lib/utils";

export const SLOT_META: Record<SlotKey, { label: string; icon: LucideIcon; hint: string }> = {
  cpu: { label: "Procesador", icon: Cpu, hint: "Define el socket y el tipo de memoria." },
  motherboard: { label: "Placa madre", icon: CircuitBoard, hint: "Debe tener el mismo socket que el procesador." },
  ram: { label: "Memoria RAM", icon: MemoryStick, hint: "DDR4 o DDR5 según la placa." },
  gpu: { label: "Tarjeta gráfica", icon: Gpu, hint: "Opcional si el procesador trae gráficos." },
  storage: { label: "Almacenamiento", icon: HardDrive, hint: "Puedes sumar más de una unidad." },
  psu: { label: "Fuente de poder", icon: PlugZap, hint: "Con margen sobre el consumo estimado." },
  case: { label: "Gabinete", icon: PcCase, hint: "Que acepte la placa, la tarjeta y la fuente." },
  cooler: { label: "Refrigeración", icon: Fan, hint: "Obligatoria si el procesador no trae disipador." },
};

const LEVEL_META: Record<Issue["level"], { icon: LucideIcon; className: string; label: string }> = {
  error: { icon: CircleX, className: "text-destructive", label: "Incompatible" },
  warning: { icon: TriangleAlert, className: "text-amber-600 dark:text-amber-400", label: "Atención" },
  info: { icon: Info, className: "text-muted-foreground", label: "Dato" },
};

export function ReportPanel({ report, compact = false }: { report: CompatibilityReport; compact?: boolean }) {
  const errors = report.issues.filter((issue) => issue.level === "error");
  const warnings = report.issues.filter((issue) => issue.level === "warning");
  const infos = report.issues.filter((issue) => issue.level === "info");
  const shown = compact ? [...errors, ...warnings] : [...errors, ...warnings, ...infos];
  const tone = errors.length ? "error" : warnings.length || !report.complete ? "warning" : "ok";

  return (
    <div className="space-y-3">
      <div
        className={cn(
          "flex items-start gap-3 rounded-lg border p-3",
          tone === "error" && "border-destructive/40 bg-destructive/5",
          tone === "warning" && "border-amber-300/60 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10",
          tone === "ok" && "border-emerald-300/60 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/10",
        )}
        role="status"
      >
        {tone === "error" ? (
          <CircleX className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden="true" />
        ) : tone === "warning" ? (
          <TriangleAlert className="mt-0.5 size-5 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
        ) : (
          <CircleCheck className="mt-0.5 size-5 shrink-0 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
        )}
        <div className="min-w-0 text-sm">
          <p className="font-medium">{report.summary}</p>
          {report.missing_labels.length > 0 ? <p className="mt-0.5 text-muted-foreground">Falta: {report.missing_labels.join(", ")}.</p> : null}
        </div>
      </div>

      <dl className="grid grid-cols-3 gap-2 text-center text-sm">
        <div className="rounded-lg bg-muted/50 p-2">
          <dt className="text-xs text-muted-foreground">Consumo estimado</dt>
          <dd className="font-semibold tabular-nums">{report.estimated_watts} W</dd>
        </div>
        <div className="rounded-lg bg-muted/50 p-2">
          <dt className="text-xs text-muted-foreground">Fuente sugerida</dt>
          <dd className="font-semibold tabular-nums">{report.recommended_psu_w} W</dd>
        </div>
        <div className="rounded-lg bg-muted/50 p-2">
          <dt className="text-xs text-muted-foreground">Total referencial</dt>
          <dd className="font-semibold tabular-nums">{formatCLP(report.total_clp)}</dd>
        </div>
      </dl>

      {shown.length > 0 ? (
        <ul className="space-y-2">
          {shown.map((issue, index) => {
            const meta = LEVEL_META[issue.level];
            const Icon = meta.icon;
            return (
              <li key={`${issue.code}-${index}`} className="flex gap-2 text-sm">
                <Icon className={cn("mt-0.5 size-4 shrink-0", meta.className)} aria-label={meta.label} />
                <span>{issue.message}</span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

export function PartsList({ parts, onRemove }: { parts: Part[]; onRemove?: (part: Part) => void }) {
  if (parts.length === 0) return <p className="text-sm text-muted-foreground">Aún no hay piezas.</p>;
  return (
    <ul className="divide-y rounded-lg border">
      {parts.map((part, index) => {
        const meta = SLOT_META[part.slot];
        const Icon = meta.icon;
        return (
          <li key={`${part.slot}-${part.product_id ?? part.name}-${index}`} className="flex items-center gap-3 p-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Icon className="size-4" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs text-muted-foreground">{meta.label}</p>
              <p className="truncate text-sm font-medium">{part.name}</p>
            </div>
            {part.legacy ? <Badge variant="secondary">Descontinuado</Badge> : null}
            <span className="shrink-0 text-sm tabular-nums">{part.price_clp ? formatCLP(part.price_clp) : "—"}</span>
            {onRemove ? (
              <Button variant="ghost" size="sm" onClick={() => onRemove(part)} aria-label={`Quitar ${part.name}`}>
                Quitar
              </Button>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export function LoginNeeded({ what }: { what: string }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-3 rounded-xl border bg-card p-8 text-center">
      <span className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
        <UserRound className="size-6" aria-hidden="true" />
      </span>
      <h2 className="text-lg font-semibold">Inicia sesión para {what}</h2>
      <p className="text-sm text-muted-foreground">Tus computadores y tus consultas quedan en tu cuenta. Crearla toma menos de un minuto.</p>
      <div className="flex gap-2">
        <Button asChild>
          <Link href="/login">Iniciar sesión</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/register">Crear cuenta</Link>
        </Button>
      </div>
    </div>
  );
}

type SaveProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  token: string;
  items: BuildItem[];
  defaults?: { name?: string; kind?: "propio" | "proyecto"; use_case?: string | null; budget_clp?: number | null };
  pcId?: number;
  source?: SavedPc["source"];
  onSaved: (pc: SavedPc) => void;
};

export function SavePcDialog({ open, onOpenChange, token, items, defaults, pcId, source = "manual", onSaved }: SaveProps) {
  const [name, setName] = useState(defaults?.name ?? "");
  const [kind, setKind] = useState<"propio" | "proyecto">(defaults?.kind ?? "proyecto");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (name.trim().length < 2) {
      setError("Ponle un nombre de al menos 2 letras.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const payload = { name: name.trim(), kind, items, use_case: defaults?.use_case ?? null, budget_clp: defaults?.budget_clp ?? null };
      const pc = pcId ? await updatePc(pcId, payload, token) : await createPc({ ...payload, source }, token);
      onSaved(pc);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={save} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{pcId ? "Guardar cambios" : "Guardar en Mis computadores"}</DialogTitle>
            <DialogDescription>Podrás revisarlo, editarlo y pedirle a la IA ideas para mejorarlo.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="pc-name">Nombre</Label>
            <Input id="pc-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Ej.: PC del escritorio" maxLength={120} autoFocus />
          </div>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">¿Qué es?</legend>
            <div className="grid grid-cols-2 gap-2">
              {(
                [
                  ["proyecto", "Un proyecto", "Un PC que planeo armar"],
                  ["propio", "Mi PC actual", "El que ya tengo"],
                ] as const
              ).map(([value, title, description]) => (
                <label
                  key={value}
                  className={cn(
                    "cursor-pointer rounded-lg border p-3 text-sm transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring",
                    kind === value ? "border-primary bg-primary/5" : "hover:bg-muted/50",
                  )}
                >
                  <input type="radio" name="kind" value={value} checked={kind === value} onChange={() => setKind(value)} className="sr-only" />
                  <span className="block font-medium">{title}</span>
                  <span className="block text-xs text-muted-foreground">{description}</span>
                </label>
              ))}
            </div>
          </fieldset>
          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
              Guardar
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function KindBadge({ kind }: { kind: "propio" | "proyecto" }) {
  return <Badge variant={kind === "propio" ? "secondary" : "outline"}>{kind === "propio" ? "Mi PC" : "Proyecto"}</Badge>;
}

export function CompatBadge({ report }: { report?: CompatibilityReport }) {
  if (!report) return null;
  if (!report.compatible) return <Badge variant="destructive">Incompatible</Badge>;
  if (!report.complete) return <Badge variant="warning">Incompleto</Badge>;
  if (report.issues.some((issue) => issue.level === "warning")) return <Badge variant="warning">Con avisos</Badge>;
  return <Badge variant="success">Compatible</Badge>;
}

type Specs = Record<string, unknown>;
const join = (values: (string | number | false | null | undefined)[]) => values.filter(Boolean).join(" · ");

/** Una línea con los datos que importan para elegir cada tipo de pieza. */
export function specLine(part: Pick<Part, "slot" | "specs">): string {
  const s = part.specs as Specs;
  const n = (key: string) => (typeof s[key] === "number" ? (s[key] as number) : null);
  const t = (key: string) => (typeof s[key] === "string" ? (s[key] as string) : null);
  const list = (key: string) => (Array.isArray(s[key]) ? (s[key] as unknown[]).join("/") : null);
  switch (part.slot) {
    case "cpu":
      return join([t("socket"), n("cores") && `${n("cores")} núcleos`, n("boost_ghz") && `${n("boost_ghz")} GHz`, n("tdp_w") && `${n("tdp_w")} W`, s.igpu ? "con gráficos" : "sin gráficos", s.includes_cooler ? "trae disipador" : "sin disipador"]);
    case "motherboard":
      return join([t("socket"), t("chipset"), t("form_factor"), t("memory_type"), n("m2_slots") && `${n("m2_slots")} M.2`, s.wifi ? "Wi-Fi" : null]);
    case "ram":
      return join([n("capacity_gb") && `${n("capacity_gb")} GB`, t("memory_type"), n("speed_mts") && `${n("speed_mts")} MT/s`, n("modules") && `${n("modules")} módulo(s)`]);
    case "gpu":
      return join([n("vram_gb") && `${n("vram_gb")} GB`, n("length_mm") && `${n("length_mm")} mm`, n("board_power_w") && `${n("board_power_w")} W`]);
    case "storage":
      return join([n("capacity_gb") && (n("capacity_gb")! >= 1000 ? `${n("capacity_gb")! / 1000} TB` : `${n("capacity_gb")} GB`), t("interface"), n("read_mbps") && `${n("read_mbps")} MB/s`]);
    case "psu":
      return join([n("watts") && `${n("watts")} W`, t("efficiency"), t("form_factor")]);
    case "case":
      return join([list("form_factors"), n("max_gpu_mm") && `tarjeta ≤ ${n("max_gpu_mm")} mm`, n("max_cooler_mm") && `disipador ≤ ${n("max_cooler_mm")} mm`]);
    case "cooler":
      return join([t("type") === "liquida" ? `líquida ${n("radiator_mm") ?? ""} mm` : n("height_mm") && `aire ${n("height_mm")} mm`, n("tdp_rating_w") && `hasta ${n("tdp_rating_w")} W`]);
    default:
      return "";
  }
}
