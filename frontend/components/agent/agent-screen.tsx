"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, MessageSquarePlus, RotateCcw, TrendingDown } from "lucide-react";

import { AgentReasoning } from "@/components/agent/agent-reasoning";
import { AgentSaved } from "@/components/agent/agent-saved";
import { ChatComposer } from "@/components/chat/chat-composer";
import { MarkdownContent } from "@/components/chat/markdown-content";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  EMPTY_STATE,
  dropDemoPrice,
  fetchAgentState,
  isDemoAvailable,
  newThreadId,
  resetDemo,
  runAgent,
  type AgentMode,
  type AgentRun,
  type AgentState,
} from "@/lib/api/agent";
import { formatCLP } from "@/lib/utils";
import { useSession } from "@/lib/supabase/use-session";
import { cn } from "@/lib/utils";

type Message = { id: string; role: "user" | "assistant" | "notice"; text: string; run?: AgentRun };

// Modo demo: catálogo de ejemplo (notebooks, un celular Samsung y uno Huawei).
const DEMO_STORIES = [
  { title: "Compra con lista", prompt: "Quiero un notebook Lenovo para la universidad, presupuesto $400.000. Arma una lista de compra." },
  { title: "Sin resultados → cambia de plan", prompt: "Quiero un notebook gamer, presupuesto $300.000. Avísame cuando baje." },
  { title: "El historial dice «esperar»", prompt: "Necesito el notebook ASUS TUF, presupuesto $900.000. Guarda la lista si conviene." },
  { title: "Memoria entre conversaciones", prompt: "Prefiero Samsung y no quiero Huawei. Busco un celular, presupuesto $400.000." },
  { title: "Revisar alertas", prompt: "Revisa mis alertas de precio." },
] as const;

// Modo real: pensadas para el catálogo ingestado (celulares, notebooks, tarjetas de video, procesadores y placas madre).
const REAL_STORIES = [
  { title: "Compra con lista", prompt: "Quiero un celular Samsung o Xiaomi, presupuesto $320.000. Arma una lista de compra." },
  { title: "Sobre el presupuesto → alerta", prompt: "Quiero el notebook HP Victus 15 con RTX 2050, mi presupuesto es $1.000.000. Avísame cuando baje a ese precio." },
  { title: "Dónde comprar más barato", prompt: "Compara el Xiaomi Redmi Note 15 Pro entre las tiendas y dime dónde conviene comprarlo." },
  { title: "Memoria entre conversaciones", prompt: "Prefiero Samsung y no quiero Xiaomi. Busco un celular, presupuesto $350.000." },
  { title: "Revisar alertas", prompt: "Revisa mis alertas de precio." },
] as const;

export function AgentScreen() {
  const { session, isLoading: isLoadingSession } = useSession();
  const [demoAvailable, setDemoAvailable] = useState<boolean | null>(null);
  const [mode, setMode] = useState<AgentMode>("demo");
  const [messages, setMessages] = useState<Message[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [state, setState] = useState<AgentState>(EMPTY_STATE);
  const [threadId, setThreadId] = useState(() => newThreadId());
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [mobileView, setMobileView] = useState<"chat" | "detalle">("chat");
  const scrollRef = useRef<HTMLDivElement>(null);

  const accessToken = session?.access_token;
  const selectedRun = messages.find((message) => message.id === selectedRunId)?.run ?? null;

  useEffect(() => {
    let cancelled = false;
    void isDemoAvailable().then((enabled) => {
      if (cancelled) return;
      setDemoAvailable(enabled);
      if (!enabled) setMode("real");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshState = useCallback(
    async (currentMode: AgentMode) => {
      if (currentMode === "real" && !accessToken) {
        setState(EMPTY_STATE);
        return;
      }
      try {
        setState(await fetchAgentState(currentMode, accessToken));
      } catch {
        setState(EMPTY_STATE);
      }
    },
    [accessToken]
  );

  useEffect(() => {
    if (demoAvailable === null || isLoadingSession) return;
    let cancelled = false;
    void (async () => {
      const next = mode === "real" && !accessToken ? EMPTY_STATE : await fetchAgentState(mode, accessToken).catch(() => EMPTY_STATE);
      if (!cancelled) setState(next);
    })();
    return () => {
      cancelled = true;
    };
  }, [mode, demoAvailable, isLoadingSession, accessToken]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isLoading]);

  function changeMode(next: AgentMode) {
    if (next === mode) return;
    setMode(next);
    setMessages([]);
    setSelectedRunId(null);
    setError("");
    setThreadId(newThreadId());
  }

  function newConversation() {
    setMessages([]);
    setSelectedRunId(null);
    setError("");
    setThreadId(newThreadId());
  }

  async function submit(text = draft) {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;
    if (mode === "real" && !accessToken) {
      setError("Inicia sesión para usar el agente con Gemini real.");
      return;
    }
    setDraft("");
    setError("");
    setIsLoading(true);
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", text: trimmed }]);
    try {
      const run = await runAgent(mode, trimmed, threadId, accessToken);
      const id = crypto.randomUUID();
      setMessages((current) => [...current, { id, role: "assistant", text: run.answer, run }]);
      setSelectedRunId(id);
      await refreshState(mode);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible consultar al agente.");
    } finally {
      setIsLoading(false);
    }
  }

  async function simulatePriceDrop() {
    setError("");
    try {
      const drop = await dropDemoPrice();
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: "notice", text: `Pasaron los días: ${drop.product} bajó de ${formatCLP(drop.before_clp)} a ${formatCLP(drop.after_clp)}. Pídele «Revisa mis alertas de precio».` },
      ]);
      await refreshState("demo");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible simular la baja de precio.");
    }
  }

  async function resetDemoData() {
    setError("");
    try {
      await resetDemo();
      newConversation();
      await refreshState("demo");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible reiniciar la demo.");
    }
  }

  const hasConversation = messages.length > 0;

  return (
    <div className="grid min-h-0 min-w-0 flex-1 grid-rows-[auto_minmax(0,1fr)] lg:grid-cols-[minmax(0,1fr)_26rem] lg:grid-rows-[minmax(0,1fr)] lg:gap-4 lg:p-4 xl:grid-cols-[minmax(0,1fr)_30rem]">
      <div className="flex shrink-0 gap-1 border-b bg-background px-4 py-2 lg:hidden" role="tablist" aria-label="Vista">
        {(["chat", "detalle"] as const).map((view) => (
          <button
            key={view}
            role="tab"
            aria-selected={mobileView === view}
            onClick={() => setMobileView(view)}
            className={cn("flex-1 rounded-lg px-3 py-1.5 text-sm font-medium", mobileView === view ? "bg-primary text-primary-foreground" : "text-muted-foreground")}
          >
            {view === "chat" ? "Conversación" : "Razonamiento y guardado"}
          </button>
        ))}
      </div>

      <section className={cn("min-h-0 min-w-0 flex-col overflow-hidden bg-card lg:flex lg:rounded-2xl lg:border", mobileView === "chat" ? "flex" : "hidden")}>
        <header className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b bg-background/80 px-4 py-3 backdrop-blur sm:px-6">
          <div className="flex size-9 items-center justify-center rounded-xl bg-primary/10 text-primary" aria-hidden="true">
            <Bot className="size-4" />
          </div>
          <div className="min-w-0">
            <h1 className="text-base font-semibold tracking-tight">Agente de ahorro</h1>
            <p className="truncate text-xs text-muted-foreground">Busca, razona sobre precios y deja alertas y listas guardadas</p>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border p-0.5 text-xs font-medium" role="group" aria-label="Modo">
              <button
                type="button"
                disabled={demoAvailable === false}
                onClick={() => changeMode("demo")}
                aria-pressed={mode === "demo"}
                className={cn("rounded-md px-2.5 py-1 disabled:opacity-40", mode === "demo" ? "bg-primary text-primary-foreground" : "text-muted-foreground")}
              >
                Demo
              </button>
              <button
                type="button"
                onClick={() => changeMode("real")}
                aria-pressed={mode === "real"}
                className={cn("rounded-md px-2.5 py-1", mode === "real" ? "bg-primary text-primary-foreground" : "text-muted-foreground")}
              >
                Gemini real
              </button>
            </div>
            <Button type="button" variant="ghost" size="sm" onClick={newConversation} className="gap-1.5">
              <MessageSquarePlus className="size-4" aria-hidden="true" />
              <span className="hidden sm:inline">Nueva conversación</span>
            </Button>
          </div>
        </header>

        {mode === "demo" ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2 border-b bg-muted/40 px-4 py-2 text-xs text-muted-foreground sm:px-6">
            <span className="min-w-full flex-1 sm:min-w-0">Modo demo: catálogo de ejemplo y modelo guionado. Sin login, sin red y sin gastar cuota.</span>
            <Button type="button" variant="outline" size="sm" onClick={() => void simulatePriceDrop()} className="gap-1.5">
              <TrendingDown className="size-3.5" aria-hidden="true" />
              Simular baja de precio
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => void resetDemoData()} className="gap-1.5">
              <RotateCcw className="size-3.5" aria-hidden="true" />
              Reiniciar demo
            </Button>
          </div>
        ) : !isLoadingSession && !session ? (
          <div className="shrink-0 border-b bg-amber-500/10 px-4 py-2 text-xs sm:px-6">
            Para usar el agente con Gemini real necesitas{" "}
            <Link href="/login?next=/agente" className="font-semibold text-primary underline underline-offset-2">
              iniciar sesión
            </Link>
            .
          </div>
        ) : null}

        <div ref={scrollRef} role="log" aria-live="polite" aria-label="Conversación con el agente" className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain">
          <div className={cn("mx-auto flex min-h-full w-full max-w-3xl flex-col px-4 py-6 sm:px-6", hasConversation ? "space-y-4" : "justify-center")}>
            {!hasConversation ? (
              <div className="mx-auto w-full max-w-2xl text-center">
                <h2 className="text-lg font-semibold tracking-tight">¿Qué quieres comprar y cuánto puedes gastar?</h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  El agente planifica, consulta el catálogo, juzga si el precio está inflado y puede dejar una alerta o una lista guardada. Prueba una de estas historias:
                </p>
                <div className="mt-5 grid gap-2 text-left sm:grid-cols-2">
                  {(mode === "demo" ? DEMO_STORIES : REAL_STORIES).map((story, index) => (
                    <button
                      key={story.title}
                      type="button"
                      onClick={() => void submit(story.prompt)}
                      className="rounded-2xl border bg-card px-4 py-3 text-sm shadow-sm transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
                    >
                      <span className="text-xs font-semibold text-primary">Historia {index + 1}</span>
                      <span className="block font-medium">{story.title}</span>
                      <span className="mt-1 block text-xs leading-5 text-muted-foreground">{story.prompt}</span>
                    </button>
                  ))}
                </div>
                {mode === "real" ? (
                  <p className="mt-3 text-xs leading-5 text-muted-foreground">
                    Con tu catálogo real: si un producto tiene menos de 3 observaciones de precio, el agente te dirá que no alcanza para juzgar su tendencia. Lo que guarde (alertas, listas, memoria) queda en tu cuenta.
                  </p>
                ) : null}
              </div>
            ) : null}

            {messages.map((message) =>
              message.role === "user" ? (
                <article key={message.id} className="animate-message-in flex justify-end">
                  <div className="max-w-[92%] [overflow-wrap:anywhere] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-6 text-primary-foreground shadow-sm sm:max-w-[78%]">
                    <p className="whitespace-pre-wrap">{message.text}</p>
                  </div>
                </article>
              ) : message.role === "notice" ? (
                <p key={message.id} className="animate-message-in rounded-xl border border-dashed bg-muted/40 px-4 py-2 text-center text-xs text-muted-foreground">
                  {message.text}
                </p>
              ) : (
                <article key={message.id} className="animate-message-in flex items-start gap-2.5">
                  <div className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary" aria-hidden="true">
                    <Bot className="size-4" />
                  </div>
                  <div
                    className={cn("min-w-0 flex-1 [overflow-wrap:anywhere] rounded-2xl rounded-bl-md bg-muted px-4 py-3", selectedRunId === message.id && "ring-2 ring-primary/40")}
                  >
                    <MarkdownContent markdown={message.text} />
                    {message.run ? (
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedRunId(message.id);
                          setMobileView("detalle");
                        }}
                        className="mt-2 text-xs font-medium text-primary underline underline-offset-2"
                      >
                        Ver cómo lo pensó ({message.run.steps} pasos{message.run.replans ? `, ${message.run.replans} replan${message.run.replans > 1 ? "es" : ""}` : ""})
                      </button>
                    ) : null}
                  </div>
                </article>
              )
            )}

            {isLoading ? <TypingIndicator label="Planificando y consultando el catálogo…" /> : null}

            {error ? (
              <div className="animate-message-in rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-2.5 text-sm text-destructive" role="alert">
                {error}
              </div>
            ) : null}
          </div>
        </div>

        <div className="shrink-0 border-t bg-background/60">
          <div className="mx-auto w-full max-w-3xl px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 sm:px-6">
            <ChatComposer draft={draft} isLoading={isLoading} onChange={setDraft} onSend={() => void submit()} />
          </div>
        </div>
      </section>

      <aside className={cn("min-h-0 min-w-0 flex-col overflow-hidden bg-card lg:flex lg:rounded-2xl lg:border", mobileView === "detalle" ? "flex" : "hidden")}>
        <Tabs defaultValue="razonamiento" className="flex min-h-0 flex-1 flex-col">
          <TabsList className="m-3 shrink-0">
            <TabsTrigger value="razonamiento">Cómo pensó</TabsTrigger>
            <TabsTrigger value="guardado">Guardado</TabsTrigger>
          </TabsList>
          <TabsContent value="razonamiento" className="min-h-0 flex-1 overflow-y-auto">
            <AgentReasoning run={selectedRun} />
          </TabsContent>
          <TabsContent value="guardado" className="min-h-0 flex-1 overflow-y-auto">
            <AgentSaved state={state} />
          </TabsContent>
        </Tabs>
      </aside>
    </div>
  );
}
