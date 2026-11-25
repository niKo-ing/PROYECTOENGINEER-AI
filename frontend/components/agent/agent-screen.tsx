"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Bookmark, Bot, LogIn, MessageSquarePlus, ShieldCheck, X } from "lucide-react";

import { AgentReasoning } from "@/components/agent/agent-reasoning";
import { AgentProducts } from "@/components/agent/agent-products";
import { AgentSaved } from "@/components/agent/agent-saved";
import { AgentThoughts, AgentWrites } from "@/components/agent/agent-thoughts";
import { ChatComposer } from "@/components/chat/chat-composer";
import { MarkdownContent } from "@/components/chat/markdown-content";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EMPTY_STATE, fetchAgentState, newThreadId, runAgent, type AgentRun, type AgentState } from "@/lib/api/agent";
import { newId } from "@/lib/utils";
import { useSession } from "@/lib/auth/use-session";
import { cn } from "@/lib/utils";

type Message = { id: string; role: "user" | "assistant"; text: string; run?: AgentRun };

// Ideas para empezar, pensadas para el catálogo ingestado (celulares, notebooks, tarjetas de video, procesadores y placas madre).
// Cada una muestra una capacidad distinta: lista guardada, alerta, comparación entre tiendas y memoria de preferencias.
const SUGGESTIONS = [
  { title: "Armar una lista de compra", prompt: "Quiero un celular Samsung o Xiaomi, presupuesto $320.000. Arma una lista de compra." },
  { title: "Avisarme si baja de precio", prompt: "Quiero el notebook HP Victus 15 con RTX 2050, mi presupuesto es $1.000.000. Avísame cuando baje a ese precio." },
  { title: "Ver dónde está más barato", prompt: "Compara el Xiaomi Redmi Note 15 Pro entre las tiendas y dime dónde conviene comprarlo." },
  { title: "Recordar lo que prefiero", prompt: "Prefiero Samsung y no quiero Xiaomi. Busco un celular, presupuesto $350.000." },
] as const;

export function AgentScreen() {
  const { session, isLoading: isLoadingSession } = useSession();
  const searchParams = useSearchParams();
  // Si el usuario llega desde la ficha de un producto (/chat?product=ID&name=…), el asistente lo sabe.
  const productParam = searchParams.get("product");
  const productId = productParam && /^\d+$/.test(productParam) ? Number(productParam) : null;
  const productName = searchParams.get("name");
  const [messages, setMessages] = useState<Message[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [state, setState] = useState<AgentState>(EMPTY_STATE);
  const [threadId, setThreadId] = useState(() => newThreadId());
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [mobileView, setMobileView] = useState<"chat" | "detalle">("chat");
  // Cada respuesta trae su resumen plegado («Pensó en N pasos»). El panel lateral con el detalle técnico (plan con
  // prioridades, herramientas y argumentos) solo se abre a pedido, y lo guardado vive en una ventana aparte.
  const [panelOpen, setPanelOpen] = useState(false);
  const [savedOpen, setSavedOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const accessToken = session?.access_token;
  const selectedRun = messages.find((message) => message.id === selectedRunId)?.run ?? null;

  const refreshState = useCallback(async () => {
    if (!accessToken) {
      setState(EMPTY_STATE);
      return;
    }
    try {
      setState(await fetchAgentState(accessToken));
    } catch {
      setState(EMPTY_STATE);
    }
  }, [accessToken]);

  useEffect(() => {
    if (isLoadingSession) return;
    let cancelled = false;
    void (async () => {
      const next = accessToken ? await fetchAgentState(accessToken).catch(() => EMPTY_STATE) : EMPTY_STATE;
      if (!cancelled) setState(next);
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoadingSession, accessToken]);

  useEffect(() => {
    // Sin conversación no se baja: en el celular, el inicio es más alto que la pantalla y quedaba cortado arriba.
    if (!messages.length && !isLoading) return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isLoading]);

  function newConversation() {
    setMessages([]);
    setSelectedRunId(null);
    setError("");
    setThreadId(newThreadId());
  }

  async function submit(text = draft) {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;
    if (!accessToken) {
      setError("Inicia sesión para usar el asistente.");
      return;
    }
    setDraft("");
    setError("");
    setIsLoading(true);
    setMessages((current) => [...current, { id: newId(), role: "user", text: trimmed }]);
    try {
      const run = await runAgent(trimmed, threadId, accessToken, productId);
      const id = newId();
      setMessages((current) => [...current, { id, role: "assistant", text: run.answer, run }]);
      setSelectedRunId(id);
      await refreshState();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible consultar al agente.");
    } finally {
      setIsLoading(false);
    }
  }

  const hasConversation = messages.length > 0;
  const savedCount = state.alerts.length + state.lists.length + state.memories.length;

  function openDetails(messageId: string) {
    setSelectedRunId(messageId);
    setPanelOpen(true);
    setMobileView("detalle");
  }

  function closeDetails() {
    setPanelOpen(false);
    setMobileView("chat");
  }

  const savedButton = (
    <Button type="button" variant="ghost" size="sm" onClick={() => setSavedOpen(true)} aria-label={savedCount ? `Guardado (${savedCount})` : "Guardado"} className="gap-1.5">
      <Bookmark className="size-4" aria-hidden="true" />
      <span className="hidden sm:inline">Guardado</span>
      {savedCount ? <span className="rounded-full bg-primary/10 px-1.5 text-xs font-semibold text-primary tabular-nums">{savedCount}</span> : null}
    </Button>
  );

  return (
    <div className={cn("grid min-h-0 min-w-0 flex-1 grid-rows-[minmax(0,1fr)]", panelOpen && "lg:grid-cols-[minmax(0,1fr)_24rem] xl:grid-cols-[minmax(0,1fr)_28rem]")}>
      <section className={cn("min-h-0 min-w-0 flex-col overflow-hidden lg:flex", !panelOpen || mobileView === "chat" ? "flex" : "hidden")}>
        {hasConversation ? (
          <header className="flex shrink-0 items-center gap-3 border-b px-4 py-2.5 sm:px-6">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary" aria-hidden="true">
              <Bot className="size-4" />
            </div>
            <h1 className="min-w-0 flex-1 truncate text-sm font-semibold tracking-tight">Asistente de ahorro</h1>
            <div className="flex items-center gap-1">
              {savedButton}
              <Button type="button" variant="ghost" size="sm" onClick={newConversation} aria-label="Nueva conversación" className="gap-1.5">
                <MessageSquarePlus className="size-4" aria-hidden="true" />
                <span className="hidden sm:inline">Nueva conversación</span>
              </Button>
            </div>
          </header>
        ) : null}

        <div ref={scrollRef} role="log" aria-live="polite" aria-label="Conversación con el asistente" className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain">
          <div className={cn("mx-auto flex min-h-full w-full max-w-3xl flex-col px-4 sm:px-6", hasConversation ? "space-y-4 py-6" : "py-8")}>
            {!hasConversation ? (
              // my-auto (y no justify-center en el padre): centra cuando cabe y, si no cabe, no recorta la parte de arriba.
              <div className="my-auto w-full">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-sm text-primary">
                    <Bot className="size-4" aria-hidden="true" />
                    Asistente de ahorro con IA
                  </div>
                  {session ? savedButton : null}
                </div>
                <h1 className="mt-1 text-2xl font-bold tracking-tight text-balance sm:text-3xl">
                  {productName ? `¿Qué quieres saber de «${productName}»?` : "¿Qué quieres comprar y cuánto puedes gastar?"}
                </h1>
                <p className="mt-2 text-muted-foreground text-pretty">
                  Busco en el catálogo, comparo tiendas, te digo si el precio está inflado y puedo dejarte una alerta o una lista de compra.
                </p>

                {!isLoadingSession && !session ? (
                  <div className="mt-5 flex flex-wrap items-center gap-3 rounded-xl border bg-muted/40 px-4 py-3 text-sm">
                    <p className="min-w-0 flex-1">Para conversar con el asistente necesitas una cuenta: así puede guardar tus alertas y listas.</p>
                    <Button asChild size="sm" className="gap-1.5">
                      <Link href="/login">
                        <LogIn className="size-4" aria-hidden="true" />
                        Iniciar sesión
                      </Link>
                    </Button>
                  </div>
                ) : null}

                <div className="mt-6 grid gap-2 sm:grid-cols-2">
                  {SUGGESTIONS.map((suggestion, index) => (
                    <button
                      key={suggestion.title}
                      type="button"
                      onClick={() => void submit(suggestion.prompt)}
                      style={{ animationDelay: `${index * 60}ms` }}
                      className="min-h-11 rounded-xl border px-4 py-3 text-left text-sm transition-colors hover:border-primary/40 hover:bg-muted/60 active:bg-muted motion-safe:animate-card-in"
                    >
                      <span className="block font-medium">{suggestion.title}</span>
                      <span className="mt-0.5 line-clamp-2 block text-xs leading-5 text-muted-foreground">{suggestion.prompt}</span>
                    </button>
                  ))}
                </div>
                <p className="mt-4 flex items-start gap-1.5 text-xs leading-5 text-muted-foreground">
                  <ShieldCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                  Respuestas generadas con IA (Gemini). Los precios son referenciales y lo que guarde (alertas, listas y tus preferencias) queda en tu cuenta.
                </p>
              </div>
            ) : null}

            {messages.map((message) =>
              message.role === "user" ? (
                <article key={message.id} className="motion-safe:animate-message-in flex justify-end">
                  <div className="max-w-[92%] [overflow-wrap:anywhere] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-6 text-primary-foreground shadow-sm sm:max-w-[78%]">
                    <p className="whitespace-pre-wrap">{message.text}</p>
                  </div>
                </article>
              ) : (
                <article key={message.id} className="motion-safe:animate-message-in flex items-start gap-2.5">
                  <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary" aria-hidden="true">
                    <Bot className="size-4" />
                  </div>
                  <div
                    className={cn("min-w-0 flex-1 [overflow-wrap:anywhere] rounded-2xl rounded-bl-md bg-muted px-4 py-3", panelOpen && selectedRunId === message.id && "ring-2 ring-primary/40")}
                  >
                    {message.run ? <AgentThoughts run={message.run} onDetails={() => openDetails(message.id)} /> : null}
                    <MarkdownContent markdown={message.text} />
                    {message.run?.products?.length ? <AgentProducts products={message.run.products} /> : null}
                    {message.run ? <AgentWrites wrote={message.run.wrote} onOpenSaved={() => setSavedOpen(true)} /> : null}
                  </div>
                </article>
              )
            )}

            {isLoading ? <TypingIndicator label="Planificando y consultando el catálogo…" /> : null}

            {error ? (
              <div className="motion-safe:animate-message-in rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-2.5 text-sm text-destructive" role="alert">
                {error}
              </div>
            ) : null}
          </div>
        </div>

        <div className="shrink-0 border-t">
          <div className="mx-auto w-full max-w-3xl px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 sm:px-6">
            <ChatComposer draft={draft} isLoading={isLoading} onChange={setDraft} onSend={() => void submit()} />
          </div>
        </div>
      </section>

      {panelOpen ? (
        <aside
          className={cn("min-h-0 min-w-0 flex-col overflow-hidden bg-muted/30 lg:flex lg:border-l motion-safe:animate-panel-in", mobileView === "detalle" ? "flex" : "hidden")}
          aria-label="Detalle técnico de la respuesta"
        >
          <div className="flex shrink-0 items-center gap-2 border-b px-4 py-2.5">
            <h2 className="min-w-0 flex-1 text-sm font-semibold">Detalle técnico</h2>
            <Button type="button" variant="ghost" size="icon" onClick={closeDetails} aria-label="Cerrar el detalle técnico" className="size-9 shrink-0">
              <X className="size-4" aria-hidden="true" />
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto motion-safe:animate-fade-in">
            <AgentReasoning run={selectedRun} loading={isLoading} />
          </div>
        </aside>
      ) : null}

      <Dialog open={savedOpen} onOpenChange={setSavedOpen}>
        <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Guardado en tu cuenta</DialogTitle>
            <DialogDescription>Alertas de precio, listas de compra y lo que el asistente recuerda de tus preferencias.</DialogDescription>
          </DialogHeader>
          <div className="-mx-4">
            <AgentSaved state={state} />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
