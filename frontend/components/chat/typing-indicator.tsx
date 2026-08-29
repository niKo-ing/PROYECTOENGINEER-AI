import { Sparkles } from "lucide-react";

export function TypingIndicator({ label }: { label: string }) {
  return (
    <div className="animate-message-in flex items-end gap-2.5">
      <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary" aria-hidden="true">
        <Sparkles className="size-4" />
      </div>
      <div className="flex flex-col gap-1.5 rounded-2xl rounded-bl-md bg-muted px-4 py-3">
        <div className="flex items-center gap-1.5" role="status" aria-label={label}>
          {[0, 1, 2].map((index) => (
            <span
              key={index}
              className="thinking-dot size-1.5 rounded-full bg-muted-foreground"
              style={{ animationDelay: `${index * 140}ms` }}
            />
          ))}
        </div>
        {label ? (
          <p className="text-xs text-muted-foreground">{label}</p>
        ) : null}
      </div>
    </div>
  );
}