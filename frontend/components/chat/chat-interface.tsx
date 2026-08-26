"use client";

import { FormEvent, KeyboardEvent, useState } from "react";

import { sendChatMessage } from "@/lib/api/chat";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  toolsUsed?: string[];
};

type ChatInterfaceProps = {
  accessToken: string;
};

export function ChatInterface({ accessToken }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    const message = draft.trim();
    if (!message || isLoading) return;

    setDraft("");
    setError("");
    setMessages((current) => [...current, { id: crypto.randomUUID(), role: "user", text: message }]);
    setIsLoading(true);
    try {
      const result = await sendChatMessage(message, accessToken);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", text: result.answer, toolsUsed: result.tools_used }]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No fue posible enviar el mensaje.");
    } finally {
      setIsLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  }

  return (
    <section className="flex min-h-[580px] flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-5 py-4 sm:px-7">
        <h1 className="text-lg font-semibold text-slate-950">Asistente de compras</h1>
        <p className="mt-1 text-sm text-slate-500">Consulta productos y precios disponibles en SoloTodo.</p>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto px-5 py-6 sm:px-7" aria-live="polite">
        {messages.length === 0 && (
          <div className="mx-auto mt-16 max-w-sm text-center">
            <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-indigo-100 text-xl" aria-hidden="true">✦</div>
            <h2 className="mt-4 text-lg font-semibold text-slate-900">¿Qué estás buscando?</h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">Describe el producto, categoría o presupuesto que te interesa.</p>
          </div>
        )}
        {messages.map((message) => (
          <article key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-6 sm:max-w-[75%] ${message.role === "user" ? "rounded-br-md bg-slate-950 text-white" : "rounded-bl-md bg-slate-100 text-slate-800"}`}>
              <p className="whitespace-pre-wrap">{message.text}</p>
              {message.toolsUsed && message.toolsUsed.length > 0 && <p className="mt-2 border-t border-slate-200 pt-2 text-xs text-slate-500">Consultó: {message.toolsUsed.join(", ")}</p>}
            </div>
          </article>
        ))}
        {isLoading && <div className="flex items-center gap-2 text-sm text-slate-500"><span className="size-2 animate-pulse rounded-full bg-indigo-500" /><span>Gemini está consultando SoloTodo…</span></div>}
      </div>

      <form className="border-t border-slate-100 p-4 sm:p-5" onSubmit={handleSubmit}>
        {error && <p className="mb-3 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">{error}</p>}
        <div className="flex items-end gap-3 rounded-2xl border border-slate-300 bg-white p-2 transition focus-within:border-indigo-500 focus-within:ring-4 focus-within:ring-indigo-100">
          <textarea className="min-h-11 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-slate-400" rows={1} placeholder="Ej. notebook para programación por menos de $800.000" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleKeyDown} disabled={isLoading} aria-label="Mensaje para el asistente" />
          <button className="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50" type="submit" disabled={!draft.trim() || isLoading}>Enviar</button>
        </div>
        <p className="mt-2 px-2 text-xs text-slate-400">Enter para enviar · Shift + Enter para una nueva línea</p>
      </form>
    </section>
  );
}
