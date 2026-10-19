"use client";

import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";

/** Indicador de «el asistente está trabajando»: tres puntos animados, la etiqueta y, pasados unos segundos,
 *  cuánto lleva esperando (las respuestas con IA real pueden tardar entre 10 y 30 s). */
export function TypingIndicator({ label }: { label: string }) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="motion-safe:animate-message-in flex items-end gap-2.5">
      <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary" aria-hidden="true">
        <Sparkles className="size-4 motion-safe:animate-pulse" />
      </div>
      <div className="flex flex-col gap-1.5 rounded-2xl rounded-bl-md bg-muted px-4 py-3">
        <div className="flex items-center gap-1.5" role="status" aria-label={label}>
          {[0, 1, 2].map((index) => (
            <span
              key={index}
              className="size-2 rounded-full bg-muted-foreground animate-thinking motion-reduce:animate-thinking-calm"
              style={{ animationDelay: `${index * 150}ms` }}
            />
          ))}
        </div>
        {label ? (
          <p className="text-xs text-muted-foreground">
            {label}
            {seconds >= 3 ? <span className="tabular-nums"> · {seconds} s</span> : null}
          </p>
        ) : null}
      </div>
    </div>
  );
}
