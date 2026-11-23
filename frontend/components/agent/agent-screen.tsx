"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, MessageSquarePlus } from "lucide-react";

import { AgentReasoning } from "@/components/agent/agent-reasoning";
import { AgentProducts } from "@/components/agent/agent-products";
import { AgentSaved } from "@/components/agent/agent-saved";
import { ChatComposer } from "@/components/chat/chat-composer";
import { MarkdownContent } from "@/components/chat/markdown-content";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EMPTY_STATE, fetchAgentState, newThreadId, runAgent, type AgentRun, type AgentState } from "@/lib/api/agent";
import { newId } from "@/lib/utils";
import { useSession } from "@/lib/auth/use-session";
import { cn } from "@/lib/utils";

type Message = { id: string; role: "user" | "assistant"; text: string; run?: AgentRun };

// Ideas para empezar, pensadas para el catálogo ingestado (celulares, notebooks, tarjetas de video, procesadores y placas madre).
const SUGGESTIONS = [
  { title: "Compra con lista", prompt: "Quiero un celular Samsung o Xiaomi, presupuesto $320.000. Arma una lista de compra." },
  { title: "Sobre el presupuesto → alerta", prompt: "Quiero el notebook HP Victus 15 con RTX 2050, mi presupuesto es $1.000.000. Avísame cuando baje a ese precio." },
  { title: "Dónde comprar más barato", prompt: "Compara el Xiaomi Redmi Note 15 Pro entre las tiendas y dime dónde conviene comprarlo." },
  { title: "Memoria entre conversaciones", prompt: "Prefiero Samsung y no quiero Xiaomi. Busco un celular, presupuesto $350.000." },
  { title: "Revisar alertas", prompt: "Revisa mis alertas de precio." },
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
          <div className="min-w-0 flex-1">
            <h1 className="text-base font-semibold tracking-tight">Asistente de ahorro</h1>
            <p className="hidden truncate text-xs text-muted-foreground sm:block">Conversa, compara, razona sobre precios y deja alertas y listas guardadas</p>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={newConversation} className="gap-1.5">
              <MessageSquarePlus className="size-4" aria-hidden="true" />
              <span className="hidden sm:inline">Nueva conversación</span>
            </Button>
          </div>
        </header>

        {!isLoadingSession && !session ? (
          <div className="shrink-0 border-b bg-amber-500/10 px-4 py-2 text-xs sm:px-6">
            Para usar el asistente necesitas{" "}
            <Link href="/login" className="font-semibold text-primary underline underline-offset-2">
              iniciar sesión
            </Link>
            .
          </div>
        ) : null}

        <div ref={scrollRef} role="log" aria-live="polite" aria-label="Conversación con el asistente" className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain">
          <div className={cn("mx-auto flex min-h-full w-full max-w-3xl flex-col px-4 py-6 sm:px-6", hasConversation ? "space-y-4" : "justify-center")}>
            {!hasConversation ? (
              <div className="mx-auto w-full max-w-2xl text-center">
                <h2 className="text-lg font-semibold tracking-tight">
                  {productName ? `¿Qué quieres saber de «${productName}»?` : "¿Qué quieres comprar y cuánto puedes gastar?"}
                </h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  El asistente planifica, consulta el catálogo, juzga si el precio está inflado y puede dejar una alerta o una lista guardada. Puede empezar con una de estas sugerencias:
                </p>
                <div className="mt-5 grid gap-2 text-left sm:grid-cols-2">
                  {SUGGESTIONS.map((story, index) => (
                    <button
                      key={story.title}
                      type="button"
                      onClick={() => void submit(story.prompt)}
                      style={{ animationDelay: `${index * 70}ms` }}
                      className="rounded-2xl border bg-card px-4 py-3 text-sm shadow-sm transition duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md active:translate-y-0 active:scale-[0.99] motion-safe:animate-card-in"
                    >
                      <span className="text-xs font-semibold text-primary">Sugerencia {index + 1}</span>
                      <span className="block font-medium">{story.title}</span>
                      <span className="mt-1 block text-xs leading-5 text-muted-foreground">{story.prompt}</span>
                    </button>
                  ))}
                </div>
                  <p className="mt-3 text-xs leading-5 text-muted-foreground">
                    Con tu catálogo real: si un producto tiene menos de 3 observaciones de precio, el agente te dirá que no alcanza para juzgar su tendencia. Lo que guarde (alertas, listas, memoria) queda en tu cuenta.
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
                    className={cn("min-w-0 flex-1 [overflow-wrap:anywhere] rounded-2xl rounded-bl-md bg-muted px-4 py-3", selectedRunId === message.id && "ring-2 ring-primary/40")}
                  >
                    <MarkdownContent markdown={message.text} />
                    {message.run?.products?.length ? <AgentProducts products={message.run.products} /> : null}
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
              <div className="motion-safe:animate-message-in rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-2.5 text-sm text-destructive" role="alert">
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
          <TabsContent value="razonamiento" className="min-h-0 flex-1 overflow-y-auto motion-safe:animate-fade-in">
            <AgentReasoning run={selectedRun} loading={isLoading} />
          </TabsContent>
          <TabsContent value="guardado" className="min-h-0 flex-1 overflow-y-auto motion-safe:animate-fade-in">
            <AgentSaved state={state} />
          </TabsContent>
        </Tabs>
      </aside>
    </div>
  );
}
