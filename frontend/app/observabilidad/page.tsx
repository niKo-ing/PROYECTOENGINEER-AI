"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Activity, CircleCheck, CircleHelp, CircleX, RefreshCw, ShieldAlert } from "lucide-react";

import { ColumnChart, formatMs, LineChart, Waterfall } from "@/components/observability/charts";
import { LoginNeeded } from "@/components/pc/pc-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ApiError, fetchMetrics, fetchRun, type Metrics, type RunRow, type Slo } from "@/lib/api/pc";
import { useSession } from "@/lib/auth/use-session";
import { cn } from "@/lib/utils";

const RANGES = [
  { hours: 24, label: "Últimas 24 h" },
  { hours: 24 * 7, label: "7 días" },
  { hours: 24 * 30, label: "30 días" },
];
const FLOW_LABEL: Record<string, string> = { agente: "Agente (chat)", asistente_pc: "Asistente de armado", revision_pc: "Revisión de PC" };
const STATUS_LABEL: Record<string, string> = { ok: "OK", fallback: "Respaldo", error: "Error", blocked: "Bloqueado" };

const pct = (value: number | null | undefined) => (value === null || value === undefined ? "—" : `${(value * 100).toLocaleString("es-CL", { maximumFractionDigits: 1 })} %`);
const num = (value: number | null | undefined) => (value === null || value === undefined ? "—" : value.toLocaleString("es-CL", { maximumFractionDigits: 1 }));

export default function ObservabilityPage() {
  return (
    <Suspense fallback={<div className="px-4 py-16 text-center text-muted-foreground">Cargando…</div>}>
      <Observability />
    </Suspense>
  );
}

function Observability() {
  const params = useSearchParams();
  const { session, isLoading } = useSession();
  const token = session?.access_token ?? "";
  const [hours, setHours] = useState(24 * 7);
  const [includeEval, setIncludeEval] = useState(false);
  const [runId, setRunId] = useState<string | null>(params.get("run"));  // ?run=<id> abre esa traza (enlace desde el análisis de logs)
  const query = useQuery({ queryKey: ["obs", token, hours, includeEval], queryFn: () => fetchMetrics(token, hours, includeEval), enabled: Boolean(token), placeholderData: keepPreviousData, refetchInterval: 30_000 });

  if (isLoading) return <div className="px-4 py-16 text-center text-muted-foreground">Cargando…</div>;
  if (!session) {
    return (
      <div className="px-4 py-16">
        <LoginNeeded what="ver la observabilidad" />
      </div>
    );
  }
  if (query.error instanceof ApiError && query.error.status === 403) {
    return <p className="mx-auto max-w-md px-4 py-16 text-center text-muted-foreground">Este panel es solo para administradores.</p>;
  }

  const data = query.data;
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight sm:text-3xl">
          <Activity className="size-6 text-primary" aria-hidden="true" />
          Observabilidad de la IA
        </h1>
        <p className="mt-1 max-w-3xl text-muted-foreground">
          Cada consulta al agente, al asistente de armado y a la revisión de PC queda trazada: tiempos, llamadas a Gemini, tokens, herramientas y protecciones. Se actualiza cada 30 segundos.
        </p>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-lg border p-0.5" role="group" aria-label="Rango de tiempo">
          {RANGES.map((range) => (
            <button
              key={range.hours}
              type="button"
              onClick={() => setHours(range.hours)}
              aria-pressed={hours === range.hours}
              className={cn("rounded-md px-3 py-1.5 text-sm transition-colors", hours === range.hours ? "bg-primary text-primary-foreground" : "hover:bg-muted")}
            >
              {range.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input type="checkbox" checked={includeEval} onChange={(event) => setIncludeEval(event.target.checked)} className="size-4" />
          Incluir ejecuciones de evaluación
        </label>
        <Button variant="ghost" size="sm" className="gap-2" onClick={() => void query.refetch()} disabled={query.isFetching}>
          <RefreshCw className={cn("size-4", query.isFetching && "animate-spin")} aria-hidden="true" />
          Actualizar
        </Button>
      </div>

      {!data ? (
        query.isError ? (
          <p className="rounded-lg border border-destructive/40 p-4 text-sm text-destructive">{(query.error as Error).message}</p>
        ) : (
          <div className="h-96 animate-pulse rounded-xl bg-muted/60" />
        )
      ) : (
        <div className={cn("space-y-6 transition-opacity", query.isFetching && "opacity-60")}>
          <Overview data={data} />
          <SloRow slos={data.slo} />
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Ejecuciones en el tiempo</CardTitle>
                <CardDescription>Cantidad por intervalo; los errores y respaldos aparecen al pasar el puntero.</CardDescription>
              </CardHeader>
              <CardContent>
                {data.timeseries.length ? (
                  <ColumnChart
                    ariaLabel="Ejecuciones por intervalo"
                    labels={data.timeseries.map((p) => timeLabel(p.t, hours))}
                    values={data.timeseries.map((p) => p.runs)}
                    valueLabel={(v) => `${Math.round(v)}`}
                    details={data.timeseries.map((p) => `${p.errors} error(es), ${p.fallbacks} respaldo(s), ${p.tokens.toLocaleString("es-CL")} tokens`)}
                  />
                ) : (
                  <Empty />
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Latencia de punta a punta</CardTitle>
                <CardDescription>Mediana (p50) y percentil 95 por intervalo.</CardDescription>
              </CardHeader>
              <CardContent>
                {data.timeseries.length ? (
                  <LineChart
                    ariaLabel="Latencia p50 y p95 por intervalo"
                    labels={data.timeseries.map((p) => timeLabel(p.t, hours))}
                    series={[
                      { name: "p50", color: "var(--viz-1)", values: data.timeseries.map((p) => p.p50_ms) },
                      { name: "p95", color: "var(--viz-2)", values: data.timeseries.map((p) => p.p95_ms) },
                    ]}
                    valueLabel={formatMs}
                  />
                ) : (
                  <Empty />
                )}
              </CardContent>
            </Card>
          </div>
          <Breakdown data={data} />
          <RecentRuns runs={data.recent} onOpen={setRunId} withDate={hours > 24} />
        </div>
      )}

      <RunDialog runId={runId} token={token} onClose={() => setRunId(null)} />
    </div>
  );
}

function timeLabel(iso: string, hours: number) {
  const date = new Date(iso);
  return hours > 48
    ? date.toLocaleDateString("es-CL", { day: "numeric", month: "short" }) + " " + date.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" });
}

function Empty() {
  return <p className="py-10 text-center text-sm text-muted-foreground">Sin ejecuciones en este rango.</p>;
}

function Overview({ data }: { data: Metrics }) {
  const s = data.summary;
  const tiles = [
    { label: "Ejecuciones", value: num(s.runs) },
    { label: "Mediana de latencia", value: formatMs(s.latency_ms.p50) },
    { label: "Tasa de error", value: pct(s.error_rate) },
    { label: "Respuestas con respaldo", value: pct(s.fallback_rate) },
    { label: "Precios con respaldo", value: pct(s.quality.grounded_rate) },
    { label: "Llamadas a Gemini por ejecución", value: num(s.llm.calls_per_run) },
    { label: "Tokens por ejecución", value: s.llm.tokens_per_run === null || s.llm.tokens_per_run === undefined ? "—" : Math.round(s.llm.tokens_per_run).toLocaleString("es-CL") },
    { label: "Intentos de inyección", value: `${s.security.injection_detected} (${s.security.blocked} bloqueados)` },
  ];
  return (
    <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
      <Card className="flex flex-col justify-center p-6">
        <p className="text-sm text-muted-foreground">Latencia p95</p>
        <p className="text-5xl font-semibold tracking-tight">{formatMs(s.latency_ms.p95)}</p>
        <p className="mt-1 text-xs text-muted-foreground">p99 {formatMs(s.latency_ms.p99)} · máx. {formatMs(s.latency_ms.max)}</p>
      </Card>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {tiles.map((tile) => (
          <div key={tile.label} className="rounded-xl border bg-card p-4">
            <dt className="text-xs text-muted-foreground">{tile.label}</dt>
            <dd className="mt-1 text-xl font-semibold">{tile.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function SloRow({ slos }: { slos: Slo[] }) {
  return (
    <section aria-labelledby="slo-titulo">
      <h2 id="slo-titulo" className="mb-3 text-sm font-medium text-muted-foreground">
        Objetivos de servicio y alertas
      </h2>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {slos.map((slo) => {
          const Icon = slo.state === "ok" ? CircleCheck : slo.state === "alerta" ? CircleX : CircleHelp;
          const color = slo.state === "ok" ? "var(--status-good)" : slo.state === "alerta" ? "var(--status-critical)" : undefined;
          const value = slo.value === null ? "—" : slo.unit === "ms" ? formatMs(slo.value) : pct(slo.value);
          const target = slo.unit === "ms" ? formatMs(slo.target) : pct(slo.target);
          return (
            <li key={slo.key} className="rounded-xl border bg-card p-4">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Icon className="size-4 shrink-0" style={color ? { color } : undefined} aria-hidden="true" />
                {slo.state === "ok" ? "Cumple" : slo.state === "alerta" ? "Alerta" : "Sin datos"}
              </div>
              <p className="mt-2 text-sm">{slo.label}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Actual <span className="font-semibold text-foreground">{value}</span> · objetivo {slo.op === "<=" ? "≤" : "≥"} {target}
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Breakdown({ data }: { data: Metrics }) {
  const s = data.summary;
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Por flujo</CardTitle>
        </CardHeader>
        <CardContent>
          <Table
            head={["Flujo", "Ejec.", "p50", "p95", "Error"]}
            rows={Object.entries(s.by_flow).map(([flow, d]) => [FLOW_LABEL[flow] ?? flow, num(d.runs), formatMs(d.latency_ms.p50), formatMs(d.latency_ms.p95), pct(d.error_rate)])}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Herramientas del agente</CardTitle>
        </CardHeader>
        <CardContent>
          <Table head={["Herramienta", "Usos", "Errores", "p95"]} rows={Object.entries(s.tools).map(([name, d]) => [name, num(d.calls), num(d.errors), formatMs(d.p95_ms)])} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Etapas y modelo</CardTitle>
          <CardDescription>
            Gemini: {num(s.llm.calls)} llamadas, p95 {formatMs(s.llm.latency_ms.p95)}, {s.llm.errors} con error.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table head={["Etapa", "n", "p50", "p95"]} rows={Object.entries(s.stages).map(([name, d]) => [name, num(d.n), formatMs(d.p50_ms), formatMs(d.p95_ms)])} />
          <p className="mt-3 text-xs text-muted-foreground">
            Explicaciones descartadas por precio sin respaldo: {s.quality.explanations_discarded} · presupuestos inventados descartados: {s.quality.invented_budget_discarded} · avisos de
            presupuesto agregados por el código: {s.quality.budget_warning_added} · desacuerdo reglas/Gemini: {s.quality.rules_llm_disagreement} ({pct(s.quality.rules_llm_disagreement_rate)}) ·
            replanificaciones: {s.quality.replans}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">Sin datos.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            {head.map((h, i) => (
              <th key={h} className={cn("py-2 font-medium", i > 0 && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="border-b last:border-0">
              {row.map((cell, i) => (
                <td key={i} className={cn("py-2", i > 0 ? "text-right tabular-nums" : "pr-2")}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ status }: { status: RunRow["status"] }) {
  const variant = status === "ok" ? "success" : status === "error" ? "destructive" : "warning";
  return <Badge variant={variant}>{STATUS_LABEL[status] ?? status}</Badge>;
}

function RecentRuns({ runs, onOpen, withDate }: { runs: RunRow[]; onOpen: (id: string) => void; withDate: boolean }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Ejecuciones recientes</CardTitle>
        <CardDescription>Vista previa con datos personales enmascarados. Toca una fila para ver su traza.</CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {runs.length === 0 ? (
          <Empty />
        ) : (
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="py-2 font-medium">Hora</th>
                <th className="py-2 font-medium">Flujo</th>
                <th className="py-2 font-medium">Estado</th>
                <th className="py-2 text-right font-medium">Latencia</th>
                <th className="py-2 text-right font-medium">Gemini</th>
                <th className="py-2 text-right font-medium">Tokens</th>
                <th className="py-2 pl-4 font-medium">Consulta</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id} className="cursor-pointer border-b last:border-0 hover:bg-muted/50" onClick={() => onOpen(run.run_id)}>
                  <td className="py-2 tabular-nums">
                    <button type="button" className="underline-offset-4 hover:underline" onClick={() => onOpen(run.run_id)}>
                      {run.started_at
                        ? new Date(run.started_at).toLocaleString("es-CL", withDate ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" } : { hour: "2-digit", minute: "2-digit" })
                        : "—"}
                    </button>
                  </td>
                  <td className="py-2">{FLOW_LABEL[run.flow] ?? run.flow}</td>
                  <td className="py-2">
                    <span className="flex items-center gap-1.5">
                      <StatusBadge status={run.status} />
                      {run.guardrails?.injection ? <ShieldAlert className="size-4 text-amber-600" aria-label="Posible inyección" /> : null}
                      {run.eval_tag ? <Badge variant="outline">eval</Badge> : null}
                    </span>
                  </td>
                  <td className="py-2 text-right tabular-nums">{formatMs(run.latency_ms)}</td>
                  <td className="py-2 text-right tabular-nums">{run.llm_calls}</td>
                  <td className="py-2 text-right tabular-nums">{(run.input_tokens + run.output_tokens).toLocaleString("es-CL")}</td>
                  <td className="max-w-xs truncate py-2 pl-4 text-muted-foreground">{run.input_preview}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

function RunDialog({ runId, token, onClose }: { runId: string | null; token: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ["obs-run", runId], queryFn: () => fetchRun(runId!, token), enabled: Boolean(runId && token) });
  const run = query.data;
  return (
    <Dialog open={Boolean(runId)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Traza de la ejecución</DialogTitle>
          <DialogDescription className="break-all font-mono text-xs">{runId}</DialogDescription>
        </DialogHeader>
        {!run ? (
          <div className="h-40 animate-pulse rounded-lg bg-muted/60" />
        ) : (
          <div className="space-y-5">
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div>
                <dt className="text-xs text-muted-foreground">Estado</dt>
                <dd>
                  <StatusBadge status={run.status} />
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Latencia</dt>
                <dd className="font-semibold">{formatMs(run.latency_ms)}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">CPU del proceso</dt>
                <dd className="font-semibold">{formatMs(run.cpu_ms)}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Tokens (entrada / salida)</dt>
                <dd className="font-semibold">
                  {run.input_tokens} / {run.output_tokens}
                </dd>
              </div>
            </dl>
            {run.input_preview ? <p className="rounded-lg bg-muted/40 p-3 text-sm">«{run.input_preview}»</p> : null}
            {run.error_message ? <p className="text-sm text-destructive">{run.error_message}</p> : null}
            {run.spans.length ? <Waterfall spans={run.spans} total={run.latency_ms} /> : <p className="text-sm text-muted-foreground">Sin tramos (respuesta inmediata).</p>}
            <details className="text-sm">
              <summary className="cursor-pointer text-muted-foreground">Ver como tabla</summary>
              <Table
                head={["Tramo", "Tipo", "Inicio", "Duración", "Estado"]}
                rows={run.spans.map((s) => [s.name, s.kind, formatMs(s.start_ms), formatMs(s.duration_ms), s.status])}
              />
            </details>
            <details className="text-sm">
              <summary className="cursor-pointer text-muted-foreground">Calidad y protecciones</summary>
              <pre className="mt-2 overflow-x-auto rounded-lg bg-muted/40 p-3 text-xs">{JSON.stringify({ quality: run.quality, guardrails: run.guardrails, extra: run.extra }, null, 2)}</pre>
            </details>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
