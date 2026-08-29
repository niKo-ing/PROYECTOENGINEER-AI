"use client";

import { Sparkles } from "lucide-react";

const SUGGESTIONS = [
  "Busca un notebook para gaming",
  "¿Dónde está más barato este producto?",
  "Compara estos notebooks",
  "¿Este precio es bueno?",
] as const;

export function SuggestionChips({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="flex flex-wrap justify-center gap-2">
      {SUGGESTIONS.map((suggestion) => (
        <button
          key={suggestion}
          type="button"
          onClick={() => onPick(suggestion)}
          className="inline-flex items-center gap-1.5 rounded-full border bg-card px-3.5 py-2 text-xs font-medium text-muted-foreground shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:text-foreground hover:shadow-md active:translate-y-0"
        >
          <Sparkles className="size-3.5 text-primary/70" aria-hidden="true" />
          {suggestion}
        </button>
      ))}
    </div>
  );
}