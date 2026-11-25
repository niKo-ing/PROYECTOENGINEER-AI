"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Bot, Monitor, Plus, Wrench } from "lucide-react";

import { CompatBadge, KindBadge, LoginNeeded, SLOT_META } from "@/components/pc/pc-ui";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { listMyPcs, saveDraft, type SavedPc } from "@/lib/api/pc";
import { useSession } from "@/lib/auth/use-session";
import { formatCLP } from "@/lib/utils";

export default function MyPcsPage() {
  const { session, isLoading } = useSession();
  const router = useRouter();
  const token = session?.access_token ?? "";
  const query = useQuery({ queryKey: ["my-pcs", token], queryFn: () => listMyPcs(token), enabled: Boolean(token) });

  if (isLoading) return <div className="px-4 py-16 text-center text-muted-foreground">Cargando…</div>;
  if (!session) {
    return (
      <div className="px-4 py-16">
        <LoginNeeded what="ver tus computadores" />
      </div>
    );
  }

  const pcs = query.data?.items ?? [];
  const own = pcs.filter((pc) => pc.kind === "propio");
  const projects = pcs.filter((pc) => pc.kind === "proyecto");

  function registerMine() {
    saveDraft([], { kind: "propio" });
    router.push("/armar");
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Mis computadores</h1>
          <p className="mt-1 text-muted-foreground">Registra el PC que ya tienes para saber qué mejorar, o guarda los que planeas armar.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="gap-2" onClick={registerMine}>
            <Monitor className="size-4" aria-hidden="true" />
            Registrar mi PC
          </Button>
          <Button asChild variant="outline" className="gap-2">
            <Link href="/armar/asistente">
              <Bot className="size-4" aria-hidden="true" />
              Armar con IA
            </Link>
          </Button>
          <Button asChild className="gap-2">
            <Link href="/armar">
              <Plus className="size-4" aria-hidden="true" />
              Nuevo proyecto
            </Link>
          </Button>
        </div>
      </div>

      {query.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-40 animate-pulse rounded-xl bg-muted/60" />
          ))}
        </div>
      ) : query.isError ? (
        <p className="rounded-lg border border-destructive/40 p-4 text-sm text-destructive">{(query.error as Error).message}</p>
      ) : pcs.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed bg-muted/30 px-6 py-16 text-center">
          <Wrench className="size-8 text-muted-foreground" aria-hidden="true" />
          <h2 className="font-semibold">Todavía no tienes computadores guardados</h2>
          <p className="max-w-md text-sm text-muted-foreground">Registra tu PC actual (hay modelos descontinuados para eso) o arma uno nuevo. La IA puede revisarlos y sugerirte mejoras.</p>
        </div>
      ) : (
        <Tabs defaultValue="todos">
          <TabsList>
            <TabsTrigger value="todos">Todos ({pcs.length})</TabsTrigger>
            <TabsTrigger value="propio">Mis PC ({own.length})</TabsTrigger>
            <TabsTrigger value="proyecto">Proyectos ({projects.length})</TabsTrigger>
          </TabsList>
          {(
            [
              ["todos", pcs],
              ["propio", own],
              ["proyecto", projects],
            ] as const
          ).map(([value, list]) => (
            <TabsContent key={value} value={value}>
              <ul className="grid gap-4 sm:grid-cols-2">
                {list.map((pc) => (
                  <PcCard key={pc.id} pc={pc} />
                ))}
              </ul>
            </TabsContent>
          ))}
        </Tabs>
      )}
    </div>
  );
}

function PcCard({ pc }: { pc: SavedPc }) {
  const main = pc.items.filter((part) => ["cpu", "gpu", "ram"].includes(part.slot));
  return (
    <li>
      <Link href={`/mis-pc/${pc.id}`} className="flex h-full flex-col gap-3 rounded-xl border bg-card p-4 transition-colors hover:border-primary/50 hover:bg-muted/30">
        <div className="flex items-start justify-between gap-2">
          <h2 className="font-semibold">{pc.name}</h2>
          <div className="flex shrink-0 gap-1.5">
            <KindBadge kind={pc.kind} />
            <CompatBadge report={pc.report} />
          </div>
        </div>
        <ul className="space-y-1 text-sm">
          {main.length ? (
            main.map((part, index) => {
              const Icon = SLOT_META[part.slot].icon;
              return (
                <li key={index} className="flex items-center gap-2 text-muted-foreground">
                  <Icon className="size-3.5 shrink-0" aria-hidden="true" />
                  <span className="truncate">{part.name}</span>
                </li>
              );
            })
          ) : (
            <li className="text-muted-foreground">Sin piezas principales</li>
          )}
        </ul>
        <div className="mt-auto flex items-center justify-between text-sm">
          <span className="text-muted-foreground">{pc.items.length} piezas{pc.use_case_label ? ` · ${pc.use_case_label}` : ""}</span>
          <span className="font-semibold tabular-nums">{pc.total_clp ? formatCLP(pc.total_clp) : "—"}</span>
        </div>
      </Link>
    </li>
  );
}
