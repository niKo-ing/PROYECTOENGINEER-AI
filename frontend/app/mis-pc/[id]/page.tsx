"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BookOpen, Bot, LoaderCircle, Pencil, Sparkles, Trash2 } from "lucide-react";

import { CompatBadge, KindBadge, LoginNeeded, PartsList, ReportPanel } from "@/components/pc/pc-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { deletePc, fetchSlots, getMyPc, itemsFromParts, reviewPc, saveDraft, type Review } from "@/lib/api/pc";
import { useSession } from "@/lib/auth/use-session";
import { formatCLP } from "@/lib/utils";

export default function PcDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const pcId = Number(id);
  const { session, isLoading } = useSession();
  const router = useRouter();
  const queryClient = useQueryClient();
  const token = session?.access_token ?? "";
  const pcQuery = useQuery({ queryKey: ["my-pc", pcId, token], queryFn: () => getMyPc(pcId, token), enabled: Boolean(token) && Number.isFinite(pcId) });
  const slotsQuery = useQuery({ queryKey: ["pc-slots"], queryFn: fetchSlots, staleTime: Infinity });
  const [budget, setBudget] = useState("300000");
  const [useCase, setUseCase] = useState<string>("");
  const [review, setReview] = useState<Review | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const reviewMutation = useMutation({
    mutationFn: () => reviewPc(pcId, Number(budget.replace(/\D/g, "")) || 300_000, useCase || null, token),
    onSuccess: setReview,
  });
  const deleteMutation = useMutation({
    mutationFn: () => deletePc(pcId, token),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["my-pcs"] });
      router.push("/mis-pc");
    },
  });

  if (isLoading) return <div className="px-4 py-16 text-center text-muted-foreground">Cargando…</div>;
  if (!session) {
    return (
      <div className="px-4 py-16">
        <LoginNeeded what="ver tus computadores" />
      </div>
    );
  }
  if (pcQuery.isLoading) return <div className="mx-auto max-w-5xl px-4 py-8"><div className="h-64 animate-pulse rounded-xl bg-muted/60" /></div>;
  if (pcQuery.isError || !pcQuery.data) {
    return (
      <div className="mx-auto max-w-xl px-4 py-16 text-center">
        <p className="text-muted-foreground">{pcQuery.error instanceof Error ? pcQuery.error.message : "No encontramos ese computador."}</p>
        <Button asChild variant="link">
          <Link href="/mis-pc">Volver a Mis computadores</Link>
        </Button>
      </div>
    );
  }

  const pc = pcQuery.data;
  const effectiveUseCase = useCase || pc.use_case || "";

  function edit() {
    saveDraft(itemsFromParts(pc.items), { name: pc.name, pcId: pc.id, kind: pc.kind, use_case: pc.use_case, budget_clp: pc.budget_clp });
    router.push("/armar");
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <Link href="/mis-pc" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden="true" />
        Mis computadores
      </Link>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{pc.name}</h1>
            <KindBadge kind={pc.kind} />
            <CompatBadge report={pc.report} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {pc.use_case_label ? `${pc.use_case_label} · ` : ""}
            {pc.source === "asistente" ? "Armado con el asistente" : pc.source === "agente" ? "Guardado por el agente" : "Armado a mano"}
            {pc.updated_at ? ` · actualizado ${new Date(pc.updated_at).toLocaleDateString("es-CL")}` : ""}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="gap-2" onClick={edit}>
            <Pencil className="size-4" aria-hidden="true" />
            Editar piezas
          </Button>
          <Button variant="outline" className="gap-2 text-destructive hover:text-destructive" onClick={() => setConfirmDelete(true)}>
            <Trash2 className="size-4" aria-hidden="true" />
            Borrar
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Piezas</CardTitle>
              <CardDescription>Total referencial {formatCLP(pc.total_clp)}</CardDescription>
            </CardHeader>
            <CardContent>
              <PartsList parts={pc.items} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Sparkles className="size-4 text-primary" aria-hidden="true" />
                Revisión con IA
              </CardTitle>
              <CardDescription>Diagnóstico del equipo y las mejoras que más rinden con tu presupuesto.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  reviewMutation.mutate();
                }}
                className="flex flex-wrap items-end gap-3"
              >
                <div className="space-y-1">
                  <Label htmlFor="budget">Presupuesto para mejorar</Label>
                  <Input id="budget" inputMode="numeric" value={budget} onChange={(event) => setBudget(event.target.value)} className="w-40" />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="use">Para</Label>
                  <Select value={effectiveUseCase} onValueChange={setUseCase}>
                    <SelectTrigger id="use" className="w-52">
                      <SelectValue placeholder="Uso principal" />
                    </SelectTrigger>
                    <SelectContent>
                      {(slotsQuery.data?.use_cases ?? []).map((uc) => (
                        <SelectItem key={uc.key} value={uc.key}>
                          {uc.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button type="submit" disabled={reviewMutation.isPending} className="gap-2">
                  {reviewMutation.isPending ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <Bot className="size-4" aria-hidden="true" />}
                  Revisar mi PC
                </Button>
              </form>
              {reviewMutation.isError ? (
                <p className="text-sm text-destructive" role="alert">
                  {(reviewMutation.error as Error).message}
                </p>
              ) : null}

              {review ? (
                <div className="space-y-4">
                  <div className="rounded-lg bg-muted/40 p-4">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <Badge variant={review.explained_by === "llm" ? "secondary" : "outline"}>{review.explained_by === "llm" ? "Explicado por IA" : "Explicación automática"}</Badge>
                      {review.guides.map((guide) => (
                        <Link key={guide.guide} href={guide.url} className="inline-flex items-center gap-1 text-xs text-primary underline-offset-4 hover:underline">
                          <BookOpen className="size-3" aria-hidden="true" />
                          {guide.title}
                        </Link>
                      ))}
                    </div>
                    <p className="whitespace-pre-line text-sm leading-relaxed">{review.answer}</p>
                  </div>
                  {review.upgrades?.options.length ? (
                    <ol className="space-y-3">
                      {review.upgrades.options.map((option, index) => (
                        <li key={index} className="rounded-lg border p-3">
                          <div className="flex flex-wrap items-baseline justify-between gap-2">
                            <p className="font-medium">
                              {index + 1}. {option.title}
                            </p>
                            <p className="text-sm">
                              <span className="font-semibold tabular-nums">{formatCLP(option.cost_clp)}</span>
                              <span className="ml-2 text-emerald-700 dark:text-emerald-400">+{option.gain_pct} %</span>
                            </p>
                          </div>
                          <p className="mt-1 text-sm text-muted-foreground">Comprar: {option.buy.map((part) => part.name).join(", ")}</p>
                          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                            <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, option.score_after)}%` }} />
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            Rendimiento estimado {option.score_before} → {option.score_after} (índice relativo para este uso)
                          </p>
                        </li>
                      ))}
                    </ol>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
          </Card>
        </div>

        <aside className="lg:sticky lg:top-20 lg:self-start">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Compatibilidad</CardTitle>
            </CardHeader>
            <CardContent>{pc.report ? <ReportPanel report={pc.report} /> : null}</CardContent>
          </Card>
        </aside>
      </div>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>¿Borrar «{pc.name}»?</DialogTitle>
            <DialogDescription>Se elimina de tu cuenta y no se puede recuperar.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Cancelar
            </Button>
            <Button variant="destructive" disabled={deleteMutation.isPending} onClick={() => deleteMutation.mutate()}>
              Borrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
