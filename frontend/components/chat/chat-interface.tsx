"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Info, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import { MarkdownContent } from "@/components/chat/markdown-content";
import { ProductRecommendations } from "@/components/chat/product-recommendations";
import { SuggestionChips } from "@/components/chat/suggestion-chips";
import { ChatComposer } from "@/components/chat/chat-composer";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import { EvidencePanel } from "@/components/chat/evidence-panel";
import {
  buildProductContext,
  isProbablyCatalogQuery,
  sendCatalogAwareMessage,
  type CatalogReference,
} from "@/lib/api/ai";
import type { EvidenceEntry, RecommendationDetail, ResearchSource } from "@/lib/api/chat";
import type { ChatTurn } from "@/lib/api/chat";
import type { ProductRead } from "@/types/product";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  toolsUsed?: string[];
  references?: CatalogReference[];
  products?: ProductRead[];
  sources?: ResearchSource[];
  evidence?: EvidenceEntry[];
  recommendation?: RecommendationDetail | null;
};

type ChatInterfaceProps = {
  accessToken: string;
  productId?: number | null;
  productName?: string | null;
};

function toChatTurns(messages: ChatMessage[]): ChatTurn[] {
  return messages.map((message) => ({
    role: message.role,
    content: message.text,
    products: message.products ?? null,
  }));
}

export function ChatInterface({ accessToken, productId, productName }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingContext, setIsLoadingContext] = useState(() => Boolean(productId));
  const [error, setError] = useState("");
  const [thinkingLabel, setThinkingLabel] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!productId) return;
    let cancelled = false;
    void (async () => {
      try {
        const context = await buildProductContext(productId);
        if (cancelled) return;
        setMessages([
          {
            id: "product-context",
            role: "assistant",
            text: context.intro,
            references: context.references,
            products: context.products,
          },
        ]);
      } catch {
        if (cancelled) return;
        setMessages([
          {
            id: "product-context",
            role: "assistant",
            text: `Podés preguntarme por el precio, las ofertas o el historial de "${productName ?? `#${productId}`}".`,
          },
        ]);
      } finally {
        if (!cancelled) setIsLoadingContext(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [productId, productName]);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
  }, [messages, isLoading, isLoadingContext]);

  async function submit(message = draft) {
    const trimmed = message.trim();
    if (!trimmed || isLoading) return;
    const isCatalog = isProbablyCatalogQuery(trimmed, productId);

    setDraft("");
    setError("");
    setThinkingLabel(isCatalog ? "Buscando en el catálogo…" : "Consultando al asistente…");
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", text: trimmed }]);
    setIsLoading(true);

    try {
      const result = await sendCatalogAwareMessage(trimmed, accessToken, productId, toChatTurns(messages));
      const backendProducts = Array.isArray(result.products) ? result.products : [];
      const catalogProducts = result.catalog.products ?? [];
      const renderedProducts = backendProducts.length > 0 ? backendProducts : catalogProducts;
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: result.answer,
          toolsUsed: result.tools_used.length > 0 ? result.tools_used : undefined,
          references: result.catalog.references.length > 0 ? result.catalog.references : undefined,
          products: renderedProducts.length > 0 ? (renderedProducts as ProductRead[]) : undefined,
          sources: result.sources && result.sources.length > 0 ? result.sources : undefined,
          evidence: result.evidence && result.evidence.length > 0 ? result.evidence : undefined,
          recommendation: result.recommendation ?? undefined,
        },
      ]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible enviar el mensaje.");
    } finally {
      setIsLoading(false);
      setThinkingLabel("");
    }
  }

  const lastAssistant = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.role === "assistant") return message;
    }
    return undefined;
  }, [messages]);

  const recommendations = useMemo(
    () => lastAssistant?.products ?? [],
    [lastAssistant]
  );

  const hasConversation = messages.length > 0;
  const contextLoading = isLoadingContext && !hasConversation;

  return (
    <div className="grid min-h-0 min-w-0 flex-1 grid-rows-[minmax(0,1fr)_auto] lg:grid-cols-[minmax(0,1fr)_28rem] lg:grid-rows-[minmax(0,1fr)] lg:gap-4 lg:p-4 xl:grid-cols-[minmax(0,1fr)_32rem]">
      <section className="flex min-h-0 min-w-0 flex-col overflow-hidden bg-card lg:rounded-2xl lg:border">
        <header className="flex shrink-0 items-center gap-3 border-b bg-background/80 px-4 pb-3 pt-[max(1rem,env(safe-area-inset-top))] backdrop-blur sm:px-6 sm:pb-4">
          <div className="flex size-9 items-center justify-center rounded-xl bg-primary/10 text-primary" aria-hidden="true">
            <Sparkles className="size-4" />
          </div>
          <div className="min-w-0">
            <h1 className="text-base font-semibold tracking-tight text-foreground">SoloTodo AI</h1>
            <p className="truncate text-xs text-muted-foreground">
              Tu asistente para encontrar y comparar productos
            </p>
          </div>
          {productName ? (
            <span className="ml-auto hidden max-w-48 truncate rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground sm:inline-block">
              {productName}
            </span>
          ) : null}
        </header>

        <div
          ref={scrollRef}
          role="log"
          aria-live="polite"
          aria-label="Conversación con el asistente"
          className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain"
        >
          <div
            className={cn(
              "mx-auto flex min-h-full w-full max-w-6xl flex-col px-4 py-8 sm:px-6",
              hasConversation ? "space-y-5" : "justify-center"
            )}
          >
            {!hasConversation && (
              <div className="mx-auto w-full max-w-2xl px-2 text-center">
                <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary" aria-hidden="true">
                  <Sparkles className="size-5" />
                </div>
                <h2 className="mt-4 text-lg font-semibold tracking-tight text-foreground">
                  ¿Qué estás buscando hoy?
                </h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  Buscá productos, compará precios o preguntá por el historial de una oferta. Estas
                  sugerencias te muestran por dónde empezar.
                </p>
                <div className="mt-6">
                  <SuggestionChips onPick={(text) => void submit(text)} />
                </div>
              </div>
            )}

            {messages.map((message) =>
              message.role === "user" ? (
                <article
                  key={message.id}
                  className="animate-message-in flex justify-end"
                >
                  <div className="max-w-[92%] [overflow-wrap:anywhere] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-6 text-primary-foreground shadow-sm sm:max-w-[78%]">
                    <p className="whitespace-pre-wrap">{message.text}</p>
                  </div>
                </article>
              ) : (
                <article key={message.id} className="animate-message-in flex items-start gap-2.5">
                  <div
                    className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"
                    aria-hidden="true"
                  >
                    <Sparkles className="size-4" />
                  </div>
                  <div className="min-w-0 flex-1 [overflow-wrap:anywhere] rounded-2xl rounded-bl-md bg-muted px-4 py-3">
                    <MarkdownContent markdown={message.text} />
                    {message.toolsUsed && message.toolsUsed.length > 0 ? (
                      <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-border/70 pt-2.5">
                        {message.toolsUsed.map((tool) => (
                          <span key={tool} className="rounded-full bg-background px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                            {tool}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {message.sources && message.sources.length > 0 ? (
                      <div className="mt-2.5 border-t border-border/70 pt-2.5">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                          Fuentes consultadas
                        </p>
                        <ul className="mt-1.5 space-y-1.5">
                          {message.sources.map((source) => (
                            <li key={`${source.source_name}-${source.source_url ?? source.title}`}>
                              {source.source_url ? (
                                <a
                                  href={source.source_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-xs leading-5 text-primary hover:underline"
                                >
                                  {source.source_name}
                                  {source.title ? (
                                    <span className="text-muted-foreground"> — {source.title}</span>
                                  ) : null}
                                </a>
                              ) : (
                                <span className="text-xs leading-5 text-muted-foreground">
                                  {source.source_name}
                                  {source.title ? ` — ${source.title}` : ""}
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    <EvidencePanel
                      evidence={message.evidence}
                      recommendation={message.recommendation}
                    />
                  </div>
                </article>
              )
            )}

            {isLoading ? <TypingIndicator label={thinkingLabel} /> : null}

            {contextLoading ? (
              <div className="animate-message-in flex items-center gap-2 text-sm text-muted-foreground">
                <Info className="size-4 text-primary/70" aria-hidden="true" />
                Cargando el contexto real del producto desde el catálogo…
              </div>
            ) : null}

            {error ? (
              <div className="animate-message-in rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-2.5 text-sm text-destructive" role="alert">
                {error}
              </div>
            ) : null}
          </div>
        </div>

        <div className="shrink-0 border-t bg-background/60">
          <div className="mx-auto w-full max-w-6xl px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 sm:px-6">
            <ChatComposer
              draft={draft}
              isLoading={isLoading}
              onChange={setDraft}
              onSend={() => void submit()}
            />
          </div>
        </div>
      </section>

      <ProductRecommendations products={recommendations} messageId={lastAssistant?.id} />
    </div>
  );
}
