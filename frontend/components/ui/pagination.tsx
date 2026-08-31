import { useMemo } from "react";

import { Button } from "@/components/ui/button";

export function Pagination({
  current,
  totalPages,
  onPageChange,
}: {
  current: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  const pages = useMemo(() => {
    const set = new Set<number>([1, totalPages, current, current - 1, current + 1]);
    return Array.from(set)
      .filter((page) => page >= 1 && page <= totalPages)
      .sort((a, b) => a - b);
  }, [current, totalPages]);

  return (
    <nav className="mt-8 flex flex-wrap items-center justify-center gap-1" aria-label="Paginación">
      <Button
        variant="outline"
        size="sm"
        disabled={current <= 1}
        onClick={() => onPageChange(current - 1)}
      >
        Anterior
      </Button>
      {pages.map((page, index) => {
        const prev = pages[index - 1];
        const isGap = prev !== undefined && page - prev > 1;
        return (
          <span key={page} className="flex items-center gap-1">
            {isGap ? <span className="px-1 text-muted-foreground">…</span> : null}
            <Button
              variant={page === current ? "default" : "outline"}
              size="sm"
              onClick={() => onPageChange(page)}
              className="min-w-9"
            >
              {page}
            </Button>
          </span>
        );
      })}
      <Button
        variant="outline"
        size="sm"
        disabled={current >= totalPages}
        onClick={() => onPageChange(current + 1)}
      >
        Siguiente
      </Button>
    </nav>
  );
}