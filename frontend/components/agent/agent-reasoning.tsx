"use client";

import { AlertTriangle, Brain, CheckCircle2, Circle, Cog, Database, ListChecks, RefreshCcw, Wrench } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import type { AgentRun, TraceEvent } from "@/lib/api/agent";

const REASON_LABELS: Record<string, string> = {
  sin_resultados: "Búsqueda sin resultados",
  sobre_presupuesto: "Todo supera el presupuesto",
  sin_stock: "Sin stock",
  precio_alto: "Precio alto según el historial",
  error_herramienta: "Falló una herramienta",
};

const TOOL_LABELS: Record<string, string> = {
  search_products: "Buscar productos",
  get_product_offers: "Ver ofertas",
  get_price_history: "Historial de precios",
  analyze_price_trend: "Analizar tendencia",
  compare_products: "Comparar",
  get_user_profile: "Perfil del usuario",
  recall_memory: "Recordar",
  check_price_alerts: "Revisar alertas",
  create_price_alert: "Crear alerta",
  save_shopping_list: "Guardar lista",
  remember_preference: "Recordar preferencia",
};

const WRITE_TOOLS = new Set(["create_price_alert", "save_shopping_list", "remember_preference"]);

export function toolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? tool;
}

function formatArgs(args: Record<string, unknown>): string {
  const parts = Object.entries(args)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => `${key}=${typeof value === "string" ? value : JSON.stringify(value)}`);
  const text = parts.join(", ");
  return text.length > 90 ? `${text.slice(0, 87)}…` : text;
}

function Row({ icon, tone = "default", children }: { icon: ReactNode; tone?: "default" | "warn" | "write" | "ok"; children: ReactNode }) {
  return (
    <li
      className={cn(
        "flex items-start gap-2.5 rounded-xl px-3 py-2 text-sm leading-5",
        tone === "warn" && "bg-amber-500/10 text-foreground",
        tone === "write" && "bg-primary/10 text-foreground",
        tone === "ok" && "bg-muted/60 text-foreground",
        tone === "default" && "bg-muted/40 text-foreground"
      )}
    >
      <span className={cn("mt-0.5 shrink-0", tone === "warn" ? "text-amber-600" : "text-primary")} aria-hidden="true">
        {icon}
      </span>
      <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">{children}</div>
    </li>
  );
}

function EventRow({ event }: { event: TraceEvent }) {
  switch (event.node) {
    case "recall":
      return (
        <Row icon={<Database className="size-4" />}>
          <p className="font-medium">Recordó {event.memories.length === 0 ? "nada relevante" : `${event.memories.length} cosa${event.memories.length > 1 ? "s" : ""}`}</p>
          {event.budget_clp ? <p className="text-xs text-muted-foreground">Presupuesto detectado: ${event.budget_clp.toLocaleString("es-CL")}</p> : null}
        </Row>
      );
    case "plan":
      return (
        <Row icon={event.replan ? <RefreshCcw className="size-4" /> : <ListChecks className="size-4" />} tone={event.replan ? "warn" : "default"}>
          <p className="font-medium">
            {event.replan ? `Replanificó: ${REASON_LABELS[event.replan] ?? event.replan}` : "Armó el plan inicial"}
          </p>
          <p className="text-xs text-muted-foreground">
            {event.plan.length} pasos · {event.source === "llm" ? "propuesto por el modelo" : "plan por reglas (respaldo)"}
          </p>
        </Row>
      );
    case "act": {
      if (event.tool_calls.length === 0) {
        return (
          <Row icon={<Brain className="size-4" />}>
            <p className="font-medium">Redactó la respuesta</p>
          </Row>
        );
      }
      return (
        <>
          {event.tool_calls.map((call, index) => (
            <Row key={`${event.step}-${index}`} icon={<Wrench className="size-4" />} tone={WRITE_TOOLS.has(call.tool) ? "write" : "default"}>
              <p className="font-medium">
                {toolLabel(call.tool)}
                {WRITE_TOOLS.has(call.tool) ? <span className="ml-2 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold uppercase text-primary-foreground">escribe</span> : null}
              </p>
              {Object.keys(call.args).length > 0 ? <p className="font-mono text-[11px] text-muted-foreground">{formatArgs(call.args)}</p> : null}
            </Row>
          ))}
        </>
      );
    }
    case "reflect":
      if (!event.diagnosis) return null;
      return (
        <Row icon={<AlertTriangle className="size-4" />} tone="warn">
          <p className="font-medium">{REASON_LABELS[event.diagnosis.reason] ?? event.diagnosis.reason}</p>
          <p className="text-xs text-muted-foreground">{event.diagnosis.detail}</p>
          <p className="mt-0.5 text-xs font-semibold text-amber-700 dark:text-amber-400">
            {event.decision === "replanificar" ? "→ cambió de plan" : "→ ya se había atendido; sigue sin replanificar"}
          </p>
        </Row>
      );
    case "give_up":
      return (
        <Row icon={<AlertTriangle className="size-4" />} tone="warn">
          <p className="font-medium">Llegó al límite de {event.max_steps} pasos</p>
        </Row>
      );
    case "remember":
      if (event.stored.length === 0) return null;
      return (
        <Row icon={<Database className="size-4" />} tone="ok">
          <p className="font-medium">Guardó en su memoria</p>
          {event.stored.map((text) => (
            <p key={text} className="text-xs text-muted-foreground">
              {text.length > 110 ? `${text.slice(0, 107)}…` : text}
            </p>
          ))}
        </Row>
      );
    default:
      return null;
  }
}

export function AgentReasoning({ run }: { run: AgentRun | null }) {
  if (!run) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 py-10 text-center text-sm text-muted-foreground">
        <Cog className="mb-3 size-8 text-primary/50" aria-hidden="true" />
        <p className="font-medium text-foreground">Aquí verás cómo piensa el agente</p>
        <p className="mt-1 max-w-xs leading-6">Su plan, cada herramienta que usa, cuándo cambia de estrategia y qué recuerda. Haz una consulta para empezar.</p>
      </div>
    );
  }

  const stats = [
    { label: "pasos", value: run.steps },
    { label: "replanes", value: run.replans },
    { label: "escrituras", value: run.wrote.length },
  ];

  return (
    <div className="space-y-5 px-4 py-4">
      <div className="grid grid-cols-3 gap-2">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-xl bg-muted/60 px-3 py-2 text-center">
            <p className="text-xl font-semibold tabular-nums text-foreground">{stat.value}</p>
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{stat.label}</p>
          </div>
        ))}
      </div>

      <section aria-label="Plan">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Plan final</h3>
        <ol className="space-y-1.5">
          {run.plan.map((step) => (
            <li key={step.id} className="flex items-start gap-2 text-sm leading-5">
              {step.status === "hecho" ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" aria-label="hecho" />
              ) : (
                <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground/50" aria-label="pendiente" />
              )}
              <span className={cn("min-w-0 flex-1 [overflow-wrap:anywhere]", step.status === "hecho" ? "text-foreground" : "text-muted-foreground")}>{step.action}</span>
              <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">P{step.priority}</span>
            </li>
          ))}
        </ol>
      </section>

      <section aria-label="Línea de tiempo">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Qué hizo, en orden</h3>
        <ul className="space-y-1.5">
          {run.trace.map((event, index) => (
            <EventRow key={index} event={event} />
          ))}
        </ul>
      </section>

      {run.memories_used.length > 0 ? (
        <section aria-label="Memoria usada">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Memoria que usó</h3>
          <ul className="space-y-1.5">
            {run.memories_used.map((memory) => (
              <li key={memory} className="rounded-xl bg-muted/40 px-3 py-2 text-xs leading-5 text-muted-foreground [overflow-wrap:anywhere]">
                {memory.length > 160 ? `${memory.slice(0, 157)}…` : memory}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
