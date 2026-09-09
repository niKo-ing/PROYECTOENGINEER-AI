"use client";

import { KeyboardEvent } from "react";
import { ArrowUp } from "lucide-react";

import { Button } from "@/components/ui/button";

type ChatComposerProps = {
  draft: string;
  isLoading: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
};

export function ChatComposer({ draft, isLoading, onChange, onSend }: ChatComposerProps) {
  const canSend = draft.trim().length > 0 && !isLoading;

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (canSend) onSend();
    }
  }

  return (
    <div>
      <div className="flex items-end gap-2 rounded-3xl border border-input bg-card p-2 pl-5 shadow-sm transition focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-ring/50">
        <textarea
          rows={1}
          value={draft}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Preguntame por un producto…"
          aria-label="Mensaje para el asistente"
          disabled={isLoading}
          className="max-h-40 min-h-10.5 min-w-0 flex-1 resize-none bg-transparent py-2 text-base leading-6 outline-none placeholder:text-muted-foreground disabled:opacity-60"
        />
        <Button
          type="submit"
          size="icon"
          onClick={onSend}
          disabled={!canSend}
          aria-label="Enviar mensaje"
          className="size-11 shrink-0 rounded-2xl transition-transform active:scale-90"
        >
          <ArrowUp className="size-5" aria-hidden="true" />
        </Button>
      </div>
      <p className="mt-2 hidden sm:block text-center text-[11px] leading-4 text-muted-foreground">
        Enter para enviar · Shift + Enter para una nueva línea
      </p>
    </div>
  );
}