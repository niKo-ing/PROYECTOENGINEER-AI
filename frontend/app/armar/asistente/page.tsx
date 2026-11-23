"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { BookOpen, Bot, LoaderCircle, Save, Scale, Send, ShieldCheck, Wrench } from "lucide-react";

import { LoginNeeded, PartsList, ReportPanel, SavePcDialog } from "@/components/pc/pc-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  askAssistant,
  itemsFromParts,
  saveDraft,
  type AssistantNeeds,
  type AssistantOption,
  type AssistantReply,
  type AssistantTurn,
  type Recommendation,
} from "@/lib/api/pc";
import { useSession } from "@/lib/auth/use-session";
import { cn, formatCLP } from "@/lib/utils";

type Message = AssistantTurn & { reply?: AssistantReply };

const STARTERS = [
  "Quiero un PC para jugar en 1080p, tengo 800 mil",
  "Necesito un equipo para editar video en DaVinci",
  "Un PC chico para estudiar y ver series, unos 400 mil",
  "Tengo 1,5 millones y quiero jugar en 1440p con AMD",
];
const HISTORY_SENT = 12;

export default function AssistantPage() {
  const { session, isLoading } = useSession();
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [needs, setNeeds] = useState<AssistantNeeds>({});
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState<Recommendation | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  async function send(text: string, extraNeeds: AssistantNeeds = {}) {
    const content = text.trim();
    if (!content || busy || !session) return;
    const history: Message[] = [...messages, { role: "user", content }];
    const known = { ...needs, ...extraNeeds };
    setMessages(history);
    setInput("");
    setBusy(true);
    setError("");
    try {
      const turns = history.slice(-HISTORY_SENT).map(({ role, content: c }) => ({ role, content: c }));
      const reply = await askAssistant(turns, known, session.access_token);
      setNeeds(reply.needs ?? known);
      setMessages([...history, { role: "assistant", content: reply.answer, reply }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pude responder. Inténtalo de nuevo.");
      setNeeds(known);
    } finally {
      setBusy(false);
    }
  }

  function pick(option: AssistantOption) {
    void send(option.label, { [option.field]: option.value } as AssistantNeeds);
  }

  function openInBuilder(rec: Recommendation) {
    saveDraft(itemsFromParts(rec.items), { use_case: rec.needs.use_case, budget_clp: rec.needs.budget_clp });
    router.push("/armar");
  }

  if (isLoading) return <div className="mx-auto max-w-3xl px-4 py-16 text-center text-muted-foreground">Cargando…</div>;
  if (!session) {
    return (
      <div className="px-4 py-16">
        <LoginNeeded what="usar el asistente de armado" />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col px-4 py-8 sm:px-6">
      <header className="mb-6">
        <div className="flex items-center gap-2 text-sm text-primary">
          <Bot className="size-4" aria-hidden="true" />
          Asistente de armado con IA
        </div>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Cuéntame para qué lo quieres</h1>
        <p className="mt-1 text-muted-foreground">Te pregunto lo que falte, armo un PC compatible dentro de tu presupuesto y te explico por qué.</p>
      </header>

      <div className="flex-1 space-y-4" aria-live="polite">
        {messages.length === 0 ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {STARTERS.map((starter) => (
              <button key={starter} type="button" onClick={() => void send(starter)} className="rounded-xl border p-3 text-left text-sm transition-colors hover:bg-muted/60">
                {starter}
              </button>
            ))}
          </div>
        ) : null}

        {messages.map((message, index) => (
          <div key={index} className={cn("flex", message.role === "user" ? "justify-end" : "justify-start")}>
            {message.role === "user" ? (
              <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">{message.content}</p>
            ) : (
              <div className="w-full space-y-3">
                <div className="flex gap-3">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                    <Bot className="size-4" aria-hidden="true" />
                  </span>
                  <div className="min-w-0 flex-1 space-y-2">
                    <p className="whitespace-pre-line text-sm leading-relaxed">{message.content}</p>
                    {message.reply ? <ReplyMeta reply={message.reply} /> : null}
                  </div>
                </div>
                {message.reply?.state === "question" && index === messages.length - 1 && message.reply.options.length > 0 ? (
                  <div className="flex flex-wrap gap-2 pl-11">
                    {message.reply.options.map((option) => (
                      <Button key={`${option.field}-${option.value}`} variant="outline" size="sm" onClick={() => pick(option)} disabled={busy}>
                        {option.label}
                      </Button>
                    ))}
                  </div>
                ) : null}
                {message.reply?.recommendation ? (
                  <BuildCard
                    rec={message.reply.recommendation}
                    reply={message.reply}
                    onSave={() => setSaving(message.reply!.recommendation!)}
                    onOpen={() => openInBuilder(message.reply!.recommendation!)}
                    onBudget={(amount) => void send(`Muéstrame la opción de ${formatCLP(amount)}`, { budget_clp: amount })}
                  />
                ) : null}
              </div>
            )}
          </div>
        ))}

        {busy ? (
          <div className="flex items-center gap-3 pl-1 text-sm text-muted-foreground">
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            Pensando y revisando compatibilidades…
          </div>
        ) : null}
        {error ? (
          <p className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void send(input);
        }}
        className="sticky bottom-0 mt-6 flex items-end gap-2 border-t bg-background/95 py-3 backdrop-blur"
      >
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send(input);
            }
          }}
          rows={1}
          maxLength={1500}
          placeholder="Ej.: Valorant y estudiar, con 700 mil"
          aria-label="Escribe tu mensaje"
          className="max-h-40 min-h-11 flex-1 resize-none rounded-xl border bg-background px-3 py-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <Button type="submit" size="icon" className="size-11 shrink-0" disabled={busy || !input.trim()} aria-label="Enviar">
          <Send className="size-4" aria-hidden="true" />
        </Button>
      </form>
      <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
        <ShieldCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        Respuestas generadas con IA (Gemini). La compatibilidad la revisa un motor de reglas y los precios son referenciales. No escribas datos personales.
      </p>

      {saving ? (
        <SavePcDialog
          open
          onOpenChange={(open) => !open && setSaving(null)}
          token={session.access_token}
          items={itemsFromParts(saving.items)}
          source="asistente"
          defaults={{ name: `PC para ${saving.use_case_label.toLowerCase()}`, kind: "proyecto", use_case: saving.needs.use_case, budget_clp: saving.needs.budget_clp }}
          onSaved={(pc) => router.push(`/mis-pc/${pc.id}`)}
        />
      ) : null}
    </div>
  );
}

function ReplyMeta({ reply }: { reply: AssistantReply }) {
  if (reply.state === "blocked") return <Badge variant="warning">Pedido bloqueado por seguridad</Badge>;
  return (
    <>
      {reply.overrides?.map((override) => (
        <p key={override.field} className="flex items-start gap-2 rounded-lg border border-dashed px-3 py-2 text-xs text-muted-foreground">
          <Scale className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>
            <span className="font-medium text-foreground">Regla automática corregida por la IA.</span> {override.message}
          </span>
        </p>
      ))}
      <div className="flex flex-wrap items-center gap-2">
        {reply.state === "build" ? (
          <Badge variant={reply.explained_by === "llm" ? "secondary" : "outline"}>{reply.explained_by === "llm" ? "Explicado por IA" : "Explicación automática"}</Badge>
        ) : null}
        {reply.guides?.map((guide) => (
          <Link key={guide.guide} href={guide.url} className="inline-flex items-center gap-1 text-xs text-primary underline-offset-4 hover:underline">
            <BookOpen className="size-3" aria-hidden="true" />
            {guide.title}
          </Link>
        ))}
      </div>
    </>
  );
}

function BuildCard({ rec, reply, onSave, onOpen, onBudget }: { rec: Recommendation; reply: AssistantReply; onSave: () => void; onOpen: () => void; onBudget: (amount: number) => void }) {
  const cheaper = rec.alternatives.mas_barato;
  const better = rec.alternatives.mejor;
  return (
    <div className="ml-11 space-y-4 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">{rec.use_case_label}</h2>
        <p className="text-sm">
          <span className="text-lg font-bold tabular-nums">{formatCLP(rec.total_clp)}</span>
          <span className="text-muted-foreground"> de {formatCLP(rec.needs.budget_clp)}</span>
        </p>
      </div>
      <PartsList parts={rec.items} />
      <ReportPanel report={rec.report} compact />
      <div className="flex flex-wrap gap-2">
        <Button onClick={onSave} className="gap-2">
          <Save className="size-4" aria-hidden="true" />
          Guardar en Mis computadores
        </Button>
        <Button variant="outline" onClick={onOpen} className="gap-2">
          <Wrench className="size-4" aria-hidden="true" />
          Ajustar en el armador
        </Button>
      </div>
      {cheaper || better ? (
        <div className="flex flex-wrap gap-2 border-t pt-3 text-sm">
          <span className="text-muted-foreground">Otras opciones:</span>
          {cheaper ? (
            <button type="button" onClick={() => onBudget(cheaper.budget_clp)} className="text-primary underline-offset-4 hover:underline">
              Más barata ({cheaper.gpu ?? cheaper.cpu}, {formatCLP(cheaper.total_clp)})
            </button>
          ) : null}
          {better ? (
            <button type="button" onClick={() => onBudget(better.budget_clp)} className="text-primary underline-offset-4 hover:underline">
              Mejor ({better.gpu ?? better.cpu}, {formatCLP(better.total_clp)})
            </button>
          ) : null}
        </div>
      ) : null}
      {reply.source === "reglas" ? <p className="text-xs text-muted-foreground">La IA no estaba disponible: entendí tu pedido con reglas.</p> : null}
    </div>
  );
}
