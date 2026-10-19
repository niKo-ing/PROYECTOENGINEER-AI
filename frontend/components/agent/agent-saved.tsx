"use client";

import { Bell, BellRing, Brain, ShoppingCart } from "lucide-react";

import { cn } from "@/lib/utils";
import { formatCLP } from "@/lib/utils";
import type { AgentState } from "@/lib/api/agent";

const KIND_LABELS: Record<string, string> = { preference: "Preferencia", fact: "Dato", episode: "Tarea anterior" };

function Section({ title, icon, empty, children, count }: { title: string; icon: React.ReactNode; empty: string; children: React.ReactNode; count: number }) {
  return (
    <section className="space-y-2">
      <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <span className="text-primary" aria-hidden="true">
          {icon}
        </span>
        {title}
        <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] tabular-nums">{count}</span>
      </h3>
      {count === 0 ? <p className="rounded-xl bg-muted/40 px-3 py-2 text-xs text-muted-foreground">{empty}</p> : <ul className="space-y-1.5">{children}</ul>}
    </section>
  );
}

export function AgentSaved({ state }: { state: AgentState }) {
  return (
    <div className="space-y-5 px-4 py-4">
      <Section title="Alertas de precio" icon={<Bell className="size-4" />} count={state.alerts.length} empty="Aún no hay alertas. Pídele «avísame cuando baje».">
        {state.alerts.map((alert) => (
          <li key={alert.id} className={cn("rounded-xl px-3 py-2 text-sm leading-5", alert.active ? "bg-muted/50" : "bg-primary/10")}>
            <div className="flex items-start gap-2">
              {alert.active ? <Bell className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" /> : <BellRing className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />}
              <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                <p className="font-medium">{alert.product}</p>
                <p className="text-xs text-muted-foreground">
                  Objetivo {formatCLP(alert.target_price_clp)}
                  {alert.current_price_clp ? ` · hoy ${formatCLP(alert.current_price_clp)}` : ""}
                </p>
                <p className={cn("text-xs font-semibold", alert.active ? "text-muted-foreground" : "text-primary")}>
                  {alert.active ? "Activa" : `Cumplida a ${formatCLP(alert.triggered_price_clp ?? 0)}`}
                </p>
              </div>
            </div>
          </li>
        ))}
      </Section>

      <Section title="Listas de compra" icon={<ShoppingCart className="size-4" />} count={state.lists.length} empty="Aún no hay listas. Pídele «arma una lista de compra».">
        {state.lists.map((list) => (
          <li key={list.id} className="rounded-xl bg-muted/50 px-3 py-2 text-sm leading-5">
            <p className="font-medium [overflow-wrap:anywhere]">{list.name}</p>
            {list.items.map((item) => (
              <p key={item.name} className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
                {item.name} · {formatCLP(item.price_clp)} en {item.store}
              </p>
            ))}
            <p className="mt-1 text-xs font-semibold text-foreground">
              Total {formatCLP(list.total_clp)}
              {list.budget_clp ? ` de ${formatCLP(list.budget_clp)}` : ""}
            </p>
          </li>
        ))}
      </Section>

      <Section title="Lo que recuerda" icon={<Brain className="size-4" />} count={state.memories.length} empty="Aún no recuerda nada. Dile, por ejemplo, «prefiero Samsung».">
        {state.memories.map((memory) => (
          <li key={memory.id} className="rounded-xl bg-muted/50 px-3 py-2 text-xs leading-5 [overflow-wrap:anywhere]">
            <span className="mr-1.5 rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-primary">{KIND_LABELS[memory.kind] ?? memory.kind}</span>
            {memory.content.length > 140 ? `${memory.content.slice(0, 137)}…` : memory.content}
          </li>
        ))}
      </Section>
    </div>
  );
}
