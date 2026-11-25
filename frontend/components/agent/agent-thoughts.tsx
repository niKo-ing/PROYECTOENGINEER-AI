"use client";

import { useId, useState } from "react";
import Link from "next/link";
import { Check, ChevronRight, Sparkles } from "lucide-react";

import { cn, formatCLP } from "@/lib/utils";
import type { AgentRun, TraceEvent } from "@/lib/api/agent";

// Resumen en lenguaje simple de lo que hizo el agente, plegado sobre cada respuesta (como «Pensó durante…» en otros
// asistentes). El detalle técnico (plan con prioridades, herramientas y argumentos) queda en el panel lateral, que solo
// se abre a pedido.

const REASONS: Record<string, string> = {
  sin_resultados: "no encontró resultados y amplió la búsqueda",
  sobre_presupuesto: "todo superaba el presupuesto y buscó alternativas",
  sin_stock: "no había stock y buscó otra opción",
  precio_alto: "el precio estaba alto según el historial",
  error_herramienta: "una consulta falló y la reintentó por otro camino",
  piezas_incompatibles: "había piezas incompatibles y buscó un reemplazo",
  armado_fuera_de_presupuesto: "el equipo se pasaba del presupuesto y lo ajustó",
};

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function money(value: unknown): string | null {
  return typeof value === "number" && value > 0 ? formatCLP(value) : null;
}

function describeCall(tool: string, args: Record<string, unknown>): string {
  const query = text(args.query) ?? text(args.question);
  const budget = money(args.max_price_clp) ?? money(args.budget_clp);
  switch (tool) {
    case "search_products":
      return `Buscó ${query ? `«${query}»` : "productos"} en el catálogo${budget ? ` hasta ${budget}` : ""}`;
    case "get_product_offers":
      return "Revisó las ofertas y el stock de las tiendas";
    case "get_price_history":
    case "analyze_price_trend":
      return "Revisó el historial de precios para ver si conviene comprar ahora";
    case "compare_products":
      return "Comparó los productos entre sí";
    case "get_user_profile":
      return "Revisó tu perfil";
    case "recall_memory":
      return "Revisó lo que recuerda de tus preferencias";
    case "check_price_alerts":
      return "Revisó tus alertas de precio";
    case "create_price_alert":
      return `Creó una alerta de precio${money(args.target_price_clp) ? ` a ${money(args.target_price_clp)}` : ""}`;
    case "save_shopping_list":
      return "Guardó una lista de compra";
    case "remember_preference":
      return "Guardó tu preferencia para la próxima vez";
    case "search_pc_parts":
      return `Buscó piezas${query ? ` «${query}»` : ""}`;
    case "check_pc_compatibility":
      return "Revisó la compatibilidad de las piezas (socket, memoria, medidas y fuente)";
    case "recommend_pc_build":
      return `Armó un PC${budget ? ` para ${budget}` : " dentro del presupuesto"}`;
    case "suggest_pc_upgrade":
      return "Buscó la mejora que más rinde por lo que cuesta";
    case "list_my_pcs":
      return "Revisó tus computadores guardados";
    case "save_pc_build":
      return "Guardó el PC en «Mis computadores»";
    case "search_compatibility_guide":
      return "Consultó las guías de compatibilidad";
    case "research_part_web":
      return "Buscó el dato que faltaba en la web";
    default:
      return "Consultó otra herramienta";
  }
}

/** Pasos en lenguaje simple, sin repetir líneas seguidas iguales. */
export function describeRun(run: AgentRun): string[] {
  const lines: string[] = [];
  const push = (line: string) => {
    if (lines[lines.length - 1] !== line) lines.push(line);
  };
  run.trace.forEach((event: TraceEvent) => {
    switch (event.node) {
      case "recall":
        if (event.memories.length) push(`Recordó lo que le dijiste antes: «${event.memories[0].content.slice(0, 80)}»`);
        break;
      case "plan":
        if (event.replan) push(`Cambió de plan: ${REASONS[event.replan] ?? "las condiciones cambiaron"}`);
        break;
      case "act":
        event.tool_calls.forEach((call) => push(describeCall(call.tool, call.args)));
        break;
      case "give_up":
        push("Llegó al límite de pasos y respondió con lo que tenía");
        break;
      default:
        break;
    }
  });
  return lines;
}

export function AgentThoughts({ run, onDetails }: { run: AgentRun; onDetails: () => void }) {
  const [open, setOpen] = useState(false);
  const regionId = useId();
  const lines = describeRun(run);
  if (!lines.length) return null;
  const summary = `Pensó en ${lines.length} paso${lines.length === 1 ? "" : "s"}${run.replans ? ` · cambió de plan ${run.replans === 1 ? "una vez" : `${run.replans} veces`}` : ""}`;

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={regionId}
        className="-ml-1 inline-flex min-h-8 items-center gap-1.5 rounded-md px-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-primary"
      >
        <Sparkles className="size-3.5 text-primary" aria-hidden="true" />
        {summary}
        <ChevronRight className={cn("size-3.5 transition-transform duration-200", open && "rotate-90")} aria-hidden="true" />
      </button>
      {open ? (
        <div id={regionId} className="mt-1 border-l-2 border-primary/20 pl-3 motion-safe:animate-fade-in">
          <ol className="space-y-1 text-xs leading-5 text-muted-foreground">
            {lines.map((line, index) => (
              <li key={`${index}-${line}`} className="[overflow-wrap:anywhere]">
                {line}
              </li>
            ))}
          </ol>
          <button type="button" onClick={onDetails} className="mt-1.5 text-xs font-medium text-primary underline-offset-2 hover:underline">
            Ver detalle técnico
          </button>
        </div>
      ) : null}
    </div>
  );
}

const WRITES: Record<string, { label: string; href?: string }> = {
  create_price_alert: { label: "Alerta creada" },
  save_shopping_list: { label: "Lista guardada" },
  remember_preference: { label: "Preferencia guardada" },
  save_pc_build: { label: "PC guardado", href: "/mis-pc" },
};

/** Confirmación, dentro de la respuesta, de lo que el agente guardó en la cuenta. */
export function AgentWrites({ wrote, onOpenSaved }: { wrote: string[]; onOpenSaved: () => void }) {
  const items = [...new Set(wrote)].filter((tool) => WRITES[tool]);
  if (!items.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {items.map((tool) => {
        const item = WRITES[tool];
        const content = (
          <>
            <Check className="size-3.5" aria-hidden="true" />
            {item.label}
            <span className="text-primary/70">· ver</span>
          </>
        );
        const className = "inline-flex min-h-8 items-center gap-1 rounded-full bg-primary/10 px-2.5 text-xs font-medium text-primary transition-colors hover:bg-primary/15";
        return item.href ? (
          <Link key={tool} href={item.href} className={className}>
            {content}
          </Link>
        ) : (
          <button key={tool} type="button" onClick={onOpenSaved} className={className}>
            {content}
          </button>
        );
      })}
    </div>
  );
}
