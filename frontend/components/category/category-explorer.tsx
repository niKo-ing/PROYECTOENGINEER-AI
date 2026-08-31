import Link from "next/link";
import { ArrowRight, Layers } from "lucide-react";

import { categoryDescription, categoryIcon } from "@/lib/catalog-meta";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import type { CategoryRead } from "@/types/category";

export function CategoryExplorer({ groups }: { groups: CategoryRead[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {groups.map((group) => {
        const Icon = categoryIcon(group);
        const subcategoryCount = group.children.length;
        const productCount = group.total_products;
        return (
          <Link
            key={group.id}
            href={`/category/${group.slug}`}
            className="group relative flex flex-col gap-4 overflow-hidden rounded-2xl border bg-card p-5 transition-all duration-300 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg"
          >
            <div className="flex items-start justify-between gap-3">
              <span className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon className="size-6" />
              </span>
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground opacity-0 transition-all duration-200 group-hover:translate-x-0.5 group-hover:bg-primary/10 group-hover:text-primary group-hover:opacity-100">
                <ArrowRight className="size-4" />
              </span>
            </div>

            <div>
              <h3 className="text-base font-semibold tracking-tight">{group.name}</h3>
              <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                {categoryDescription(group)}
              </p>
            </div>

            <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1 border-t pt-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <Layers className="size-3.5" />
                {subcategoryCount} {subcategoryCount === 1 ? "categoría" : "categorías"}
              </span>
              {productCount > 0 ? (
                <span className="font-medium text-foreground">
                  {productCount.toLocaleString("es-CL")} producto{productCount === 1 ? "" : "s"}
                </span>
              ) : (
                <span>Próximamente</span>
              )}
            </div>
          </Link>
        );
      })}
    </div>
  );
}

export function CategoryExplorerSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className={cn("rounded-2xl border bg-card p-5")}>
          <Skeleton className="mb-4 size-11 rounded-xl" />
          <Skeleton className="mb-2 h-5 w-2/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="mt-1 h-4 w-4/5" />
          <Skeleton className="mt-5 h-4 w-1/2" />
        </div>
      ))}
    </div>
  );
}