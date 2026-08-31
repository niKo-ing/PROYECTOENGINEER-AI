"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Scale, Trash2 } from "lucide-react";

import { useCompare } from "@/components/product/compare-provider";
import { Button } from "@/components/ui/button";

export function CompareBar() {
  const { ids, clear } = useCompare();
  const pathname = usePathname();

  if (ids.length === 0 || pathname === "/compare") return null;

  const href = `/compare?ids=${ids.join(",")}`;
  const canCompare = ids.length >= 2;

  return (
    <div className="fixed inset-x-0 bottom-4 z-40 flex justify-center px-4">
      <div className="flex items-center gap-3 rounded-full border bg-background/95 py-2 pl-4 pr-2 shadow-lg shadow-primary/10 backdrop-blur">
        <span className="flex items-center gap-2 text-sm font-medium">
          <Scale className="h-4 w-4 text-primary" />
          {ids.length} producto{ids.length === 1 ? "" : "s"} en comparación
        </span>
        <Button asChild variant="outline" size="sm" disabled={!canCompare} className={!canCompare ? "opacity-50" : undefined}>
          <Link href={href} aria-disabled={!canCompare} tabIndex={canCompare ? 0 : -1}>
            Comparar
          </Link>
        </Button>
        <Button variant="ghost" size="icon" onClick={clear} aria-label="Limpiar comparación" className="h-8 w-8">
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}