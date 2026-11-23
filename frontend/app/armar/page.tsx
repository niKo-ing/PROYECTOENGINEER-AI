"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, CircleCheck, CircleX, LoaderCircle, RefreshCw, Save, Sparkles, TriangleAlert } from "lucide-react";

import { PartsList, ReportPanel, SavePcDialog, SLOT_META, specLine } from "@/components/pc/pc-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  checkCompatibility,
  fetchOptions,
  fetchSlots,
  itemsFromParts,
  recommendPc,
  SLOT_ORDER,
  takeDraft,
  type Part,
  type PartOption,
  type SlotKey,
} from "@/lib/api/pc";
import { useSession } from "@/lib/auth/use-session";
import { cn, formatCLP } from "@/lib/utils";

const MAX_STORAGE = 4;

export default function BuilderPage() {
  const router = useRouter();
  const { session } = useSession();
  const [parts, setParts] = useState<Part[]>([]);
  const [slot, setSlot] = useState<SlotKey>("cpu");
  const [includeLegacy, setIncludeLegacy] = useState(false);
  const [filter, setFilter] = useState("");
  const [saveOpen, setSaveOpen] = useState(false);
  const [draftMeta, setDraftMeta] = useState<{ name?: string; use_case?: string | null; budget_clp?: number | null; pcId?: number; kind?: "propio" | "proyecto" }>({});
  const [useCase, setUseCase] = useState("gaming_1080");
  const [budget, setBudget] = useState("800000");
  const [recommending, setRecommending] = useState(false);
  const [notice, setNotice] = useState("");

  const items = useMemo(() => itemsFromParts(parts), [parts]);
  const slotsQuery = useQuery({ queryKey: ["pc-slots"], queryFn: fetchSlots, staleTime: Infinity });
  const optionsQuery = useQuery({ queryKey: ["pc-options", slot, items, includeLegacy], queryFn: () => fetchOptions(slot, items, includeLegacy) });
  const reportQuery = useQuery({ queryKey: ["pc-compat", items], queryFn: () => checkCompatibility(items), enabled: items.length > 0 });

  // Un armado que llega desde el asistente, una recomendación o «editar» en Mis computadores.
  useEffect(() => {
    const draft = takeDraft();
    if (!draft) return;
    void (async () => {
      const data = draft.items.length > 0 ? await checkCompatibility(draft.items).catch(() => null) : null;
      setDraftMeta({ name: draft.name, use_case: draft.use_case, budget_clp: draft.budget_clp, pcId: draft.pcId, kind: draft.kind });
      if (draft.kind === "propio") setIncludeLegacy(true);
      if (data) setParts(data.items);
    })();
  }, []);

  const filled = new Set(parts.map((part) => part.slot));
  const options = (optionsQuery.data?.items ?? []).filter((option) => !filter || option.name.toLowerCase().includes(filter.toLowerCase()));
  const nextSlot = (current: SlotKey) => SLOT_ORDER.find((key) => key !== current && !filled.has(key) && key !== "cooler") ?? current;

  function choose(option: PartOption) {
    setNotice("");
    if (option.slot === "storage") {
      const disks = parts.filter((part) => part.slot === "storage");
      if (disks.length >= MAX_STORAGE) {
        setNotice(`Puedes sumar hasta ${MAX_STORAGE} unidades de almacenamiento.`);
        return;
      }
      setParts([...parts, option]);
    } else {
      setParts([...parts.filter((part) => part.slot !== option.slot), option]);
      setSlot(nextSlot(option.slot));
    }
    setFilter("");
  }

  function remove(target: Part) {
    const index = parts.indexOf(target);
    setParts(parts.filter((_, i) => i !== index));
  }

  async function quickRecommend(event: React.FormEvent) {
    event.preventDefault();
    const amount = Number(budget.replace(/\D/g, ""));
    if (!amount || amount < 250_000) {
      setNotice("Indica un presupuesto de al menos $250.000.");
      return;
    }
    setRecommending(true);
    setNotice("");
    try {
      const rec = await recommendPc({ use_case: useCase, budget_clp: amount });
      setParts(rec.items);
      setDraftMeta((meta) => ({ ...meta, use_case: useCase, budget_clp: amount }));
      setNotice(rec.within_budget ? `Listo: ${rec.use_case_label.toLowerCase()} por ${formatCLP(rec.total_clp)}. Ajusta lo que quieras.` : `Para ese uso el mínimo compatible cuesta ${formatCLP(rec.total_clp)}.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "No se pudo recomendar.");
    } finally {
      setRecommending(false);
    }
  }

  const report = reportQuery.data?.report;
  const useCases = slotsQuery.data?.use_cases ?? [];

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{draftMeta.pcId ? `Editar «${draftMeta.name}»` : "Arma tu PC"}</h1>
          <p className="mt-1 max-w-2xl text-muted-foreground">
            Elige pieza por pieza: cada opción te dice si calza con lo que ya elegiste (socket, memoria, medidas y watts).
          </p>
        </div>
        <Button asChild variant="outline" className="gap-2">
          <Link href="/armar/asistente">
            <Bot className="size-4" aria-hidden="true" />
            Prefiero que la IA me pregunte
          </Link>
        </Button>
      </div>

      <form onSubmit={quickRecommend} className="mb-6 flex flex-wrap items-end gap-3 rounded-xl border bg-muted/30 p-4">
        <Sparkles className="mb-2 size-5 text-primary" aria-hidden="true" />
        <div className="space-y-1">
          <Label htmlFor="uso">Partir de una recomendación</Label>
          <Select value={useCase} onValueChange={setUseCase}>
            <SelectTrigger id="uso" className="w-56">
              <SelectValue placeholder="Uso" />
            </SelectTrigger>
            <SelectContent>
              {useCases.map((uc) => (
                <SelectItem key={uc.key} value={uc.key}>
                  {uc.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="presupuesto">Presupuesto (CLP)</Label>
          <Input id="presupuesto" inputMode="numeric" value={budget} onChange={(event) => setBudget(event.target.value)} className="w-40" />
        </div>
        <Button type="submit" disabled={recommending} className="gap-2">
          {recommending ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="size-4" aria-hidden="true" />}
          Armar por mí
        </Button>
        {notice ? (
          <p className="basis-full text-sm text-muted-foreground" role="status">
            {notice}
          </p>
        ) : null}
      </form>

      <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)_360px]">
        <nav aria-label="Piezas del PC" className="flex gap-2 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible lg:pb-0">
          {SLOT_ORDER.map((key) => {
            const meta = SLOT_META[key];
            const Icon = meta.icon;
            const chosen = parts.filter((part) => part.slot === key);
            const issues = report?.issues.filter((issue) => issue.slots.includes(key) && issue.level !== "info") ?? [];
            const hasError = issues.some((issue) => issue.level === "error");
            return (
              <button
                key={key}
                type="button"
                onClick={() => setSlot(key)}
                aria-current={slot === key ? "true" : undefined}
                className={cn(
                  "flex min-w-44 items-center gap-3 rounded-lg border p-2.5 text-left text-sm transition-colors lg:min-w-0",
                  slot === key ? "border-primary bg-primary/5" : "hover:bg-muted/60",
                )}
              >
                <Icon className="size-4 shrink-0 text-primary" aria-hidden="true" />
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">{meta.label}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {chosen.length ? chosen.map((part) => part.name).join(" + ") : key === "gpu" || key === "cooler" ? "Opcional" : "Elegir"}
                  </span>
                </span>
                {chosen.length ? (
                  hasError ? (
                    <CircleX className="size-4 shrink-0 text-destructive" aria-label="Incompatible" />
                  ) : issues.length ? (
                    <TriangleAlert className="size-4 shrink-0 text-amber-600" aria-label="Con avisos" />
                  ) : (
                    <CircleCheck className="size-4 shrink-0 text-emerald-600" aria-label="Calza" />
                  )
                ) : null}
              </button>
            );
          })}
        </nav>

        <section aria-labelledby="opciones-titulo" className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <h2 id="opciones-titulo" className="text-lg font-semibold">
              {SLOT_META[slot].label}
            </h2>
            <span className="text-sm text-muted-foreground">{SLOT_META[slot].hint}</span>
          </div>
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <Input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filtrar por modelo o marca…" className="max-w-xs" aria-label="Filtrar piezas" />
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input type="checkbox" checked={includeLegacy} onChange={(event) => setIncludeLegacy(event.target.checked)} className="size-4 accent-[var(--primary)]" />
              Mostrar modelos descontinuados (para registrar un PC que ya tienes)
            </label>
          </div>

          {optionsQuery.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, index) => (
                <div key={index} className="h-16 animate-pulse rounded-lg bg-muted/60" />
              ))}
            </div>
          ) : optionsQuery.isError ? (
            <p className="rounded-lg border border-destructive/40 p-4 text-sm text-destructive">No pudimos cargar las piezas. Revisa que el backend esté corriendo.</p>
          ) : (
            <ul className="space-y-2">
              {options.map((option) => {
                const selected = parts.some((part) => part.product_id === option.product_id);
                const reason = option.issues.find((issue) => issue.level === "error") ?? option.issues.find((issue) => issue.level === "warning");
                return (
                  <li key={option.product_id ?? option.name}>
                    <button
                      type="button"
                      onClick={() => choose(option)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-colors",
                        selected ? "border-primary bg-primary/5" : "hover:bg-muted/50",
                        !option.compatible && "opacity-70",
                      )}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{option.name}</span>
                          {option.legacy ? <Badge variant="secondary">Descontinuado</Badge> : null}
                          {selected ? <Badge>Elegido</Badge> : null}
                        </span>
                        <span className="block text-xs text-muted-foreground">{specLine(option)}</span>
                        {reason ? (
                          <span className={cn("mt-1 flex gap-1.5 text-xs", reason.level === "error" ? "text-destructive" : "text-amber-700 dark:text-amber-400")}>
                            {reason.level === "error" ? <CircleX className="size-3.5 shrink-0" aria-hidden="true" /> : <TriangleAlert className="size-3.5 shrink-0" aria-hidden="true" />}
                            {reason.message}
                          </span>
                        ) : null}
                      </span>
                      <span className="shrink-0 text-right text-sm font-semibold tabular-nums">{option.price_clp ? formatCLP(option.price_clp) : "—"}</span>
                    </button>
                  </li>
                );
              })}
              {options.length === 0 ? <li className="text-sm text-muted-foreground">No hay piezas con ese filtro.</li> : null}
            </ul>
          )}
        </section>

        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Tu armado</CardTitle>
              <CardDescription>Precios referenciales en pesos chilenos.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <PartsList parts={parts} onRemove={remove} />
              {report ? <ReportPanel report={report} /> : <p className="text-sm text-muted-foreground">Elige un procesador para empezar.</p>}
              <div className="flex flex-wrap gap-2">
                <Button
                  className="flex-1 gap-2"
                  disabled={parts.length === 0}
                  onClick={() => (session ? setSaveOpen(true) : router.push("/login"))}
                >
                  <Save className="size-4" aria-hidden="true" />
                  {draftMeta.pcId ? "Guardar cambios" : "Guardar"}
                </Button>
                <Button variant="outline" disabled={parts.length === 0} onClick={() => setParts([])}>
                  Vaciar
                </Button>
              </div>
            </CardContent>
          </Card>
        </aside>
      </div>

      {session ? (
        <SavePcDialog
          key={`${saveOpen}-${draftMeta.pcId ?? "nuevo"}`}
          open={saveOpen}
          onOpenChange={setSaveOpen}
          token={session.access_token}
          items={items}
          pcId={draftMeta.pcId}
          defaults={{ name: draftMeta.name, kind: draftMeta.kind ?? (parts.some((part) => part.legacy) ? "propio" : "proyecto"), use_case: draftMeta.use_case, budget_clp: draftMeta.budget_clp }}
          onSaved={(pc) => router.push(`/mis-pc/${pc.id}`)}
        />
      ) : null}
    </div>
  );
}
