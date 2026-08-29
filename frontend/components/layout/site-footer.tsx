import { useMemo } from "react";

export function SiteFooter() {
  const year = useMemo(() => new Date().getFullYear(), []);
  return (
    <footer className="border-t bg-muted/40">
      <div className="mx-auto max-w-7xl px-4 py-6 text-center text-sm text-muted-foreground sm:px-6">
        <p>© {year} SoloTodo. Comparador de precios.</p>
      </div>
    </footer>
  );
}
